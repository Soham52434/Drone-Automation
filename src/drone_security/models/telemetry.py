from dataclasses import dataclass


@dataclass(frozen=True)
class TaggedReading:
    """One vision reading reduced to its class tags, as the telemetry log keeps it."""

    timestamp_ms: int
    classes: tuple[tuple[str, float], ...]  # (class, score), strongest first
    scene: str = ""
    summary: str = ""
    label: str = ""
    alert_rule: str | None = None
    #: Advanced analytics: the LLM's entity descriptions for this reading ("blue Ford F150 pickup").
    descriptions: tuple[str, ...] = ()

    @property
    def class_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.classes)


@dataclass(frozen=True)
class ClassActivity:
    """How one class showed up over a session: how often, when, how strongly, and in which spans."""

    name: str
    frames: int
    first_ms: int
    last_ms: int
    best_score: float
    avg_score: float
    alerts: int
    #: (start_ms, end_ms) runs of consecutive readings that carried this tag.
    spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class SessionTelemetry:
    """Session telemetry built from class tags: per-class activity plus the tagged reading log."""

    readings: int
    alerts: int
    first_ms: int | None
    last_ms: int | None
    classes: tuple[ClassActivity, ...]
    #: Newest first, capped; `readings` is the full count.
    log: tuple[TaggedReading, ...]

    @property
    def duration_ms(self) -> int:
        return 0 if self.first_ms is None or self.last_ms is None else self.last_ms - self.first_ms
