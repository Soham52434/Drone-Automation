import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from drone_security.config import AppConfig
from drone_security.agent.summary_graph import LangGraphSummarizer
from drone_security.agent.entity_graph import DESCRIBED_CLASSES, LangGraphEntityDescriber
from drone_security.agent.keyframes import KeyframeSelector
from drone_security.agent.metering import metered_session
from drone_security.indexing import ChunkWriter, GraphIndex, HourlyObservationLog, KeyframeStore, SummaryArchive, observation_id
from drone_security.ingest import VideoFileSource
from drone_security.models import (
    AlertNote,
    ChunkArtifact,
    ChunkEvidence,
    ChunkTrigger,
    FramePacket,
    Keyframe,
    LlmSettings,
    Session,
    SessionKind,
    SessionStatus,
    SummaryKind,
    SummaryRequest,
)
from drone_security.models.events import (
    AlertEvent,
    AnalysisEvent,
    DecisionEvent,
    ErrorEvent,
    ObservationEvent,
    StatsEvent,
    StatusEvent,
    SummaryEvent,
)
from drone_security.models.perception import DecisionWindow, GateResult, SceneObservation
from drone_security.models.session import WatchBrief
from drone_security.pipeline.analyzer import StreamAnalyzer
from drone_security.pipeline.latest_frame import LatestFrame
from drone_security.pipeline.playhead import StepClock, WallClock
from drone_security.pipeline.stream_session import ClipDebouncedError, CommitDebouncer, StreamSession
from drone_security.pipeline.presence import PresenceTracker, window_context
from drone_security.pipeline.summary_schedule import SessionEvidence, SummaryScheduler

SaveClip = Callable[..., Awaitable[ChunkArtifact]]
_RECENT_LIMIT = 100
_STATS_INTERVAL_SECONDS = 1.0


