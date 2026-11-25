from dataclasses import replace

import sqlite3

import pytest

from drone_security.indexing import SessionNotFoundError, SessionStore
from drone_security.models import ChunkArtifact, ChunkTrigger, SessionKind, SessionStatus
from drone_security.models.session import DEFAULT_WATCH_BRIEF


def _chunk(session_id: str, start_ms: int) -> ChunkArtifact:
    return ChunkArtifact(
        session_id=session_id,
        chunk_file=f"chunk_{start_ms}.mp4",
        metadata_file=f"chunk_{start_ms}.json",
        chunk_start_ms=start_ms,
        chunk_end_ms=start_ms + 10_000,
        detection_ms=start_ms + 8_000,
        frame_count=150,
        fps=15.0,
        trigger=ChunkTrigger.MANUAL,
        created_ms=start_ms,
    )


def test_create_and_get_round_trip(store: SessionStore):
    created = store.create(SessionKind.LIVE, "Gate cam", SessionStatus.IDLE)
    assert store.get(created.id) == created


def test_list_is_newest_first(store: SessionStore):
    first = store.create(SessionKind.LIVE, "first", SessionStatus.IDLE)
    second = store.create(SessionKind.UPLOAD, "second", SessionStatus.READY)
    store.update(replace(first, title="first"))
    ids = [s.id for s in store.list_sessions()]
    assert ids.index(second.id) <= ids.index(first.id)


def test_update_and_set_status(store: SessionStore):
    session = store.create(SessionKind.UPLOAD, "clip", SessionStatus.IDLE)
    store.update(replace(session, source_file="source.mp4", duration_ms=1234))
    updated = store.set_status(session.id, SessionStatus.READY)
    assert (updated.source_file, updated.duration_ms, updated.status) == ("source.mp4", 1234, SessionStatus.READY)


def test_chunks_are_listed_by_detection_time_and_cascade_on_delete(store: SessionStore):
    session = store.create(SessionKind.LIVE, "cam", SessionStatus.STREAMING)
    store.add_chunk(_chunk(session.id, 50_000))
    store.add_chunk(_chunk(session.id, 10_000))
    assert [c.chunk_start_ms for c in store.list_chunks(session.id)] == [10_000, 50_000]
    store.delete(session.id)
    assert store.list_chunks(session.id) == []


def test_blank_watch_brief_stores_the_default(store: SessionStore):
    created = store.create(SessionKind.LIVE, "Gate cam", SessionStatus.IDLE, watch_brief="  ")
    assert created.watch_brief == DEFAULT_WATCH_BRIEF
    assert store.get(created.id).watch_brief == DEFAULT_WATCH_BRIEF


def test_custom_watch_brief_round_trips(store: SessionStore):
    brief = "Only alert when a boat is near the dock."
    created = store.create(SessionKind.UPLOAD, "Harbor", SessionStatus.READY, watch_brief=brief)
    assert store.get(created.id).watch_brief == brief


def test_older_database_without_the_brief_column_reads_the_default(tmp_path):
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,"
        " status TEXT NOT NULL, created_ms INTEGER NOT NULL, source_file TEXT, duration_ms INTEGER)"
    )
    conn.execute(
        "INSERT INTO sessions (id, kind, title, status, created_ms) VALUES ('abc', 'live', 'cam', 'idle', 1)"
    )
    conn.commit()
    conn.close()
    session = SessionStore(db).get("abc")
    assert session.watch_brief == DEFAULT_WATCH_BRIEF


def test_missing_session_raises(store: SessionStore):
    with pytest.raises(SessionNotFoundError):
        store.get("missing")
    with pytest.raises(SessionNotFoundError):
        store.delete("missing")
