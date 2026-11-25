import os
from dataclasses import dataclass
from pathlib import Path

from drone_security.models.rules import TimeRules

MAX_DECISION_WINDOW_SECONDS = 15.0


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path
    buffer_seconds: float = MAX_DECISION_WINDOW_SECONDS
    clip_pre_seconds: float = 8.0
    clip_post_seconds: float = 2.0
    alert_cooldown_seconds: float = 10.0
    max_buffer_fps: float = 15.0
    max_frame_width: int = 640
    ice_servers: tuple[str, ...] = ()
    decision_window_seconds: float = 10.0
    # Predefined time rules: alert on people/vehicles after hours, and on people loitering.
    after_hours: str = "22:00-06:00"
    loiter_seconds: float = 60.0
    vision_sample_ms: int = 250
    alert_noul_threshold: float = 0.6
    decision_model: str = "gemini-decision-1"
    # One free-tier model for every LLM job by default (free tier: 30 RPM, 16K TPM, 14.4K requests/day).
    # Each setting may also be a comma-separated chain; later models take over on errors.
    summary_model: str = "gemma-4-26b-a4b-it"
    chat_model: str = "gemma-4-26b-a4b-it"
    llm_api_key: str = ""
    vision_dir: Path | None = None

    def __post_init__(self) -> None:
        window = self.clip_pre_seconds + self.clip_post_seconds
        if window > MAX_DECISION_WINDOW_SECONDS:
            raise ValueError(f"clip window {window}s exceeds {MAX_DECISION_WINDOW_SECONDS}s")
        if window > self.buffer_seconds:
            raise ValueError(f"clip window {window}s exceeds ring buffer {self.buffer_seconds}s")
        if self.decision_window_seconds > MAX_DECISION_WINDOW_SECONDS:
            raise ValueError(f"decision window {self.decision_window_seconds}s exceeds {MAX_DECISION_WINDOW_SECONDS}s")
        if self.decision_window_seconds > self.buffer_seconds:
            raise ValueError(f"decision window {self.decision_window_seconds}s exceeds ring buffer {self.buffer_seconds}s")
        if self.max_buffer_fps <= 0 or self.max_frame_width <= 0 or self.vision_sample_ms <= 0:
            raise ValueError("max_buffer_fps, max_frame_width, and vision_sample_ms must be positive")
        if not 0.0 < self.alert_noul_threshold < 0.99:
            raise ValueError("alert_noul_threshold must be between 0 and 0.99")

    def time_rules(self) -> TimeRules:
        return TimeRules.parse(self.after_hours, self.loiter_seconds)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "drone.db"

    @property
    def usage_path(self) -> Path:
        """Every LLM/API request and its tokens (the Cost panel)."""
        return self.data_dir / "usage.sqlite3"

    @property
    def graph_path(self) -> Path:
        return self.data_dir / "graph.db"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def chunk_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "chunks"

    def keyframe_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "keyframes"

    def summary_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "logs" / "summaries"

    @property
    def resolved_vision_dir(self) -> Path:
        if self.vision_dir is not None:
            return self.vision_dir
        return Path(__file__).resolve().parents[2] / "models" / "vision"

    @classmethod
    def from_env(cls) -> "AppConfig":
        ice = os.environ.get("DRONE_ICE_SERVERS", "")
        vision_dir = os.environ.get("DRONE_VISION_DIR", "").strip()
        return cls(
            data_dir=Path(os.environ.get("DRONE_DATA_DIR", "data")).resolve(),
            ice_servers=tuple(url.strip() for url in ice.split(",") if url.strip()),
            llm_api_key=os.environ.get("GOOGLE_API_KEY", ""),
            decision_model=os.environ.get("DRONE_DECISION_MODEL", cls.decision_model),
            summary_model=os.environ.get("DRONE_SUMMARY_MODEL", cls.summary_model),
            chat_model=os.environ.get("DRONE_CHAT_MODEL", cls.chat_model),
            after_hours=os.environ.get("DRONE_AFTER_HOURS", cls.after_hours),
            loiter_seconds=float(os.environ.get("DRONE_LOITER_SECONDS", cls.loiter_seconds)),
            vision_dir=Path(vision_dir).resolve() if vision_dir else None,
        )
