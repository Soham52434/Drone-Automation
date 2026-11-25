# Architecture

An on-site security analyst for a docked drone that watches one property. It takes a live camera feed or an uploaded video, describes what it sees, decides when something is worth an alert, keeps the evidence, and answers questions about the day.

## Three model roles

| Role | Where it runs | What it does | How often |
|------|---------------|--------------|-----------|
| **Vision model** | Locally, on the dock | Describes one frame: objects with scores, the scene, a short reasoning | As fast as the machine allows, always on the newest frame |
| **Alert classifier** | Hosted API | Answers closed questions on a 10 s window: alert? which rule? how severe? | Once per window |
| **Language model (LLM)** | Hosted API | Writes summaries, answers the chat, optionally describes people and vehicles | A few calls per session, only when LLM usage is on |

The vision model is cheap and continuous but shallow and has no memory across frames. The application supplies the timeline. The alert classifier sees short clips, never the full stream. The LLM sees a text log and a few still frames, never video.

## End-to-end flow

```
Live camera (WebRTC)  or  uploaded video
        │
        ▼
Ring buffer (15 s, in memory, ≤640 px, ≤15 fps)   ← no continuous recording
        │  newest frame when the vision model is free
        ▼
Vision model (local) ──► perception graph: describe → map_observation → classify_objects
        │                 reading = objects → classes (person, vehicle, …) + scene
        ├──► hourly JSON log      sessions/<id>/logs/observations/<hour>.json
        ├──► graph index          Session → Day → Hour → Minute → Observation
        ├──► key frames           (LLM on) a few JPEGs of notable readings
        │
        ▼ every 10 s of timeline (hard max 15 s)
Decision window: re-encoded clip + the window's readings + time of day + who is lingering
        │
        ▼
Alert graph: classify (alert classifier) → apply_time_rules (after hours, loitering) → alert | clear
        │
   clear ─► logged only
        │
   alert ─► pop-up in the browser (at once)
            alert clip: 8 s before + 2 s after the detection → chunk_<start>.mp4 + .json (seek offset)
            10 s debounce so one event makes one clip
            optional LLM alert write-up (session setting)
        │
        ▼ (LLM usage on)
Summary graph: period summary every N minutes · dead-hand final summary as the last work of the session
```

## Components

| Package | Responsibility |
|---------|----------------|
| `ingest/` | Frame sources: WebRTC live track (aiortc), video file reader, ring buffer, frame normalizer |
| `perception/` | Vision-model adapter (weights downloaded once), payload → `SceneObservation`, object → class mapping, perception graph |
| `decisions/` | Alert graph over the alert classifier, plus the predefined time rules |
| `pipeline/` | Session lifecycle, sampling loop, decision windows, presence (dwell) tracking, summary scheduling, server-sent events |
| `indexing/` | SQLite session store, chunk writer (mp4 + json), hourly logs, summary archive, key frames, graph index, usage ledger |
| `agent/` | LLM graphs: summaries, chat, entity descriptions; model builder with fallback chains; usage metering |
| `telemetry/` | Per-class activity report built from the class tags |
| `main.py` | FastAPI app. Every route calls one `SessionManager` method and maps the result to a schema |
| `web/` | React + Vite + TypeScript single-page UI |

## The five LangGraphs

Every model call goes through a LangGraph, so routing, retries, and failure records have one shape. `uv run python -m drone_security.graphs` prints them as Mermaid; `langgraph-structure.png` is drawn from that output.

| Graph | Nodes |
|-------|-------|
| Perception | `describe → map_observation → classify_objects`, or `reject` a malformed payload |
| Alert decision | `classify → apply_time_rules → accept_alert \| reject` |
| Summaries | `gather → quiet \| unavailable \| write_alert_detail \| write_period_summary \| write_final_summary`, each writer `→ finalize \| retry \| record_failure` |
| Chat | `route → plan_frame_query → [verify_classes, human in the loop] → query_frames`; `route → answer_summary`; `route → search_sightings` |
| Entity descriptions | `describe_entities → normalize` |

## Alert decision

