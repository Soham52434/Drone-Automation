import base64
from typing import Protocol, TypedDict

from langchain_core.decisions import Choice, Noul
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph

from drone_security.models.perception import DecisionWindow, GateResult
from drone_security.models.rules import RuleHit, TimeRules, WindowContext
from drone_security.perception.classes import classes_named_in
from drone_security.models.session import WatchBrief

_MAX_INLINE_VIDEO_BYTES = 15 * 1024 * 1024
_SEVERITIES = {"info", "warn", "critical"}


def _questions(brief: WatchBrief) -> dict[str, Noul | Choice]:
    """Closed questions for this session. The watch brief decides what is worth an alert."""
    return {
        "alert": Noul(
            instructions=(
                "Given this session's watch brief, should the operator be alerted about this window?\n"
                f"Watch brief: {brief.text}"
            ),
            criteria={
                "true": "The window shows something the watch brief asks to report.",
                "false": "Nothing in this window matches the watch brief.",
            },
        ),
        "rule": Choice(
            instructions=(
                "Which label best matches this window under the watch brief? "
                "Choose none when the brief does not ask to report it."
            ),
            criteria={
                "person_on_property": "A person the brief cares about.",
                "vehicle": "A vehicle the brief cares about.",
                "package_delivery": "A package delivery the brief cares about.",
                "animal": "An animal the brief cares about.",
                "hazard": "Fire, smoke, or another hazard the brief cares about.",
                "loitering": "A person the brief cares about has stayed in view for a long time.",
                "after_hours": "A person or vehicle the brief cares about appears at night or after hours.",
                "brief_match": "Something else the watch brief explicitly asks to report.",
                "none": "Nothing the watch brief asks to report.",
            },
        ),
        "severity": Choice(
            instructions="How severe is this window for the operator, given the watch brief?",
            criteria={
                "info": "Worth a glance, no urgency.",
                "warn": "The operator should look soon.",
                "critical": "Possible intrusion, hazard, or immediate risk.",
            },
        ),
    }


class DecisionClassifier(Protocol):
    def invoke(self, payload: dict[str, object]) -> object: ...


class DecisionState(TypedDict):
    evidence: str
    video_b64: str
    watch_brief: str
    worth_reporting: bool
    confidence: float
    fired_rules: list[str]
    severity: str | None
    detail: str
    context: WindowContext | None
    present: list[str]
    rule_hits: list[RuleHit]
    route: str


_SEVERITY_ORDER = {None: 0, "info": 1, "warn": 2, "critical": 3}


