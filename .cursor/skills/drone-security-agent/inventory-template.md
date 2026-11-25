# Code inventory template

Copy into `docs/code-inventory.md` and keep updated. Agents must read this before coding and update it after coding.

```markdown
# Code inventory

**Last updated:** YYYY-MM-DD  
**Rule:** If it is public and real, it is listed here.

## Packages / modules

| Module | Role |
|--------|------|
| `src/drone_security/models/...` | Shared data |

## Data models (classes / dataclasses)

| Name | Module | Fields (summary) | Used by |
|------|--------|------------------|---------|
| | | | |

## Services / classes

| Name | Module | Public methods | Notes |
|------|--------|----------------|-------|
| | | | |

## Public functions (module-level)

| Name | Module | Signature | Notes |
|------|--------|-----------|-------|
| | | | |

## Entrypoints

| Command | File | Purpose |
|---------|------|---------|
| `python main.py` | `main.py` | Temporary bootstrap |

## Test modules

| File | Covers |
|------|--------|
| | |

## Intentionally not built yet

- Perception (vision model) adapter
- Alert classifier client
- LLM summarizer
- SQLite (or other) index
- Full pipeline orchestrator
```
