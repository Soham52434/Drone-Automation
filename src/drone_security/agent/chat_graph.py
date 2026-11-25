import re
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from drone_security.agent.llm import ChatModel, parse_json_object, response_text
from drone_security.indexing.graph_index import GraphIndex
from drone_security.models.chat import ChatIntent, ChatTurn, FramePlan, Verification, VideoClip
from drone_security.models.entities import EntityMatch, EntitySighting, group_visits
from drone_security.models.index import ClassCount, DayLog, FrameQuery, FrameQueryResult, IndexedFrame, timeline_label
from drone_security.models.session import Session, SessionKind
from drone_security.models.summaries import LlmSummary, SummaryKind
from drone_security.perception.classes import ALL_CLASSES, OTHER, ObjectClassifier

_SUMMARY_WORDS = re.compile(
    r"\b(summar\w*|recap|overview|what happened|report|digest|hourly|daily|each hour|per hour|whole day|the day)\b", re.I
)
# Repeat-visit and appearance questions go to the LLM's entity descriptions (advanced analytics).
_SIGHTING_WORDS = re.compile(
    r"\b(how many times|how often|twice|again|visits?|came (?:back|by)|come by|entered|returned|same|repeat\w*|"
    r"colou?r|red|blue|white|black|silver|gr[ae]y|green|yellow|orange|brown|ford|toyota|honda|tesla|bmw|"
    r"mercedes|hyundai|suzuki|f-?150|make|model|wearing|shirt|jacket|hat)\b",
    re.I,
)
VISIT_GAP_MS = 120_000
_TIME = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")
_STOP = {
    "show", "me", "all", "any", "the", "a", "an", "of", "in", "at", "on", "to", "and", "or", "with", "for", "from",
    "find", "list", "get", "give", "events", "event", "frames", "frame", "readings", "reading", "video", "clips",
    "clip", "times", "time", "when", "where", "was", "were", "is", "are", "there", "did", "do", "does", "see", "seen",
    "spotted", "appear", "appeared", "between", "after", "before", "until", "today", "yesterday", "minute",
    "minutes", "hour", "hours", "pm", "am", "near", "around", "please", "which", "what", "who", "how", "many",
    "only", "that", "this", "it", "they", "some", "detected", "detections", "activity", "log", "logs", "every",
    "alert", "alerts", "raised", "camera", "drone", "session", "property", "any", "about", "by", "up",
}
_MAX_CLIPS = 6


class ChatState(TypedDict):
    session_id: str
    kind: str
    use_llm: bool
    question: str
    intent: ChatIntent
    available: list[ClassCount]
    day_log: DayLog | None
    plan: FramePlan | None
    result: FrameQueryResult | None
    answer: str
    llm_used: bool
    notice: str
    advanced: bool
    entities: list[EntityMatch]


