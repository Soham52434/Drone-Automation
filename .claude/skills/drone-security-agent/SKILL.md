---
name: drone-security-agent
description: >-
  Project guide for the Drone Security Analyst (local vision model → alert classifier → LLM summarizer).
  Enforces architecture, class/data neatness, code inventory, and the
  write-tests → pass-tests → run gate. Use for any coding, refactor, test, architecture,
  feature, or agent work in this repo.
---

# Drone Security Analyst — Agent Project Guide

## Mandatory first actions (every coding turn)

Before writing or editing code, **read these files in order** (skip only if already read this session and unchanged):

1. This skill (`SKILL.md`)
2. [project-outcome.md](project-outcome.md) — definition of done
3. [architecture-map.md](architecture-map.md) — pipeline contract
4. Root sources of truth:
   - `FEATURES.md`
   - `docs/architecture.md`
   - `docs/design-decisions.md` (if changing design)
5. `docs/code-inventory.md` — **what already exists** (classes, data, functions)
6. [coding-standards.md](coding-standards.md) + [test-and-run.md](test-and-run.md)

If `docs/code-inventory.md` is missing, create it from [inventory-template.md](inventory-template.md) before adding substantial code.

---

## Hard gates (non-negotiable)

```
Code change → update inventory → write/update tests → tests PASS → run the relevant entrypoint → only then claim done
```

1. **No untested code paths** for new behavior.
2. **No “tests later”** — write tests in the same change.
3. **Tests must pass** before finishing the turn.
4. **Run** the affected entrypoint after tests (smoke check).
5. **Update `docs/code-inventory.md`** whenever you add/rename/remove a class, dataclass, or public function.
6. Prefer **classes + typed data models** over scattered dicts/scripts.

Fail any gate → fix before adding features.

---

## Architecture contract (change only with a design-decision entry)

```
Live|Upload → ring buffer → vision model (sampled, local) → hourly JSON log
                          → 10s window (max 15s): video + vision readings
                          → alert classifier + time rules (ALERT?) → popup + save chunk
                          → optional LLM alert write-up (session setting)
                          → LLM period summary (every N minutes)
                          → LLM dead-hand summary (LAST before the session ends)
```

- The vision model analyzes sampled frames **on-site**; it never raises the web popup alone.
- The alert classifier decides **ALERT vs NOT ALERT** on a **10s window (max 15s)**; the after-hours and loitering rules can also alert.
- On alert: web popup + paired `chunk_*.mp4` / `.json` + debounce.
- Every model call runs through a LangGraph (`src/drone_security/graphs.py`).
- No continuous full-stream cloud upload.
- Design changes → entry in `docs/design-decisions.md` + update `docs/architecture.md`.

Details: [architecture-map.md](architecture-map.md)

---

## Coding workflow (agent loop)

```
Task Progress:
- [ ] 1. Read inventory + locate existing classes/data/functions
- [ ] 2. Plan: which module, which class/dataclass, which tests
- [ ] 3. Implement neat structured code (models first, then services)
- [ ] 4. Update docs/code-inventory.md
- [ ] 5. Write/update tests
- [ ] 6. Run tests until PASS
- [ ] 7. Run smoke entrypoint
- [ ] 8. Confirm FEATURES still aligned
```

### Survey before inventing

- What **classes** already own this responsibility?
- What **data models** already exist?
- What **functions** already implement pieces of this?

Extend existing types. Do not duplicate parallel dict shapes.

### Layout

```
src/drone_security/
  models/          # dataclasses only
  ingest/          # frame sources: ring buffer, video file, WebRTC
  perception/      # local vision-model adapter + perception graph
  decisions/       # alert classifier graph + time rules
  agent/           # LLM graphs: summaries, chat, entity descriptions; metering
  indexing/        # SQLite, graph index, logs, archives, usage ledger
  pipeline/        # orchestration
  telemetry/       # telemetry from class tags
tests/
docs/code-inventory.md
```

Rules: [coding-standards.md](coding-standards.md). Test and run: [test-and-run.md](test-and-run.md).

---

## When asked for a feature

1. Map it to a `FEATURES.md` item and a pipeline layer.
2. Implement through existing classes/data where possible.
3. Record a design decision only if the architecture changes.
4. Close with: tests passed + command run + inventory updated.

## Anti-patterns

- One-off scripts that bypass models/pipeline
- Passing raw untyped dicts across layers
- Calling the LLM on every frame
- Claiming done without green tests
- Changing the architecture without updating the design docs
- Ignoring `docs/code-inventory.md`
