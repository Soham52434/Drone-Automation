from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from drone_security.models.perception import SceneObservation
from drone_security.models.session import SessionKind


class SummaryKind(StrEnum):
    """Which LLM job produced a summary."""

    ALERT = "alert"  # optional detailed write-up for one alert
    PERIOD = "period"  # every N minutes while the session runs
    FINAL = "final"  # dead hand: last work before the session ends


SummaryStatus = Literal["ok", "quiet", "failed"]


@dataclass(frozen=True)
class AlertNote:
    """What a summary needs to know about one alert, including where its proof lives."""

    window_start_ms: int
    detection_ms: int
    rule: str
    severity: str | None
    summary: str
    chunk_file: str | None = None
    seek_offset_sec: float | None = None
    location: str = ""
    classes: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """Matches the incident key the web UI uses for this alert."""
        return f"window-{self.window_start_ms}"


@dataclass(frozen=True)
class Keyframe:
    """A small JPEG of a frame worth showing to the LLM, with what the vision model said about it."""

    timestamp_ms: int
    file_name: str
    classes: tuple[str, ...] = ()
    location: str = ""
    summary: str = ""
    alert: bool = False
    confidence: float = 0.0


@dataclass(frozen=True)
class EvidenceRef:
    """A timestamped pointer a reviewer can jump to."""

    at_ms: int
    label: str
    note: str
    chunk_file: str | None = None
    seek_offset_sec: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "at_ms": self.at_ms,
            "label": self.label,
            "note": self.note,
            "chunk_file": self.chunk_file,
            "seek_offset_sec": self.seek_offset_sec,
        }


@dataclass(frozen=True)
class SummaryRequest:
    """Everything one LLM job may read. Text and metadata only — never the video."""

    session_id: str
    session_kind: SessionKind
    kind: SummaryKind
    start_ms: int
    end_ms: int
    watch_brief: str
    observations: tuple[SceneObservation, ...] = ()
    alerts: tuple[AlertNote, ...] = ()
    earlier_summaries: tuple[str, ...] = ()
    alert_key: str | None = None
    #: A few frames chosen for this summary (see KeyframeSelector); the LLM sees these images.
    keyframes: tuple[Keyframe, ...] = ()
    #: Base64 JPEG for each keyframe, same order. Kept beside the metadata so the graph stays I/O free.
    images: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.end_ms < self.start_ms:
            raise ValueError("summary end must not be before its start")
        if self.kind is SummaryKind.ALERT and not self.alert_key:
            raise ValueError("an alert summary needs the alert key")
        if self.images and len(self.images) != len(self.keyframes):
            raise ValueError("each keyframe needs exactly one image")

    @property
    def is_quiet(self) -> bool:
        return not self.observations and not self.alerts and not self.earlier_summaries


@dataclass(frozen=True)
class LlmSummary:
    """A stored LLM result. A failed attempt is kept too, so the trail shows it was tried."""

    session_id: str
    kind: SummaryKind
    start_ms: int
    end_ms: int
    created_ms: int
    status: SummaryStatus
    text: str
    model: str
    attempts: int
    evidence: tuple[EvidenceRef, ...] = field(default_factory=tuple)
    alert_key: str | None = None
    #: Keyframe files the LLM looked at, so a reviewer sees the same images.
    frames: tuple[str, ...] = ()

    @property
    def file_name(self) -> str:
        if self.kind is SummaryKind.FINAL:
            return "final.summary.json"
        if self.kind is SummaryKind.ALERT:
            return f"alert_{self.start_ms}.summary.json"
        return f"period_{self.start_ms}_{self.end_ms}.summary.json"

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "kind": self.kind.value,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "created_ms": self.created_ms,
            "status": self.status,
            "text": self.text,
            "model": self.model,
            "attempts": self.attempts,
            "alert_key": self.alert_key,
            "evidence": [ref.to_dict() for ref in self.evidence],
            "frames": list(self.frames),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "LlmSummary":
        evidence = data.get("evidence") or []
        return cls(
            session_id=str(data["session_id"]),
            kind=SummaryKind(str(data["kind"])),
            start_ms=int(data["start_ms"]),  # type: ignore[arg-type]
            end_ms=int(data["end_ms"]),  # type: ignore[arg-type]
            created_ms=int(data["created_ms"]),  # type: ignore[arg-type]
            status=data["status"],  # type: ignore[arg-type]
            text=str(data["text"]),
            model=str(data.get("model", "")),
            attempts=int(data.get("attempts", 0)),  # type: ignore[arg-type]
            alert_key=data.get("alert_key") if isinstance(data.get("alert_key"), str) else None,  # type: ignore[arg-type]
            frames=tuple(str(f) for f in data.get("frames") or [] if isinstance(f, str)),  # type: ignore[union-attr]
            evidence=tuple(
                EvidenceRef(
                    at_ms=int(ref["at_ms"]),
                    label=str(ref["label"]),
                    note=str(ref["note"]),
                    chunk_file=ref.get("chunk_file"),
                    seek_offset_sec=ref.get("seek_offset_sec"),
                )
                for ref in evidence  # type: ignore[union-attr]
                if isinstance(ref, dict)
            ),
        )
