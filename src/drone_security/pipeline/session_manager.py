import asyncio
import re
import shutil
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import BinaryIO

from drone_security.config import AppConfig
from drone_security.agent.chat_graph import LangGraphChat
from drone_security.agent.entity_graph import LangGraphEntityDescriber
from drone_security.agent.metering import metered_session
from drone_security.indexing.usage_ledger import UsageLedger
from drone_security.models.cost import SessionCost, build_session_cost
from drone_security.agent.summary_graph import LangGraphSummarizer
from drone_security.agent.llm import ChatModel
from drone_security.indexing import ChunkWriter, GraphIndex, KeyframeStore, SessionNotFoundError, SessionStore, SummaryArchive
from drone_security.ingest import FrameNormalizer, LiveFeed, SdpMessage, VideoFileError, VideoFileSource
from drone_security.models import (
    BufferStats,
    ChunkArtifact,
    ChunkEvidence,
    ChunkTrigger,
    ClipPlan,
    LlmSummary,
    LlmSettings,
    Session,
    SessionTelemetry,
    SessionKind,
    SessionStatus,
)
from drone_security.models.chat import ChatTurn
from drone_security.models.events import ErrorEvent
from drone_security.models.index import ClassCount, DayLog
from drone_security.pipeline.analysis import SessionAnalysis
from drone_security.pipeline.session_changes import SessionChangeFeed
from drone_security.pipeline.stream_session import ClipDebouncedError, ClipUnavailableError, StreamSession
from drone_security.telemetry import ClassTelemetryBuilder

_CHUNK_FILE = re.compile(r"^chunk_\d+(_\d+)?\.(mp4|json)$")
_POST_ROLL_GRACE_MS = 1000
_POST_ROLL_POLL_SECONDS = 0.1


class InvalidSessionStateError(RuntimeError):
    pass


@dataclass
class _LiveState:
    feed: LiveFeed
    stream: StreamSession


