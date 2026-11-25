from drone_security.models.perception import DecisionWindow, SceneObservation

_MAX_WINDOW_MS = 15_000


class StreamAnalyzer:
    """Closes a decision window every `window_ms` of timeline from the frames the vision model actually saw."""

    def __init__(self, session_id: str, window_ms: int) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        if window_ms > _MAX_WINDOW_MS:
            raise ValueError(f"decision window {window_ms} ms exceeds {_MAX_WINDOW_MS} ms")
        self.session_id = session_id
        self._window_ms = window_ms
        self._window_start: int | None = None
        self._observations: list[SceneObservation] = []

    def open_window(self, timestamp_ms: int) -> int:
        """Anchor the window that is still open. The first call sets the start."""
        if self._window_start is None:
            self._window_start = timestamp_ms
        return self._window_start

    @property
    def window_start(self) -> int | None:
        return self._window_start

    def record(self, observation: SceneObservation) -> None:
        self._observations.append(observation)

    def close_remaining(self, end_ms: int) -> DecisionWindow | None:
        """At the end of a video or feed: the open window up to `end_ms`, if it holds any readings."""
        if self._window_start is None or not self._observations:
            return None
        start = self._window_start
        end = max(start, min(end_ms, start + self._window_ms))
        chosen = tuple(o for o in self._observations if start <= o.timestamp_ms <= end)
        self._observations = []
        self._window_start = None
        if not chosen:
            return None
        return DecisionWindow(session_id=self.session_id, start_ms=start, end_ms=end, observations=chosen)

    def close_ready(self, timestamp_ms: int) -> DecisionWindow | None:
        """Close one window when the timeline has covered it. Empty windows are still returned."""
        if self._window_start is None:
            self._window_start = timestamp_ms
            return None
        if timestamp_ms - self._window_start < self._window_ms:
            return None
        start = self._window_start
        end = start + self._window_ms
        chosen = tuple(
            observation
            for observation in self._observations
            if start <= observation.timestamp_ms < end
        )
        self._observations = [
            observation for observation in self._observations if observation.timestamp_ms >= end
        ]
        self._window_start = end
        return DecisionWindow(session_id=self.session_id, start_ms=start, end_ms=end, observations=chosen)
