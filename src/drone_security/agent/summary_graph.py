import time
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from drone_security.agent.llm import ChatModel, answered_by, build_llm, model_chain
from drone_security.agent.llm import response_text as _response_text
from drone_security.models.index import timeline_label as _clock
from drone_security.models.session import SessionKind
from drone_security.models.summaries import (
    EvidenceRef,
    LlmSummary,
    SummaryKind,
    SummaryRequest,
    SummaryStatus,
)

MAX_ATTEMPTS = 2  # dead-hand rule: try, retry once, then keep a failure record
_MAX_OBSERVATION_LINES = 160

_WRITERS = {
    SummaryKind.ALERT: "write_alert_detail",
    SummaryKind.PERIOD: "write_period_summary",
    SummaryKind.FINAL: "write_final_summary",
}

_INSTRUCTIONS = {
    SummaryKind.ALERT: (
        "Write a detailed write-up of this single alert for the operator: what happened, who or what was "
        "involved, where in view, and why it matches the watch brief. 3–6 sentences. Cite the alert time and "
        "clip as [t=<time>] and [clip=<file> @ <seek>s]."
    ),
    SummaryKind.PERIOD: (
        "Summarize this period of monitoring for the operator. Lead with alerts, then notable activity, then "
        "quiet stretches. Every claim must cite its evidence as [t=<time>] and, for alerts, "
        "[clip=<file> @ <seek>s]. Use short bullet points. Do not invent anything the evidence does not show."
    ),
    SummaryKind.FINAL: (
        "This is the final summary written as the session ends. Give a short overall verdict, then the "
        "alerts in time order, then anything still unresolved. Fold in the earlier period summaries. Cite "
        "evidence as [t=<time>] and [clip=<file> @ <seek>s]. Use short bullet points."
    ),
}


class SummaryState(TypedDict):
    request: SummaryRequest
    prompt: str
    frames: list[dict[str, object]]
    evidence: list[EvidenceRef]
    text: str
    model_used: str
    error: str
    attempts: int
    status: SummaryStatus


