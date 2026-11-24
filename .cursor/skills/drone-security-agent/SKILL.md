---
name: drone-security-agent
description: >-
  Project guide for the Drone Security Analyst (Mirage → Decision 1 → Flash).
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
   - `architecture-decisions/00-current-architecture.md`
   - `architecture-decisions/changelog.md` (if changing design)
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
4. **Run** the affected CLI/module after tests (smoke check).
5. **Update `docs/code-inventory.md`** whenever you add/rename/remove a class, dataclass, or public function.
6. Prefer **classes + typed data models** over scattered dicts/scripts. Keep neat structure.

Fail any gate → fix before adding features.

---

## Architecture contract (do not violate without ADR)

Pipeline:

```
Live|Upload → ring buffer → Mirage (sampled, local) → hourly JSON log
                          → 10s window (max 15s): video + Mirage JSON
                          → Decision 1 (ALERT?) → popup + save chunk
                          → optional Flash detailed alert (settings toggle)
                          → Flash 1-hour summary (required)
                          → Flash dead-hand summary (required, LAST before phase end)
```

- Mirage analyzes sampled frames **on-site**; it does **not** raise the web popup alone.
- Decision 1 classifies **ALERT vs NOT ALERT** on a **10s window (max 15s)**.
- On alert: web popup (Mirage output) + paired `chunk_*.mp4` / `.json` + debounce.
- Flash detailed alert summaries are **optional** (frontend setting, default OFF).
- Flash **1-hour** and **dead-hand** summaries are **required**; dead hand is the last job before a video/phase ends.
- No continuous full-stream cloud upload.
- Design changes → new ADR under `architecture-decisions/adrs/` + changelog entry.

Details: [architecture-map.md](architecture-map.md)

---

## Coding workflow (agent loop)

Copy and track:

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

### Step 1 — Survey before inventing

Ask and answer from inventory + codebase:

- What **classes** already own this responsibility?
- What **data models** already exist?
- What **functions** already implement pieces of this?

Extend existing types. Do not duplicate parallel dict shapes.

### Step 2 — Structure

Default layout (create as needed):

```
src/drone_security/
  models/          # dataclasses / pydantic models only
  perception/      # Mirage adapters
  decisions/       # Decision 1 + local rules
  agent/           # Flash / LangChain agent
  indexing/        # frame/event store + query
  pipeline/        # orchestration
  telemetry/       # telemetry types + join
tests/
docs/code-inventory.md
```

Rules: [coding-standards.md](coding-standards.md)

### Step 3 — Test + run

Follow [test-and-run.md](test-and-run.md). Typical commands (adjust when project matures):

```bash
# from repo root, with project venv
python -m pytest -q
python -m drone_security  # or: uv run python main.py / documented CLI
```

---

## Project outcome (north star)

Ship a private-repo prototype that:

- Simulates telemetry + frames
- Perceives with Mirage (structured)
- Gates with Decision 1 (“worth reporting?”)
- Calls Flash LLM only when needed
- Logs events, raises alerts, indexes/query by time or object
- Has passing tests, README, design docs, voiceover demo, PDF report

Full checklist: [project-outcome.md](project-outcome.md)

---

## When the user asks for a feature

1. Map feature → `FEATURES.md` item + pipeline layer.
2. Implement through existing classes/data when possible.
3. Add ADR only if architecture changes.
4. Close with: tests passed + command run + inventory updated.

---

## Anti-patterns

- One-off scripts that bypass models/pipeline
- Passing raw untyped dicts across layers
- Calling Flash/VLM on every frame
- Claiming done without green tests
- Editing architecture without changelog/ADR
- Ignoring `docs/code-inventory.md`
