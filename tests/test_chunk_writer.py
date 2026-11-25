import json
from pathlib import Path

import av
import pytest

from drone_security.indexing import ChunkWriter
from drone_security.models import ChunkTrigger, ClipPlan
from tests.conftest import make_packets


def _plan(count: int = 30, interval_ms: int = 100, start_ms: int = 5_000) -> ClipPlan:
    frames = tuple(make_packets(count, interval_ms, start_ms=start_ms))
    return ClipPlan("s1", ChunkTrigger.MANUAL, detection_ms=start_ms + 2_000, frames=frames)


def test_writes_paired_mp4_and_json(tmp_path: Path):
    artifact = ChunkWriter().write(_plan(), tmp_path)
    assert artifact.chunk_file == "chunk_5000.mp4"
    assert artifact.metadata_file == "chunk_5000.json"
    assert (tmp_path / "chunk_5000.mp4").stat().st_size > 0
    metadata = json.loads((tmp_path / "chunk_5000.json").read_text())
    assert metadata["seek_offset_sec"] == 2.0
    assert metadata["chunk_start_ms"] == 5000
    assert metadata["detection_ms"] == 7000


def test_encoded_video_keeps_frame_count_and_timing(tmp_path: Path):
    artifact = ChunkWriter().write(_plan(count=30, interval_ms=100), tmp_path)
    assert artifact.fps == pytest.approx(10.0)
    with av.open(str(tmp_path / artifact.chunk_file)) as container:
        frames = list(container.decode(video=0))
    assert len(frames) == 30
    assert frames[-1].time == pytest.approx(2.9, abs=0.05)


def test_same_start_time_gets_a_distinct_file(tmp_path: Path):
    writer = ChunkWriter()
    first = writer.write(_plan(), tmp_path)
    second = writer.write(_plan(), tmp_path)
    assert (first.chunk_file, second.chunk_file) == ("chunk_5000.mp4", "chunk_5000_2.mp4")
    assert second.metadata_file == "chunk_5000_2.json"
    assert json.loads((tmp_path / "chunk_5000_2.json").read_text())["chunk_file"] == "chunk_5000_2.mp4"


def test_rejects_empty_plan(tmp_path: Path):
    plan = ClipPlan("s1", ChunkTrigger.MANUAL, detection_ms=0, frames=())
    with pytest.raises(ValueError):
        ChunkWriter().write(plan, tmp_path)
