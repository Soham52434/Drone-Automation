"""Uploaded videos are sampled continuously: fast forward reads, decisions that never block
perception, the last window judged at the end, and disk errors that do not stop the session."""

import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest
from fastapi.testclient import TestClient

from drone_security.config import AppConfig
from drone_security.decisions import LangGraphDecisionGate
from drone_security.indexing.hourly_log import HourlyObservationLog
from drone_security.ingest import FrameNormalizer, VideoFileSource
from drone_security.models import ClassHit, FramePacket
from drone_security.models.perception import SceneObservation
from drone_security.perception import LangGraphPerception
from drone_security.pipeline.analysis import _thin
from drone_security.pipeline.analyzer import StreamAnalyzer
from main import create_app
from tests.test_analysis_stream import ScriptedClassifier, _events


def _video(path: Path, seconds: int, fps: int = 10, gop: int = 10) -> Path:
    """A video whose frame i has brightness i, so a frame's identity can be checked."""
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=fps, options={"g": str(gop), "keyint_min": str(gop)})
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        for i in range(seconds * fps):
            frame = av.VideoFrame.from_ndarray(np.full((48, 64, 3), i % 250, dtype=np.uint8), format="rgb24")
            frame.pts, frame.time_base = i, Fraction(1, fps)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


@pytest.fixture
def source(tmp_path) -> VideoFileSource:
    return VideoFileSource(_video(tmp_path / "v.mp4", seconds=12), FrameNormalizer(640))


def test_forward_reader_returns_the_same_frames_as_a_fresh_seek(source):
    with source.playback() as reader:
        for at in (0, 350, 2_000, 2_000, 5_550, 9_900, 1_000, 11_900):
            ours, fresh = reader.frame_at(at), VideoFileSource.frame_at(source, at)
            assert ours.timestamp_ms == fresh.timestamp_ms <= at
            assert np.array_equal(ours.image, fresh.image)


def test_asking_twice_for_the_same_moment_returns_the_same_frame(source):
    with source.playback() as reader:
        first, again = reader.frame_at(4_000), reader.frame_at(4_000)
    assert first.timestamp_ms == again.timestamp_ms == 4_000


def test_reader_jumps_to_keyframes_instead_of_decoding_everything(source, monkeypatch):
    decoded = 0
    with source.playback() as reader:
        original = reader._decode

        def counting():
            nonlocal decoded
            for item in original():
                decoded += 1
                yield item

        monkeypatch.setattr(reader, "_decode", counting)
        reader.frame_at(0)
        reader.frame_at(11_000)  # 11 s ahead, keyframe every 1 s: decode ~1 s, not 11 s
    assert decoded < 25


