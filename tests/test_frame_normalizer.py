import av
import numpy as np

from drone_security.ingest import FrameNormalizer


def test_keeps_small_frames_at_even_size():
    assert FrameNormalizer(640).target_size(321, 241) == (320, 240)


def test_downscales_wide_frames_preserving_aspect():
    assert FrameNormalizer(640).target_size(1280, 720) == (640, 360)


def test_normalize_produces_rgb_packet():
    frame = av.VideoFrame.from_ndarray(np.zeros((720, 1280, 3), dtype=np.uint8), format="rgb24")
    packet = FrameNormalizer(640).normalize(frame, timestamp_ms=1234, frame_index=7)
    assert packet.image.shape == (360, 640, 3)
    assert (packet.timestamp_ms, packet.frame_index) == (1234, 7)
    assert (packet.width, packet.height) == (640, 360)
