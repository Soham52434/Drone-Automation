from pathlib import Path

import pytest

from drone_security.ingest import FrameNormalizer, VideoFileError, VideoFileSource


def test_probe_reads_duration_and_size(sample_video: Path):
    info = VideoFileSource(sample_video, FrameNormalizer(640)).probe()
    assert info.duration_ms == pytest.approx(12_000, abs=100)
    assert (info.width, info.height) == (160, 120)
    assert info.fps == pytest.approx(15)


def test_frames_respect_requested_range(sample_video: Path):
    frames = list(VideoFileSource(sample_video, FrameNormalizer(640)).frames(start_ms=4_000, end_ms=6_000))
    assert frames[0].timestamp_ms >= 4_000
    assert frames[-1].timestamp_ms <= 6_000
    assert len(frames) == pytest.approx(30, abs=2)
    assert frames[0].frame_index == pytest.approx(60, abs=1)


def test_frame_at_returns_the_frame_on_screen(sample_video: Path):
    source = VideoFileSource(sample_video, FrameNormalizer(640))
    early = source.frame_at(0)
    mid = source.frame_at(5_000)
    assert early is not None and mid is not None
    assert early.timestamp_ms <= 100
    assert mid.timestamp_ms == pytest.approx(5_000, abs=100)
    assert mid.timestamp_ms > early.timestamp_ms


def test_non_video_file_is_rejected(tmp_path: Path):
    bogus = tmp_path / "notes.mp4"
    bogus.write_text("not a video")
    with pytest.raises(VideoFileError):
        VideoFileSource(bogus, FrameNormalizer(640)).probe()
