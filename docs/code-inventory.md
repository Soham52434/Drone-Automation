# Code inventory

**Last updated:** 2026-11-23  
**Rule:** If it is public and real, it is listed here. Agents must update this file when adding, renaming, or removing classes, data models, or public functions.

## Packages / modules

| Module | Role |
|--------|------|
| `main.py` | Temporary bootstrap entrypoint (placeholder) |

## Data models (classes / dataclasses)

| Name | Module | Fields (summary) | Used by |
|------|--------|------------------|---------|
| — | — | none yet | — |

## Services / classes

| Name | Module | Public methods | Notes |
|------|--------|----------------|-------|
| — | — | none yet | — |

## Public functions (module-level)

| Name | Module | Signature | Notes |
|------|--------|-----------|-------|
| `main` | `main.py` | `() -> None` | Prints hello placeholder |

## Entrypoints

| Command | File | Purpose |
|---------|------|---------|
| `python main.py` / `uv run python main.py` | `main.py` | Placeholder until `drone_security` package exists |

## Test modules

| File | Covers |
|------|--------|
| — | none yet |

## Intentionally not built yet

- `src/drone_security/` package layout
- Perception Mirage client + `SceneObservation`
- Decision 1 / rules gate + `GateResult`
- Flash / LangChain agent
- Indexing store + query APIs
- Pipeline orchestrator
- pytest suite
