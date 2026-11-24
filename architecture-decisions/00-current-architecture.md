# Current architecture (v1)

**Status:** Planned — not yet implemented  
**Last updated:** 2026-11-23  

---

## Pitch

Analyze video on-site with Mirage. Decide alerts with Gemini Decision 1 on short clips. Show Mirage findings in a web popup only when Decision 1 classifies an alert. Persist hourly Mirage logs and alert video chunks. Use **Gemini Flash** for (1) optional richer alert text and (2) required hour / end-of-phase evidence summaries — including a **dead-hand** summary when a video or monitoring phase ends.

---

## Input modes (same orchestrator)

| Mode | Behavior |
|------|----------|
| **Live stream** | OpenCV / GStreamer frames enter a rolling ring buffer continuously |
| **Uploaded video** | Same pipeline; file is read as a frame source instead of a camera |

One orchestrator owns time, buffering, sampling, storage, and indexing. **Mirage has no memory across frames** — the wrapper is the timeline.

---

## End-to-end event flow

```
Live stream  OR  uploaded video
        │
        ▼
┌─────────────────────────────────────┐
│ Capture + ring buffer               │
│ Keep last ~10–15s of raw frames     │
│ in memory (deque). Do not write     │
│ continuous disk recording by        │
│ default.                            │
└─────────────────┬───────────────────┘
                  │ sample keyframes (~3–6 FPS)
                  ▼
┌─────────────────────────────────────┐
│ Layer 1 — Mirage (local)            │
│ One sampled frame → structured JSON │
│ + timestamp / frame_index           │
│ Always append to hourly Mirage log  │
└─────────────────┬───────────────────┘
                  │ when evaluating a window
                  ▼
┌─────────────────────────────────────┐
│ Decision window                     │
│ Target: 10 seconds of video         │
│ Hard max: 15 seconds                │
│ Payload to Decision 1:              │
│   • that video chunk                │
│   • Mirage JSON for frames in it    │
│   • telemetry for the window        │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│ Layer 2 — Gemini Decision 1         │
│ Classify: ALERT or NOT ALERT        │
│ (+ which rule / severity / conf.)   │
└─────────────────┬───────────────────┘
                  │
         NOT ALERT ──► keep hourly log; no popup; no chunk commit
                  │
               ALERT
                  ▼
┌─────────────────────────────────────┐
│ Alert path                          │
│ 1. Web popup: show Mirage output    │
│ 2. Commit video chunk to disk       │
│ 3. Write paired JSON metadata       │
│ 4. Index for later search           │
│ 5. Optional Flash detailed alert    │
│    summary (frontend setting OFF    │
│    by default)                      │
└─────────────────────────────────────┘
                  │
                  ▼ (time / lifecycle)
┌─────────────────────────────────────┐
│ Gemini Flash — summaries            │
│ A. Every clock hour: 1-hour         │
│    evidence summary with timestamps │
│ B. Dead hand: when video/phase ends │
│    Flash runs LAST — final summary  │
│    for the incomplete hour / whole  │
│    session before shutdown          │
└─────────────────────────────────────┘
```

---

## Layer responsibilities

### Capture & buffer

- Push every incoming frame into an in-memory **ring buffer**.
- For a ~10s clip at 30 FPS → about **300 frames** (`maxlen≈300`); allow growth toward **15s** (`maxlen≈450`) when the Decision window needs it.
- Normal path: **no continuous .mp4 writing**. Disk commits happen on alert (and any explicit export).

### Mirage (perception)

- Sample every Nth frame (about **3–6 FPS**, e.g. every 5th–10th frame at 30 FPS).
- Each call returns structured JSON. Orchestrator attaches `timestamp_ms`, `frame_index`, telemetry.
- Example observation shape:

```json
{
  "timestamp_ms": 1732365012450,
  "frame_index": 372,
  "event_detected": true,
  "label": "package_dropped",
  "confidence": 0.91,
  "summary": "Delivery driver placed a brown box near the front door."
}
```

- **Hourly Mirage log (always):** append Mirage outputs into an hour-scoped JSON log (e.g. `logs/mirage/2026-11-23T18.json`), whether or not an alert fires.

### Decision window → Decision 1 (alert classifier)

- **Target window:** **10 seconds**.
- **Allowed overrun:** up to **15 seconds** before send (never design for longer windows in v1).
- Send **video chunk + Mirage outputs for that window** (+ telemetry).
- Decision 1 answers closed questions: **Is this an alert?** Which rule? Severity? Confidence?
- **Decision 1 is the authority for ALERT vs NOT ALERT.** Mirage alone does not raise the web popup.

### Alert path

On `ALERT`:

1. **Web popup notification** — display the Mirage structured output (label, summary, confidence, time/place). Popup does **not** wait on Flash.
2. **Save video chunk** from the ring buffer (include a short post-roll of following frames when live).
3. **Save paired metadata JSON** (and index row).
4. **Debounce** — after a save, ignore duplicate triggers for a cooldown (default **10 seconds**) so one event does not produce many clips.
5. Write chunk encode on a **background thread** so inference is not blocked.
6. **Optional Flash detailed alert summary** — only if the frontend setting **“Detailed alert summaries (Gemini Flash)”** is **ON**. Produces a longer narrative for that alert; stored alongside the chunk metadata. Default: **OFF**.

### Gemini Flash — two jobs (clear)

