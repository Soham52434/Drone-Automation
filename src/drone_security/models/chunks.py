from dataclasses import dataclass
from enum import StrEnum

from drone_security.models.frames import FramePacket


class ChunkTrigger(StrEnum):
    MANUAL = "manual"
    ALERT = "alert"


@dataclass(frozen=True)
class ChunkEvidence:
    """Vision finding and alert-classifier result stored beside an alert clip."""

    label: str
    summary: str
    confidence: float
    event_detected: bool
    alert: bool
    decision_confidence: float
    rules_fired: tuple[str, ...]
    severity: str | None

    def as_metadata(self) -> dict[str, object]:
        return {
            "vision_output": {
                "label": self.label,
                "summary": self.summary,
                "confidence": self.confidence,
                "event_detected": self.event_detected,
            },
            "decision": {
                "alert": self.alert,
                "confidence": self.decision_confidence,
                "rules_fired": list(self.rules_fired),
                "severity": self.severity,
            },
        }


@dataclass(frozen=True, eq=False)
class ClipPlan:
    session_id: str
    trigger: ChunkTrigger
    detection_ms: int
    frames: tuple[FramePacket, ...]
    evidence: ChunkEvidence | None = None

    @property
    def start_ms(self) -> int:
        return self.frames[0].timestamp_ms

    @property
    def end_ms(self) -> int:
        return self.frames[-1].timestamp_ms


@dataclass(frozen=True)
class ChunkArtifact:
    session_id: str
    chunk_file: str
    metadata_file: str
    chunk_start_ms: int
    chunk_end_ms: int
    detection_ms: int
    frame_count: int
    fps: float
    trigger: ChunkTrigger
    created_ms: int
    evidence: ChunkEvidence | None = None

    @property
    def seek_offset_sec(self) -> float:
        return round((self.detection_ms - self.chunk_start_ms) / 1000, 3)

    @property
    def duration_sec(self) -> float:
        return round((self.chunk_end_ms - self.chunk_start_ms) / 1000, 3)

    def to_metadata(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "chunk_file": self.chunk_file,
            "chunk_start_ms": self.chunk_start_ms,
            "chunk_end_ms": self.chunk_end_ms,
            "detection_ms": self.detection_ms,
            "seek_offset_sec": self.seek_offset_sec,
            "duration_sec": self.duration_sec,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "trigger": self.trigger.value,
            "created_ms": self.created_ms,
            **(self.evidence.as_metadata() if self.evidence is not None else {}),
        }
