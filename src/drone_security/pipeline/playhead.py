import time


class WallClock:
    """Milliseconds since this clock was created."""

    def __init__(self) -> None:
        self._origin = time.monotonic()

    def now_ms(self) -> int:
        return int((time.monotonic() - self._origin) * 1000)


class StepClock:
    """Jumps forward by a fixed step. Used so tests cover a timeline without sleeping."""

    def __init__(self, step_ms: int) -> None:
        if step_ms <= 0:
            raise ValueError("step_ms must be positive")
        self._step_ms = step_ms
        self._now = 0

    def now_ms(self) -> int:
        return self._now

    def advance(self) -> None:
        self._now += self._step_ms
