# Architecture map (actionable)

Canonical detail: `docs/architecture.md`  
Why it looks this way: `docs/design-decisions.md`

## Pipeline contract

```
Live|Upload → ring buffer → vision model (sampled, local) → hourly JSON log
                          → 10s window (max 15s): video + vision readings
                          → alert classifier + time rules → ALERT?
                               no → log only
                              yes → web popup + save chunk
                                    → optional LLM alert write-up (setting ON)
                          → LLM period summary (every N minutes)
                          → LLM dead-hand summary (LAST before the session ends)
```

## LLM jobs (do not blur)

| Job | Required? | Trigger |
|-----|-----------|---------|
| Alert write-up | Optional (session setting, default OFF) | After an alert |
| Period summary | When LLM usage is on | Every N minutes of the session |
| Dead-hand final summary | When LLM usage is on | Session end — **last work before exit** |
| Chat answers | On request | Operator question |
| Entity descriptions | Optional (advanced analytics) | New key frame with a person/vehicle/animal/package |

- The popup never waits on the LLM.
- Summaries cite evidence: timestamps, chunk files, seek offsets.
- The LLM sees the text log plus a few key frames — never full video.

## Layers → packages

| Layer | Responsibility | Package | Owns data |
|-------|----------------|---------|-----------|
| Capture / buffer | Stream or file → ring buffer | `ingest/`, `pipeline/` | `FramePacket`, `RingBuffer` |
| Perception | Vision model on the newest frame | `perception/` | `SceneObservation` |
| Logging | Hourly observation JSON | `indexing/` | `HourlyObservationLog` |
| Windowing | Pack 10–15 s evidence | `pipeline/` | `DecisionWindow` |
| Gate | Alert classifier + time rules | `decisions/` | `GateResult`, `RuleHit` |
| Commit | mp4 + paired json | `indexing/` | `ChunkArtifact` |
| Summaries / chat / analytics | LLM graphs | `agent/` | `LlmSummary`, `ChatTurn`, `EntitySighting` |
| Memory | Graph index | `indexing/` | `IndexedFrame`, `HourDigest` |
| Cost | Usage ledger | `agent/metering.py`, `indexing/` | `UsageRecord`, `SessionCost` |

## Changing the architecture

1. Add an entry to `docs/design-decisions.md`
2. Update `docs/architecture.md`
3. Align `FEATURES.md` if user-facing behavior changes
