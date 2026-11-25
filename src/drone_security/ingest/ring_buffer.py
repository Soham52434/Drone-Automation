import threading
from collections import deque

from drone_security.models import FramePacket


class RingBuffer:
    """Holds the most recent `max_seconds` of frames, evicting by timestamp."""

    def __init__(self, max_seconds: float) -> None:
        if max_seconds <= 0:
            raise ValueError("max_seconds must be positive")
        self._max_ms = int(max_seconds * 1000)
        self._frames: deque[FramePacket] = deque()
        self._lock = threading.Lock()

    def push(self, packet: FramePacket) -> None:
        with self._lock:
            if self._frames and packet.timestamp_ms < self._frames[-1].timestamp_ms:
                raise ValueError("frames must arrive in timestamp order")
            self._frames.append(packet)
            cutoff = packet.timestamp_ms - self._max_ms
            while self._frames and self._frames[0].timestamp_ms < cutoff:
                self._frames.popleft()

    def window(self, start_ms: int, end_ms: int) -> tuple[FramePacket, ...]:
        with self._lock:
            return tuple(f for f in self._frames if start_ms <= f.timestamp_ms <= end_ms)

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()

    @property
    def latest_timestamp_ms(self) -> int | None:
        with self._lock:
            return self._frames[-1].timestamp_ms if self._frames else None

    @property
    def buffered_seconds(self) -> float:
        with self._lock:
            if len(self._frames) < 2:
                return 0.0
            return (self._frames[-1].timestamp_ms - self._frames[0].timestamp_ms) / 1000

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)
