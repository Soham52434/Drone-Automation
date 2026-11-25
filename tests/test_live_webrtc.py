import asyncio

import av
import numpy as np
import pytest
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack

from drone_security.config import AppConfig
from drone_security.ingest import SdpMessage
from drone_security.models import SessionStatus
from drone_security.pipeline import InvalidSessionStateError, SessionManager


class SyntheticCamera(VideoStreamTrack):
    async def recv(self) -> av.VideoFrame:
        pts, time_base = await self.next_timestamp()
        image = np.full((240, 320, 3), pts % 255, dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(image, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame


async def _connect(manager: SessionManager, session_id: str) -> RTCPeerConnection:
    client = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    client.addTrack(SyntheticCamera())
    await client.setLocalDescription(await client.createOffer())
    offer = client.localDescription
    answer = await manager.start_live(session_id, SdpMessage(sdp=offer.sdp, type=offer.type))
    await client.setRemoteDescription(RTCSessionDescription(sdp=answer.sdp, type=answer.type))
    return client


async def _wait_for_buffer(manager: SessionManager, session_id: str, seconds: float, timeout: float = 20) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while manager.live_stats(session_id).buffered_seconds < seconds:
        if asyncio.get_running_loop().time() > deadline:
            pytest.fail(f"live buffer did not reach {seconds}s: {manager.live_stats(session_id)}")
        await asyncio.sleep(0.1)


async def test_live_feed_buffers_frames_and_saves_clip(manager: SessionManager, config: AppConfig):
    session = manager.create_live("Dock cam")
    client = await _connect(manager, session.id)
    try:
        assert manager.get_session(session.id).status is SessionStatus.STREAMING
        await _wait_for_buffer(manager, session.id, seconds=1.5)

        artifact = await manager.save_clip(session.id)

        assert artifact.frame_count > 5
        assert artifact.seek_offset_sec > 0
        assert (config.chunk_dir(session.id) / artifact.chunk_file).is_file()
        stats = manager.live_stats(session.id)
        assert stats.frames_received >= stats.frames_buffered
        assert stats.latest_timestamp_ms is not None
    finally:
        await client.close()
        await manager.stop_live(session.id)

    assert manager.get_session(session.id).status is SessionStatus.ENDED
    with pytest.raises(InvalidSessionStateError):
        manager.live_stats(session.id)


async def test_ended_live_session_cannot_restart(manager: SessionManager):
    session = manager.create_live()
    await manager.stop_live(session.id)
    with pytest.raises(InvalidSessionStateError):
        await manager.start_live(session.id, SdpMessage(sdp="v=0", type="offer"))
