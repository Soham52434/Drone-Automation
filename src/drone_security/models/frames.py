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
