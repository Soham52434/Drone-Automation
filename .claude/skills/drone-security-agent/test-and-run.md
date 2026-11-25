# Test and run gate

## Rule

**Write tests → run tests until they pass → run the smoke entrypoint.**  
Do not mark a coding task complete if any of these failed.

## What must be tested

| Change type | Minimum tests |
|-------------|----------------|
| New data model | Construction / validation / immutability as relevant |
| Perception adapter | Returns `SceneObservation` shape (fake vision model) |
| Decision gate | Worth-reporting true/false; rule firing; confidence handling |
| Indexing | Insert + query by time; query by object |
| Pipeline | End-to-end with fakes: boring frame skips LLM; alert frame calls agent |
| LLM graphs | Prompt wiring with a fake chat model |

Always include at least one **negative** case (should not alert / should not call LLM).

## How to run (repo defaults)

Backend (from repo root):

```bash
uv run pytest -q
```

Frontend (when `web/` changes):

```bash
cd web && npm test && npm run build
```

Smoke after green tests — start the server on a scratch data dir and hit the API:

```bash
DRONE_DATA_DIR=/tmp/drone-smoke uv run python main.py --port 8765 &
curl -s http://127.0.0.1:8765/api/health
# exercise the changed endpoint(s), e.g. upload a video then POST /api/sessions/{id}/chunks
pkill -f "main.py --port 8765"
```

`tests/conftest.py::write_test_video` generates a sample mp4 for smoke uploads.

## Agent behavior on failure

1. Read the failure output.
2. Fix code or test (do not delete failing tests to “pass”).
3. Re-run the **full** relevant suite.
4. Only then run smoke.

## Test doubles

- The vision model, alert classifier, and LLM **must** be replaceable by fakes.
- Default unit tests do **not** require live API keys.
- Live API calls are never part of the default suite.

## Definition of “passed”

- Exit code 0 from pytest for the changed scope (prefer whole suite).
- Smoke command exits 0 and shows expected high-level behavior (or documented placeholder until wired).
