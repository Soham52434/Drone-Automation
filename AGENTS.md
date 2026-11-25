# AGENTS.md

Instructions for AI coding agents working in this repository.

## Load first

1. `.cursor/skills/drone-security-agent/SKILL.md` — **primary project skill**
2. `docs/code-inventory.md` — existing classes, data models, functions
3. `docs/architecture.md` — current design
4. `FEATURES.md` — product outcomes

Skill references (read as needed):

- `.cursor/skills/drone-security-agent/project-outcome.md`
- `.cursor/skills/drone-security-agent/coding-standards.md`
- `.cursor/skills/drone-security-agent/test-and-run.md`
- `.cursor/skills/drone-security-agent/architecture-map.md`

## Non-negotiable engineering loop

```
survey inventory → implement neat classes/data → update inventory → write tests → tests PASS → run smoke
```

## Architecture reminder

Live/upload → ring buffer → local vision model (hourly JSON) → **10s window (max 15s)** → alert classifier + time rules → on ALERT: web popup + chunk save → optional LLM alert write-up (**setting**, default OFF) → LLM **period** summaries → LLM **dead-hand** summary as the **last work** before the session ends.

Why the design looks this way: `docs/design-decisions.md`.