class LangGraphDecisionGate:
    """The alert classifier as a LangGraph: classify → apply_time_rules → alert or clear.

    `apply_time_rules` adds the predefined rules (after hours, loitering): either one raises an
    alert on its own, even when the classifier said clear, for classes the watch brief cares about.
    """

    def __init__(
        self,
        classifier: DecisionClassifier | None,
        threshold: float,
        unavailable_reason: str = "",
        rules: TimeRules | None = None,
    ) -> None:
        if not 0.0 < threshold < 0.99:
            raise ValueError("alert threshold must be between 0 and 0.99")
        self._classifier = classifier
        self._threshold = threshold
        self._unavailable_reason = unavailable_reason
        self._rules = rules or TimeRules()
        graph = StateGraph(DecisionState)
        graph.add_node("classify", self._classify)
        graph.add_node("apply_time_rules", self._apply_time_rules)
        graph.add_node("accept_alert", _mark_route("alert"))
        graph.add_node("reject", _mark_route("clear"))
        graph.add_edge(START, "classify")
        graph.add_edge("classify", "apply_time_rules")
        graph.add_conditional_edges(
            "apply_time_rules",
            _route,
            {"alert": "accept_alert", "clear": "reject"},
        )
        graph.add_edge("accept_alert", END)
        graph.add_edge("reject", END)
        self.graph = graph.compile()

    def evaluate(self, window: DecisionWindow, watch_brief: str | None = None) -> GateResult:
        brief = WatchBrief.resolve(watch_brief)
        video = window.video if window.video and len(window.video) <= _MAX_INLINE_VIDEO_BYTES else b""
        evidence = _evidence_text(window, video_attached=bool(video))
        state = self.graph.invoke(
            {
                "evidence": evidence,
                "video_b64": base64.b64encode(video).decode("ascii") if video else "",
                "watch_brief": brief.text,
                "worth_reporting": False,
                "confidence": 0.0,
                "fired_rules": [],
                "severity": None,
                "detail": "",
                "context": window.context,
                "present": sorted({name for o in window.observations for name in o.class_names}),
                "rule_hits": [],
                "route": "",
            }
        )
        if state.get("route") not in {"alert", "clear"}:
            raise RuntimeError("decision graph did not route the window")
        severity = state["severity"] if state["severity"] in _SEVERITIES else None
        return GateResult(
            worth_reporting=bool(state["worth_reporting"]),
            confidence=float(state["confidence"]),
            fired_rules=tuple(state["fired_rules"]),
            severity=severity,  # type: ignore[arg-type]
            detail=str(state["detail"]),
        )

    def _apply_time_rules(self, state: DecisionState) -> dict[str, object]:
        context = state["context"]
        if context is None:
            return {}
        watched = classes_named_in(state["watch_brief"])
        present = set(state["present"])
        hits: list[RuleHit] = []
        if context.after_hours:
            when = f"at {context.clock}" if context.clock else "at night (per the vision model's scene)"
            for name in self._rules.after_hours_classes:
                if name in present and name in watched:
                    severity = "critical" if name == "person" else "warn"
                    hits.append(RuleHit("after_hours", name, severity, f"{name} seen {when}, after hours ({self._rules.after_hours_label})"))
        for name in self._rules.loiter_classes:
            stay = context.dwell_of(name)
            if stay and name in watched and stay.seconds >= self._rules.loiter_seconds:
                severity = "critical" if context.after_hours else "warn"
                hits.append(RuleHit("loitering", name, severity, f"{name} in view for {stay.seconds:.0f} s (limit {self._rules.loiter_seconds:.0f} s)"))
        if not hits:
            return {"rule_hits": []}
        rules = list(dict.fromkeys([*(h.rule for h in hits), *state["fired_rules"]]))
        severity = max([state["severity"], *(h.severity for h in hits)], key=lambda s: _SEVERITY_ORDER.get(s, 0))
        detail = "; ".join(h.detail for h in hits)
        if state["detail"]:
            detail = f"{detail}. {state['detail']}"
        return {
            "worth_reporting": True,
            "confidence": max(state["confidence"], 1.0),
            "fired_rules": rules,
            "severity": severity,
            "detail": detail,
            "rule_hits": hits,
        }

    def _classify(self, state: DecisionState) -> dict[str, object]:
        if self._classifier is None:
            return {
                "worth_reporting": False,
                "confidence": 0.0,
                "fired_rules": [],
                "severity": None,
                "detail": self._unavailable_reason or "The alert classifier is not configured",
            }
        brief = WatchBrief.resolve(state["watch_brief"])
        content: list[object] = [SystemMessage(content=brief.system_prompt()), state["evidence"]]
        if state["video_b64"]:
            content.append({"type": "video", "base64": state["video_b64"], "mime_type": "video/mp4"})
        response = self._classifier.invoke({"state": content, "questions": _questions(brief)})
        noul = float(response.nouls["alert"].noul)  # type: ignore[attr-defined]
        rule = str(response.choices["rule"].choice)  # type: ignore[attr-defined]
        severity = str(response.choices["severity"].choice)  # type: ignore[attr-defined]
        worth = noul >= self._threshold and rule != "none"
        return {
            "worth_reporting": worth,
            "confidence": noul,
            "fired_rules": [] if rule == "none" else [rule],
            "severity": severity,
            "detail": "",
        }


def build_decision_gate(
    api_key: str, model: str, threshold: float, rules: TimeRules | None = None, meter: object | None = None
) -> LangGraphDecisionGate:
    key = api_key.strip()
    if not key:
        return LangGraphDecisionGate(None, threshold, "GOOGLE_API_KEY is not set", rules=rules)
    from langchain_google_genai import GoogleGenAIClassifier

    classifier = GoogleGenAIClassifier(model=model, api_key=key)
    if meter is not None:
        from drone_security.agent.metering import MeteredModel

        classifier = MeteredModel(classifier, meter, "decision", model)  # type: ignore[assignment,arg-type]
    return LangGraphDecisionGate(classifier, threshold, rules=rules)


def _route(state: DecisionState) -> str:
    return "alert" if state["worth_reporting"] else "clear"


def _mark_route(route: str):
    def mark(_: DecisionState) -> dict[str, str]:
        return {"route": route}

    return mark


def _evidence_text(window: DecisionWindow, video_attached: bool) -> str:
    lines = [
        f"Window {window.start_ms}–{window.end_ms} ms on session {window.session_id}.",
    ]
    context = window.context
    if context is not None:
        if context.source == "clock":
            lines.append(f"Local time: {context.clock} ({'after hours' if context.after_hours else 'normal hours'}).")
        elif context.source == "scene":
            lines.append(f"Time of day (from the vision model's scene, no clock for uploaded video): {context.daypart}.")
        stays = [f"{d.name} {d.seconds:.0f} s" for d in context.dwell if d.seconds >= 1]
        if stays:
            lines.append(f"Continuously in view: {', '.join(stays)}.")
    lines.append("Vision observations (the vision model has no memory across frames; these are the sampled readings):")
    if not window.observations:
        lines.append("(none)")
    for observation in window.observations:
        classes = f" classes={','.join(observation.class_names)}" if observation.classes else ""
        scene = f" scene={observation.scene}" if observation.scene else ""
        lines.append(
            f"- t={observation.timestamp_ms} frame={observation.frame_index}{scene} "
            f"event={observation.event_detected} label={observation.label}{classes} "
            f"confidence={observation.confidence:.3f} summary={observation.summary}"
        )
    if window.video and not video_attached:
        lines.append("The video clip was omitted because it is larger than 15 MB.")
    elif video_attached:
        lines.append("A video clip of this window is attached.")
    return "\n".join(lines)
