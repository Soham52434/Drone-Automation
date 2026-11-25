import pytest

from drone_security.config import AppConfig
from drone_security.models import ChunkTrigger
from drone_security.pipeline import ClipUnavailableError, CommitDebouncer, StreamSession
from tests.conftest import make_packet, make_packets


@pytest.fixture
def stream(config: AppConfig) -> StreamSession:
    session = StreamSession("s1", config)
    for packet in make_packets(15 * 20, interval_ms=67, start_ms=1_000_000):
        session.ingest(packet)
    return session


def test_throttles_input_above_max_fps(config: AppConfig):
    session = StreamSession("s1", config)
    kept = [session.ingest(p) for p in make_packets(60, interval_ms=33)]
    assert sum(kept) == pytest.approx(30, abs=1)
    assert session.stats().frames_received == 60


def test_keeps_every_frame_at_max_fps_with_rounded_timestamps(config: AppConfig):
    session = StreamSession("s1", config)
    packets = [make_packet(round(i * 1000 / 15), i) for i in range(150)]
    assert all(session.ingest(p) for p in packets)


def test_keeps_every_frame_below_max_fps(config: AppConfig):
    session = StreamSession("s1", config)
    assert all(session.ingest(p) for p in make_packets(20, interval_ms=100))


def test_resumes_after_gap_without_burst(config: AppConfig):
    session = StreamSession("s1", config)
    session.ingest(make_packets(1, 33)[0])
    later = make_packets(4, interval_ms=33, start_ms=5_000)
    assert [session.ingest(p) for p in later] == [True, False, True, False]


def test_plan_clip_spans_pre_and_post_roll(stream: StreamSession):
    detection = stream.latest_timestamp_ms - 3000
    plan = stream.plan_clip(ChunkTrigger.MANUAL, detection)
    assert plan is not None
    assert detection - plan.start_ms <= 8000
    assert detection - plan.start_ms > 7800
    assert plan.end_ms - detection <= 2000
    assert plan.end_ms - plan.start_ms <= 10_000


def test_buffer_never_holds_more_than_fifteen_seconds(stream: StreamSession):
    assert stream.stats().buffered_seconds <= 15.0


def test_manual_saves_are_never_debounced(stream: StreamSession):
    detection = stream.latest_timestamp_ms - 3000
    assert stream.plan_clip(ChunkTrigger.MANUAL, detection) is not None
    assert stream.plan_clip(ChunkTrigger.MANUAL, detection) is not None


def test_alert_saves_are_debounced_within_cooldown(stream: StreamSession):
    detection = stream.latest_timestamp_ms - 3000
    assert stream.plan_clip(ChunkTrigger.ALERT, detection) is not None
    assert stream.plan_clip(ChunkTrigger.ALERT, detection + 500) is None


def test_debouncer_allows_alert_after_cooldown():
    debouncer = CommitDebouncer(cooldown_ms=10_000)
    assert debouncer.try_acquire(ChunkTrigger.ALERT, 0)
    assert not debouncer.try_acquire(ChunkTrigger.ALERT, 9_999)
    assert debouncer.try_acquire(ChunkTrigger.ALERT, 10_000)


def test_plan_clip_without_frames_raises(config: AppConfig):
    with pytest.raises(ClipUnavailableError):
        StreamSession("s1", config).plan_clip(ChunkTrigger.MANUAL, 1000)


def test_held_timeframe_survives_after_the_ring_drops_it(config: AppConfig):
    session = StreamSession("s1", config)
    session.hold_from(0)
    for packet in make_packets(40, interval_ms=1_000):
        session.ingest(packet)
    assert session.stats().buffered_seconds <= 15
    plan = session.plan_clip(ChunkTrigger.MANUAL, 5_000)
    assert plan is not None
    assert plan.start_ms <= 5_000
    assert any(frame.timestamp_ms <= 5_000 for frame in plan.frames)
    session.release_hold(0)
    with pytest.raises(ClipUnavailableError):
        session.plan_clip(ChunkTrigger.MANUAL, 5_000)


def test_has_post_roll_waits_for_frames_after_detection(stream: StreamSession):
    latest = stream.latest_timestamp_ms
    assert stream.has_post_roll(latest - 2000)
    assert not stream.has_post_roll(latest - 1000)