class LangGraphChat:
    """Chat over the day log, as a LangGraph with a human in the loop.

    route → plan_frame_query → [verify_classes: interrupt, only if the classes are in doubt] → query_frames
    route → answer_summary   (hourly / daily questions, from hour digests and LLM summaries)
    route → search_sightings (advanced analytics: "how many times did the blue F150 come by?")
    """

    def __init__(
        self,
        index: GraphIndex,
        summaries: Callable[[str], list[LlmSummary]],
        llm: ChatModel | None = None,
        classifier: ObjectClassifier | None = None,
    ) -> None:
        self._index = index
        self._summaries = summaries
        self._llm = llm
        self._classifier = classifier or ObjectClassifier()
        graph = StateGraph(ChatState)
        graph.add_node("route", self._route)
        graph.add_node("plan_frame_query", self._plan)
        graph.add_node("verify_classes", self._verify)
        graph.add_node("query_frames", self._query_frames)
        graph.add_node("answer_summary", self._answer_summary)
        graph.add_node("search_sightings", self._search_sightings)
        graph.add_edge(START, "route")
        graph.add_conditional_edges(
            "route",
            lambda s: s["intent"],
            {"frames": "plan_frame_query", "summary": "answer_summary", "sightings": "search_sightings"},
        )
        graph.add_conditional_edges(
            "plan_frame_query", self._route_after_plan, {"verify": "verify_classes", "query": "query_frames"}
        )
        graph.add_edge("verify_classes", "query_frames")
        graph.add_edge("query_frames", END)
        graph.add_edge("answer_summary", END)
        graph.add_edge("search_sightings", END)
        self.graph = graph.compile(checkpointer=InMemorySaver())

    @property
    def llm_available(self) -> bool:
        return self._llm is not None

    def ask(self, session: Session, question: str) -> ChatTurn:
        thread_id = uuid.uuid4().hex
        state = {
            "session_id": session.id,
            "kind": session.kind.value,
            "use_llm": session.llm.enabled and self._llm is not None,
            "question": question.strip(),
            "intent": "frames",
            "available": [],
            "day_log": None,
            "plan": None,
            "result": None,
            "answer": "",
            "llm_used": False,
            "notice": "",
            "advanced": session.llm.describes_entities,
            "entities": [],
        }
        return self._turn(thread_id, self.graph.invoke(state, _config(thread_id)))

    def verify(self, thread_id: str, classes: list[str]) -> ChatTurn:
        """Resume a paused query with the classes the human confirmed."""
        config = _config(thread_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.next or "verify_classes" not in snapshot.next:
            raise KeyError(f"no question is waiting for class verification on thread {thread_id}")
        return self._turn(thread_id, self.graph.invoke(Command(resume=list(classes)), config))

    # ---- nodes ------------------------------------------------------------------

    def _route(self, state: ChatState) -> dict[str, object]:
        question = state["question"]
        intent: ChatIntent = "frames"
        if state["advanced"] and _SIGHTING_WORDS.search(question):
            intent = "sightings"
        elif _SUMMARY_WORDS.search(question):
            intent = "summary"
        return {
            "intent": intent,
            "available": self._index.classes(state["session_id"]),
            "day_log": self._index.day_log(state["session_id"]),
        }

    def _plan(self, state: ChatState) -> dict[str, object]:
        kind = SessionKind(state["kind"])
        if state["use_llm"]:
            try:
                return {"plan": self._llm_plan(state, kind), "llm_used": True}
            except Exception as exc:  # fall back to the local planner; the human can still correct the classes
                return {"plan": self._keyword_plan(state, kind), "notice": _llm_notice(exc, "local search")}
        return {"plan": self._keyword_plan(state, kind)}

    def _route_after_plan(self, state: ChatState) -> str:
        available = {c.name for c in state["available"]}
        return "verify" if state["plan"].needs_verification(available) else "query"  # type: ignore[union-attr]

    def _verify(self, state: ChatState) -> dict[str, object]:
        plan = state["plan"]
        assert plan is not None
        available = {c.name for c in state["available"]}
        chosen = interrupt(
            Verification(
                question=state["question"],
                proposed=tuple(name for name in plan.classes if name in available),
                available=tuple(state["available"]),
                unmatched_terms=plan.unmatched_terms,
                interpretation=plan.interpretation,
            )
        )
        classes = tuple(name for name in chosen if name in available) if isinstance(chosen, list) else ()
        return {"plan": replace(plan, classes=classes, unmatched_terms=(), confident=True)}

    def _query_frames(self, state: ChatState) -> dict[str, object]:
        plan = state["plan"]
        assert plan is not None
        query = FrameQuery(plan.classes, plan.start_ms, plan.end_ms, plan.alerts_only, limit=200)
        result = self._index.find_frames(state["session_id"], query)
        return {"result": result, "answer": _describe_result(SessionKind(state["kind"]), plan, result)}

    def _answer_summary(self, state: ChatState) -> dict[str, object]:
        kind = SessionKind(state["kind"])
        log = state["day_log"] or DayLog(state["session_id"])
        summaries = [s for s in self._summaries(state["session_id"]) if s.kind is not SummaryKind.ALERT and s.status == "ok"]
        digest = _digest_text(kind, log, summaries)
        if state["use_llm"] and log.hours:
            try:
                reply = self._llm.invoke(  # type: ignore[union-attr]
                    [
                        SystemMessage(
                            content=(
                                "You answer an operator's question about a drone security session using only the "
                                "hour-by-hour log and the summaries below. Be concise. Lead with the answer. Cite "
                                "hours and times. If the log does not cover it, say so."
                            )
                        ),
                        HumanMessage(content=f"Question: {state['question']}\n\n{digest}"),
                    ]
                )
                return {"answer": response_text(reply).strip() or digest, "llm_used": True}
            except Exception as exc:
                return {"answer": digest, "notice": _llm_notice(exc, "the hour-by-hour log")}
        if not log.hours:
            return {"answer": "Nothing has been indexed for this session yet."}
        return {"answer": digest}

    def _search_sightings(self, state: ChatState) -> dict[str, object]:
        kind = SessionKind(state["kind"])
        sightings = self._index.sightings(state["session_id"])
        if not sightings:
            return {"answer": "No detailed descriptions yet. Advanced analytics describes people and vehicles in key frames as the session runs."}
        groups: dict[str, list[EntitySighting]] = {}
        for s in sightings:
            groups.setdefault(s.signature, []).append(s)
        catalogue = [
            (signature, Counter(x.description for x in items).most_common(1)[0][0], items) for signature, items in groups.items()
        ]
        chosen: list[int] = []
        llm_used, notice = False, ""
        if state["use_llm"]:
            try:
                chosen = self._llm_pick_entities(state["question"], catalogue)
                llm_used = True
            except Exception as exc:
                notice = _llm_notice(exc, "a word match")
        if not llm_used:
            chosen = _word_match(state["question"], catalogue)
        matches = []
        for i in chosen:
            signature, description, items = catalogue[i]
            matches.append(
                EntityMatch(
                    signature=signature,
                    description=description,
                    class_name=items[0].class_name,
                    visits=group_visits([x.timestamp_ms for x in items], VISIT_GAP_MS),
                    observation_ids=tuple(dict.fromkeys(x.observation_id for x in items)),
                )
            )
        ids = {oid for m in matches for oid in m.observation_ids}
        frames = tuple(f for f in self._index.find_frames(state["session_id"], FrameQuery(limit=1_000)).frames if f.observation_id in ids)
        result = FrameQueryResult(FrameQuery(limit=1_000), len(frames), frames)
        return {
            "entities": matches,
            "result": result,
            "answer": _describe_visits(kind, matches),
            "llm_used": llm_used,
            "notice": notice,
        }

    def _llm_pick_entities(self, question: str, catalogue: list[tuple[str, str, list[EntitySighting]]]) -> list[int]:
        listing = "\n".join(f"{i}: {description} ({len(items)} sightings)" for i, (_, description, items) in enumerate(catalogue))
        reply = self._llm.invoke(  # type: ignore[union-attr]
            [
                SystemMessage(content="You match an operator's question to entities a camera recorded."),
                HumanMessage(
                    content=f"Question: {question}\nEntities seen:\n{listing}\n\n"
                    'Return JSON only: {"matches": [indexes of every entity the question is about]}. '
                    "Match on what is described (class, colour, make, model, clothing); an empty list if none fit."
                ),
            ]
        )
        data = parse_json_object(response_text(reply))
        picks = data.get("matches") or []
        return [int(i) for i in picks if isinstance(i, (int, float, str)) and str(i).isdigit() and int(i) < len(catalogue)]

    # ---- planners ----------------------------------------------------------------

    def _llm_plan(self, state: ChatState, kind: SessionKind) -> FramePlan:
        log = state["day_log"] or DayLog(state["session_id"])
        classes = ", ".join(f"{c.name} ({c.frames} frames, {c.alerts} alerts)" for c in state["available"]) or "none yet"
        hours = log.hours
        span = (
            f"{timeline_label(kind, hours[0].first_ms or hours[0].start_ms)} to {timeline_label(kind, hours[-1].last_ms or hours[-1].start_ms)}"
            if hours
            else "nothing indexed yet"
        )
        clock = "local clock time HH:MM[:SS]" if kind is SessionKind.LIVE else "position in the video H:MM:SS"
        prompt = (
            f"Question: {state['question']}\n"
            f"Object classes in the index: {classes}\n"
            f"Days: {', '.join(sorted(log.days)) or 'none'}. Timeline covers {span} ({clock}).\n\n"
            "Return JSON only:\n"
            '{"classes": [class names from the list only], "start": time or null, "end": time or null, '
            '"day": "YYYY-MM-DD" or null, "alerts_only": bool, "unmatched_terms": [words from the question that name '
            'things with no exact class], "confident": bool, "interpretation": "one short sentence"}\n'
            "Map synonyms to classes (truck → vehicle, man → person). Put a word in unmatched_terms when the mapping "
            "is a guess, and set confident=false when the question is vague."
        )
        reply = self._llm.invoke(  # type: ignore[union-attr]
            [SystemMessage(content="You turn a security operator's question into an index query."), HumanMessage(content=prompt)]
        )
        data = parse_json_object(response_text(reply))
        day = data.get("day") if isinstance(data.get("day"), str) else _last_day(log)
        return FramePlan(
            classes=tuple(str(c) for c in data.get("classes") or [] if isinstance(c, str)),
            start_ms=_parse_time(kind, data.get("start"), day),
            end_ms=_parse_time(kind, data.get("end"), day, end=True),
            alerts_only=bool(data.get("alerts_only")),
            unmatched_terms=tuple(str(t) for t in data.get("unmatched_terms") or [] if isinstance(t, str)),
            confident=bool(data.get("confident", True)),
            interpretation=str(data.get("interpretation") or ""),
            planner="llm",
        )

    def _keyword_plan(self, state: ChatState, kind: SessionKind) -> FramePlan:
        question = state["question"]
        words = re.findall(r"[a-z0-9]+", _TIME.sub(" ", question.lower()))
        class_names = {c.name for c in state["available"]} | set(self._classifier_classes())
        classes: list[str] = []
        unmatched: list[str] = []
        for word in words:
            if word in _STOP or word.isdigit():
                continue
            singular = word[:-1] if word.endswith("s") and word[:-1] in class_names else word
            if singular in class_names:
                cls = singular  # the word names a class outright, "other" included
            else:
                cls = self._classifier.class_of(word)
                if cls == OTHER:
                    unmatched.append(word)
                    continue
            if cls not in classes:
                classes.append(cls)
        times = _TIME.findall(question)
        day = _last_day(state["day_log"] or DayLog(state["session_id"]))
        start = _parse_time(kind, times[0], day) if times else None
        end = _parse_time(kind, times[1], day, end=True) if len(times) > 1 else None
        alerts_only = bool(re.search(r"\balerts?\b", question, re.I))
        described = ", ".join(classes) or ("alerts" if alerts_only else "everything")
        return FramePlan(
            classes=tuple(classes),
            start_ms=start,
            end_ms=end,
            alerts_only=alerts_only,
            unmatched_terms=tuple(unmatched),
            confident=bool(classes) or alerts_only or bool(times),
            interpretation=f"Readings with {described}" + (f" from {times[0]}" if times else "") + (f" to {times[1]}" if len(times) > 1 else ""),
            planner="keywords",
        )

    def _classifier_classes(self) -> list[str]:
        return [c for c in ALL_CLASSES if c != OTHER]

    # ---- output -------------------------------------------------------------------

    def _turn(self, thread_id: str, state: dict) -> ChatTurn:
        pending = state.get("__interrupt__")
        if pending:
            verification: Verification = pending[0].value
            return ChatTurn(
                thread_id=thread_id,
                status="needs_verification",
                intent="frames",
                answer="Which classes did you mean? Confirm and I will search the day log.",
                plan=state.get("plan"),
                verification=verification,
                llm_used=bool(state.get("llm_used")),
                classes=tuple(state.get("available") or ()),
                notice=state.get("notice") or "",
            )
        result: FrameQueryResult | None = state.get("result")
        log: DayLog | None = state.get("day_log")
        kind = SessionKind(state["kind"])
        return ChatTurn(
            thread_id=thread_id,
            status="answered",
            intent=state["intent"],
            answer=state["answer"],
            plan=state.get("plan"),
            frames=result.frames if result else (),
            total=result.total if result else 0,
            clips=_clips(kind, result.frames) if result else (),
            hours=log.hours if (log and state["intent"] == "summary") else (),
            llm_used=bool(state.get("llm_used")),
            classes=tuple(state.get("available") or ()),
            notice=state.get("notice") or "",
            entities=tuple(state.get("entities") or ()),
        )


def _word_match(question: str, catalogue: list[tuple[str, str, list[EntitySighting]]]) -> list[int]:
    """Without the LLM: entities whose description or attributes share the most words with the question."""
    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in _STOP and len(w) > 1}
    words -= {"times", "many", "how", "often", "twice", "again", "visits", "visit", "came", "come", "entered", "today"}
    scores = []
    for i, (signature, description, _items) in enumerate(catalogue):
        text = set(re.findall(r"[a-z0-9]+", f"{signature} {description}".lower()))
        scores.append((len(words & text), i))
    best = max((score for score, _ in scores), default=0)
    return [i for score, i in scores if best and score == best]


