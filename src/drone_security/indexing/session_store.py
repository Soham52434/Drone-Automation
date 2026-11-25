import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from drone_security.models import ChunkArtifact, ChunkTrigger, Session, SessionKind, SessionStatus
from drone_security.models.session import LlmSettings, WatchBrief

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    source_file TEXT,
    duration_ms INTEGER
);
CREATE TABLE IF NOT EXISTS chunks (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    chunk_file TEXT NOT NULL,
    metadata_file TEXT NOT NULL,
    chunk_start_ms INTEGER NOT NULL,
    chunk_end_ms INTEGER NOT NULL,
    detection_ms INTEGER NOT NULL,
    frame_count INTEGER NOT NULL,
    fps REAL NOT NULL,
    trigger TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    PRIMARY KEY (session_id, chunk_file)
);
CREATE INDEX IF NOT EXISTS idx_chunks_detection ON chunks(session_id, detection_ms);
"""

# Columns added after the first release; older databases gain them on open.
_ADDED_COLUMNS = {
    "watch_brief": "TEXT NOT NULL DEFAULT ''",
    "llm_enabled": "INTEGER NOT NULL DEFAULT 0",
    "summary_interval_min": "INTEGER NOT NULL DEFAULT 60",
    "detailed_alerts": "INTEGER NOT NULL DEFAULT 0",
    "advanced_analytics": "INTEGER NOT NULL DEFAULT 0",
}


class SessionNotFoundError(KeyError):
    pass


class SessionStore:
    """SQLite persistence for sessions and their saved chunks."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._ensure_columns()
        self._lock = threading.Lock()
        self._listeners: list[Callable[[], None]] = []

    def on_change(self, listener: Callable[[], None]) -> None:
        """Call `listener` after every session create, update, or delete (any thread)."""
        self._listeners.append(listener)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    def create(
        self,
        kind: SessionKind,
        title: str,
        status: SessionStatus,
        watch_brief: str | None = None,
        llm: LlmSettings | None = None,
    ) -> Session:
        session = Session(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            title=title,
            status=status,
            created_ms=int(time.time() * 1000),
            watch_brief=WatchBrief.resolve(watch_brief).text,
            llm=llm or LlmSettings(),
        )
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions (id, kind, title, status, created_ms, watch_brief,"
                " llm_enabled, summary_interval_min, detailed_alerts, advanced_analytics)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.kind.value,
                    session.title,
                    session.status.value,
                    session.created_ms,
                    session.watch_brief,
                    int(session.llm.enabled),
                    session.llm.summary_interval_minutes,
                    int(session.llm.detailed_alerts),
                    int(session.llm.advanced_analytics),
                ),
            )
        self._changed()
        return session

    def get(self, session_id: str) -> Session:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise SessionNotFoundError(session_id)
        return self._to_session(row)

    def list_sessions(self) -> list[Session]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM sessions ORDER BY created_ms DESC").fetchall()
        return [self._to_session(row) for row in rows]

    def update(self, session: Session) -> Session:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE sessions SET title = ?, status = ?, source_file = ?, duration_ms = ?, watch_brief = ?"
                " WHERE id = ?",
                (
                    session.title,
                    session.status.value,
                    session.source_file,
                    session.duration_ms,
                    session.watch_brief,
                    session.id,
                ),
            )
        if cursor.rowcount == 0:
            raise SessionNotFoundError(session.id)
        self._changed()
        return session

    def set_status(self, session_id: str, status: SessionStatus) -> Session:
        return self.update(replace(self.get(session_id), status=status))

    def delete(self, session_id: str) -> None:
        with self._lock, self._conn:
            cursor = self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        if cursor.rowcount == 0:
            raise SessionNotFoundError(session_id)
        self._changed()

    def add_chunk(self, artifact: ChunkArtifact) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO chunks (session_id, chunk_file, metadata_file, chunk_start_ms, chunk_end_ms,"
                " detection_ms, frame_count, fps, trigger, created_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact.session_id,
                    artifact.chunk_file,
                    artifact.metadata_file,
                    artifact.chunk_start_ms,
                    artifact.chunk_end_ms,
                    artifact.detection_ms,
                    artifact.frame_count,
                    artifact.fps,
                    artifact.trigger.value,
                    artifact.created_ms,
                ),
            )

    def list_chunks(self, session_id: str) -> list[ChunkArtifact]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE session_id = ? ORDER BY detection_ms", (session_id,)
            ).fetchall()
        return [self._to_chunk(row) for row in rows]

    def _ensure_columns(self) -> None:
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(sessions)")}
        with self._conn:
            for name, definition in _ADDED_COLUMNS.items():
                if name not in columns:
                    self._conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _to_session(row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            kind=SessionKind(row["kind"]),
            title=row["title"],
            status=SessionStatus(row["status"]),
            created_ms=row["created_ms"],
            source_file=row["source_file"],
            duration_ms=row["duration_ms"],
            watch_brief=WatchBrief.resolve(row["watch_brief"]).text,
            llm=LlmSettings(
                enabled=bool(row["llm_enabled"]),
                summary_interval_minutes=row["summary_interval_min"],
                detailed_alerts=bool(row["detailed_alerts"]),
                advanced_analytics=bool(row["advanced_analytics"]),
            ),
        )

    @staticmethod
    def _to_chunk(row: sqlite3.Row) -> ChunkArtifact:
        return ChunkArtifact(
            session_id=row["session_id"],
            chunk_file=row["chunk_file"],
            metadata_file=row["metadata_file"],
            chunk_start_ms=row["chunk_start_ms"],
            chunk_end_ms=row["chunk_end_ms"],
            detection_ms=row["detection_ms"],
            frame_count=row["frame_count"],
            fps=row["fps"],
            trigger=ChunkTrigger(row["trigger"]),
            created_ms=row["created_ms"],
        )
