import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from aiortc import (
    MediaStreamTrack,
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.mediastreams import MediaStreamError

from drone_security.ingest.frame_normalizer import FrameNormalizer
from drone_security.models import FramePacket

logger = logging.getLogger(__name__)

FrameSink = Callable[[FramePacket], None]
EndedCallback = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class SdpMessage:
    sdp: str
    type: str


class LiveFeed:
    """One browser camera connection: receives the WebRTC video track into a frame sink."""

    def __init__(
        self,
        normalizer: FrameNormalizer,
        sink: FrameSink,
        on_ended: EndedCallback,
        ice_servers: tuple[str, ...] = (),
    ) -> None:
        self._normalizer = normalizer
        self._sink = sink
        self._on_ended = on_ended
        servers = [RTCIceServer(urls=url) for url in ice_servers]
        self._pc = RTCPeerConnection(RTCConfiguration(iceServers=servers))
        self._consumer: asyncio.Task[None] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._pc.on("track", self._on_track)
        self._pc.on("connectionstatechange", self._on_connection_state)

    async def connect(self, offer: SdpMessage) -> SdpMessage:
        await self._pc.setRemoteDescription(RTCSessionDescription(sdp=offer.sdp, type=offer.type))
        answer = await self._pc.createAnswer()
        await self._pc.setLocalDescription(answer)
        local = self._pc.localDescription
        return SdpMessage(sdp=local.sdp, type=local.type)

    async def close(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._shutdown())
        await asyncio.shield(self._close_task)

    async def _shutdown(self) -> None:
        if self._consumer is not None:
            self._consumer.cancel()
            await asyncio.gather(self._consumer, return_exceptions=True)
        await self._pc.close()
        await self._on_ended()

    def _on_track(self, track: MediaStreamTrack) -> None:
        if track.kind == "video" and self._consumer is None:
            self._consumer = asyncio.create_task(self._consume(track))

    async def _on_connection_state(self) -> None:
        if self._pc.connectionState in ("failed", "closed"):
            await self.close()

    async def _consume(self, track: MediaStreamTrack) -> None:
        index = 0
        while True:
            try:
                frame = await track.recv()
            except MediaStreamError:
                break
            packet = self._normalizer.normalize(frame, int(time.time() * 1000), index)
            self._sink(packet)
            index += 1
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._shutdown())
