# Project outcome — definition of done

## Product outcome

A working **Drone Security Analyst Agent** prototype for a docked drone monitoring a fixed property:

| Outcome | Evidence |
|---------|----------|
| Ingests video | Live stream or uploaded file through one orchestrator + ring buffer |
| Sees the scene | Mirage on sampled frames returns structured JSON with timestamps |
| Hourly trail | Mirage outputs appended to hour-scoped JSON logs always |
| Decides | Decision 1 on ~10s window (max 15s: video + Mirage JSON) → ALERT or not |
| Alerts | Web popup shows Mirage output only when Decision 1 says ALERT |
| Evidence clips | Paired `chunk_*.mp4` + `.json` with `seek_offset_sec`; debounced |
| Remembers | Events queryable by time and object type |
| Optional detailed alert | Flash richer alert text only if frontend setting ON (default OFF) |
| Hour summary | Flash 1-hour summary with evidence timestamps |
| Dead hand | Flash final summary is last job before video/phase end |

Privacy outcome: continuous frame **analysis** on-site; cloud used sparsely for decision/report helpers (see architecture).

## Ship checklist

- [ ] Feature list — see `FEATURES.md`
- [ ] Architecture docs — see `architecture-decisions/`
- [ ] Runnable Python prototype
- [ ] Indexing with query examples
- [ ] Automated tests
- [ ] README: setup, run, and design

## Bonus outcomes (if time)

- [ ] One-sentence video/day summary
- [ ] Follow-up Q&A over indexed events

## Engineering outcome (every PR / agent turn)

- Neat modules with clear classes and data models
- `docs/code-inventory.md` current
- New behavior covered by tests that **pass**
- Smoke run of the affected entrypoint succeeds
