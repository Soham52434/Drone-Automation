import io
from pathlib import Path

import pytest

from drone_security.config import AppConfig
from drone_security.ingest import VideoFileError
from drone_security.models import ChunkTrigger, SessionKind, SessionStatus
from drone_security.pipeline import ClipUnavailableError, InvalidSessionStateError, SessionManager
from drone_security.pipeline.stream_session import StreamSession
from drone_security.indexing import SessionNotFoundError

from tests.conftest import make_packets


def _upload(manager: SessionManager, video: Path):
    with video.open("rb") as data:
        return manager.create_upload("gate-camera.mp4", data)


def test_upload_creates_ready_session_with_duration(manager: SessionManager, sample_video: Path):
    session = _upload(manager, sample_video)
    assert session.kind is SessionKind.UPLOAD
    assert session.status is SessionStatus.READY
    assert session.title == "gate-camera"
    assert session.duration_ms == pytest.approx(12_000, abs=100)
    assert manager.source_path(session.id).is_file()


def test_invalid_upload_is_rolled_back(manager: SessionManager, config: AppConfig):
    with pytest.raises(VideoFileError):
        manager.create_upload("broken.mp4", io.BytesIO(b"nope"))
    assert manager.list_sessions() == []
    assert not any(config.sessions_dir.iterdir())


async def test_upload_clip_is_saved_around_video_position(manager: SessionManager, sample_video: Path, config: AppConfig):
    session = _upload(manager, sample_video)
    artifact = await manager.save_clip(session.id, detection_ms=10_000)
    assert artifact.seek_offset_sec == pytest.approx(8.0, abs=0.1)
    assert artifact.duration_sec == pytest.approx(10.0, abs=0.2)
    assert (config.chunk_dir(session.id) / artifact.chunk_file).is_file()
    assert (config.chunk_dir(session.id) / artifact.metadata_file).is_file()
    assert manager.list_chunks(session.id) == [artifact]


async def test_upload_clip_near_start_is_clamped(manager: SessionManager, sample_video: Path):
    session = _upload(manager, sample_video)
    artifact = await manager.save_clip(session.id, detection_ms=3_000)
    assert artifact.chunk_start_ms == 0
    assert artifact.seek_offset_sec == pytest.approx(3.0, abs=0.1)


async def test_clips_with_same_start_are_both_kept(manager: SessionManager, sample_video: Path):
    session = _upload(manager, sample_video)
    first = await manager.save_clip(session.id, detection_ms=3_000)
    second = await manager.save_clip(session.id, detection_ms=5_000)
    assert first.chunk_start_ms == second.chunk_start_ms == 0
    assert first.chunk_file != second.chunk_file
    assert len(manager.list_chunks(session.id)) == 2
    assert manager.chunk_path(session.id, second.chunk_file).is_file()


async def test_upload_clip_requires_position(manager: SessionManager, sample_video: Path):
    session = _upload(manager, sample_video)
    with pytest.raises(ClipUnavailableError):
        await manager.save_clip(session.id)


async def test_live_clip_requires_running_feed(manager: SessionManager):
    session = manager.create_live()
    with pytest.raises(InvalidSessionStateError):
        await manager.save_clip(session.id)


async def test_alert_clip_saves_from_its_own_stream_after_feed_stops(manager: SessionManager, config: AppConfig):
    session = manager.create_live()
    await manager.stop_live(session.id)
    stream = StreamSession(session.id, config)
    for packet in make_packets(150, 100, start_ms=1_000):
        stream.ingest(packet)
    artifact = await manager.save_clip(
        session.id, detection_ms=10_000, trigger=ChunkTrigger.ALERT, stream=stream
    )
    assert artifact.trigger is ChunkTrigger.ALERT
    assert artifact.seek_offset_sec == pytest.approx(8.0, abs=0.2)
    assert manager.list_chunks(session.id) == [artifact]


async def test_stopping_idle_live_session_ends_it(manager: SessionManager):
    session = manager.create_live("Dock cam")
    stopped = await manager.stop_live(session.id)
    assert stopped.status is SessionStatus.ENDED


async def test_delete_removes_session_and_files(manager: SessionManager, sample_video: Path, config: AppConfig):
    session = _upload(manager, sample_video)
    await manager.delete_session(session.id)
    assert not config.session_dir(session.id).exists()
    with pytest.raises(SessionNotFoundError):
        manager.get_session(session.id)


def test_chunk_path_rejects_traversal(manager: SessionManager):
    session = manager.create_live()
    with pytest.raises(InvalidSessionStateError):
        manager.chunk_path(session.id, "../../drone.db")


def test_orphaned_streaming_sessions_end_on_restart(config: AppConfig, store):
    from drone_security.indexing import ChunkWriter

    session = store.create(SessionKind.LIVE, "cam", SessionStatus.STREAMING)
    SessionManager(config, store, ChunkWriter())
    assert store.get(session.id).status is SessionStatus.ENDED
