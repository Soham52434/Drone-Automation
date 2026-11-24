# Coding standards — neat classes & data

## Principles

1. **Models first** — define dataclasses (or pydantic models) before services.
2. **One responsibility per class** — perception ≠ gating ≠ indexing ≠ agent.
3. **Typed boundaries** — public functions accept/return models, not anonymous dicts.
4. **Small functions** — prefer methods on the owning class over free-floating helpers.
5. **Explicit names** — `GateResult.worth_reporting`, not `ok` / `flag`.
6. **Inventory sync** — every new public type/function appears in `docs/code-inventory.md`.

## Before adding a function

Check `docs/code-inventory.md` + codebase:

- Does a class already own this?
- Can this be a method instead of a new module-level function?
- Is there an existing data model to extend?

If inventing a new parallel type for the same concept → **stop and reuse**.

## Preferred patterns

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class TelemetrySample:
    timestamp: datetime
    location: str
    altitude_m: float | None = None


@dataclass(frozen=True)
class SceneObservation:
    frame_id: str
    objects: tuple[str, ...]
    raw: dict  # provider-specific payload; keep at the edge


@dataclass(frozen=True)
class GateResult:
    worth_reporting: bool
    confidence: float
    fired_rules: tuple[str, ...]
    severity: Literal["info", "warn", "critical"] | None = None


class PerceptionService:
    def observe(self, frame_path: str, telemetry: TelemetrySample) -> SceneObservation:
        ...


class DecisionGate:
    def evaluate(self, observation: SceneObservation, telemetry: TelemetrySample) -> GateResult:
        ...
```

## Module rules

- `models/`: pure data — no I/O, no API clients.
- `*_client.py` / adapters: wrap Mirage, Decision 1, Flash; convert to/from models at the edge.
- `pipeline/`: orchestration only — no embedding vendor SDKs deeply.
- Tests may use fakes implementing the same class interfaces.

## Style

- Python 3.11+
- Type hints on public APIs
- No dead code or commented-out blocks left behind
- Keep files focused; split when a file mixes unrelated layers
- Secrets via env vars; never commit API keys

## Forbidden for v1

- Calling Flash/VLM inside a tight “every frame” loop without the gate
- Dumping Mirage JSON through the stack as untyped `dict` at every layer
- Giant `main.py` with all logic inline (thin entrypoint only)
