import asyncio

from drone_security.models import FramePacket


class LatestFrame:
    """Keeps only the newest frame. Frames that arrive during inference replace the previous one."""

    def __init__(self) -> None:
        self._packet: FramePacket | None = None
        self._version = 0
        self._seen = 0
        self._stopped = False
        self._ready = asyncio.Event()

    def offer(self, packet: FramePacket) -> None:
        self._packet = packet
        self._version += 1
        self._ready.set()

    @property
    def stopped(self) -> bool:
        return self._stopped

    def stop(self) -> None:
        self._stopped = True
        self._ready.set()

    async def next_unseen(self) -> FramePacket | None:
        while self._version == self._seen and not self._stopped:
            self._ready.clear()
            if self._version != self._seen or self._stopped:
                break
            await self._ready.wait()
        if self._version == self._seen:
            return None
        self._seen = self._version
        return self._packet
