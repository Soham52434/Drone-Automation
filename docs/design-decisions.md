# Design decisions

The main choices behind the prototype: what was decided, why, and what was weighed against it. [architecture.md](architecture.md) describes the system as built.

---

## 1. Split the work across three model roles

**Decision.** A small local vision model reads frames continuously. A hosted alert classifier judges short windows. A hosted LLM writes reports and answers questions.

**Why.** No single model is cheap enough to watch every frame and good enough to judge intent. The local model gives continuous coverage at no per-frame cost. The classifier answers closed questions (alert? which rule? how severe?) with calibrated confidence. The LLM is used where language matters: summaries, chat, and detailed descriptions.

**Alternatives considered.**
- One multimodal LLM on every frame: too slow and expensive, and it sends the whole stream off site.
- Local model only: no notion of intent or of the operator's own rules, and weak descriptions.

**Trade-off.** Short clips and a few still frames leave the site, so this is a hybrid design rather than an air-gapped one.

## 2. One orchestrator, a ring buffer, and no continuous recording

**Decision.**
- Live camera (WebRTC) and uploaded video go through the same pipeline.
- Frames sit in a 15 s in-memory ring buffer, downscaled to ≤640 px and throttled to ≤15 fps.
- Disk writes happen only for alerts and manual clips.

**Why.** Testing uploads exercises the live path too. Memory stays bounded, and the disk holds evidence rather than hours of empty footage.

**Alternatives considered.** Recording continuously and clipping afterwards: simpler, but unbounded storage and more data at rest.

## 3. Always describe the newest frame

**Decision.** When the vision model finishes a frame, it takes whatever frame is current: the newest live frame, or the frame at the wall-clock playhead of an upload. Nothing queues.

**Why.** A fixed stride (say, every 250 ms) on a machine that needs 4 s per frame builds a growing backlog, and the analysis drifts minutes behind the video. Taking the newest frame keeps the system at the live moment, and a faster machine samples more often.

**Making it hold on real footage.** Three things keep the vision model the only bottleneck:
- Uploads are read like a video player: the decoder stays open, and a keyframe index (built from packet headers) lets the playhead jump instead of decoding every frame. Only the sampled frame is converted. On 4K footage this cut a playhead move from up to 25 s to about 0.2 s.
- Decisions run in a background queue, in window order, so encoding a clip and waiting for the classifier never pause the readings.
- The classifier's clip is 5 fps, which is enough to see motion.

## 4. Ten-second decision windows, pinned until the clip is saved

**Decision.**
- The alert classifier sees one window per 10 s of timeline (hard maximum 15 s), with a re-encoded clip plus the window's readings.
- Frames from 8 s before an open window are pinned until its clip is written.
- The alert clip is 8 s before and 2 s after the detection.
- A 10 s debounce stops one event from producing several clips.

**Why.** The vision model can take longer than the ring buffer remembers. Without pinning, the classifier could alert and then find no frames left to save. Short windows bound cost and latency.

**Alternatives considered.** Sending single frames instead of clips: cheaper, but motion and intent (approaching vs passing) are lost.

## 5. A watch brief per session

**Decision.** Each session has an optional brief, such as "only alert when a boat comes near the dock". It becomes the classifier's system prompt. A blank brief means people, vehicles, packages, animals, and hazards.

**Why.** A dock, a gate, and a loading bay need different rules. Putting the operator's intent in the prompt keeps one classifier useful for all of them.

## 6. Predefined time rules beside the classifier

**Decision.** An `apply_time_rules` step after the classifier adds two rules:
- **After hours:** a person or vehicle inside a configurable window (default 22:00–06:00). Uploads use the scene's day/night reading.
- **Loitering:** a person continuously in view for 60 s or more. Gaps under 15 s are tolerated.

Either rule alerts even when the classifier says clear, but only for classes the brief cares about.

**Why.** "Person loitering at midnight" is a rule about time and duration, and a per-window classifier cannot see duration. Deterministic rules are testable and explainable, and they still work without an API key.

## 7. Session setup, and LLM usage as an opt-in

**Decision.** Going live or uploading opens a setup form with these options:
- the watch brief, with examples
- LLM usage yes or no
- the summary interval (1, 5, 10 … 60 minutes)
- detailed alert write-ups (default off)
- advanced analytics (default off)

The alert classifier always runs. When LLM usage is on, the last work of every session is the **dead-hand summary**: earlier summaries finish first, each writer retries once, and then a failure record is stored.

**Why.** A five-minute clip and an overnight watch need different reporting cadences, and some sites should not send anything to an LLM. Asking once, up front, keeps setup controls out of the session view. The dead hand means every session ends with a report, or with a record of why there isn't one.

