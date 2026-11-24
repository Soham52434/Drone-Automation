# Test and run gate

## Rule

**Write tests → run tests until they pass → run the smoke entrypoint.**  
Do not mark a coding task complete if any of these failed.

## What must be tested

| Change type | Minimum tests |
|-------------|----------------|
| New data model | Construction / validation / immutability as relevant |
| Perception adapter | Returns `SceneObservation` shape (mock Mirage if needed) |
| Decision gate | Worth-reporting true/false; rule firing; confidence handling |
| Indexing | Insert + query by time; query by object |
| Pipeline | End-to-end with fakes: boring frame skips LLM; alert frame calls agent |
| Agent / Flash | Prompt/tool wiring with mocked client |

Always include at least one **negative** case (should not alert / should not call LLM).

## How to run (repo defaults)

Prefer project tooling when present (`uv`, `pytest`):

```bash
cd /home/soham-jagtap/Desktop/OA
# activate or use uv
uv run pytest -q
# or
.venv/bin/python -m pytest -q
```

If pytest is not installed yet, add it as a dev dependency before claiming test coverage.

Smoke after green tests:

```bash
uv run python main.py
# later: uv run python -m drone_security ...
```

## Agent behavior on failure

1. Read the failure output.
2. Fix code or test (do not delete failing tests to “pass”).
3. Re-run the **full** relevant suite.
4. Only then run smoke.

## Test doubles

- External Mirage / Decision 1 / Flash **must** be mockable.
- Default unit tests do **not** require live API keys.
- Optional marked integration tests may call live APIs when the user asks.

## Definition of “passed”

- Exit code 0 from pytest for the changed scope (prefer whole suite).
- Smoke command exits 0 and shows expected high-level behavior (or documented placeholder until wired).
