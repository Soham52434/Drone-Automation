# Drone Automation

On-site security analyst for a docked drone that watches one property.

Video stays on site. A small local vision model describes sampled frames. A decision model looks at short clips (about 10 seconds, up to 15) and decides whether to raise an alert. Alerts show what was seen, save a matching video chunk, and keep an hourly record. A language model writes hour summaries and a final summary when a video or monitoring phase ends.

## Pipeline

```
Live stream or uploaded video
  → in-memory ring buffer
  → Mirage (local, sampled frames) → hourly JSON log
  → 10s window (max 15s) + Mirage JSON
  → Gemini Decision 1 → alert or not
  → alert: web popup + saved chunk
  → optional Gemini Flash detailed alert (frontend setting, default off)
  → Gemini Flash 1-hour summary
  → Gemini Flash final summary (last step before the phase ends)
```

## Docs

- [Features](FEATURES.md) — what the product does, in plain language
- [Architecture](architecture-decisions/00-current-architecture.md) — current design
- [Decisions](architecture-decisions/README.md) — why the design changed
- [Code inventory](docs/code-inventory.md) — classes, data, and functions that exist today

## Status

Design is in place. The Python package and tests are not built yet.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python main.py
```

Requires Python 3.11+.

## Configuration

Copy `.env.example` to `.env` for API keys. Do not commit `.env`.

| Variable | Used for |
|----------|----------|
| `GEMINI_API_KEY` | Decision 1 and Flash |