## 8. Every model call behind a LangGraph

**Decision.** Perception, the alert decision, summaries, chat, and entity descriptions are each a compiled LangGraph.

**Why.**
- One pattern for routing, retries, and failure records.
- `interrupt` gives the chat a clean human-in-the-loop pause.
- Each graph can be tested with fakes.
- One diagram (`langgraph-structure.png`) shows the whole system.

## 9. Summaries see a few key frames, never video

**Decision.** When LLM usage is on, notable readings are saved as small JPEGs (≤512 px). Each summary gets at most 3, 4, or 6 frames (alert, period, final). They are chosen by alert frames first, then classes the brief asks about, then confidence, with at most one per minute. The prompt tells the LLM to trust the frame over the vision model's label when they disagree.

**Why.** The vision model names "a man" but not what he is doing or carrying. A handful of frames adds that depth for a fraction of what video would cost.

## 10. Classes instead of free-text objects

**Decision.** The vision model's object names ("man in a black shirt", "white van") are rolled up into classes: person, vehicle, animal, package, hazard, weapon, and scene classes. Each reading keeps the scene as its location.

**Why.** Search, telemetry, rules, and alerts need a stable vocabulary. Free text is kept alongside for display.

## 11. An embedded graph database for memory

**Decision.** FalkorDBLite (embedded, Cypher) holds `Session → Day → Hour → Minute → Observation`, with edges to classes, alerts, and sightings. Sessions and clips stay in SQLite.

**Why.** Time and class questions become short path queries, and there is no extra server to run.

**Alternatives considered.**
- SQLite tables only: workable, but the time-and-class joins grow awkward as features are added.
- A first embedded graph engine: replaced because of slow per-reading writes and query-parameter limitations. FalkorDBLite writes a reading in about 4 ms.

## 12. Telemetry from class tags, not simulated flight data

**Decision.** Telemetry is the per-class activity report built from what the vision model actually saw: when each class was in view, how often, how strongly, and the tagged log.

**Why.** The brief mentions drone position and altitude, but this prototype has no drone feed. Simulated flight data was tried and dropped: it was not derived from the video and contradicted it (a "side fence" position over an indoor scene). Every number in the class-tag telemetry traces back to a real frame.

**Trade-off.** Drone position and altitude are not modelled. A real dock feed would attach to each reading at the same point the class tags are attached, and would flow into the alert evidence the same way.

## 13. Chat with a human check on uncertain classes

**Decision.** The chat plans a query (classes plus a time span) with the LLM. It pauses for the operator only when a word has no exact class or the plan is not confident. Hourly and daily questions are answered from hour digests and stored summaries. Without LLM usage, a local keyword planner answers.

**Why.** Asking every time is tedious, and never asking makes guesses silently. Pausing only when the mapping is a guess keeps answers trustworthy.

## 14. Advanced analytics as an option

**Decision.** With this setting on, the LLM describes each person, vehicle, animal, or package in new key frames (colour, make, model, kind, clothing), one call at a time per session. Sightings are grouped by an attribute signature, and sightings more than 2 minutes apart count as separate visits.

**Why.** "A blue Ford F150 entered twice today" needs colour, make, and counting across time, which classes alone cannot give. It costs extra requests, so it is opt-in.

**Trade-off.** "Same vehicle" means "matching description". Two identical vehicles count as one.

## 15. Cost is measured, not estimated

**Decision.** Every hosted-model request passes through a metering wrapper. It records the job, the model, the tokens the provider reported, and whether the request failed, in a local ledger. A Cost button beside Ask shows the session's requests, tokens, cost at paid-tier prices, and today's use of each model's free daily limit.

**Why.** Operators and reviewers should see what the system spends. Using the provider's own token counts keeps the number honest, and failed requests are counted because they still use quota.

## 16. Push, not polling

**Decision.** The browser gets readings, decisions, alerts, summaries, buffer stats, and session-list changes as server-sent events.

**Why.** Polling every few seconds creates constant request noise and still lags. One event stream per view is cheaper and immediate.

## 17. Models are configuration

**Decision.** The code refers to roles (vision model, alert classifier, LLM). Model IDs are set in configuration (`DRONE_DECISION_MODEL`, `DRONE_SUMMARY_MODEL`, `DRONE_CHAT_MODEL`). An LLM setting may be a comma-separated chain: earlier models fail over fast and the last one gets full retries.

**Why.** Models change faster than the pipeline. A busy or rate-limited model should not take a summary down with it.

---

## Not built

- Embedding-based triggers to open a decision window early on scene change
- A dead-hand summary when a session is deleted or the server stops mid-session
- Chat history across server restarts (paused questions live in memory)
- Re-identification beyond attribute matching (licence plates, faces)