def test_decision_clip_is_thinned_before_conversion(source):
    clip = source.window_frames(0, 10_000, 200)
    assert 45 <= len(clip) <= 51
    assert all(b.timestamp_ms - a.timestamp_ms >= 198 for a, b in zip(clip, clip[1:]))
    packets = tuple(FramePacket(t, t // 100, np.zeros((2, 2, 3), np.uint8)) for t in range(0, 1_000, 100))
    assert [p.timestamp_ms for p in _thin(packets, 200)] == [0, 200, 400, 600, 800]


def test_open_window_is_judged_when_the_video_ends():
    analyzer = StreamAnalyzer("s", 10_000)
    analyzer.open_window(20_000)
    reading = SceneObservation(23_000, 1, True, "man", 0.8, "man", classes=(ClassHit("person", 0.8),))
    analyzer.record(reading)
    window = analyzer.close_remaining(24_000)
    assert (window.start_ms, window.end_ms, window.observations) == (20_000, 24_000, (reading,))
    assert analyzer.close_remaining(30_000) is None


class _Vision:
    loaded = True

    def describe(self, packet) -> dict:
        return {"reasoning": "A man by the gate.", "scene": {"background": "gate"}, "objects": [{"name": "man", "score": 0.8}]}


class _SlowClassifier(ScriptedClassifier):
    def invoke(self, payload: dict) -> object:
        time.sleep(0.4)
        return super().invoke(payload)


def test_slow_decisions_do_not_stall_the_readings(tmp_path):
    video = _video(tmp_path / "gate.mp4", seconds=30)
    config = AppConfig(data_dir=tmp_path / "data", vision_sample_ms=500)
    app = create_app(
        config,
        perception=LangGraphPerception(_Vision()),
        gate=LangGraphDecisionGate(_SlowClassifier(0.2, "none"), 0.6),
        playback_pace=False,
    )
    with TestClient(app) as client:
        with video.open("rb") as data:
            session = client.post("/api/sessions/upload", files={"file": ("gate.mp4", data, "video/mp4")}).json()
        events = _events(client, session["id"])
    names = [name for name, _ in events]
    readings = [body["timestamp_ms"] for name, body in events if name == "observation"]
    assert len(readings) >= 55 and readings[-1] >= 29_000, "the whole video is read"
    assert names.count("decision") == 3, "every 10 s window is judged, the last one at the end"
    # The first window closes after ~20 readings; with decisions in the background, more readings
    # arrive while the classifier is still answering (the old blocking loop stopped at ~21).
    first_decision = names.index("decision")
    assert sum(1 for n in names[:first_decision] if n == "observation") > 25, "readings kept coming while a decision ran"
    assert not any(name == "error" for name in names)


def test_a_full_disk_does_not_stop_the_session(tmp_path, monkeypatch):
    def full(self, observation, recorded_ms=None):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(HourlyObservationLog, "append", full)
    video = _video(tmp_path / "gate.mp4", seconds=12)
    app = create_app(
        AppConfig(data_dir=tmp_path / "data"),
        perception=LangGraphPerception(_Vision()),
        gate=LangGraphDecisionGate(ScriptedClassifier(0.2, "none"), 0.6),
        playback_pace=False,
    )
    with TestClient(app) as client:
        with video.open("rb") as data:
            session = client.post("/api/sessions/upload", files={"file": ("gate.mp4", data, "video/mp4")}).json()
        events = _events(client, session["id"])
    readings = [body for name, body in events if name == "observation"]
    errors = [body["detail"] for name, body in events if name == "error"]
    assert len(readings) > 20 and readings[-1]["timestamp_ms"] >= 11_000
    assert any("No space left" in e for e in errors)
    assert events[-1][0] == "status" and events[-1][1]["status"] == "ended"


def _cut_off(path: Path, seconds: int, keep: float) -> Path:
    """A video with its index at the front (like most downloads) whose tail is missing, as when
    a download stops early: the header still promises the full length."""
    full = path.with_name("full.mp4")
    with av.open(str(full), mode="w", options={"movflags": "faststart"}) as container:
        stream = container.add_stream("libx264", rate=10, options={"g": "10"})
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        for i in range(seconds * 10):
            frame = av.VideoFrame.from_ndarray(np.random.randint(0, 255, (48, 64, 3), dtype=np.uint8), format="rgb24")
            frame.pts, frame.time_base = i, Fraction(1, 10)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    data = full.read_bytes()
    path.write_bytes(data[: int(len(data) * keep)])
    return path


def test_a_cut_off_file_is_recognised(tmp_path):
    cut = VideoFileSource(_cut_off(tmp_path / "cut.mp4", seconds=30, keep=0.3), FrameNormalizer(640))
    info = cut.probe()
    assert info.duration_ms == 30_000 and info.playable_ms < 15_000 and info.truncated
    whole = VideoFileSource(_video(tmp_path / "whole.mp4", seconds=12), FrameNormalizer(640)).probe()
    assert not whole.truncated
    with cut.playback() as reader:
        assert reader.frame_at(2_000).timestamp_ms == 2_000
        # Past the real data, playback ends: either no frame, or the last real frame with the decoder exhausted.
        last = reader.frame_at(29_000)
        assert last is None or (reader.exhausted and last.timestamp_ms < 15_000)


def test_uploading_a_cut_off_file_explains_what_is_wrong(tmp_path):
    video = _cut_off(tmp_path / "drone.mp4", seconds=30, keep=0.3)
    app = create_app(AppConfig(data_dir=tmp_path / "data"))
    with TestClient(app) as client:
        with video.open("rb") as data:
            response = client.post("/api/sessions/upload", files={"file": ("drone.mp4", data, "video/mp4")})
        assert response.status_code == 400
        assert "incomplete" in response.json()["detail"] and "0:30" in response.json()["detail"]
        assert client.get("/api/sessions").json() == []
