import asyncio

from drone_security.pipeline.latest_frame import LatestFrame
from tests.conftest import make_packet


def test_only_the_newest_frame_is_kept():
    slot = LatestFrame()

    async def scenario():
        slot.offer(make_packet(0))
        slot.offer(make_packet(1_000))
        first = await slot.next_unseen()
        slot.offer(make_packet(2_000))
        slot.offer(make_packet(5_000))
        second = await slot.next_unseen()
        return first, second

    first, second = asyncio.run(scenario())
    assert first is not None and first.timestamp_ms == 1_000
    assert second is not None and second.timestamp_ms == 5_000


def test_stop_ends_the_wait():
    slot = LatestFrame()

    async def scenario():
        stopper = asyncio.create_task(_stop_soon(slot))
        packet = await slot.next_unseen()
        await stopper
        return packet

    assert asyncio.run(scenario()) is None


async def _stop_soon(slot: LatestFrame) -> None:
    await asyncio.sleep(0.01)
    slot.stop()


def test_stopped_is_visible():
    from drone_security.pipeline.latest_frame import LatestFrame

    slot = LatestFrame()
    assert slot.stopped is False
    slot.stop()
    assert slot.stopped is True
