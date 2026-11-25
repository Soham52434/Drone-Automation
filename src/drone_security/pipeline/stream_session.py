import threading
from collections import deque

from drone_security.config import AppConfig
from drone_security.ingest import RingBuffer
from drone_security.models import BufferStats, ChunkTrigger, ClipPlan, FramePacket

_TIMESTAMP_TOLERANCE_MS = 2


class ClipUnavailableError(RuntimeError):
    pass


class ClipDebouncedError(RuntimeError):
    pass


class CommitDebouncer:
    """Suppresses repeat ALERT commits inside the cooldown. MANUAL saves always pass."""

    def __init__(self, cooldown_ms: int) -> None:
        self._cooldown_ms = cooldown_ms
        self._last_alert_ms: int | None = None

    def try_acquire(self, trigger: ChunkTrigger, detection_ms: int) -> bool:
        if trigger is ChunkTrigger.MANUAL:
            return True
        if self._last_alert_ms is not None and 0 <= detection_ms - self._last_alert_ms < self._cooldown_ms:
            return False
        self._last_alert_ms = detection_ms
        return True


class StreamSession:
    """Per-session timeline: throttled ring buffer plus clip planning around a detection time."""

    def __init__(self, session_id: str, config: AppConfig) -> None:
        self.session_id = session_id
        self._buffer = RingBuffer(config.buffer_seconds)
        self._min_interval_ms = 1000 / config.max_buffer_fps
        self._pre_ms = int(config.clip_pre_seconds * 1000)
        self._post_ms = int(config.clip_post_seconds * 1000)
        self._debouncer = CommitDebouncer(int(config.alert_cooldown_seconds * 1000))
        self._frames_received = 0
        self._next_due_ms: float | None = None
        self._retained: deque[FramePacket] = deque()
        self._holds: list[int] = []
        self._retain_lock = threading.Lock()

    def ingest(self, packet: FramePacket) -> bool:
        self._frames_received += 1
        ts = packet.timestamp_ms
        if self._next_due_ms is not None and ts + _TIMESTAMP_TOLERANCE_MS < self._next_due_ms:
            return False
        self._buffer.push(packet)
        self._remember(packet)
        if self._next_due_ms is None or ts - self._next_due_ms > self._min_interval_ms:
            self._next_due_ms = ts + self._min_interval_ms
        else:
            self._next_due_ms += self._min_interval_ms
        return True

    def hold_from(self, start_ms: int) -> None:
        """Keep frames from `start_ms` until `release_hold`, even after the 15 s ring drops them.

        An alert crop is 8 s before the detection. The vision model can take longer than the ring
        keeps, so the open decision window pins its timeframe until the clip is written.
        """
        latest = self._buffer.latest_timestamp_ms
        seeded = self._buffer.window(start_ms, latest) if latest is not None else ()
        with self._retain_lock:
            if start_ms in self._holds:
                return
            self._holds.append(start_ms)
            for packet in seeded:
                self._remember_unlocked(packet)
            self._trim_retained()

    def release_hold(self, start_ms: int) -> None:
        with self._retain_lock:
            try:
                self._holds.remove(start_ms)
            except ValueError:
                return
            self._trim_retained()

    def plan_clip(self, trigger: ChunkTrigger, detection_ms: int) -> ClipPlan | None:
        frames = self._span(detection_ms - self._pre_ms, detection_ms + self._post_ms)
        if not frames:
            raise ClipUnavailableError("no buffered frames around the detection time")
        if not self._debouncer.try_acquire(trigger, detection_ms):
            return None
        return ClipPlan(session_id=self.session_id, trigger=trigger, detection_ms=detection_ms, frames=frames)

    def frames_between(self, start_ms: int, end_ms: int) -> tuple[FramePacket, ...]:
        return self._span(start_ms, end_ms)

    def _remember(self, packet: FramePacket) -> None:
        with self._retain_lock:
            self._remember_unlocked(packet)

    def _remember_unlocked(self, packet: FramePacket) -> None:
        if not self._holds or packet.timestamp_ms < min(self._holds):
            return
        if self._retained and packet.timestamp_ms <= self._retained[-1].timestamp_ms:
            return
        self._retained.append(packet)

    def _trim_retained(self) -> None:
        if not self._holds:
            self._retained.clear()
            return
        cutoff = min(self._holds)
        while self._retained and self._retained[0].timestamp_ms < cutoff:
            self._retained.popleft()

    def _span(self, start_ms: int, end_ms: int) -> tuple[FramePacket, ...]:
        with self._retain_lock:
            retained = tuple(self._retained)
        by_time: dict[int, FramePacket] = {}
        for packet in retained:
            if start_ms <= packet.timestamp_ms <= end_ms:
                by_time[packet.timestamp_ms] = packet
        for packet in self._buffer.window(start_ms, end_ms):
            by_time.setdefault(packet.timestamp_ms, packet)
        return tuple(by_time[stamp] for stamp in sorted(by_time))

    def has_post_roll(self, detection_ms: int) -> bool:
        latest = self._buffer.latest_timestamp_ms
        return latest is not None and latest >= detection_ms + self._post_ms

    @property
    def post_roll_ms(self) -> int:
        return self._post_ms

    @property
    def latest_timestamp_ms(self) -> int | None:
        return self._buffer.latest_timestamp_ms

    def stats(self) -> BufferStats:
        return BufferStats(
            frames_received=self._frames_received,
            frames_buffered=len(self._buffer),
            buffered_seconds=round(self._buffer.buffered_seconds, 3),
            latest_timestamp_ms=self._buffer.latest_timestamp_ms,
        )
