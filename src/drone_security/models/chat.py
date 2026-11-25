from dataclasses import dataclass, field
from typing import Literal

from drone_security.models.entities import EntityMatch
from drone_security.models.index import ClassCount, HourDigest, IndexedFrame

ChatIntent = Literal["frames", "summary", "sightings"]
ChatStatus = Literal["answered", "needs_verification"]
Planner = Literal["llm", "keywords"]


@dataclass(frozen=True)
class FramePlan:
    """The operator's question turned into an index query: which classes, which span."""

    classes: tuple[str, ...] = ()
    start_ms: int | None = None
    end_ms: int | None = None
    alerts_only: bool = False
    unmatched_terms: tuple[str, ...] = ()
    confident: bool = True
    interpretation: str = ""
    planner: Planner = "keywords"

    def needs_verification(self, available: set[str]) -> bool:
        """Ask the human only when the classes are in doubt; otherwise answer straight away."""
        unknown = [name for name in self.classes if name not in available]
        nothing_chosen = not self.classes and not self.alerts_only and self.start_ms is None and self.end_ms is None
        return bool(self.unmatched_terms) or not self.confident or bool(unknown) or nothing_chosen

    def to_dict(self) -> dict[str, object]:
        return {
            "classes": list(self.classes),
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "alerts_only": self.alerts_only,
            "unmatched_terms": list(self.unmatched_terms),
            "confident": self.confident,
            "interpretation": self.interpretation,
            "planner": self.planner,
        }


@dataclass(frozen=True)
class Verification:
    """What the human sees when the classes need confirming."""

    question: str
    proposed: tuple[str, ...]
    available: tuple[ClassCount, ...]
    unmatched_terms: tuple[str, ...]
    interpretation: str


@dataclass(frozen=True)
class VideoClip:
    """Something playable for a result: a saved alert clip, or a seek point in the uploaded video."""

    source: Literal["alert", "video"]
    start_sec: float
    label: str
    chunk_file: str | None = None


@dataclass(frozen=True)
class ChatTurn:
    thread_id: str
    status: ChatStatus
    intent: ChatIntent
    answer: str
    plan: FramePlan | None = None
    frames: tuple[IndexedFrame, ...] = ()
    total: int = 0
    clips: tuple[VideoClip, ...] = ()
    verification: Verification | None = None
    hours: tuple[HourDigest, ...] = ()
    llm_used: bool = False
    classes: tuple[ClassCount, ...] = field(default_factory=tuple)
    #: Why the LLM was not used when it should have been (quota, timeout); empty otherwise.
    notice: str = ""
    #: Advanced analytics: matched entities and their separate visits.
    entities: tuple[EntityMatch, ...] = ()
