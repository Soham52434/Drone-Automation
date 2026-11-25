import json
from dataclasses import dataclass

from drone_security.models.chunks import ChunkArtifact
from drone_security.models.frames import BufferStats
from drone_security.models.perception import GateResult, SceneObservation
from drone_security.models.summaries import LlmSummary


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@dataclass(frozen=True)
class ObservationEvent:
    session_id: str
    observation: SceneObservation

    def to_sse(self) -> str:
        return _sse("observation", {"session_id": self.session_id, **self.observation.to_dict()})


@dataclass(frozen=True)
class DecisionEvent:
    session_id: str
    start_ms: int
    end_ms: int
    result: GateResult

    def to_sse(self) -> str:
        return _sse(
            "decision",
            {
                "session_id": self.session_id,
                "start_ms": self.start_ms,
                "end_ms": self.end_ms,
                "decision": self.result.to_dict(),
            },
        )


@dataclass(frozen=True)
class AlertEvent:
    session_id: str
    observation: SceneObservation
    result: GateResult
    debounced: bool
    chunk: ChunkArtifact | None = None

    def to_sse(self) -> str:
        payload: dict[str, object] = {
            "session_id": self.session_id,
            "debounced": self.debounced,
            "observation": self.observation.to_dict(),
            "decision": self.result.to_dict(),
            "chunk_file": self.chunk.chunk_file if self.chunk else None,
            "chunk_start_ms": self.chunk.chunk_start_ms if self.chunk else None,
            "chunk_end_ms": self.chunk.chunk_end_ms if self.chunk else None,
            "detection_ms": self.chunk.detection_ms if self.chunk else None,
            "seek_offset_sec": self.chunk.seek_offset_sec if self.chunk else None,
            "video_url": (
                f"/api/sessions/{self.session_id}/chunks/{self.chunk.chunk_file}" if self.chunk else None
            ),
        }
        return _sse("alert", payload)


@dataclass(frozen=True)
class StatusEvent:
    session_id: str
    status: str
    detail: str

    def to_sse(self) -> str:
        return _sse(
            "status",
            {"session_id": self.session_id, "status": self.status, "detail": self.detail},
        )


@dataclass(frozen=True)
class ErrorEvent:
    session_id: str
    detail: str

    def to_sse(self) -> str:
        return _sse("error", {"session_id": self.session_id, "detail": self.detail})


@dataclass(frozen=True)
class SummaryEvent:
    session_id: str
    summary: LlmSummary

    def to_sse(self) -> str:
        return _sse("summary", self.summary.to_dict())


@dataclass(frozen=True)
class StatsEvent:
    """Live ring-buffer readout, pushed once a second while a camera streams."""

    session_id: str
    stats: BufferStats

    def to_sse(self) -> str:
        return _sse(
            "stats",
            {
                "session_id": self.session_id,
                "frames_received": self.stats.frames_received,
                "frames_buffered": self.stats.frames_buffered,
                "buffered_seconds": round(self.stats.buffered_seconds, 2),
                "latest_timestamp_ms": self.stats.latest_timestamp_ms,
            },
        )


AnalysisEvent = ObservationEvent | DecisionEvent | AlertEvent | StatusEvent | ErrorEvent | SummaryEvent | StatsEvent
