import av

from drone_security.models import FramePacket


class FrameNormalizer:
    """Converts decoded video frames into RGB packets no wider than `max_width`."""

    def __init__(self, max_width: int) -> None:
        self._max_width = max_width

    def target_size(self, width: int, height: int) -> tuple[int, int]:
        if width <= self._max_width:
            return self._even(width), self._even(height)
        scale = self._max_width / width
        return self._even(self._max_width), self._even(round(height * scale))

    def normalize(self, frame: av.VideoFrame, timestamp_ms: int, frame_index: int) -> FramePacket:
        width, height = self.target_size(frame.width, frame.height)
        image = frame.reformat(width=width, height=height, format="rgb24").to_ndarray()
        return FramePacket(timestamp_ms=timestamp_ms, frame_index=frame_index, image=image)

    @staticmethod
    def _even(value: int) -> int:
        return max(2, value - value % 2)
