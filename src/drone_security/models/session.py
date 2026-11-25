from dataclasses import dataclass
from enum import StrEnum


class SessionKind(StrEnum):
    LIVE = "live"
    UPLOAD = "upload"


class SessionStatus(StrEnum):
    IDLE = "idle"
    STREAMING = "streaming"
    READY = "ready"
    ENDED = "ended"


DEFAULT_WATCH_BRIEF = (
    "Person detection, vehicle detection, package deliveries, animals, "
    "and hazards such as fire or smoke. Alert when any of these appear. "
    "Ignore empty scenes and routine background."
)
_MAX_WATCH_BRIEF = 2_000


@dataclass(frozen=True)
class WatchBrief:
    """What this session should alert on. Blank input uses the property-security default."""

    text: str

    @classmethod
    def resolve(cls, text: str | None) -> "WatchBrief":
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return cls(DEFAULT_WATCH_BRIEF)
        return cls(cleaned[:_MAX_WATCH_BRIEF])

    def system_prompt(self) -> str:
        return (
            "You are the alert classifier for this session only. "
            "The watch brief below is the rule for what counts as an alert. "
            "Vision readings have no memory across frames. Judge only this window.\n\n"
            f"Watch brief:\n{self.text}"
        )


SUMMARY_INTERVAL_CHOICES: tuple[int, ...] = (1, *range(5, 61, 5))


@dataclass(frozen=True)
class LlmSettings:
    """Per-session LLM settings, chosen in the session setup form.

    The alert classifier is the alert gate and runs regardless. These settings only govern the LLM:
    the periodic evidence summary, the dead-hand final summary, and optional alert write-ups.
    """

    enabled: bool = False
    summary_interval_minutes: int = 60
    detailed_alerts: bool = False
    #: The LLM describes people and vehicles in key frames (colour, make, clothing) for repeat-visit questions.
    advanced_analytics: bool = False

    def __post_init__(self) -> None:
        if self.summary_interval_minutes not in SUMMARY_INTERVAL_CHOICES:
            raise ValueError(
                f"summary interval must be one of {SUMMARY_INTERVAL_CHOICES} minutes, got {self.summary_interval_minutes}"
            )

    @property
    def summary_interval_ms(self) -> int:
        return self.summary_interval_minutes * 60_000

    @property
    def writes_alert_details(self) -> bool:
        return self.enabled and self.detailed_alerts

    @property
    def describes_entities(self) -> bool:
        return self.enabled and self.advanced_analytics


@dataclass(frozen=True)
class Session:
    """One sidebar conversation: a live camera feed or an uploaded video.

    Timeline values for this session are epoch milliseconds for LIVE and
    media-position milliseconds for UPLOAD.
    """

    id: str
    kind: SessionKind
    title: str
    status: SessionStatus
    created_ms: int
    source_file: str | None = None
    duration_ms: int | None = None
    watch_brief: str = DEFAULT_WATCH_BRIEF
    llm: LlmSettings = LlmSettings()
