from drone_security.models.telemetry import ClassActivity, SessionTelemetry, TaggedReading


class ClassTelemetryBuilder:
    """Session telemetry from class tags: what was seen, when, how often, and how strongly.

    A span is a run of consecutive readings carrying the tag; it breaks when a reading lacks the tag
    or the gap between readings exceeds `max_gap_ms`. The log keeps the newest `log_limit` readings.
    """

    def __init__(self, max_gap_ms: int = 15_000, log_limit: int = 500) -> None:
        if max_gap_ms <= 0 or log_limit <= 0:
            raise ValueError("max_gap_ms and log_limit must be positive")
        self._max_gap = max_gap_ms
        self._log_limit = log_limit

    def build(self, readings: list[TaggedReading] | tuple[TaggedReading, ...]) -> SessionTelemetry:
        ordered = sorted(readings, key=lambda r: r.timestamp_ms)
        if not ordered:
            return SessionTelemetry(0, 0, None, None, (), ())
        stats: dict[str, dict[str, object]] = {}
        open_spans: dict[str, list[int]] = {}
        spans: dict[str, list[tuple[int, int]]] = {}
        previous_ms: int | None = None
        for reading in ordered:
            gap_broken = previous_ms is not None and reading.timestamp_ms - previous_ms > self._max_gap
            present = set(reading.class_names)
            for name in list(open_spans):
                if name not in present or gap_broken:
                    start, end = open_spans.pop(name)
                    spans.setdefault(name, []).append((start, end))
            for name, score in reading.classes:
                s = stats.setdefault(name, {"frames": 0, "first": reading.timestamp_ms, "last": 0, "best": 0.0, "sum": 0.0, "alerts": 0})
                s["frames"] = int(s["frames"]) + 1  # type: ignore[arg-type]
                s["last"] = reading.timestamp_ms
                s["best"] = max(float(s["best"]), score)  # type: ignore[arg-type]
                s["sum"] = float(s["sum"]) + score  # type: ignore[arg-type]
                if reading.alert_rule:
                    s["alerts"] = int(s["alerts"]) + 1  # type: ignore[arg-type]
                if name in open_spans:
                    open_spans[name][1] = reading.timestamp_ms
                else:
                    open_spans[name] = [reading.timestamp_ms, reading.timestamp_ms]
            previous_ms = reading.timestamp_ms
        for name, (start, end) in open_spans.items():
            spans.setdefault(name, []).append((start, end))
        classes = tuple(
            sorted(
                (
                    ClassActivity(
                        name=name,
                        frames=int(s["frames"]),  # type: ignore[arg-type]
                        first_ms=int(s["first"]),  # type: ignore[arg-type]
                        last_ms=int(s["last"]),  # type: ignore[arg-type]
                        best_score=round(float(s["best"]), 3),  # type: ignore[arg-type]
                        avg_score=round(float(s["sum"]) / int(s["frames"]), 3),  # type: ignore[arg-type]
                        alerts=int(s["alerts"]),  # type: ignore[arg-type]
                        spans=tuple(spans.get(name, ())),
                    )
                    for name, s in stats.items()
                ),
                key=lambda c: (-c.frames, c.name),
            )
        )
        return SessionTelemetry(
            readings=len(ordered),
            alerts=sum(1 for r in ordered if r.alert_rule),
            first_ms=ordered[0].timestamp_ms,
            last_ms=ordered[-1].timestamp_ms,
            classes=classes,
            log=tuple(reversed(ordered[-self._log_limit :])),
        )
