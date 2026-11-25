import asyncio
import json
from pathlib import Path

from drone_security.config import AppConfig
from drone_security.indexing import ChunkWriter
from drone_security.models import Session, SessionKind, SessionStatus
from drone_security.pipeline import analysis as analysis_module
from drone_security.pipeline.analysis import SessionAnalysis
from drone_security.pipeline.stream_session import StreamSession
from tests.conftest import make_packet


class _Never:
    def observe(self, packet):
        raise AssertionError("not used")

    def evaluate(self, window, brief=None):
        raise AssertionError("not used")


async def test_live_stats_are_pushed_not_polled_and_not_replayed(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(analysis_module, "_STATS_INTERVAL_SECONDS", 0.05)
    config = AppConfig(data_dir=tmp_path)
    analysis = SessionAnalysis(
        config, _Never(), _Never(), ChunkWriter(), save_clip=None, set_status=lambda *_: None, source_path=lambda _: tmp_path
    )
    session = Session("live1", SessionKind.LIVE, "Gate", SessionStatus.STREAMING, 0)
    stream = StreamSession(session.id, config)
    stream.ingest(make_packet(1_000))
    # bind_live starts the consumer and the stats ticker; the consumer waits for frames that never come.
    analysis.bind_live(session, stream)
    events = analysis.iter_events(session)
    seen: list[tuple[str, dict]] = []
    while not any(name == "stats" for name, _ in seen):
        block = await asyncio.wait_for(anext(events), 2)
        name, data = block.split("\n")[0].removeprefix("event: "), json.loads(block.split("\n")[1].removeprefix("data: "))
        seen.append((name, data))
    stats = next(data for name, data in seen if name == "stats")
    assert stats["frames_received"] == 1 and stats["frames_buffered"] == 1
    assert all(e.to_sse().split("\n")[0] != "event: stats" for e in analysis._recent.get(session.id, []))
    await events.aclose()
    await analysis.shutdown()
    assert analysis._stats_tasks == {}