def _describe_visits(kind: SessionKind, matches: list[EntityMatch]) -> str:
    if not matches:
        return "Nothing recorded matches that description."
    lines = []
    for m in matches:
        visits = m.visits
        spans = ", ".join(
            timeline_label(kind, v.start_ms) if v.start_ms == v.end_ms else f"{timeline_label(kind, v.start_ms)}–{timeline_label(kind, v.end_ms)}"
            for v in visits
        )
        times = "once" if len(visits) == 1 else "twice" if len(visits) == 2 else f"{len(visits)} times"
        lines.append(f"{m.description[0].upper()}{m.description[1:]}: seen {times} ({spans}); {m.sightings} sighting(s).")
    return "\n".join(lines)


def _llm_notice(exc: Exception, fallback: str) -> str:
    text = str(exc)
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        reason = "The model's quota is used up"
    elif "UNAVAILABLE" in text or "503" in text or "high demand" in text:
        reason = "The model is busy right now"
    elif "DEADLINE" in text or "timeout" in text.lower():
        reason = "The model timed out"
    else:
        reason = f"The model failed ({exc.__class__.__name__})"
    return f"{reason}; answered with {fallback} instead."


def _config(thread_id: str) -> dict[str, object]:
    return {"configurable": {"thread_id": thread_id}}