| Job | When | Required? | Input | Output |
|-----|------|-----------|-------|--------|
| **Detailed alert summary** | After an ALERT, if settings toggle is ON | **Optional** (UI setting) | Mirage output + Decision 1 result + chunk refs | Richer alert text for UI/history |
| **1-hour evidence summary** | At each hour boundary while a session is running | **Yes** | That hour’s Mirage JSON log + alert chunk index (paths, seek offsets, times) | Hour summary with **proper timestamps** pointing at evidence |
| **Dead-hand summary** | When uploaded video ends, live session stops, or phase shuts down | **Yes** — **last work before the phase ends** | Mirage log + alerts for the open/partial hour (or whole short video) | Final stamped summary; then phase may exit |

**Dead hand (definition):** Flash is the **last handler** before ending a video or monitoring phase. No clean shutdown without attempting this final summary (retry once on failure, then persist a failure record and exit).

Hour / dead-hand summaries must cite evidence with timestamps, e.g. alert times, `chunk_*.mp4` names, and `seek_offset_sec` where available — so a reviewer can jump to proof.

---

## Storage & identity

### Pairing convention

Same prefix for media + metadata:

- `chunk_1732365005000.mp4`
- `chunk_1732365005000.json`

### Metadata must include seek offset

```text
seek_offset_sec = (detection_ms - chunk_start_ms) / 1000
```

Example:

```json
{
  "chunk_file": "chunk_1732365005000.mp4",
  "chunk_start_ms": 1732365005000,
  "detection_ms": 1732365012450,
  "seek_offset_sec": 7.45,
  "decision": {
    "alert": true,
    "confidence": 0.87,
    "rules_fired": ["package_near_door"]
  },
  "mirage_output": {
    "label": "package_dropped",
    "summary": "Delivery driver placed a brown box near the front door.",
    "confidence": 0.91
  }
}
```

### Hourly Mirage logs

- Rolling file or hour-keyed JSON array of all sampled Mirage observations.
- Separate from alert chunk files; used for audit, demos, indexing backfill, and as **primary input to Flash hour / dead-hand summaries**.

### Hour / dead-hand Flash summary artifacts

- e.g. `logs/summaries/2026-11-23T18.summary.json` (clock hour)
- e.g. `logs/summaries/<session_id>.final.summary.json` (dead hand)
- Each includes narrative + timestamped evidence references (chunk files / seek offsets / Mirage event times).

---

## Orchestration steps (implementation map)

| Step | Component | Role |
|------|-----------|------|
| 1 | Capture (OpenCV / GStreamer) | Frames → fixed-length memory deque |
| 2 | Sampler | Every ~200–300 ms, one frame → Mirage; attach timestamps |
| 3 | Hourly logger | Append Mirage JSON continuously |
| 4 | Window builder | Pack ~10s (max 15s) video + Mirage JSON → Decision 1 |
| 5 | Decision 1 | Classify alert / not alert |
| 6 | Debounce | Suppress repeat commits for cooldown after an alert save |
| 7 | Commit (background) | Write `.mp4` + paired `.json`; index; web popup |
| 8 | Optional Flash alert detail | If frontend setting ON → detailed alert summary |
| 9 | Flash hour summary | At hour boundary → 1-hour summary with evidence timestamps |
| 10 | Flash dead hand | On video/phase end → **last** job: final summary, then stop |

---

## Privacy stance (clear)

| Data | Where it goes |
|------|----------------|
| Continuous full stream to cloud | **No** |
| Mirage inference on frames | **On-site / local** |
| ~10–15s chunk + Mirage JSON to Decision 1 | **Yes — only for window evaluation** |
| Flash LLM | **Yes — text/log-based summaries** (hour + dead hand always; detailed alert only if setting ON). Prefer Mirage JSON + index metadata, not full hour video |
| Hourly Mirage logs + alert chunks | **Local disk** (prototype) |

This is **hybrid**: on-site continuous perception; short cloud decision clips; sparse Flash on structured evidence — not air-gapped.

---

## Future research (not v1)

- **Embedding-based event trigger** — use embedding similarity / change detection to decide when to open a Decision window or sample harder, instead of fixed timers only.

---

## Explicit non-goals (v1)

- Fine-tuning Mirage or Decision 1
- Sending the entire live stream to any cloud model
- Letting Mirage alone raise user-facing alerts without Decision 1
- Decision windows longer than 15 seconds
- Continuous disk recording of the full day as the default path

---

## Open choices (lock during build)

- [ ] Exact sample stride (every 5th vs 10th frame)
- [ ] Exact debounce cooldown (default 10s)
- [ ] Decision 1 question/rubric pack for security rules
- [ ] Web popup stack (simple local UI vs notification service)
- [ ] Flash model ID (Google Flash free-tier class)
- [ ] Frontend setting key for detailed alert summaries (default OFF)
- [ ] Hour-boundary scheduler vs wall-clock hour
- [ ] Dead-hand retry / failure record schema
- [ ] Index backend (SQLite first)
- [ ] Post-roll seconds after detection when dumping the buffer

---

## Design intent

Mirage is the **local sensor**. Decision 1 is the **alert classifier** on short evidence windows. Storage and the UI are the **proof trail** (hourly JSON, seekable chunks, popup). Gemini Flash is the **summarizer**: optional richer alerts via a settings toggle, required hour summaries with evidence timestamps, and a **dead-hand final summary** as the last work before a video or phase ends. Continuous monitoring without continuous cloud video cost.
