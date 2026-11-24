# Architecture map (actionable)

Canonical detail: `architecture-decisions/00-current-architecture.md`  
ADRs: `001` (stack) · `002` (chunks) · `003` (Flash summaries)  
Evolution: `architecture-decisions/changelog.md`

## Pipeline contract

```
Live|Upload → ring buffer → Mirage (sampled, local) → hourly JSON log
                          → 10s window (max 15s): video + Mirage JSON
                          → Decision 1 → ALERT?
                               no → log only
                              yes → web popup (Mirage) + save chunk
                                    → optional Flash detailed alert (settings ON)
                          → Flash 1-hour summary (required, hour boundary)
                          → Flash dead-hand summary (required, LAST before phase end)
```

## Flash rules (do not blur)

| Job | Required? | Trigger |
|-----|-----------|---------|
| Detailed alert summary | Optional (frontend setting, default OFF) | After ALERT |
| 1-hour evidence summary | Required | Hour boundary |
| Dead-hand final summary | Required | Video/phase end — **last work before exit** |

- Popup never waits on Flash.
- Hour / dead-hand summaries use Mirage logs + alert index with **timestamps / chunk / seek** evidence refs.
- Prefer structured text to Flash — not a full hour of video.

## Layers → packages

| Layer | Responsibility | Package | Owns data |
|-------|----------------|---------|-----------|
| Capture / buffer | Stream or file → deque | `pipeline/`, `ingest/` | `FramePacket`, `RingBuffer` |
| Perception | Mirage on keyframes | `perception/` | `SceneObservation` |
| Logging | Hourly Mirage JSON | `indexing/` / `logging/` | `HourlyMirageLog` |
| Windowing | Pack 10–15s evidence | `pipeline/` | `DecisionWindow` |
| Gate | Decision 1 alert classify | `decisions/` | `GateResult` |
| Alert UX | Web popup | `ui/` / `alerts/` | `AlertNotification` |
| Commit | mp4 + paired json | `indexing/` | `ChunkArtifact` |
| Flash | Optional alert detail + hour/dead-hand | `agent/` / `summaries/` | `AlertDetailSummary`, `HourSummary`, `FinalSummary` |
| Settings | Frontend toggles | `ui/` + config | `AppSettings.detailed_alert_summaries` |

## Changing the architecture

1. ADR under `architecture-decisions/adrs/`
2. Update `00-current-architecture.md`
3. Changelog entry (newest first)
4. Align `FEATURES.md` if user-facing behavior changes