def _last_day(log: DayLog) -> str | None:
    return max(log.days) if log.days else None


def _parse_time(kind: SessionKind, value: object, day: str | None, end: bool = False) -> int | None:
    if not isinstance(value, str) or not _TIME.fullmatch(value.strip()):
        return None
    parts = [int(p) for p in value.strip().split(":")]
    if kind is SessionKind.LIVE:
        hour, minute, second = (parts + [0])[:3]
        if not day:
            day = time.strftime("%Y-%m-%d")
        stamp = time.mktime(time.strptime(f"{day} {hour:02d}:{minute:02d}:{second:02d}", "%Y-%m-%d %H:%M:%S"))
        ms = int(stamp * 1000)
        return ms + (999 if len(parts) == 3 else 59_999) if end else ms
    seconds = parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
    return seconds * 1000 + (999 if end else 0)


def _describe_result(kind: SessionKind, plan: FramePlan, result: FrameQueryResult) -> str:
    what = ", ".join(plan.classes) or ("alerts" if plan.alerts_only else "all readings")
    span = ""
    if plan.start_ms is not None or plan.end_ms is not None:
        start = timeline_label(kind, plan.start_ms) if plan.start_ms is not None else "start"
        stop = timeline_label(kind, plan.end_ms) if plan.end_ms is not None else "end"
        span = f" between {start} and {stop}"
    if result.total == 0:
        return f"No readings with {what}{span}."
    frames = result.frames
    alerts = sum(1 for f in frames if f.alert_rule)
    minutes = len({(f.day, f.minute_label) for f in frames})
    first, last = timeline_label(kind, frames[0].timestamp_ms), timeline_label(kind, frames[-1].timestamp_ms)
    text = f"{result.total} readings with {what}{span}, across {minutes} minute(s) from {first} to {last}."
    if alerts:
        text += f" {alerts} raised an alert."
    return text


