import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from drone_security.models.cost import UsageRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    session_id TEXT NOT NULL,
    job TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    ok INTEGER NOT NULL,
    at_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_session ON usage(session_id);
CREATE INDEX IF NOT EXISTS idx_usage_model_time ON usage(model, at_ms);
"""

_QUOTA_DAY = ZoneInfo("America/Los_Angeles")  # free-tier daily limits reset at midnight Pacific


class UsageLedger:
    """Every LLM/API request with its tokens, for the Cost panel. Kept after a session is deleted
    so the project's free-tier counts for the day stay right."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def record(self, entry: UsageRecord) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO usage VALUES (?, ?, ?, ?, ?, ?, ?)",
                (entry.session_id, entry.job, entry.model, entry.input_tokens, entry.output_tokens, int(entry.ok), entry.at_ms),
            )

    def records(self, session_id: str) -> list[UsageRecord]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM usage WHERE session_id = ? ORDER BY at_ms", (session_id,)).fetchall()
        return [UsageRecord(r[0], r[1], r[2], r[3], r[4], bool(r[5]), r[6]) for r in rows]

    def requests_today(self, now_ms: int) -> dict[str, int]:
        """Requests per model since midnight Pacific (when free-tier daily limits reset)."""
        now = datetime.fromtimestamp(now_ms / 1000, _QUOTA_DAY)
        start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        with self._lock:
            rows = self._conn.execute(
                "SELECT model, COUNT(*) FROM usage WHERE at_ms >= ? GROUP BY model", (start,)
            ).fetchall()
        return {model: count for model, count in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
