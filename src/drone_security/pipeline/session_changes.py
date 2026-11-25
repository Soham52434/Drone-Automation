import asyncio
import threading
from collections.abc import AsyncIterator
from typing import Literal

SessionTick = Literal["changed", "ping"]

_CLOSED = object()


class SessionChangeFeed:
    """Tells every connected page that the session list changed, instead of pages polling for it.

    `notify()` may be called from any thread (sync routes run in a thread pool). Bursts coalesce:
    a subscriber that has not caught up yet gets one "changed", not one per write.
    """

    def __init__(self, heartbeat_seconds: float = 25.0) -> None:
        self._heartbeat = heartbeat_seconds
        self._queues: set[asyncio.Queue[object]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._closed = False

    @property
    def subscribers(self) -> int:
        return len(self._queues)

    def notify(self) -> None:
        with self._lock:
            loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._wake, "changed")
        except RuntimeError:
            pass  # loop shutting down

    def close(self) -> None:
        """End every open stream (server shutdown)."""
        self._closed = True
        with self._lock:
            loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._wake, _CLOSED)
            except RuntimeError:
                pass

    async def subscribe(self) -> AsyncIterator[SessionTick]:
        """Yields "changed" at once (the initial snapshot), then on every change; "ping" when idle."""
        queue: asyncio.Queue[object] = asyncio.Queue()
        with self._lock:
            self._loop = asyncio.get_running_loop()
        self._queues.add(queue)
        try:
            yield "changed"
            while not self._closed:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=self._heartbeat)
                except TimeoutError:
                    yield "ping"
                    continue
                if item is _CLOSED:
                    return
                yield "changed"
        finally:
            self._queues.discard(queue)

    def _wake(self, item: object) -> None:
        for queue in list(self._queues):
            if item is _CLOSED or queue.empty():
                queue.put_nowait(item)