def _clips(kind: SessionKind, frames: tuple[IndexedFrame, ...]) -> tuple[VideoClip, ...]:
    clips: list[VideoClip] = []
    seen: set[str] = set()
    for frame in frames:
        if frame.chunk_file and frame.chunk_file not in seen:
            seen.add(frame.chunk_file)
            clips.append(VideoClip("alert", frame.seek_offset_sec or 0.0, f"Alert · {timeline_label(kind, frame.timestamp_ms)}", frame.chunk_file))
    if kind is SessionKind.UPLOAD:
        minutes: set[str] = set()
        for frame in frames:
            if frame.minute_label not in minutes:
                minutes.add(frame.minute_label)
                clips.append(VideoClip("video", max(0.0, frame.timestamp_ms / 1000 - 2), timeline_label(kind, frame.timestamp_ms)))
    return tuple(clips[:_MAX_CLIPS])


def _digest_text(kind: SessionKind, log: DayLog, summaries: list[LlmSummary]) -> str:
    lines = ["Hour-by-hour log:"]
    for day in sorted(log.days):
        lines.append(f"Day {day}:")
        for hour in log.days[day]:
            classes = ", ".join(f"{c.name} {c.frames}" for c in hour.classes[:6]) or "no classes"
            span = ""
            if hour.first_ms is not None and hour.last_ms is not None:
                span = f" ({timeline_label(kind, hour.first_ms)}–{timeline_label(kind, hour.last_ms)})"
            lines.append(f"- {hour.hour_label}{span}: {hour.frames} readings, {hour.alerts} alerts; classes {classes}")
    if summaries:
        lines.append("\nLLM summaries:")
        for summary in summaries:
            label = "Final" if summary.kind is SummaryKind.FINAL else "Period"
            lines.append(f"[{label} {timeline_label(kind, summary.start_ms)}–{timeline_label(kind, summary.end_ms)}]\n{summary.text}")
    return "\n".join(lines)
