from pathlib import Path

import pytest

from drone_security.config import AppConfig
from drone_security.models import ChunkArtifact, ChunkTrigger, ClipPlan
from tests.conftest import make_packets


def _artifact(**overrides) -> ChunkArtifact:
    values = dict(
        session_id="s1",
        chunk_file="chunk_1000.mp4",
        metadata_file="chunk_1000.json",
        chunk_start_ms=1000,
        chunk_end_ms=11000,
        detection_ms=8450,
        frame_count=150,
        fps=15.0,
        trigger=ChunkTrigger.MANUAL,
        created_ms=20000,
    )
    values.update(overrides)
    return ChunkArtifact(**values)


def test_seek_offset_is_detection_minus_start_in_seconds():
    assert _artifact().seek_offset_sec == 7.45


def test_duration_and_metadata_round_trip_fields():
    metadata = _artifact().to_metadata()
    assert metadata["duration_sec"] == 10.0
    assert metadata["seek_offset_sec"] == 7.45
    assert metadata["trigger"] == "manual"
    assert metadata["chunk_file"] == "chunk_1000.mp4"


def test_clip_plan_bounds_follow_frames():
    plan = ClipPlan("s1", ChunkTrigger.MANUAL, 500, tuple(make_packets(5, 100, start_ms=200)))
    assert (plan.start_ms, plan.end_ms) == (200, 600)


def test_config_rejects_window_over_fifteen_seconds(tmp_path: Path):
    with pytest.raises(ValueError, match="exceeds 15"):
        AppConfig(data_dir=tmp_path, buffer_seconds=20, clip_pre_seconds=14, clip_post_seconds=2)


def test_config_rejects_window_larger_than_buffer(tmp_path: Path):
    with pytest.raises(ValueError, match="ring buffer"):
        AppConfig(data_dir=tmp_path, buffer_seconds=5, clip_pre_seconds=8, clip_post_seconds=2)


def test_config_paths_are_scoped_per_session(tmp_path: Path):
    config = AppConfig(data_dir=tmp_path)
    assert config.chunk_dir("abc") == tmp_path / "sessions" / "abc" / "chunks"
    assert config.db_path == tmp_path / "drone.db"


def test_config_reads_ice_servers_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DRONE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DRONE_ICE_SERVERS", "stun:a.example:3478, stun:b.example:3478")
    config = AppConfig.from_env()
    assert config.ice_servers == ("stun:a.example:3478", "stun:b.example:3478")



def test_summary_and_chat_models_share_one_default(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DRONE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DRONE_SUMMARY_MODEL", raising=False)
    monkeypatch.delenv("DRONE_CHAT_MODEL", raising=False)
    config = AppConfig.from_env()
    assert config.summary_model == config.chat_model and config.summary_model
    monkeypatch.setenv("DRONE_CHAT_MODEL", "model-b")
    assert AppConfig.from_env().chat_model == "model-b"
