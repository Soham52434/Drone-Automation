import time

from drone_security.models.perception import SceneObservation
from drone_security.models.rules import ClassDwell, TimeRules, WindowContext

_NIGHT_WORDS = ("night", "dark", "evening", "dusk", "midnight", "nighttime")
_DAY_WORDS = ("day", "daylight", "morning", "afternoon", "noon", "sunny", "bright")


class PresenceTracker:
    """How long each class has been continuously in view.

    A class stays "present" through short gaps (the vision model misses someone for a frame or two);
    a gap longer than `max_gap_ms` starts a new stay.
    """

    def __init__(self, max_gap_ms: int = 15_000) -> None:
        if max_gap_ms <= 0:
            raise ValueError("max_gap_ms must be positive")
        self._max_gap = max_gap_ms
        self._since: dict[str, int] = {}
        self._last: dict[str, int] = {}

    def record(self, observation: SceneObservation) -> None:
        now = observation.timestamp_ms
        for name in observation.class_names:
            last = self._last.get(name)
            if last is None or now - last > self._max_gap:
                self._since[name] = now
            self._last[name] = now

    def dwell(self, at_ms: int) -> tuple[ClassDwell, ...]:
        """Classes still in view at `at_ms` and for how long, longest first."""
        stays = [
            ClassDwell(name, self._since[name], round((self._last[name] - self._since[name]) / 1000, 1))
            for name, last in self._last.items()
            if at_ms - last <= self._max_gap
        ]
        return tuple(sorted(stays, key=lambda d: -d.seconds))


def scene_daypart(observations: tuple[SceneObservation, ...] | list[SceneObservation]) -> str:
    """Day or night from the vision model's own scene reading (time_of_day, then lighting), by majority."""
    votes = {"day": 0, "night": 0}
    for observation in observations:
        scene = observation.raw.get("scene") if isinstance(observation.raw, dict) else None
        if not isinstance(scene, dict):
            continue
        text = " ".join(str(scene.get(key, "")) for key in ("time_of_day", "lighting")).lower()
        if any(word in text for word in _NIGHT_WORDS):
            votes["night"] += 1
        elif any(word in text for word in _DAY_WORDS):
            votes["day"] += 1
    if votes["night"] == votes["day"] == 0:
        return "unknown"
    return "night" if votes["night"] > votes["day"] else "day"


def window_context(
    rules: TimeRules,
    live: bool,
    end_ms: int,
    observations: tuple[SceneObservation, ...],
    tracker: PresenceTracker,
) -> WindowContext:
    """When the window happened (clock for live, the vision model's scene for uploads) and what is lingering."""
    dwell = tracker.dwell(end_ms)
    if live:
        local = time.localtime(end_ms / 1000)
        minute = local.tm_hour * 60 + local.tm_min
        after = rules.is_after_hours(minute)
        return WindowContext(
            daypart="night" if after else "day",
            source="clock",
            after_hours=after,
            clock=time.strftime("%H:%M", local),
            dwell=dwell,
        )
    daypart = scene_daypart(observations)
    return WindowContext(
        daypart=daypart,  # type: ignore[arg-type]
        source="scene" if daypart != "unknown" else "none",
        after_hours=daypart == "night",
        dwell=dwell,
    )
