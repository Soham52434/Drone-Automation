import pytest

from drone_security.ingest import RingBuffer
from tests.conftest import make_packet, make_packets


def test_evicts_frames_older_than_max_seconds():
    buffer = RingBuffer(max_seconds=1.0)
    for packet in make_packets(30, interval_ms=100):
        buffer.push(packet)
    assert buffer.latest_timestamp_ms == 2900
    assert buffer.window(0, 10_000)[0].timestamp_ms == 1900
    assert buffer.buffered_seconds == pytest.approx(1.0)


def test_window_returns_inclusive_range():
    buffer = RingBuffer(max_seconds=10)
    for packet in make_packets(10, interval_ms=100):
        buffer.push(packet)
    assert [f.timestamp_ms for f in buffer.window(200, 400)] == [200, 300, 400]


def test_rejects_out_of_order_frames():
    buffer = RingBuffer(max_seconds=10)
    buffer.push(make_packet(500))
    with pytest.raises(ValueError, match="timestamp order"):
        buffer.push(make_packet(400))


def test_empty_buffer_reports_nothing():
    buffer = RingBuffer(max_seconds=10)
    assert len(buffer) == 0
    assert buffer.latest_timestamp_ms is None
    assert buffer.buffered_seconds == 0.0


def test_clear_empties_buffer():
    buffer = RingBuffer(max_seconds=10)
    buffer.push(make_packet(0))
    buffer.clear()
    assert len(buffer) == 0


def test_rejects_non_positive_capacity():
    with pytest.raises(ValueError):
        RingBuffer(max_seconds=0)