class LangGraphSummarizer:
    """LLM summaries as a LangGraph.

    gather → (quiet | unavailable | write_alert_detail | write_period_summary | write_final_summary)
    writer → finalize, or the same writer again once, then record_failure.
    """

    def __init__(self, llm: ChatModel | None, model: str = "", unavailable_reason: str = "") -> None:
        self._llm = llm
        self._model = model
        self._unavailable_reason = unavailable_reason or "The LLM is not configured"
        graph = StateGraph(SummaryState)
        graph.add_node("gather", self._gather)
        graph.add_node("quiet", self._quiet)
        graph.add_node("unavailable", self._unavailable)
        for kind, node in _WRITERS.items():
            graph.add_node(node, self._writer(kind))
        graph.add_node("finalize", self._finalize)
        graph.add_node("record_failure", self._record_failure)
        graph.add_edge(START, "gather")
        graph.add_conditional_edges(
            "gather",
            self._route_after_gather,
            {"quiet": "quiet", "unavailable": "unavailable", **{node: node for node in _WRITERS.values()}},
        )
        for node in _WRITERS.values():
            graph.add_conditional_edges(
                node,
                _route_after_write,
                {"finalize": "finalize", "retry": node, "record_failure": "record_failure"},
            )
        for node in ("quiet", "unavailable", "finalize", "record_failure"):
            graph.add_edge(node, END)
        self.graph = graph.compile()

    @property
    def available(self) -> bool:
        return self._llm is not None

    def summarize(self, request: SummaryRequest) -> LlmSummary:
        state = self.graph.invoke(
            {"request": request, "prompt": "", "frames": [], "evidence": [], "text": "", "model_used": "", "error": "", "attempts": 0, "status": "failed"}
        )
        return LlmSummary(
            session_id=request.session_id,
            kind=request.kind,
            start_ms=request.start_ms,
            end_ms=request.end_ms,
            created_ms=int(time.time() * 1000),
            status=state["status"],
            text=state["text"],
            model=state["model_used"] or self._model,
            attempts=state["attempts"],
            evidence=tuple(state["evidence"]),
            alert_key=request.alert_key,
            frames=tuple(frame.file_name for frame in request.keyframes) if request.images else (),
        )

    def _gather(self, state: SummaryState) -> dict[str, object]:
        request = state["request"]
        return {"prompt": _prompt(request), "frames": _frame_blocks(request), "evidence": _evidence(request)}

    def _route_after_gather(self, state: SummaryState) -> str:
        request = state["request"]
        if request.is_quiet:
            return "quiet"
        if self._llm is None:
            return "unavailable"
        return _WRITERS[request.kind]

    def _quiet(self, state: SummaryState) -> dict[str, object]:
        request = state["request"]
        span = f"{_clock(request.session_kind, request.start_ms)}–{_clock(request.session_kind, request.end_ms)}"
        return {"status": "quiet", "text": f"No activity was recorded between {span}."}

    def _unavailable(self, _: SummaryState) -> dict[str, object]:
        return {"status": "failed", "text": f"Summary not written: {self._unavailable_reason}."}

    def _writer(self, kind: SummaryKind):
        def write(state: SummaryState) -> dict[str, object]:
            attempts = state["attempts"] + 1
            try:
                response = self._llm.invoke(  # type: ignore[union-attr]
                    [
                        SystemMessage(content=_system_prompt(state["request"])),
                        HumanMessage(content=[{"type": "text", "text": state["prompt"]}, *state["frames"]])
                        if state["frames"]
                        else HumanMessage(content=state["prompt"]),
                    ]
                )
                text = _response_text(response).strip()
                if not text:
                    raise RuntimeError("The LLM returned an empty summary")
            except Exception as exc:  # retried once by the graph, then recorded
                return {"attempts": attempts, "error": str(exc) or exc.__class__.__name__, "text": ""}
            return {"attempts": attempts, "error": "", "text": text, "model_used": answered_by(response)}

        write.__name__ = _WRITERS[kind]
        return write

    def _finalize(self, _: SummaryState) -> dict[str, object]:
        return {"status": "ok"}

    def _record_failure(self, state: SummaryState) -> dict[str, object]:
        return {
            "status": "failed",
            "text": f"Summary failed after {state['attempts']} attempts: {state['error']}",
        }


def build_summarizer(api_key: str, model: str, meter: object | None = None) -> LangGraphSummarizer:
    llm = build_llm(api_key, model)
    if llm is not None and meter is not None:
        from drone_security.agent.metering import MeteredModel

        llm = MeteredModel(llm, meter, "summaries", model_chain(model)[0])  # type: ignore[arg-type,assignment]
    label = model_chain(model)[0] if model_chain(model) else model
    if llm is None:
        return LangGraphSummarizer(None, label, "GOOGLE_API_KEY is not set")
    return LangGraphSummarizer(llm, label)


def _route_after_write(state: SummaryState) -> str:
    if not state["error"]:
        return "finalize"
    return "retry" if state["attempts"] < MAX_ATTEMPTS else "record_failure"


def _system_prompt(request: SummaryRequest) -> str:
    return (
        "You are the summarizer for an on-site drone security analyst. "
        "You get the vision frame readings, the alert index, and a few key frames (never full video). "
        "The vision model is a small local model: its labels are useful but shallow. Use the frames to confirm, correct, "
        "or add detail the vision model missed (what people are doing, vehicle type and colour, carried items, hazards). "
        "Cite a picture as [frame N]. If a frame contradicts the vision model, trust the frame and say so.\n\n"
        f"Watch brief for this session:\n{request.watch_brief}\n\n{_INSTRUCTIONS[request.kind]}"
    )


