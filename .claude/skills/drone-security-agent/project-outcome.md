# Project outcome — definition of done

## Product outcome

A working **Drone Security Analyst Agent** prototype for a docked drone monitoring a fixed property:

| Outcome | Evidence |
|---------|----------|
| Ingests video | Live stream or uploaded file through one orchestrator + ring buffer |
| Sees the scene | Local vision model on sampled frames returns structured JSON with timestamps and classes |
| Hourly trail | Every reading appended to hour-scoped JSON logs |
| Decides | Alert classifier on a ~10s window (max 15s: video + readings) plus time rules → ALERT or not |
| Alerts | Web popup only when the gate says ALERT |
| Evidence clips | Paired `chunk_*.mp4` + `.json` with `seek_offset_sec`; debounced |
| Remembers | Readings queryable by time and object class (graph index + chat) |
| Telemetry | Per-class activity and a tagged log, from class tags |
| Summaries | LLM period summaries with evidence timestamps; dead-hand final summary last |
| Cost | Requests, tokens, and cost per session |

Privacy outcome: continuous frame **analysis** on-site; the cloud sees short decision clips and a few key frames.

## Ship checklist

- [x] Feature list — `FEATURES.md`
- [x] Architecture and design docs — `docs/`
- [x] Runnable prototype
- [x] Indexing with query examples
- [x] Automated tests
- [ ] README with screenshots and demo video
- [ ] Report

## Engineering outcome (every change)

- Neat modules with clear classes and data models
- `docs/code-inventory.md` current
- New behavior covered by tests that **pass**
- Smoke run of the affected entrypoint succeeds
