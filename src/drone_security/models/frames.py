from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, eq=False)
class FramePacket:
    timestamp_ms: int
    frame_index: int
    image: np.ndarray

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


@dataclass(frozen=True)
class BufferStats:
    frames_received: int
    frames_buffered: int
    buffered_seconds: float
    latest_timestamp_ms: int | None


@dataclass(frozen=True)
class VideoInfo:
    duration_ms: int
    width: int
    height: int
    fps: float
    #: How much video the file really holds (last packet). Less than `duration_ms` when the file was cut off.
    playable_ms: int | None = None

    @property
    def truncated(self) -> bool:
        """The header promises noticeably more video than the file contains (an interrupted download or copy)."""
        if self.playable_ms is None:
            return False
        missing = self.duration_ms - self.playable_ms
        return missing > 2_000 and self.playable_ms < 0.9 * self.duration_ms
