import asyncio
import json
import threading

from fastapi.testclient import TestClient

from drone_security.config import AppConfig
from drone_security.indexing import SessionStore
from drone_security.models import SessionKind, SessionStatus
from drone_security.pipeline.session_changes import SessionChangeFeed
from main import create_app


async def _next(stream, timeout: float = 2.0):
    return await asyncio.wait_for(anext(stream), timeout)


async def test_first_tick_is_the_snapshot_then_one_per_change():
    feed = SessionChangeFeed()
    stream = feed.subscribe()
    assert await _next(stream) == "changed"
    feed.notify()
    assert await _next(stream) == "changed"
    await stream.aclose()
    assert feed.subscribers == 0


async def test_bursts_coalesce_and_other_threads_can_notify():
    feed = SessionChangeFeed()
    stream = feed.subscribe()
    await _next(stream)
    worker = threading.Thread(target=lambda: [feed.notify() for _ in range(25)])
    worker.start()
    worker.join()
    assert await _next(stream) == "changed"
    feed.notify()
    assert await _next(stream) == "changed"  # nothing was left queued from the burst
    await stream.aclose()


async def test_idle_streams_get_a_keepalive_and_close_ends_them():
    feed = SessionChangeFeed(heartbeat_seconds=0.05)
    stream = feed.subscribe()
    await _next(stream)
    assert await _next(stream) == "ping"
    feed.close()
    ended = False
    try:
        while True:
            await _next(stream)
    except StopAsyncIteration:
        ended = True
    assert ended


def test_notify_without_listeners_is_harmless():
    SessionChangeFeed().notify()


def test_store_reports_every_write(tmp_path):
    store = SessionStore(tmp_path / "db.sqlite")
    calls: list[int] = []
    store.on_change(lambda: calls.append(1))
    session = store.create(SessionKind.LIVE, "Gate", SessionStatus.IDLE)
    store.set_status(session.id, SessionStatus.STREAMING)
    store.delete(session.id)
    store.list_sessions()
    assert len(calls) == 3
    store.close()


def test_stream_route_sends_the_session_list_first(config: AppConfig):
    with TestClient(create_app(config)) as client:
        created = client.post("/api/sessions/live", json={"title": "Gate"}).json()
        with client.stream("GET", "/api/sessions/stream") as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                if "\n\n" in buffer:
                    break
        name, data = buffer.split("\n", 1)
        assert name == "event: sessions"
        sessions = json.loads(data.removeprefix("data: ").strip())
        assert [s["id"] for s in sessions] == [created["id"]] and sessions[0]["title"] == "Gate"
        assert client.get("/api/sessions/stream-not-a-session").status_code == 404
