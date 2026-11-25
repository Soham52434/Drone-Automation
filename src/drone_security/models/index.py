import time
from dataclasses import dataclass, field

from drone_security.models.session import SessionKind


def timeline_label(kind: SessionKind, ms: int) -> str:
    """Clock time for live sessions, position in the file (H:MM:SS) for uploads."""
    if kind is SessionKind.LIVE:
        return time.strftime("%H:%M:%S", time.localtime(ms / 1000))
    seconds = max(0, ms // 1000)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


@dataclass(frozen=True)
class TimeBucket:
    """Where a reading sits in the Session → Day → Hour → Minute tree.

    Live sessions bucket by local clock time. Uploaded videos bucket by position in the file,
    under the day the session was created.
    """

    day: str
    hour: int
    minute: int
    hour_start_ms: int
    minute_start_ms: int

    @classmethod
    def of(cls, kind: SessionKind, timestamp_ms: int, anchor_ms: int) -> "TimeBucket":
        if kind is SessionKind.LIVE:
            local = time.localtime(timestamp_ms / 1000)
            hour_start = timestamp_ms - (local.tm_min * 60 + local.tm_sec) * 1000 - timestamp_ms % 1000
            minute_start = timestamp_ms - local.tm_sec * 1000 - timestamp_ms % 1000
            return cls(time.strftime("%Y-%m-%d", local), local.tm_hour, local.tm_min, hour_start, minute_start)
        position = max(0, timestamp_ms)
        hour, minute = position // 3_600_000, position // 60_000 % 60
        return cls(
            time.strftime("%Y-%m-%d", time.localtime(anchor_ms / 1000)),
            hour,
            minute,
            hour * 3_600_000,
            position - position % 60_000,
        )

    @property
    def hour_label(self) -> str:
        return f"{self.hour:02d}:00"

    @property
    def minute_label(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"


@dataclass(frozen=True)
class ClassCount:
    name: str
    frames: int
    best_score: float
    alerts: int = 0

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "frames": self.frames, "best_score": round(self.best_score, 3), "alerts": self.alerts}


@dataclass(frozen=True)
class FrameQuery:
    """What to pull from the index: any of these classes, inside this span (session timeline ms)."""

    classes: tuple[str, ...] = ()
    start_ms: int | None = None
    end_ms: int | None = None
    alerts_only: bool = False
    limit: int = 200

    def __post_init__(self) -> None:
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("query end must not be before its start")
        if not 0 < self.limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")


@dataclass(frozen=True)
class IndexedFrame:
    """One vision reading as stored in the graph, with any alert it raised."""

    observation_id: str
    timestamp_ms: int
    day: str
    hour_label: str
    minute_label: str
    summary: str
    label: str
    confidence: float
    classes: tuple[str, ...]
    scene: str
    alert_rule: str | None = None
    alert_severity: str | None = None
    chunk_file: str | None = None
    seek_offset_sec: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "timestamp_ms": self.timestamp_ms,
            "day": self.day,
            "hour": self.hour_label,
            "minute": self.minute_label,
            "summary": self.summary,
            "label": self.label,
            "confidence": self.confidence,
            "classes": list(self.classes),
            "scene": self.scene,
            "alert": None
            if self.alert_rule is None
            else {
                "rule": self.alert_rule,
                "severity": self.alert_severity,
                "chunk_file": self.chunk_file,
                "seek_offset_sec": self.seek_offset_sec,
            },
        }


@dataclass(frozen=True)
class FrameQueryResult:
    query: FrameQuery
    total: int
    frames: tuple[IndexedFrame, ...]


@dataclass(frozen=True)
class HourDigest:
    """One hour of the day log: how many readings, which classes, how many alerts."""

    day: str
    hour_label: str
    start_ms: int
    frames: int
    alerts: int
    classes: tuple[ClassCount, ...] = ()
    first_ms: int | None = None
    last_ms: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "day": self.day,
            "hour": self.hour_label,
            "start_ms": self.start_ms,
            "frames": self.frames,
            "alerts": self.alerts,
            "classes": [c.to_dict() for c in self.classes],
            "first_ms": self.first_ms,
            "last_ms": self.last_ms,
        }


@dataclass(frozen=True)
class DayLog:
    session_id: str
    days: dict[str, tuple[HourDigest, ...]] = field(default_factory=dict)

    @property
    def hours(self) -> tuple[HourDigest, ...]:
        return tuple(hour for day in sorted(self.days) for hour in self.days[day])