class SessionAnalysis:
    """Feeds the vision model one frame at a time and each closed window to the alert classifier.

    The next frame is whatever is on screen when inference finishes. Frames that arrive
    while the vision model is busy are skipped, so a slow machine stays at the live moment instead
    of working through a backlog. Uploaded video uses the same rule on a playhead that
    follows the wall clock.
    """

    def __init__(
        self,
        config: AppConfig,
        perception: object,
        gate: object,
        writer: ChunkWriter,
        save_clip: SaveClip,
        set_status: Callable[[str, SessionStatus], None],
        source_path: Callable[[str], Path],
        playback_pace: bool = True,
        summarizer: LangGraphSummarizer | None = None,
        index: GraphIndex | None = None,
        describer: LangGraphEntityDescriber | None = None,
    ) -> None:
        self._config = config
        self._perception = perception
        self._gate = gate
        self._writer = writer
        self._save_clip = save_clip
        self._set_status = set_status
        self._source_path = source_path
        self._pace = playback_pace
        self._fast_step_ms = config.vision_sample_ms
        self._window_ms = int(config.decision_window_seconds * 1000)
        self._pre_ms = int(config.clip_pre_seconds * 1000)
        self._analyzers: dict[str, StreamAnalyzer] = {}
        self._streams: dict[str, StreamSession] = {}
        self._logs: dict[str, HourlyObservationLog] = {}
        self._debouncers: dict[str, CommitDebouncer] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._latest: dict[str, LatestFrame] = {}
        self._subscribers: dict[str, list[asyncio.Queue[AnalysisEvent]]] = {}
        self._recent: dict[str, list[AnalysisEvent]] = {}
        self._commits: set[asyncio.Task[None]] = set()
        self._briefs: dict[str, str] = {}
        self._summarizer = summarizer or LangGraphSummarizer(None, unavailable_reason="GOOGLE_API_KEY is not set")
        self._summary_sessions: dict[str, _SummarySession] = {}
        self._index = index
        self._selector = KeyframeSelector()
        self._stats_tasks: dict[str, asyncio.Task[None]] = {}
        self._rules = config.time_rules()
        self._presence: dict[str, PresenceTracker] = {}
        self._kinds: dict[str, SessionKind] = {}
        self._describer = describer
        self._describing: set[str] = set()

    def bind_live(self, session: Session, stream: StreamSession) -> Callable[[FramePacket], None]:
        """Return the WebRTC sink. Every frame is buffered; the vision model only sees the newest one."""
        session_id = session.id
        self._briefs[session_id] = session.watch_brief
        self._open_session(session, stream)
        slot = LatestFrame()
        self._latest[session_id] = slot
        loop = asyncio.get_running_loop()
        self._tasks[session_id] = asyncio.create_task(self._consume_live(session_id, slot))
        self._stats_tasks[session_id] = asyncio.create_task(self._push_stats(session_id, stream, slot))

        def sink(packet: FramePacket) -> None:
            stream.ingest(packet)

            def _offer() -> None:
                slot.offer(packet)

            loop.call_soon_threadsafe(_offer)

        return sink

    def finish_live(self, session_id: str) -> None:
        slot = self._latest.get(session_id)
        if slot is None:
            return
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(slot.stop)

    async def iter_events(self, session: Session) -> AsyncIterator[str]:
        queue: asyncio.Queue[AnalysisEvent] = asyncio.Queue()
        recent = list(self._recent.get(session.id, []))
        self._subscribers.setdefault(session.id, []).append(queue)
        if session.kind is SessionKind.UPLOAD and session.status is SessionStatus.READY:
            self._start_playback(session)
        try:
            for event in recent:
                yield event.to_sse()
            while True:
                yield (await queue.get()).to_sse()
        finally:
            subscribers = self._subscribers.get(session.id, [])
            if queue in subscribers:
                subscribers.remove(queue)

    async def cancel(self, session_id: str) -> None:
        task = self._tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        slot = self._latest.pop(session_id, None)
        if slot is not None:
            slot.stop()
        stats_task = self._stats_tasks.pop(session_id, None)
        if stats_task is not None:
            stats_task.cancel()
        self._streams.pop(session_id, None)
        self._analyzers.pop(session_id, None)
        self._presence.pop(session_id, None)
        llm_state = self._summary_sessions.pop(session_id, None)
        if llm_state is not None:
            for summary_task in list(llm_state.tasks):
                summary_task.cancel()

    async def shutdown(self) -> None:
        for session_id in list(self._tasks):
            await self.cancel(session_id)
        for task in list(self._commits):
            task.cancel()
        if self._commits:
            await asyncio.gather(*self._commits, return_exceptions=True)
        for llm_state in self._summary_sessions.values():
            for summary_task in list(llm_state.tasks):
                summary_task.cancel()

    def _start_playback(self, session: Session) -> None:
        current = self._tasks.get(session.id)
        if current is not None and not current.done():
            return
        self._briefs[session.id] = session.watch_brief
        self._mark(session.id, SessionStatus.STREAMING)
        self._tasks[session.id] = asyncio.create_task(self._play(session))

    async def _play(self, session: Session) -> None:
        stream = self._open_session(session, StreamSession(session.id, self._config))
        source = VideoFileSource(self._source_path(session.id), _normalizer(self._config))
        duration = session.duration_ms or 0
        clock: WallClock | StepClock = WallClock() if self._pace else StepClock(self._fast_step_ms)
        self._publish(StatusEvent(session.id, "playing", "Sampling the video at the current moment"))
        last_frame_ms: int | None = None
        try:
            while True:
                now_ms = clock.now_ms()
                if now_ms >= duration:
                    break
                packet = await asyncio.to_thread(source.frame_at, now_ms)
                if packet is None:
                    break
                if last_frame_ms is not None and packet.timestamp_ms <= last_frame_ms:
                    if isinstance(clock, StepClock):
                        clock.advance()
                        continue
                    await asyncio.sleep(0.02)
                    continue
                await self._observe(session.id, stream, packet, source)
                last_frame_ms = packet.timestamp_ms
                if isinstance(clock, StepClock):
                    clock.advance()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._publish(ErrorEvent(session.id, str(exc)))
            await self._dead_hand(session.id)
        else:
            if self._commits:
                await asyncio.gather(*list(self._commits), return_exceptions=True)
            await self._dead_hand(session.id)
        finally:
            self._mark(session.id, SessionStatus.ENDED)
            self._publish(StatusEvent(session.id, "ended", "Video analysis finished"))

    async def _push_stats(self, session_id: str, stream: StreamSession, slot: LatestFrame) -> None:
        """Buffer readout for the live badge, pushed instead of polled. Stops with the feed."""
        try:
            while not slot.stopped:
                self._publish(StatsEvent(session_id, stream.stats()), remember=False)
                await asyncio.sleep(_STATS_INTERVAL_SECONDS)
        finally:
            self._stats_tasks.pop(session_id, None)

    async def _consume_live(self, session_id: str, slot: LatestFrame) -> None:
        stream = self._streams[session_id]
        self._publish(StatusEvent(session_id, "live", "The vision model is watching the camera stream"))
        try:
            while True:
                packet = await slot.next_unseen()
                if packet is None:
                    break
                await self._observe(session_id, stream, packet, source=None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._publish(ErrorEvent(session_id, str(exc)))
            await self._dead_hand(session_id)
        else:
            if self._commits:
                await asyncio.gather(*list(self._commits), return_exceptions=True)
            await self._dead_hand(session_id)
        finally:
            self._publish(StatusEvent(session_id, "ended", "Live stream ended"))

    async def _observe(
        self,
        session_id: str,
        stream: StreamSession,
        packet: FramePacket,
        source: VideoFileSource | None,
    ) -> None:
        if source is not None:
            stream.ingest(packet)
        analyzer = self._analyzers[session_id]
        stream.hold_from(analyzer.open_window(packet.timestamp_ms) - self._pre_ms)
        try:
            observation = await asyncio.to_thread(self._perception.observe, packet)  # type: ignore[attr-defined]
        except Exception as exc:
            self._publish(ErrorEvent(session_id, f"The vision model failed: {exc}"))
        else:
            await self._index_observation(session_id, observation)
            analyzer.record(observation)
            self._presence[session_id].record(observation)
            self._logs[session_id].append(observation)
            self._publish(ObservationEvent(session_id, observation))
            llm_state = self._summary_sessions.get(session_id)
            if llm_state is not None:
                llm_state.evidence.record(observation)
                keyframe = await asyncio.to_thread(llm_state.keyframes.offer, packet, observation)
                if keyframe is not None:
                    llm_state.evidence.add_keyframe(keyframe)
                    self._maybe_describe(session_id, llm_state, keyframe, observation)
        self._schedule_periods(session_id, packet.timestamp_ms)
        while True:
            window = analyzer.close_ready(packet.timestamp_ms)
            if window is None:
                return
            if analyzer.window_start is not None:
                stream.hold_from(analyzer.window_start - self._pre_ms)
            hold_ms = window.start_ms - self._pre_ms
            if window.observations:
                await self._decide(session_id, stream, window, source, hold_ms)
            else:
                stream.release_hold(hold_ms)

    async def _decide(
        self,
        session_id: str,
        stream: StreamSession,
        window: DecisionWindow,
        source: VideoFileSource | None,
        hold_ms: int,
    ) -> None:
        if source is not None:
            interval = max(1, int(1000 / self._config.max_buffer_fps))
            frames = await asyncio.to_thread(source.window_frames, window.start_ms, window.end_ms, interval)
        else:
            frames = stream.frames_between(window.start_ms, window.end_ms)
        video = await asyncio.to_thread(self._encode, frames) if len(frames) >= 2 else None
        context = window_context(
            self._rules,
            live=self._kinds.get(session_id) is SessionKind.LIVE,
            end_ms=window.end_ms,
            observations=window.observations,
            tracker=self._presence[session_id],
        )
        window = replace(window, video=video if video is not None else window.video, context=context)
        try:
            with metered_session(session_id):
                result = await asyncio.to_thread(self._gate.evaluate, window, self._briefs.get(session_id, ""))  # type: ignore[attr-defined]
        except Exception as exc:
            stream.release_hold(hold_ms)
            self._publish(ErrorEvent(session_id, f"The alert classifier failed: {exc}"))
            return
        self._publish(DecisionEvent(session_id, window.start_ms, window.end_ms, result))
        if not result.worth_reporting:
            stream.release_hold(hold_ms)
            return
        task = asyncio.create_task(self._commit_alert(session_id, stream, window, result, hold_ms))
        self._commits.add(task)
        task.add_done_callback(self._commits.discard)

    async def _commit_alert(
        self,
        session_id: str,
        stream: StreamSession,
        window: DecisionWindow,
        result: GateResult,
        hold_ms: int,
    ) -> None:
        try:
            await self._save_alert(session_id, stream, window, result)
        finally:
            stream.release_hold(hold_ms)

    async def _save_alert(
        self, session_id: str, stream: StreamSession, window: DecisionWindow, result: GateResult
    ) -> None:
        focus = _focus(window)
        evidence = ChunkEvidence(
            label=focus.label,
            summary=focus.summary,
            confidence=focus.confidence,
            event_detected=focus.event_detected,
            alert=True,
            decision_confidence=result.confidence,
            rules_fired=result.fired_rules,
            severity=result.severity,
        )
        debouncer = self._debouncers.setdefault(
            session_id, CommitDebouncer(int(self._config.alert_cooldown_seconds * 1000))
        )
        if not debouncer.try_acquire(ChunkTrigger.ALERT, focus.timestamp_ms):
            self._publish(AlertEvent(session_id, focus, result, debounced=True))
            return
        chunk: ChunkArtifact | None = None
        try:
            chunk = await self._save_clip(
                session_id,
                detection_ms=focus.timestamp_ms,
                trigger=ChunkTrigger.ALERT,
                evidence=evidence,
                stream=stream,
            )
        except ClipDebouncedError:
            self._publish(AlertEvent(session_id, focus, result, debounced=True))
            return
        except Exception as exc:
            self._publish(ErrorEvent(session_id, f"Could not save the alert clip: {exc}"))
        else:
            self._publish(AlertEvent(session_id, focus, result, debounced=False, chunk=chunk))
        await self._note_alert(session_id, stream, window, focus, result, chunk)

    def _encode(self, frames: tuple[FramePacket, ...]) -> bytes | None:
        path = self._config.data_dir / "tmp" / f"window_{frames[0].timestamp_ms}_{frames[-1].timestamp_ms}.mp4"
        try:
            self._writer.encode_mp4(frames, path)
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)

    def _open_session(self, session: Session, stream: StreamSession) -> StreamSession:
        session_id, kind, llm = session.id, session.kind, session.llm
        if self._index is not None:
            self._index.register_session(session_id, kind, session.title, session.watch_brief, session.created_ms)
        self._streams[session_id] = stream
        self._analyzers[session_id] = StreamAnalyzer(session_id, self._window_ms)
        self._presence[session_id] = PresenceTracker()
        self._kinds[session_id] = kind
        self._logs[session_id] = HourlyObservationLog(self._config.session_dir(session_id) / "logs" / "observations")
        self._summary_sessions.pop(session_id, None)
        if llm.enabled:
            self._summary_sessions[session_id] = _SummarySession(
                kind=kind,
                settings=llm,
                scheduler=SummaryScheduler(llm.summary_interval_ms),
                evidence=SessionEvidence(),
                archive=SummaryArchive(self._config.summary_dir(session_id)),
                keyframes=KeyframeStore(self._config.keyframe_dir(session_id)),
            )
        return stream

    async def _index_observation(self, session_id: str, observation: SceneObservation) -> None:
        if self._index is None:
            return
        try:
            await asyncio.to_thread(self._index.record_observation, session_id, observation)
        except Exception as exc:
            self._publish(ErrorEvent(session_id, f"Could not index the reading: {exc}"))

    # ---- LLM summaries (LangGraph) -------------------------------------------------

    def _schedule_periods(self, session_id: str, timestamp_ms: int) -> None:
        llm_state = self._summary_sessions.get(session_id)
        if llm_state is None:
            return
        for start_ms, end_ms in llm_state.scheduler.advance(timestamp_ms):
            observations, alerts = llm_state.evidence.take_period(start_ms, end_ms)
            request = SummaryRequest(
                session_id=session_id,
                session_kind=llm_state.kind,
                kind=SummaryKind.PERIOD,
                start_ms=start_ms,
                end_ms=end_ms,
                watch_brief=self._brief_text(session_id),
                observations=observations,
                alerts=alerts,
            )
            self._spawn_summary(session_id, llm_state, request, llm_state.evidence.keyframes_between(start_ms, end_ms))

    async def _note_alert(
        self,
        session_id: str,
        stream: StreamSession,
        window: DecisionWindow,
        focus: SceneObservation,
        result: GateResult,
        chunk: ChunkArtifact | None,
    ) -> None:
        note = AlertNote(
            window_start_ms=window.start_ms,
            detection_ms=focus.timestamp_ms,
            rule=result.fired_rules[0] if result.fired_rules else "alert",
            severity=result.severity,
            summary=focus.summary,
            location=focus.location,
            classes=focus.class_names,
            chunk_file=chunk.chunk_file if chunk else None,
            seek_offset_sec=chunk.seek_offset_sec if chunk else None,
        )
        if self._index is not None:
            try:
                await asyncio.to_thread(self._index.record_alert, session_id, note, observation_id(session_id, focus))
            except Exception as exc:
                self._publish(ErrorEvent(session_id, f"Could not index the alert: {exc}"))
        llm_state = self._summary_sessions.get(session_id)
        if llm_state is None:
            return
        llm_state.evidence.add_alert(note)
        alert_frames = await asyncio.to_thread(self._keep_alert_frames, llm_state, stream, window, focus)
        for keyframe in alert_frames:
            llm_state.evidence.add_keyframe(keyframe)
        if not llm_state.settings.writes_alert_details:
            return
        request = SummaryRequest(
            session_id=session_id,
            session_kind=llm_state.kind,
            kind=SummaryKind.ALERT,
            start_ms=window.start_ms,
            end_ms=window.end_ms,
            watch_brief=self._brief_text(session_id),
            observations=window.observations,
            alerts=(note,),
            alert_key=note.key,
        )
        self._spawn_summary(session_id, llm_state, request, alert_frames)

    def _spawn_summary(
        self, session_id: str, llm_state: "_SummarySession", request: SummaryRequest, candidates: tuple[Keyframe, ...] = ()
    ) -> None:
        task = asyncio.create_task(self._run_summary(session_id, llm_state, request, candidates))
        llm_state.tasks.add(task)
        task.add_done_callback(llm_state.tasks.discard)

    async def _run_summary(
        self, session_id: str, llm_state: "_SummarySession", request: SummaryRequest, candidates: tuple[Keyframe, ...] = ()
    ) -> None:
        try:
            request = await asyncio.to_thread(self._with_frames, llm_state, request, candidates)
            with metered_session(session_id):
                summary = await asyncio.to_thread(self._summarizer.summarize, request)
            await asyncio.to_thread(llm_state.archive.write, summary)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._publish(ErrorEvent(session_id, f"LLM summary failed: {exc}"))
            return
        if summary.kind is SummaryKind.PERIOD and summary.status == "ok":
            llm_state.evidence.remember_summary(summary.start_ms, summary.text)
        self._publish(SummaryEvent(session_id, summary))

    async def _dead_hand(self, session_id: str) -> None:
        """Final LLM summary: the last work before the session ends. Earlier summaries finish first."""
        llm_state = self._summary_sessions.get(session_id)
        if llm_state is None or llm_state.scheduler.first_ms is None:
            return
        if llm_state.tasks:
            await asyncio.gather(*list(llm_state.tasks), return_exceptions=True)
        self._publish(StatusEvent(session_id, "summarizing", "The LLM is writing the final summary"))
        start_ms = llm_state.scheduler.period_start or llm_state.scheduler.first_ms
        request = SummaryRequest(
            session_id=session_id,
            session_kind=llm_state.kind,
            kind=SummaryKind.FINAL,
            start_ms=llm_state.scheduler.first_ms,
            end_ms=max(llm_state.scheduler.last_ms or start_ms, llm_state.scheduler.first_ms),
            watch_brief=self._brief_text(session_id),
            observations=llm_state.evidence.remaining(),
            alerts=llm_state.evidence.all_alerts(),
            earlier_summaries=llm_state.evidence.earlier_summaries(),
        )
        await self._run_summary(session_id, llm_state, request, llm_state.evidence.all_keyframes())

    def _maybe_describe(
        self, session_id: str, llm_state: "_SummarySession", keyframe: Keyframe, observation: SceneObservation
    ) -> None:
        """Advanced analytics: let the LLM describe people/vehicles in this key frame, one call at a time."""
        if (
            self._describer is None
            or self._index is None
            or not llm_state.settings.describes_entities
            or session_id in self._describing
            or not set(keyframe.classes) & set(DESCRIBED_CLASSES)
        ):
            return
        self._describing.add(session_id)
        task = asyncio.create_task(self._describe(session_id, llm_state, keyframe, observation))
        llm_state.tasks.add(task)
        task.add_done_callback(llm_state.tasks.discard)

    async def _describe(
        self, session_id: str, llm_state: "_SummarySession", keyframe: Keyframe, observation: SceneObservation
    ) -> None:
        try:
            image = await asyncio.to_thread(llm_state.keyframes.base64, keyframe)
            with metered_session(session_id):
                sightings = await asyncio.to_thread(
                    self._describer.describe,  # type: ignore[union-attr]
                    image,
                    observation.summary,
                    observation.class_names,
                    observation.timestamp_ms,
                    observation_id(session_id, observation),
                )
            if sightings:
                await asyncio.to_thread(self._index.record_sightings, session_id, sightings)  # type: ignore[union-attr]
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._publish(ErrorEvent(session_id, f"Advanced analytics could not describe a frame: {exc}"))
        finally:
            self._describing.discard(session_id)

    def _with_frames(
        self, llm_state: "_SummarySession", request: SummaryRequest, candidates: tuple[Keyframe, ...]
    ) -> SummaryRequest:
        """Attach the few frames this summary should see, chosen for the session's watch brief."""
        picked = self._selector.pick(candidates, request.kind, request.watch_brief)
        images: list[str] = []
        kept: list[Keyframe] = []
        for keyframe in picked:
            try:
                images.append(llm_state.keyframes.base64(keyframe))
            except OSError:
                continue
            kept.append(keyframe)
        return replace(request, keyframes=tuple(kept), images=tuple(images))

    @staticmethod
    def _keep_alert_frames(
        llm_state: "_SummarySession", stream: StreamSession, window: DecisionWindow, focus: SceneObservation
    ) -> tuple[Keyframe, ...]:
        """The detection frame and up to two others from the alert window, while they are still held."""
        frames = stream.frames_between(window.start_ms, window.end_ms)
        if not frames:
            return ()
        nearest = min(frames, key=lambda f: abs(f.timestamp_ms - focus.timestamp_ms))
        chosen = [nearest]
        for packet in (frames[0], frames[len(frames) // 2], frames[-1]):
            if len(chosen) < 3 and all(packet.timestamp_ms != c.timestamp_ms for c in chosen):
                chosen.append(packet)
        return tuple(llm_state.keyframes.save(packet, focus, alert=True) for packet in sorted(chosen, key=lambda f: f.timestamp_ms))

    def _brief_text(self, session_id: str) -> str:
        return WatchBrief.resolve(self._briefs.get(session_id)).text

    def _mark(self, session_id: str, status: SessionStatus) -> None:
        try:
            self._set_status(session_id, status)
        except Exception:
            return

    def _publish(self, event: AnalysisEvent, remember: bool = True) -> None:
        """Send to every open page. `remember=False` for readouts not worth replaying (live stats)."""
        if remember:
            recent = self._recent.setdefault(event.session_id, [])
            recent.append(event)
            if len(recent) > _RECENT_LIMIT:
                del recent[:-_RECENT_LIMIT]
        for queue in self._subscribers.get(event.session_id, []):
            queue.put_nowait(event)


@dataclass
class _SummarySession:
    kind: SessionKind
    settings: LlmSettings
    scheduler: SummaryScheduler
    evidence: SessionEvidence
    archive: SummaryArchive
    keyframes: KeyframeStore
    tasks: set[asyncio.Task[None]] = field(default_factory=set)


def _focus(window: DecisionWindow) -> SceneObservation:
    detected = [observation for observation in window.observations if observation.event_detected]
    pool = detected or list(window.observations)
    return max(pool, key=lambda observation: observation.confidence)


def _normalizer(config: AppConfig):
    from drone_security.ingest import FrameNormalizer

    return FrameNormalizer(config.max_frame_width)

