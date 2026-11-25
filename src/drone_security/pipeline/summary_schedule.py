from drone_security.models.perception import SceneObservation
from drone_security.models.summaries import AlertNote, Keyframe


class SummaryScheduler:
    """Cuts the session timeline into fixed periods for LLM summaries.

    Periods start at the first frame the session sees and run every `interval_ms` on the
    session's own timeline (wall clock for live, position in the file for uploads).
    """

    def __init__(self, interval_ms: int) -> None:
        if interval_ms <= 0:
            raise ValueError("summary interval must be positive")
        self._interval = interval_ms
        self._first_ms: int | None = None
        self._period_start: int | None = None
        self._last_ms: int | None = None

    @property
    def first_ms(self) -> int | None:
        return self._first_ms

    @property
    def last_ms(self) -> int | None:
        return self._last_ms

    @property
    def period_start(self) -> int | None:
        return self._period_start

    def advance(self, timestamp_ms: int) -> list[tuple[int, int]]:
        """Note the playhead. Returns every period that has now closed, oldest first."""
        if self._period_start is None:
            self._first_ms = self._period_start = timestamp_ms
        self._last_ms = timestamp_ms if self._last_ms is None else max(self._last_ms, timestamp_ms)
        closed: list[tuple[int, int]] = []
        while timestamp_ms >= self._period_start + self._interval:
            end = self._period_start + self._interval
            closed.append((self._period_start, end))
            self._period_start = end
        return closed


class SessionEvidence:
    """What the LLM may read for one session: readings since the last period, every alert, earlier summaries."""

    def __init__(self) -> None:
        self._observations: list[SceneObservation] = []
        self._alerts: list[AlertNote] = []
        self._summaries: list[tuple[int, str]] = []
        self._keyframes: list[Keyframe] = []

    def record(self, observation: SceneObservation) -> None:
        self._observations.append(observation)

    def add_alert(self, note: AlertNote) -> None:
        self._alerts.append(note)

    def take_period(self, start_ms: int, end_ms: int) -> tuple[tuple[SceneObservation, ...], tuple[AlertNote, ...]]:
        """Readings and alerts inside [start, end). Readings before `end` are then released."""
        observations = tuple(o for o in self._observations if start_ms <= o.timestamp_ms < end_ms)
        alerts = tuple(a for a in self._alerts if start_ms <= a.detection_ms < end_ms)
        self._observations = [o for o in self._observations if o.timestamp_ms >= end_ms]
        return observations, alerts

    def remaining(self) -> tuple[SceneObservation, ...]:
        return tuple(self._observations)

    def all_alerts(self) -> tuple[AlertNote, ...]:
        return tuple(sorted(self._alerts, key=lambda a: a.detection_ms))

    def add_keyframe(self, keyframe: Keyframe) -> None:
        self._keyframes.append(keyframe)

    def keyframes_between(self, start_ms: int, end_ms: int) -> tuple[Keyframe, ...]:
        return tuple(k for k in self._keyframes if start_ms <= k.timestamp_ms < end_ms)

    def all_keyframes(self) -> tuple[Keyframe, ...]:
        return tuple(self._keyframes)

    def remember_summary(self, start_ms: int, text: str) -> None:
        self._summaries.append((start_ms, text))

    def earlier_summaries(self) -> tuple[str, ...]:
        return tuple(text for _, text in sorted(self._summaries))
