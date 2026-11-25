# Testing

Two suites: 206 backend tests (pytest) and 64 frontend tests (Vitest). Neither needs an API key, a GPU, or a camera. Every model is replaced by a fake with the same interface, and test videos are generated on the fly.

## Run

```bash
uv run pytest -q                           # backend
cd web && npm test && npm run build        # frontend: tests, typecheck, production build
```

A smoke run after the tests starts the real server on a scratch data folder:

```bash
DRONE_DATA_DIR=/tmp/drone-smoke uv run python main.py --port 8765
curl -s http://127.0.0.1:8765/api/health
```

## The brief's examples, as tests

`tests/test_assignment_examples.py` turns the scenarios from the brief into executable checks:

| Scenario | What the test proves |
|----------|----------------------|
| "Alert triggered at midnight" | A person seen at 00:01 on a live session raises a critical `after_hours` alert, even though the classifier says clear. The same scene at noon raises nothing |
| "Person loitering" | 90 s of continuous presence raises `loitering`; 30 s does not. At night it is critical |
| Loitering, end to end | A generated 32 s video is uploaded through the API, and the alert arrives over the event stream with a saved clip |
| "Truck logged correctly" | A reading of "white pickup truck" is stored as class `vehicle` in the graph and found by a vehicle query |
| Brief scoping | With a boats-only brief, people never trigger the time rules |
| Uploads without a clock | Night is read from the scene for uploaded video |

`tests/test_advanced_analytics.py` covers "a blue Ford F150 entered twice": three sightings in two separate visits answer "seen twice", both with and without the LLM.

## Coverage by layer

| Layer | Tests |
|-------|-------|
| Ingest | Ring buffer eviction and windows, frame normalizer, video file reader, latest-frame slot, real WebRTC loopback (`test_live_webrtc.py`) |
| Perception | Payload mapping including quiet frames, the vision-model adapter, the perception graph (accept and reject), object → class mapping |
| Alert decision | Alert and clear, the `none` rule, a missing API key, oversized clips, time rules with midnight wrap-around and presence gaps |
| Pipeline | Upload playback over the event stream: alert clip, quiet window, cooldown, readings indexed; LLM on gives period, alert, and final summaries with the dead hand last; LLM off makes no LLM calls |
| Summaries | Evidence citations, one writer per job, retry once, failure record, quiet periods skip the LLM, key frames labelled and attached |
| Memory | Graph time buckets, class and time queries, alerts on readings, hour digests, per-session delete, close and reopen |
| Chat | Direct answers, human-in-the-loop pause and resume, upload time windows, LLM planner with fallback notice, LLM off, hourly summaries |
| Telemetry | Class activity, spans with gaps, capped log, the `/telemetry` endpoint |
| Cost | Price table, token metering from replies, failed requests, per-session attribution end to end, Pacific-day reset of free-tier counts |
| API | Every endpoint's success and error codes, range requests for video, settings validation |
| Frontend | API client, live registry, feed and incident records, alert watcher, preferences, session setup payloads, telemetry and cost formatting |

## Test doubles

- **Vision model:** a fake `describe` that returns scripted readings ("man in dark jacket", "white delivery van").
- **Alert classifier:** a scripted classifier with a fixed confidence and rule.
- **LLM:** fake chat models that return fixed text or JSON, raise quota errors, or record the prompts and images they received.
- **Video:** `tests/conftest.py::write_test_video` writes a short mp4 for upload and clip tests.

Every graph takes its model as a constructor argument, so the production code paths run unchanged in tests.

## Negative cases

Each feature has at least one "should not" test:
- A quiet window shows no pop-up.
- LLM off means no LLM calls.
- A watch brief that excludes people means people never trigger the time rules.
- 30 s in view is not loitering.
- With advanced analytics off, no descriptions are requested.