class SessionManager:
    """Owns session lifecycle: live WebRTC feeds, uploaded videos, and chunk saving."""

    def __init__(
        self,
        config: AppConfig,
        store: SessionStore,
        writer: ChunkWriter,
        perception: object | None = None,
        gate: object | None = None,
        playback_pace: bool = True,
        summarizer: LangGraphSummarizer | None = None,
        chat_llm: ChatModel | None = None,
        describer: LangGraphEntityDescriber | None = None,
        usage: UsageLedger | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._writer = writer
        self._normalizer = FrameNormalizer(config.max_frame_width)
        self._live: dict[str, _LiveState] = {}
        self.changes = SessionChangeFeed()
        store.on_change(self.changes.notify)
        self.index = GraphIndex(config.graph_path)
        self.chat = LangGraphChat(self.index, self._summaries_of, chat_llm)
        self._usage = usage
        self._analysis: SessionAnalysis | None = None
        if (perception is None) != (gate is None):
            raise ValueError("perception and gate must be provided together")
        if perception is not None and gate is not None:
            self._analysis = SessionAnalysis(
                config,
                perception,
                gate,
                writer,
                self.save_clip,
                self._store.set_status,
                self.source_path,
                playback_pace=playback_pace,
                summarizer=summarizer,
                index=self.index,
                describer=describer,
            )
        self._end_orphaned_streams()

    @property
    def vision_loaded(self) -> bool:
        return self._analysis is not None

    def list_sessions(self) -> list[Session]:
        return self._store.list_sessions()

    def get_session(self, session_id: str) -> Session:
        return self._store.get(session_id)

    def list_chunks(self, session_id: str) -> list[ChunkArtifact]:
        self._store.get(session_id)
        return self._store.list_chunks(session_id)

    def create_live(
        self, title: str | None = None, watch_brief: str | None = None, llm: LlmSettings | None = None
    ) -> Session:
        return self._store.create(
            SessionKind.LIVE,
            title or self._default_live_title(),
            SessionStatus.IDLE,
            watch_brief=watch_brief,
            llm=llm,
        )

    def create_upload(
        self, filename: str, data: BinaryIO, watch_brief: str | None = None, llm: LlmSettings | None = None
    ) -> Session:
        session = self._store.create(
            SessionKind.UPLOAD, Path(filename).stem or "Video", SessionStatus.IDLE, watch_brief=watch_brief, llm=llm
        )
        session_dir = self._config.session_dir(session.id)
        session_dir.mkdir(parents=True, exist_ok=True)
        source = session_dir / f"source{Path(filename).suffix.lower() or '.mp4'}"
        try:
            with source.open("wb") as out:
                shutil.copyfileobj(data, out)
            info = VideoFileSource(source, self._normalizer).probe()
            if info.truncated:
                raise VideoFileError(
                    f"This video file is incomplete: it holds {_clock(info.playable_ms or 0)} of video, but its header "
                    f"says {_clock(info.duration_ms)}. The download or copy was probably cut off; download it again."
                )
        except VideoFileError:
            self._store.delete(session.id)
            shutil.rmtree(session_dir, ignore_errors=True)
            raise
        return self._store.update(
            replace(session, status=SessionStatus.READY, source_file=source.name, duration_ms=info.duration_ms)
        )

    async def start_live(self, session_id: str, offer: SdpMessage) -> SdpMessage:
        session = self._store.get(session_id)
        if session.kind is not SessionKind.LIVE:
            raise InvalidSessionStateError("session is not a live session")
        if session.status is not SessionStatus.IDLE or session_id in self._live:
            raise InvalidSessionStateError(f"live session is {session.status.value}")
        stream = StreamSession(session_id, self._config)
        sink = (
            self._analysis.bind_live(session, stream)
            if self._analysis is not None
            else stream.ingest
        )
        feed = LiveFeed(
            self._normalizer,
            sink,
            lambda: self._finish_live(session_id),
            ice_servers=self._config.ice_servers,
        )
        self._live[session_id] = _LiveState(feed=feed, stream=stream)
        try:
            answer = await feed.connect(offer)
        except Exception:
            self._live.pop(session_id, None)
            raise
        self._store.set_status(session_id, SessionStatus.STREAMING)
        return answer

    async def stop_live(self, session_id: str) -> Session:
        session = self._store.get(session_id)
        state = self._live.get(session_id)
        if state is not None:
            await state.feed.close()
        elif session.kind is SessionKind.LIVE and session.status is not SessionStatus.ENDED:
            self._store.set_status(session_id, SessionStatus.ENDED)
        return self._store.get(session_id)

    def live_stats(self, session_id: str) -> BufferStats:
        self._store.get(session_id)
        state = self._live.get(session_id)
        if state is None:
            raise InvalidSessionStateError("live feed is not running")
        return state.stream.stats()

    async def save_clip(
        self,
        session_id: str,
        detection_ms: int | None = None,
        trigger: ChunkTrigger = ChunkTrigger.MANUAL,
        evidence: ChunkEvidence | None = None,
        stream: StreamSession | None = None,
    ) -> ChunkArtifact:
        """Save a clip. `stream` lets an alert in flight crop from its own buffer after the feed stops."""
        session = self._store.get(session_id)
        if session.kind is SessionKind.LIVE:
            plan = await self._plan_live_clip(session_id, detection_ms, trigger, stream)
        else:
            plan = await asyncio.to_thread(self._plan_upload_clip, session, detection_ms, trigger)
        if plan is None:
            raise ClipDebouncedError("alert clip suppressed by cooldown")
        if evidence is not None:
            plan = replace(plan, evidence=evidence)
        artifact = await asyncio.to_thread(self._writer.write, plan, self._config.chunk_dir(session_id))
        self._store.add_chunk(artifact)
        return artifact

    def list_summaries(self, session_id: str) -> list[LlmSummary]:
        self._store.get(session_id)
        return self._summaries_of(session_id)

    def index_classes(self, session_id: str) -> list[ClassCount]:
        self._store.get(session_id)
        return self.index.classes(session_id)

    def telemetry(self, session_id: str) -> SessionTelemetry:
        """Telemetry from class tags: what was seen, when, how often, and the tagged log."""
        self._store.get(session_id)
        return ClassTelemetryBuilder().build(self.index.tagged_readings(session_id))

    def cost(self, session_id: str) -> SessionCost:
        """LLM/API requests and tokens this session used, and today's free-tier use of each model."""
        self._store.get(session_id)
        if self._usage is None:
            return build_session_cost([], {})
        return build_session_cost(self._usage.records(session_id), self._usage.requests_today(int(time.time() * 1000)))

    def day_log(self, session_id: str) -> DayLog:
        self._store.get(session_id)
        return self.index.day_log(session_id)

    async def ask(self, session_id: str, question: str) -> ChatTurn:
        session = self._store.get(session_id)
        with metered_session(session_id):
            return await asyncio.to_thread(self.chat.ask, session, question)

    async def verify_classes(self, session_id: str, thread_id: str, classes: list[str]) -> ChatTurn:
        self._store.get(session_id)
        try:
            with metered_session(session_id):
                return await asyncio.to_thread(self.chat.verify, thread_id, classes)
        except KeyError as exc:
            raise InvalidSessionStateError(str(exc.args[0])) from exc

    def _summaries_of(self, session_id: str) -> list[LlmSummary]:
        return SummaryArchive(self._config.summary_dir(session_id)).list()

    async def iter_events(self, session_id: str):
        session = self._store.get(session_id)
        if self._analysis is None:
            yield ErrorEvent(session_id, "Models are not connected.").to_sse()
            await asyncio.Future()
            return
        async for chunk in self._analysis.iter_events(session):
            yield chunk

    async def delete_session(self, session_id: str) -> None:
        self._store.get(session_id)
        if self._analysis is not None:
            await self._analysis.cancel(session_id)
        state = self._live.pop(session_id, None)
        if state is not None:
            await state.feed.close()
        self._store.delete(session_id)
        await asyncio.to_thread(self.index.delete_session, session_id)
        shutil.rmtree(self._config.session_dir(session_id), ignore_errors=True)

    def source_path(self, session_id: str) -> Path:
        session = self._store.get(session_id)
        if session.source_file is None:
            raise InvalidSessionStateError("session has no source video")
        return self._config.session_dir(session_id) / session.source_file

    def keyframe_path(self, session_id: str, file_name: str) -> Path:
        """A keyframe the LLM looked at; the name is validated so it cannot escape the folder."""
        self._store.get(session_id)
        try:
            path = KeyframeStore(self._config.keyframe_dir(session_id)).path(file_name)
        except ValueError as exc:
            raise InvalidSessionStateError("invalid keyframe file name") from exc
        if not path.is_file():
            raise InvalidSessionStateError("keyframe not found")
        return path

    def chunk_path(self, session_id: str, file_name: str) -> Path:
        self._store.get(session_id)
        if not _CHUNK_FILE.match(file_name):
            raise InvalidSessionStateError("invalid chunk file name")
        path = self._config.chunk_dir(session_id) / file_name
        if not path.is_file():
            raise InvalidSessionStateError("chunk file not found")
        return path

    def session_changes(self):
        """Ticks for the session-list stream: "changed" (send the list) or "ping" (keep alive)."""
        return self.changes.subscribe()

    async def shutdown(self) -> None:
        self.changes.close()
        if self._analysis is not None:
            await self._analysis.shutdown()
        for state in list(self._live.values()):
            await state.feed.close()
        self._live.clear()
        self.index.close()

    async def _plan_live_clip(
        self,
        session_id: str,
        detection_ms: int | None,
        trigger: ChunkTrigger,
        stream: StreamSession | None = None,
    ) -> ClipPlan | None:
        if stream is None:
            state = self._live.get(session_id)
            if state is None:
                raise InvalidSessionStateError("live feed is not running")
            stream = state.stream
        detection = detection_ms if detection_ms is not None else stream.latest_timestamp_ms
        if detection is None:
            raise ClipUnavailableError("no frames received yet")
        deadline = time.monotonic() + (stream.post_roll_ms + _POST_ROLL_GRACE_MS) / 1000
        while not stream.has_post_roll(detection) and time.monotonic() < deadline:
            await asyncio.sleep(_POST_ROLL_POLL_SECONDS)
        return stream.plan_clip(trigger, detection)

    def _plan_upload_clip(
        self, session: Session, detection_ms: int | None, trigger: ChunkTrigger
    ) -> ClipPlan | None:
        if detection_ms is None:
            raise ClipUnavailableError("detection_ms (video position) is required for uploads")
        duration = session.duration_ms or 0
        detection = max(0, min(detection_ms, duration)) if duration else max(0, detection_ms)
        stream = StreamSession(session.id, self._config)
        source = VideoFileSource(self.source_path(session.id), self._normalizer)
        start = max(0, detection - int(self._config.clip_pre_seconds * 1000))
        end = detection + int(self._config.clip_post_seconds * 1000)
        for packet in source.frames(start_ms=start, end_ms=end):
            stream.ingest(packet)
        return stream.plan_clip(trigger, detection)

    async def _finish_live(self, session_id: str) -> None:
        if self._analysis is not None:
            self._analysis.finish_live(session_id)
        await self._on_live_ended(session_id)

    async def _on_live_ended(self, session_id: str) -> None:
        self._live.pop(session_id, None)
        try:
            self._store.set_status(session_id, SessionStatus.ENDED)
        except SessionNotFoundError:
            pass

    def _end_orphaned_streams(self) -> None:
        for session in self._store.list_sessions():
            if session.status is not SessionStatus.STREAMING:
                continue
            if session.kind is SessionKind.LIVE:
                self._store.set_status(session.id, SessionStatus.ENDED)
            else:
                self._store.set_status(session.id, SessionStatus.READY)

    @staticmethod
    def _default_live_title() -> str:
        return f"Live {time.strftime('%b %d, %H:%M')}"


def _clock(ms: int) -> str:
    seconds = round(ms / 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"