def _prompt(request: SummaryRequest) -> str:
    kind = request.session_kind
    lines = [
        f"Session {request.session_id} ({'live camera, clock time' if kind is SessionKind.LIVE else 'uploaded video, position in file'}).",
        f"Period: {_clock(kind, request.start_ms)} to {_clock(kind, request.end_ms)}.",
        "",
        f"Alerts raised by the alert classifier ({len(request.alerts)}):",
    ]
    if not request.alerts:
        lines.append("- none")
    for alert in request.alerts:
        clip = f" clip={alert.chunk_file} @ {alert.seek_offset_sec:.2f}s" if alert.chunk_file and alert.seek_offset_sec is not None else " (no clip saved)"
        where = f" at {alert.location}" if alert.location else ""
        classes = f" classes={','.join(alert.classes)}" if alert.classes else ""
        lines.append(
            f"- t={_clock(kind, alert.detection_ms)}{where} rule={alert.rule} severity={alert.severity or 'unknown'}"
            f"{classes}{clip}: {alert.summary}"
        )
    observations = _thin(request.observations)
    lines += ["", f"Vision readings ({len(request.observations)} total, {len(observations)} shown):"]
    if not observations:
        lines.append("- none")
    for observation in observations:
        flag = "event" if observation.event_detected else "quiet"
        where = f" at {observation.location}" if observation.location else ""
        classes = f" classes={','.join(observation.class_names)}" if observation.classes else ""
        lines.append(
            f"- t={_clock(kind, observation.timestamp_ms)}{where} [{flag}] {observation.label} "
            f"{observation.confidence:.0%}{classes}: {observation.summary}"
        )
    if request.earlier_summaries:
        lines += ["", "Earlier period summaries in this session:"]
        lines += [f"---\n{text}" for text in request.earlier_summaries]
    return "\n".join(lines)


def _frame_blocks(request: SummaryRequest) -> list[dict[str, object]]:
    """Label then image for each keyframe, so the LLM can tie [frame N] to a time and place."""
    blocks: list[dict[str, object]] = []
    for number, (frame, image) in enumerate(zip(request.keyframes, request.images), start=1):
        where = f" at {frame.location}" if frame.location else ""
        classes = f"; classes {', '.join(frame.classes)}" if frame.classes else ""
        alert = " (raised the alert)" if frame.alert else ""
        blocks.append(
            {
                "type": "text",
                "text": f"[frame {number}] t={_clock(request.session_kind, frame.timestamp_ms)}{where}{alert}{classes}. "
                f"The vision model said: {frame.summary or 'nothing'}",
            }
        )
        blocks.append({"type": "image", "base64": image, "mime_type": "image/jpeg"})
    return blocks


def _evidence(request: SummaryRequest) -> list[EvidenceRef]:
    refs = [
        EvidenceRef(
            at_ms=alert.detection_ms,
            label=alert.rule,
            note=alert.summary,
            chunk_file=alert.chunk_file,
            seek_offset_sec=alert.seek_offset_sec,
        )
        for alert in request.alerts
    ]
    seen_labels: set[str] = set()
    for observation in request.observations:
        if observation.event_detected and observation.label not in seen_labels:
            seen_labels.add(observation.label)
            refs.append(EvidenceRef(at_ms=observation.timestamp_ms, label=observation.label, note=observation.summary))
    return sorted(refs, key=lambda ref: ref.at_ms)


def _thin(observations: tuple, limit: int = _MAX_OBSERVATION_LINES) -> tuple:
    """Keep the prompt bounded: every event reading, then evenly spaced quiet ones."""
    if len(observations) <= limit:
        return observations
    events = [o for o in observations if o.event_detected]
    if len(events) >= limit:
        step = len(events) / limit
        return tuple(events[int(i * step)] for i in range(limit))
    quiet = [o for o in observations if not o.event_detected]
    room = limit - len(events)
    step = len(quiet) / room
    kept = events + [quiet[int(i * step)] for i in range(room)]
    return tuple(sorted(kept, key=lambda o: o.timestamp_ms))
