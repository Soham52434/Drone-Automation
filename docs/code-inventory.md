# Code inventory

**Last updated:** 2026-11-25  
**Rule:** If it is public and real, it is listed here. Agents must update this file when adding, renaming, or removing classes, data models, or public functions.

## Packages / modules

| Module | Role |
|--------|------|
| `src/drone_security/config.py` | `AppConfig`: data paths, buffer/clip windows, models, time rules, ICE servers |
| `src/drone_security/models/` | Pure data: sessions, frames, clip plans, chunk artifacts |
| `src/drone_security/ingest/` | Frame sources: ring buffer, normalizer, video file reader, WebRTC live feed |
| `src/drone_security/indexing/` | Persistence: chunk writer (mp4 + json), SQLite session store, hourly observation log, summary archive, FalkorDBLite graph index |
| `src/drone_security/perception/` | The local vision model: weight download, `describe`, mapping to `SceneObservation`; `LangGraphPerception` graph |
| `src/drone_security/agent/` | LLM summaries and the day-log chat as LangGraphs; shared LLM helpers |
| `src/drone_security/telemetry/` | Session telemetry built from class tags |
| `src/drone_security/graphs.py` | Builds every LangGraph for inspection; `python -m drone_security.graphs` prints Mermaid |
| `src/drone_security/decisions/` | Alert decision as a LangGraph over the alert classifier, plus time rules |
| `src/drone_security/pipeline/` | Timeline, session lifecycle, sampled analysis, SSE events |
| `src/drone_security/api/schemas.py` | Pydantic request/response schemas |
| `main.py` | FastAPI app, all HTTP routes, error mapping, server entrypoint; routes only call `SessionManager` |
| `web/` | React + Vite frontend (chat-style UI) |

## Data models (classes / dataclasses)

