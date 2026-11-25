from dataclasses import dataclass, field
from typing import Literal

from drone_security.models.rules import WindowContext


MAX_DECISION_WINDOW_MS = 15_000

Severity = Literal["info", "warn", "critical"]


@dataclass(frozen=True)
class ClassHit:
    """One object class in a frame (e.g. `person`), rolled up from the vision model's exact object names."""

    name: str
    score: float
    count: int = 1

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "score": round(float(self.score), 3), "count": self.count}


@dataclass(frozen=True)
class SceneObservation:
    """One vision reading of a sampled frame. The vision model itself keeps no timeline.

    `classes` and `scene` are filled by the perception graph.
    """

    timestamp_ms: int
    frame_index: int
    event_detected: bool
    label: str
    confidence: float
    summary: str
    raw: dict[str, object] = field(default_factory=dict)
    classes: tuple[ClassHit, ...] = ()
    scene: str = ""

    @property
    def class_names(self) -> tuple[str, ...]:
        return tuple(hit.name for hit in self.classes)

    @property
    def location(self) -> str:
        """Where this was seen, as the vision model describes the scene (e.g. "indoor room", "driveway")."""
        return self.scene

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "timestamp_ms": self.timestamp_ms,
            "frame_index": self.frame_index,
            "event_detected": self.event_detected,
            "label": self.label,
            "confidence": round(float(self.confidence), 3),
            "summary": self.summary,
            "classes": [hit.to_dict() for hit in self.classes],
            "scene": self.scene,
            "location": self.location,
        }
        if self.raw:
            payload["raw"] = self.raw
        return payload


@dataclass(frozen=True)
class GateResult:
    """Alert-classifier answer for one window. `worth_reporting` is the alert bit."""

    worth_reporting: bool
    confidence: float
    fired_rules: tuple[str, ...]
    severity: Severity | None
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "alert": self.worth_reporting,
            "confidence": round(float(self.confidence), 3),
            "rules_fired": list(self.fired_rules),
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DecisionWindow:
    """About 10 seconds (never more than 15) of vision notes, plus the clip bytes."""

    session_id: str
    start_ms: int
    end_ms: int
    observations: tuple[SceneObservation, ...]
    video: bytes | None = None
    #: Time of day and continuous presence, for the predefined time-based rules.
    context: WindowContext | None = None

    def __post_init__(self) -> None:
        span = self.end_ms - self.start_ms
        if span < 0 or span > MAX_DECISION_WINDOW_MS:
            raise ValueError(f"decision window must be 0–{MAX_DECISION_WINDOW_MS} ms, got {span}")