- **Input:** a re-encoded clip of the window (when under 15 MB) and a text block with every reading in the window, the local time (live) or the scene's time of day (uploads), and how long each class has been continuously in view.
- **Watch brief:** each session has an optional brief, such as "only boats near the dock". It is the classifier's system prompt, so alerts follow the use case. A blank brief means people, vehicles, packages, animals, and hazards.
- **Classifier questions:** alert yes/no with a confidence, the rule (person, vehicle, package, animal, hazard, loitering, after hours, brief match, none), and the severity.
- **Time rules:** these alert on their own, even when the classifier says clear, but only for classes the brief cares about:
  - *After hours:* a person (critical) or vehicle (warning) seen inside `DRONE_AFTER_HOURS` (default 22:00–06:00). Uploads have no clock, so they use the scene's own day/night reading.
  - *Loitering:* a person continuously in view for at least `DRONE_LOITER_SECONDS` (default 60 s). Gaps under 15 s, when the vision model misses someone for a frame or two, do not reset the count. The alert is critical when it is also after hours.

## Memory: the graph index

An embedded graph database (FalkorDBLite, Cypher) stores every reading:

```
Session -HAS_DAY-> Day -HAS_HOUR-> Hour -HAS_MINUTE-> Minute -HAS_OBSERVATION-> Observation
Observation -SEEN {score, count}-> ObjectClass
Observation -RAISED-> Alert {rule, severity, chunk_file, seek}
Observation -DESCRIBED-> Sighting {description, colour, make, model, signature}   (advanced analytics)
```

"What happened at 14:00" is one path match down the time tree, and "all vehicle events" is one more hop. Live sessions bucket by local clock time. Uploads bucket by position in the file.

## LLM features (when the session turns LLM usage on)

- **Period summaries** every N minutes (1, 5, 10 … 60, chosen at setup), with timestamps that cite clips and seek offsets.
- **Dead-hand summary:** when the video or live feed ends, earlier summaries finish first and the final summary is the last work before the session is marked ended. Each writer retries once, then a failure record is stored.
- **Alert write-ups** (optional): a richer description after each alert. The pop-up never waits for it.
- **Key frames:** each summary gets at most 3, 4, or 6 frames (alert, period, final). They are ranked by alert frames first, then classes the brief asks about, then confidence, with at most one per minute.
- **Chat:** "show all vehicle events between 14:00 and 15:00", "summarize each hour". When a word does not map cleanly to a class, the graph pauses with a LangGraph `interrupt` and asks the operator to confirm the classes.
- **Advanced analytics** (optional): the LLM describes each person, vehicle, animal, or package in new key frames, recording colour, make, model, kind, and clothing. Sightings with the same attributes are grouped, and sightings more than 2 minutes apart count as separate visits. This answers "how many times did the blue Ford F150 come by?".

Without LLM usage, the chat still works: a local keyword planner and the hourly digests answer instead.

## Telemetry and cost

- **Telemetry** is built from the class tags on every reading. For each class it records readings, first and last seen, best and average score, alerts, and the spans when it was in view. It also keeps a filterable log of every tagged reading.
- **Cost:** every hosted-model request goes through a metering wrapper. It records the job, the model, the tokens the provider reported, and whether the request failed. The Cost panel shows the totals per job, the cost at paid-tier prices, and today's use of each model's free daily limit.

## Storage layout

```
data/
  drone.db                     sessions and saved clips (SQLite)
  graph.db                     graph index (FalkorDBLite)
  usage.sqlite3                model requests and tokens
  sessions/<id>/
    source.<ext>               uploaded video
    chunks/chunk_<start>.mp4   alert or manual clip
    chunks/chunk_<start>.json  what was seen, the decision, seek_offset_sec
    logs/observations/<hour>.json
    logs/summaries/*.summary.json
    keyframes/*.jpg
models/vision/                 local vision-model weights (downloaded on first start)
```

## Live updates

The browser receives server-sent events: readings, decisions, alerts, clip status, summaries, buffer stats, and session-list changes. It never polls.

## Privacy

| Data | Where it goes |
|------|---------------|
| Continuous video | Stays on site (in-memory ring buffer) |
| Frame analysis | Local vision model |
| Alert classifier input | One short re-encoded clip per 10 s window, plus the text readings |
| LLM input | Text log plus at most 6 small still frames per summary; nothing when LLM usage is off |
| Logs, clips, summaries | Local disk |

This is a hybrid design: perception is on site, and decisions and reports use hosted models on small, bounded inputs. It is not air-gapped.