| Name | Module | Fields (summary) | Used by |
|------|--------|------------------|---------|
| `AppConfig` | `config` | `data_dir`, `buffer_seconds`=15, `clip_pre_seconds`=8, `clip_post_seconds`=2, `alert_cooldown_seconds`=10, `max_buffer_fps`=15, `max_frame_width`=640, `ice_servers`, `decision_window_seconds`=10, `decision_clip_fps`=5, `after_hours`=`22:00-06:00`, `loiter_seconds`=60, `time_rules()`, `vision_sample_ms`=250 (test playhead step only; production follows the wall clock), `alert_noul_threshold`=0.6, `decision_model`, `summary_model`, `chat_model` (same default; comma-separated fallback chains allowed), `llm_api_key`, `vision_dir`; paths `db_path`, `usage_path`, `graph_path`, `sessions_dir`, `session_dir()`, `chunk_dir()`, `summary_dir()`, `resolved_vision_dir`; `from_env()` | everything |
| `SceneObservation` | `models.perception` | `timestamp_ms`, `frame_index`, `event_detected`, `label`, `confidence`, `summary`, `raw` (parsed record without masks), `classes`, `scene`; `class_names`, `location` (The vision model's scene), `to_dict()` | vision model, hourly log, the alert classifier, graph index, SSE |
| `ClassHit` | `models.perception` | `name`, `score`, `count`; `to_dict()` | perception graph → everything downstream |
| `TaggedReading`, `ClassActivity`, `SessionTelemetry` | `models.telemetry` | A reading's class tags (+ scene, summary, alert); per-class frames, first/last seen, best/avg score, alerts, presence spans; the session report with the newest-first log | graph → builder → `/telemetry` → Telemetry tab |
| `TimeBucket`, `timeline_label` | `models.index` | Day/hour/minute bucket of a reading (`of(kind, ts, anchor)`); clock or file-position label | graph index, chat, the LLM |
| `ClassCount`, `FrameQuery`, `IndexedFrame`, `FrameQueryResult`, `HourDigest`, `DayLog` | `models.index` | Index query and result shapes | graph index ↔ chat ↔ API |
| `FramePlan`, `Verification`, `VideoClip`, `ChatTurn` | `models.chat` | Planned query (`needs_verification`), human check payload, playable clip, one chat reply (`notice` when the LLM was skipped) | chat graph → API |
| `GateResult` | `models.perception` | `worth_reporting`, `confidence`, `fired_rules`, `severity`, `detail`; `to_dict()` | Decision gate, SSE, chunk evidence |
| `DecisionWindow` | `models.perception` | `session_id`, `start_ms`, `end_ms`, `observations`, `video`, `context`; span must be ≤ 15 s | Analyzer → gate |
| `TimeRules`, `WindowContext`, `ClassDwell`, `RuleHit` | `models.rules` | After-hours window (`is_after_hours`, `parse`), loiter seconds; a window's time of day + continuous presence; a fired rule | pipeline → alert classifier graph |
| `ChunkEvidence` | `models.chunks` | vision model label/summary/confidence plus decision alert/rules/severity; `as_metadata()` | Alert clips |
| `ObservationEvent`, `DecisionEvent`, `AlertEvent`, `StatusEvent`, `ErrorEvent`, `SummaryEvent`, `StatsEvent` | `models.events` | `to_sse()`; status `summarizing` precedes the dead hand; `stats` is the live buffer readout (not replayed) | `SessionAnalysis` → browser |
| `SessionKind` | `models.session` | `LIVE`, `UPLOAD` | store, manager, API |
| `SessionStatus` | `models.session` | `IDLE`, `STREAMING`, `READY`, `ENDED` | store, manager, API |
| `WatchBrief` | `models.session` | `text`; `resolve(text)` (blank → default person/vehicle/package/animal/hazard brief); `system_prompt()` | session create, the alert classifier |
| `Session` | `models.session` | `id`, `kind`, `title`, `status`, `created_ms`, `source_file`, `duration_ms`, `watch_brief`, `llm` | store, manager, API, the alert classifier |
| `UsageRecord`, `CostLine`, `ModelQuota`, `SessionCost`, `ModelPrice`, `PRICES`, `usd`, `build_session_cost` | `models.cost` | One metered request; totals per job/model; free-tier use today; paid-tier price table; cost builder | ledger → `/cost` |
| `MeteredModel`, `UsageMeter`, `metered_session`, `metered` | `agent.metering` | Wraps any model's `invoke`, reads tokens from the reply, records to the ledger under the current session | builders in `main.py` |
| `UsageLedger` | `indexing.usage_ledger` | `record`, `records(session_id)`, `requests_today(now_ms)` (Pacific day), `close`. SQLite `data/usage.sqlite3` | `SessionManager.cost` |
| `EntitySighting`, `Visit`, `EntityMatch`, `group_visits` | `models.entities` | An LLM-described entity (class, description, colour, make, model, kind, clothing; `signature`); a visit; a matched entity with its visits; split sightings into visits (2 min gap) | describer → graph → chat |
| `LlmSettings`, `SUMMARY_INTERVAL_CHOICES` | `models.session` | `enabled`, `summary_interval_minutes` (1, 5 … 60), `detailed_alerts`; `summary_interval_ms`, `writes_alert_details` | setup form → store → analysis |
| `SummaryKind` | `models.summaries` | `ALERT`, `PERIOD`, `FINAL` | Summary graph, archive, API |
| `AlertNote` | `models.summaries` | `window_start_ms`, `detection_ms`, `rule`, `severity`, `summary`, `chunk_file`, `seek_offset_sec`, `location`, `classes`; `key` (= UI incident key) | analysis → LLM, graph index |
| `Keyframe` | `models.summaries` | `timestamp_ms`, `file_name`, `classes`, `location`, `summary`, `alert`, `confidence` | keyframe store → selector → LLM |
| `EvidenceRef` | `models.summaries` | `at_ms`, `label`, `note`, `chunk_file`, `seek_offset_sec` | LLM summaries |
| `SummaryRequest` | `models.summaries` | session, kind, span, watch brief, observations, alerts, earlier summaries, `alert_key`, `keyframes`, `images` (base64 JPEG, same order); `is_quiet` | analysis → LLM graph |
| `LlmSummary` | `models.summaries` | kind, span, `status` (`ok`/`quiet`/`failed`), `text`, `model`, `attempts`, `evidence`, `alert_key`, `frames` (keyframes seen); `file_name`, `to_dict`, `from_dict` | Summary graph → archive → API/SSE |
| `FramePacket` | `models.frames` | `timestamp_ms`, `frame_index`, `image` (RGB ndarray); `width`, `height` | ingest, pipeline, writer |
| `BufferStats` | `models.frames` | `frames_received`, `frames_buffered`, `buffered_seconds`, `latest_timestamp_ms` | `StreamSession`, API |
| `VideoInfo` | `models.frames` | `duration_ms` (header), `width`, `height`, `fps`, `playable_ms` (last packet actually in the file), `truncated` | `VideoFileSource` |
| `ChunkTrigger` | `models.chunks` | `MANUAL`, `ALERT` | pipeline, writer, store |
| `ClipPlan` | `models.chunks` | `session_id`, `trigger`, `detection_ms`, `frames`; `start_ms`, `end_ms` | `StreamSession` → `ChunkWriter` |
| `ChunkArtifact` | `models.chunks` | `session_id`, `chunk_file`, `metadata_file`, `chunk_start_ms`, `chunk_end_ms`, `detection_ms`, `frame_count`, `fps`, `trigger`, `created_ms`; `seek_offset_sec`, `duration_sec`, `to_metadata()` | writer, store, API |
| `SdpMessage` | `ingest.webrtc` | `sdp`, `type` | `LiveFeed`, manager, API |

## Services / classes

| Name | Module | Public methods | Notes |
|------|--------|----------------|-------|
| `RingBuffer` | `ingest.ring_buffer` | `push`, `window(start_ms, end_ms)`, `clear`, `latest_timestamp_ms`, `buffered_seconds`, `__len__` | Time-based eviction, thread-safe |
| `FrameNormalizer` | `ingest.frame_normalizer` | `target_size(w, h)`, `normalize(frame, ts, index)` | RGB, even dims, max width |
| `VideoFileSource` | `ingest.video_file` | `probe() -> VideoInfo`, `frames(start_ms, end_ms, min_interval_ms=0)`, `frame_at(media_ms)`, `playback() -> PlaybackReader`, `window_frames(start, end, min_interval_ms)` | Frames are thinned before conversion; multithreaded decoding |
| `PlaybackReader` | `ingest.video_file` | `frame_at(media_ms)`, `close()`; context manager | `exhausted` once the data runs out. Forward reader for a moving playhead: decoder stays open, keyframe index (packet headers) lets it jump instead of decoding everything, only the returned frame is converted |
| `LiveFeed` | `ingest.webrtc` | `connect(offer) -> SdpMessage`, `close()` | aiortc peer; idempotent close; calls `on_ended` once |
| `ChunkWriter` | `indexing.chunk_writer` | `write(plan, out_dir) -> ChunkArtifact`, `encode_mp4(frames, path)` | H.264 mp4 (ms timebase, faststart) + paired json; `_2`, `_3` suffix on name collision. `encode_mp4` is the decision-window clip and writes no sidecar |
| `SessionStore` | `indexing.session_store` | `on_change(listener)`, `create(..., watch_brief=None, llm=None)`, `get`, `list_sessions`, `update`, `set_status`, `delete`, `add_chunk`, `list_chunks`, `close` | SQLite, chunks cascade on delete; adds `watch_brief` and LLM columns on older databases |
| `CommitDebouncer` | `pipeline.stream_session` | `try_acquire(trigger, detection_ms)` | ALERT cooldown; MANUAL always passes |
| `StreamSession` | `pipeline.stream_session` | `ingest(packet) -> bool`, `hold_from(start_ms)`, `release_hold(start_ms)`, `plan_clip(trigger, detection_ms)`, `frames_between(start, end)`, `has_post_roll`, `post_roll_ms`, `latest_timestamp_ms`, `stats()` | 15 s ring plus a pin for the open alert timeframe. Clip = detection −8 s / +2 s |
| `StreamAnalyzer` | `pipeline.analyzer` | `open_window(timestamp_ms)`, `record(observation)`, `close_ready(timestamp_ms)`, `close_remaining(end_ms)` (the window open at the end), `window_start` | Closes a 10 s window from the frames the vision model actually saw |
| `LatestFrame` | `pipeline.latest_frame` | `offer(packet)`, `stop()`, `stopped`, `next_unseen()` | Live camera: only the newest frame is inferred |
| `WallClock`, `StepClock` | `pipeline.playhead` | `now_ms()`; `StepClock.advance()` | Upload playhead. Wall clock in production; fixed jumps in tests |
| `SessionAnalysis` | `pipeline.analysis` | `bind_live(session, stream)`, `finish_live`, `iter_events`, `cancel`, `shutdown` | The next vision-model frame is the live/playhead frame when inference finishes; publishes SSE. Attaches telemetry, writes every reading and alert to the graph index. With LLM on: period summaries in the background, alert write-ups, dead-hand final summary last. Decisions run in a per-session background queue (in window order) so perception never waits; the window open at the end is judged; disk write errors are reported, not fatal; low-disk warning at start |
| `SessionChangeFeed` | `pipeline.session_changes` | `notify()` (any thread), `subscribe()` → "changed" / "ping", `close()`, `subscribers` | Pushes session-list changes; bursts coalesce; 25 s keep-alive |
| `PresenceTracker`, `window_context`, `scene_daypart` | `pipeline.presence` | `record`, `dwell(at_ms)`; build a window's context (clock for live, the scene reading for uploads) | Time rules |
| `SummaryScheduler` | `pipeline.summary_schedule` | `advance(timestamp_ms) -> closed periods`, `first_ms`, `last_ms`, `period_start` | Every N minutes from the first frame |
| `SessionEvidence` | `pipeline.summary_schedule` | `record`, `add_alert`, `take_period`, `remaining`, `all_alerts`, `add_keyframe`, `keyframes_between`, `all_keyframes`, `remember_summary`, `earlier_summaries` | What the LLM may read and see |
| `SessionManager` | `pipeline.session_manager` | `list_sessions`, `get_session`, `list_chunks`, `create_live(title, watch_brief, llm)`, `create_upload(filename, data, watch_brief, llm)`, `list_summaries`, `index_classes`, `day_log`, `telemetry`, `ask`, `verify_classes`, `session_changes`, `changes`, `start_live`, `stop_live`, `live_stats`, `save_clip(..., stream=None)`, `iter_events`, `delete_session`, `source_path`, `chunk_path`, `shutdown`, `vision_loaded` | Owns live feeds; passes the session brief into analysis. An alert passes its own `StreamSession` to `save_clip`, so its clip still saves after the feed stops |
| `VisionModel` | `perception.vision_model` | `load()`, `describe(packet)`, `observe(packet) -> SceneObservation`, `loaded` | Vendor SDK, local weights; no masks |
| `LangGraphPerception` | `perception.graph` | `observe(packet)`, `loaded`, `graph` | LangGraph `describe → map_observation → classify_objects | reject`; production wraps the vision model in it |
| `ObjectClassifier`, `CLASS_WORDS`, `ALL_CLASSES`, `classes_named_in` | `perception.classes` | `class_of(name)`, `classify(objects) -> tuple[ClassHit]`; classes a text names | vision model object names → classes; watch brief → classes |
| `ClassTelemetryBuilder` | `telemetry.report` | `build(readings) -> SessionTelemetry` | Spans break on a missing tag or a > 15 s gap; log keeps the newest 500 |
| `GraphIndex` | `indexing.graph_index` | `register_session`, `record_observation -> id`, `record_alert(note, raised_by)`, `record_sightings`, `sightings`, `delete_session`, `tagged_readings`, `classes`, `find_frames(query)`, `day_log`, `close` | FalkorDBLite (embedded FalkorDB, Cypher), `data/graph.db`. One query per reading; `close` saves then stops the server |
| `LangGraphEntityDescriber`, `DESCRIBED_CLASSES` | `agent.entity_graph` | `describe(image, vision_summary, classes, ts, observation_id) -> tuple[EntitySighting]`, `graph` | Advanced analytics as a LangGraph: `describe_entities → normalize` |
| `LangGraphChat` | `agent.chat_graph` | `ask(session, question) -> ChatTurn`, `verify(thread_id, classes)`, `graph` | `route → plan_frame_query → [verify_classes: interrupt] → query_frames`; `route → answer_summary`; `route → search_sightings` (advanced analytics). In-memory checkpointer |
| `KeyframeStore`, `NOTABLE_CLASSES` | `indexing.keyframe_store` | `worth_keeping`, `offer(packet, observation)`, `save(packet, observation, alert)`, `path`, `base64` | Small JPEGs of notable readings and alert frames, `sessions/<id>/keyframes/` |
| `KeyframeSelector`, `FRAME_LIMITS` | `agent.keyframes` | `pick(keyframes, kind, watch_brief)`, `brief_classes(brief)` | Alert → watch-brief class → confidence; one per minute per class set; 3 / 4 / 6 frames |
| `SummaryArchive` | `indexing.summary_archive` | `write(summary) -> Path`, `list()` | `sessions/<id>/logs/summaries/*.summary.json`; final sorts last |
| `LangGraphSummarizer` | `agent.summary_graph` | `summarize(request) -> LlmSummary`, `available`, `graph` | LangGraph `gather → quiet | unavailable | write_alert_detail | write_period_summary | write_final_summary → finalize | retry once | record_failure` |
| `HourlyObservationLog` | `indexing.hourly_log` | `append(observation, recorded_ms=None) -> Path` | `logs/observations/<UTC hour>.json` |
| `LangGraphDecisionGate` | `decisions.graph` | `evaluate(window, watch_brief=None) -> GateResult`, `graph`; LangGraph `classify → apply_time_rules → alert | clear` | System message is the session brief; classify → alert or clear |

## Errors

| Name | Module | HTTP status |
|------|--------|-------------|
| `SessionNotFoundError` | `indexing.session_store` | 404 |
| `InvalidSessionStateError` | `pipeline.session_manager` | 409 |
| `ClipUnavailableError` | `pipeline.stream_session` | 409 |
| `ClipDebouncedError` | `pipeline.session_manager` | 429 |
| `VideoFileError` | `ingest.video_file` | 400 |
| `VisionRejectedError` | `perception.graph` | — (reported as an SSE error) |

## Public functions (module-level)

| Name | Module | Signature | Notes |
|------|--------|-----------|-------|
| `create_app` | `main` (repo root) | `(config=None, web_dist=None, *, load_models=False, perception=None, gate=None, playback_pace=True, summarizer=None, chat_llm=None, describer=None, usage=None) -> FastAPI` | `load_models=True` loads the vision model inside `LangGraphPerception` and builds the alert gate, summarizer, chat model and entity describer, each metered into the usage ledger |
| `main` | `main` (repo root) | `() -> None` | Loads `.env`, then starts with `load_models=True` |
| `scene_observation_from_vision` | `perception.mapping` | `(payload, timestamp_ms, frame_index) -> SceneObservation` | Edge mapping only |
| `ensure_vision_weights` | `perception.vision_model` | `(directory) -> Path` | Saves the vision-model weights locally |
| `load_vision_model` | `perception.vision_model` | `(directory) -> VisionModel` | Download if needed, then `load()` |
| `build_decision_gate` | `decisions.graph` | `(api_key, model, threshold) -> LangGraphDecisionGate` | No key → gate that never alerts |
| `build_summarizer` | `agent.summary_graph` | `(api_key, model) -> LangGraphSummarizer` | No key → records why |
| `build_llm`, `model_chain`, `answered_by`, `response_text`, `parse_json_object`, `ChatModel` | `agent.llm` | `(api_key, 'a,b')` → model with fallbacks (earlier models: no retry, 30 s); split a chain; model that actually replied; reply text; first JSON object | the LLM + chat graphs |
| `observation_id` | `indexing.graph_index` | `(session_id, observation) -> str` | Graph node id of a reading |
| `build_graphs`, `langgraph_mermaid` | `graphs` | `() -> dict[name, CompiledStateGraph]`, `() -> dict[name, str]` | Source of `langgraph-structure.png` |
| `router` | `main` (repo root) | `APIRouter` (prefix `/api`) | All HTTP routes below |

## HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness; `vision_loaded` |
| GET | `/api/sessions/{id}/events` | Server-Sent Events: `observation`, `decision`, `alert`, `status`, `error`, `summary`, `stats` (live, 1/s). Opening an uploaded session starts playback |
| GET | `/api/sessions/stream` | Server-Sent Events: `sessions` (full list) on connect and on every create / status change / delete; `: ping` every 25 s. Replaces polling |
| GET | `/api/sessions` | List sessions, newest first |
| POST | `/api/sessions/live` | Create live session (`{title?, watch_brief?, llm?: {enabled, summary_interval_minutes, detailed_alerts}}`) |
| POST | `/api/sessions/upload` | Multipart video upload (`file`, optional `watch_brief`, `llm_enabled`, `summary_interval_minutes`, `detailed_alerts`) → ready session; 422 for an interval off the slider |
| GET | `/api/sessions/{id}/summaries` | LLM summaries for the session, final last |
| GET | `/api/sessions/{id}/keyframes/{file}` | A keyframe JPEG the LLM looked at |
| GET | `/api/sessions/{id}/index/classes` | Unique classes with frame and alert counts |
| GET | `/api/sessions/{id}/telemetry` | Telemetry from class tags: per-class activity and spans, the tagged log (newest 500) |
| GET | `/api/sessions/{id}/cost` | Model requests and tokens by job and model, cost at paid-tier prices, free-tier use today per model |
| GET | `/api/sessions/{id}/index/daylog` | Hour digests: readings, alerts, classes |
| POST | `/api/sessions/{id}/chat` | `{question}` → chat turn (answered, or `needs_verification` with classes to confirm) |
| POST | `/api/sessions/{id}/chat/{thread_id}/verify` | `{classes}` → resume the paused query; 409 if nothing is paused |
| GET | `/api/sessions/{id}` | Session + chunks |
| DELETE | `/api/sessions/{id}` | Delete session, files, and live feed |
| POST | `/api/sessions/{id}/webrtc/offer` | SDP offer → answer; starts live ingest |
| POST | `/api/sessions/{id}/live/stop` | Stop live feed → ended |
| GET | `/api/sessions/{id}/live/stats` | Ring buffer stats (the UI gets them pushed as `stats` events instead) |
| POST | `/api/sessions/{id}/chunks` | Save clip (`{detection_ms?}`; required for uploads) |
| GET | `/api/sessions/{id}/source` | Uploaded video (range requests) |
| GET | `/api/sessions/{id}/chunks/{file}` | Chunk mp4 / json |

## Frontend (`web/src`)

| Name | File | Role |
|------|------|------|
| `ApiClient`, `ApiError`, `api` | `api/client.ts` | Typed fetch wrapper for the HTTP API; `createLiveSession({setup})`, `uploadVideo(file, setup)`, `listSummaries`, `telemetry`, `indexClasses`, `askChat`, `verifyChat` (no polling methods) |
| `SUMMARY_INTERVALS`, `SessionSetup`, `LlmSettings`, `DEFAULT_LLM`, `WATCH_EXAMPLES`, `intervalAt`, `intervalIndex`, `formatInterval`, `formatIntervalShort`, `llmPayload` | `lib/sessionSetup.ts` | Setup form data and slider stops |
| Types `Session`, `SessionLlm`, `Chunk`, `SessionDetail`, `LiveStats`, `Summary`, `SummaryEvidence`, `ClassHit`, `ClassCount`, `HourDigest`, `IndexedFrame`, `ChatTurn`, `FramePlan`, `ChatClip`, `SessionTelemetry`, `ClassActivity`, `TaggedReading` | `api/types.ts` | Mirror backend schemas |
| `LiveConnection` | `live/liveConnection.ts` | Send-only WebRTC camera stream; `start`, `subscribe`, `close` |
| `LiveRegistry` | `live/liveConnection.ts` | Keeps live connections alive across session switches |
| `waitForIceGathering`, `CAMERA_CONSTRAINTS` | `live/liveConnection.ts` | Non-trickle ICE helper; camera request |
| `formatMediaTime`, `formatClockTime`, `formatTimeline`, `describeChunk`, `chunkPlaybackUrl` | `lib/format.ts` | Display helpers |
| `groupSessions` | `lib/sessionGroups.ts` | Today / Yesterday / Previous 7 days / Older |
| `analysisEntry`, `alertRecords`, `openAlertCount`, `alertWriteUp`, `ruleLabel` | `lib/analysisFeed.ts` | SSE rows with classes and location; incidents with a stable `key` and `clip` state; LLM write-up for an alert; rule names |
| `groupFramesByHour` | `lib/chat.ts` | Chat results as hour → minute groups |
| `formatDuration`, `matchesClasses` | `lib/telemetry.ts` | Telemetry tab helpers |
| `AnalysisEntry`, `AlertRecord`, `ClipState` | `lib/analysisFeed.ts` | Feed row; incident (alert-classifier alert merged with its clip); `saving` / `saved` / `failed` / `cooldown` |
| `SessionFeedHub` | `lib/feedHub.ts` | One SSE connection per watched session (selected + streaming); `sync`, `entries`, `stats`, `isReplaying`, `subscribe`, `close`, `closeAll` |
| `SessionListStream`, `parseSessions` | `lib/sessionStream.ts` | Pushed session list for the sidebar (replaces 5 s polling) |
| `AlertWatcher` | `lib/alertWatcher.ts` | `update(sessionId, records, replaying)` returns only new incidents, so replayed history never pops up |
| `PreferenceStore`, `AlertPreferences`, `AckStore`, `MemoryStorage`, `browserStorage` | `lib/preferences.ts` | Alert settings (pop-ups, sound, desktop); acknowledged incident keys per session |
| `App` | `App.tsx` | Sessions (pushed, not polled), go live, upload, stop, delete; owns the feed hub, alert pop-up queue, acknowledgements, chime, desktop notifications, tab-title count |
| `Sidebar`, `SettingsMenu` | `components/` | Session list with search, open-alert badges, delete confirm (a drawer below 1100 px); alert settings panel |
| `NewSession` | `components/NewSession.tsx` | Two choices (Go live / Upload) and drop overlay; each opens the setup form |
| `SessionSetupDialog` | `components/SessionSetupDialog.tsx` | File pick, watch brief + examples, LLM Yes/No, summary interval stop-slider, alert write-up toggle |
| `SessionView` | `components/SessionView.tsx` | Header (status, watch state, open incidents), error banner, stage, incidents, detections, evidence dialog |
| `LiveStage`, `UploadStage`, `StageFrame` | `components/` | Video stage with badges, fullscreen, vision reading with classes and location, controls; ended-live summary |
| `CostButton` | `components/CostButton.tsx` | Beside Ask: running cost on the button; panel with requests, tokens, per-job table, free-tier meters (refreshes with session activity, at most every 5 s) |
| `formatUsd`, `formatTokens`, `quotaShare`, `costBadge` | `lib/cost.ts` | Cost panel formatting |
| `TelemetryPanel` | `components/TelemetryPanel.tsx` | Telemetry tab: tiles, class presence track, per-class table, class-filtered tagged log |
| `PresenceTrack` | `components/charts/PresenceTrack.tsx` | One row per class, one segment per span; hover/focus readout |
| `ClassChips`, `classIcon`, `keyClassesFirst`, `CLASS_ICONS`, `KEY_CLASSES` | `components/ClassChips.tsx` | Class chips with icons; security classes highlighted |
| `ChatPanel` | `components/ChatPanel.tsx` | Day-log chat drawer: class picks, verification card, hour/minute results with video, hourly table |
| `AlertPopups` | `components/AlertPopups.tsx` | On-screen alert cards: rule, severity, location, classes, vision reading, LLM write-up when enabled, clip preview, Acknowledge / Review |
| `EvidenceDialog` | `components/EvidenceDialog.tsx` | Incident clip + facts, LLM alert write-up, prev/next, acknowledge, download; keyboard shortcuts |
| `IncidentPanel`, `ChunkMessage` | `components/` | Incident list with filters; manual clips |
| `InsightPanel` | `components/InsightPanel.tsx` | Tabs: The vision model detections / LLM summaries / Telemetry |
| `SummaryList`, `SummaryCard` | `components/SummaryList.tsx` | Period + final summaries with the key frames the LLM saw and evidence clip links |
| `ruleIcon`, `RuleBadge`, `CLIP_LABELS`, `severityLabel` | `components/icons.tsx` | Rule → lucide icon, severity styling |

## Entrypoints

| Command | Purpose |
|---------|---------|
| `uv run python main.py` | API + built UI on `http://127.0.0.1:8000` |
| `cd web && npm run dev` | Frontend dev server on `:5173`, proxies `/api` to `:8000` |
| `cd web && npm run build` | Typecheck + production bundle to `web/dist` |

## Test modules

| File | Covers |
|------|--------|
| `tests/test_models_and_config.py` | Seek offset, metadata, config window limits, env parsing |
| `tests/test_ring_buffer.py` | Eviction, window, ordering |
| `tests/test_frame_normalizer.py` | Resize and RGB conversion |
| `tests/test_stream_session.py` | Throttle, clip window, debounce, post-roll |
| `tests/test_chunk_writer.py` | mp4 + json pairing, timing, name collisions |
| `tests/test_session_store.py` | CRUD, ordering, cascade |
| `tests/test_video_file.py` | Probe, ranged frames, invalid file, `frame_at` |
| `tests/test_session_manager.py` | Upload lifecycle, clip saving (incl. alert clip after the feed stops), rollback, traversal guard, restart cleanup |
| `tests/test_live_webrtc.py` | Real aiortc loopback: stream → buffer → clip → stop |
| `tests/test_api.py` | HTTP endpoints, .MOV upload served as MP4, range requests, error codes, LLM settings validation, summaries endpoint |
| `tests/test_perception_mapping.py` | Vision-model JSON → `SceneObservation`, including a quiet frame |
| `tests/test_vision_model.py` | Describe options; observe before load fails |
| `tests/test_decision_graph.py` | Alert, clear, `none` rule, missing API key, video block |
| `tests/test_stream_analyzer.py` | 10 s decision window |
| `tests/test_latest_frame.py` | Live slot keeps only the newest frame |
| `tests/test_hourly_log.py` | Hour file append |
| `tests/test_analysis_stream.py` | Upload playback SSE: alert clip, quiet window, cooldown; readings indexed with classes, scene, and the alert; LLM on → period, alert, and final summaries with the dead hand last; LLM off → no LLM calls |
| `tests/test_summary_graph.py` | Summary graph: evidence citations, writer per job, retry once, failure record, quiet skip, no key |
| `tests/test_perception_graph.py` | Perception graph: describe → map, reject a malformed payload |
| `tests/test_summary_schedule.py` | Scheduler periods, evidence hand-off, slider-stop validation, store round-trip, archive |
| `tests/test_graphs.py` | Every model feature is a LangGraph (perception, decision, summaries, chat, entities); Mermaid output |
| `tests/test_classes.py` | Object → class mapping; perception graph classes and scene; location is the scene; alert-classifier evidence carries scene and classes only |
| `tests/test_session_changes.py` | Change feed: snapshot tick, cross-thread notify, burst coalescing, keep-alive, close; store change hook; stream route snapshot |
| `tests/test_live_stats_push.py` | Live stats pushed as events, never replayed; ticker stops on shutdown |
| `tests/test_assignment_examples.py` | The brief's examples: alert triggered at midnight, person loitering (unit + end to end), truck logged correctly; rule wrap-around, brief scoping, presence gaps, upload night from the scene, evidence text |
| `tests/test_playback.py` | Cut-off files detected and rejected at upload with a clear message; forward reader matches fresh seeks, repeat reads, keyframe jumps, thinned decision clip, last window judged at the end, slow decisions do not stall readings, a full disk does not stop the session |
| `tests/test_cost.py` | Prices, metering (tokens, failures, session), classifier usage, totals by job/model with quotas, Pacific-day reset, `/cost` route end to end with attribution |
| `tests/test_advanced_analytics.py` | Visits and signatures, describer normalisation and failure, sightings in graph and telemetry log, "blue F150 entered twice" via LLM and word match, option off routes to frame search, end-to-end describing on an upload |
| `tests/test_llm.py` | Model chains, single vs fallback client, which model answered, busy first model hands over |
| `tests/test_telemetry_report.py` | Class activity: counts, scores, alerts, spans with gaps; capped newest-first log; graph tagged readings; `/telemetry` endpoint |
| `tests/test_keyframes.py` | Keyframe keep/throttle/downscale, alert frames, name validation; selector ranking and spread; the LLM gets labelled images; plain text without frames |
| `tests/test_graph_index.py` | Time buckets, class/time queries, alerts on readings, hour digests, per-session delete, JSON-looking text, close and reopen |
| `tests/test_chat_graph.py` | Direct answers, human-in-the-loop pause/resume, upload time windows, alerts filter, LLM planner + fallback notice, LLM off, hourly summary, chat API |
| `web/src/**/*.test.ts` | API client, ICE wait, live registry, formatting, sidebar grouping, incident records, feed hub, alert watcher, preferences, session setup, telemetry, cost formatting |

## Intentionally not built yet

- Dead-hand summary when a session is deleted or the server shuts down mid-session
- Chat history across server restarts (paused questions live in memory)
- Continuous processing of uploaded videos (uploads are clipped on demand)
