from dataclasses import dataclass
from typing import Literal

Daypart = Literal["day", "night", "unknown"]
TimeSource = Literal["clock", "scene", "none"]


@dataclass(frozen=True)
class ClassDwell:
    """How long a class has been continuously in view at the end of a window."""

    name: str
    since_ms: int
    seconds: float


@dataclass(frozen=True)
class WindowContext:
    """When a decision window happened and what has been lingering, for the time-based rules.

    Live sessions read the wall clock. Uploaded videos have no trustworthy clock, so they use
    The vision model's own reading of the scene (time_of_day / lighting) to tell day from night.
    """

    daypart: Daypart
    source: TimeSource
    after_hours: bool
    clock: str = ""  # "23:58" for live sessions
    dwell: tuple[ClassDwell, ...] = ()

    def dwell_of(self, name: str) -> ClassDwell | None:
        return next((d for d in self.dwell if d.name == name), None)


@dataclass(frozen=True)
class TimeRules:
    """Predefined time-based alert rules. Times are minutes after local midnight."""

    after_hours_start: int = 22 * 60
    after_hours_end: int = 6 * 60
    loiter_seconds: float = 60.0
    after_hours_classes: tuple[str, ...] = ("person", "vehicle")
    loiter_classes: tuple[str, ...] = ("person",)

    def __post_init__(self) -> None:
        for minute in (self.after_hours_start, self.after_hours_end):
            if not 0 <= minute < 24 * 60:
                raise ValueError("after-hours times must be within the day")
        if self.loiter_seconds <= 0:
            raise ValueError("loiter_seconds must be positive")

    def is_after_hours(self, minute_of_day: int) -> bool:
        """True inside the window; a window like 22:00–06:00 wraps past midnight."""
        start, end = self.after_hours_start, self.after_hours_end
        if start == end:
            return False
        if start < end:
            return start <= minute_of_day < end
        return minute_of_day >= start or minute_of_day < end

    @property
    def after_hours_label(self) -> str:
        return f"{_hhmm(self.after_hours_start)}–{_hhmm(self.after_hours_end)}"

    @classmethod
    def parse(cls, after_hours: str = "22:00-06:00", loiter_seconds: float = 60.0) -> "TimeRules":
        """'22:00-06:00' → TimeRules; an empty string turns the after-hours rule off."""
        text = after_hours.strip()
        if not text:
            return cls(0, 0, loiter_seconds)
        start, end = (part.strip() for part in text.split("-", 1))
        return cls(_minutes(start), _minutes(end), loiter_seconds)


@dataclass(frozen=True)
class RuleHit:
    """A predefined rule that fired on a window."""

    rule: Literal["after_hours", "loitering"]
    class_name: str
    severity: Literal["warn", "critical"]
    detail: str


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
