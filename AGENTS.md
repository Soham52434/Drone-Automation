# AGENTS.md

Instructions for AI coding agents working in this repository.

## Load first

1. `.cursor/skills/drone-security-agent/SKILL.md` — **primary project skill**
2. `docs/code-inventory.md` — existing classes, data models, functions
3. `architecture-decisions/00-current-architecture.md` — current plan
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

Live/upload → ring buffer → Mirage (hourly JSON) → **10s window (max 15s)** → Decision 1 → on ALERT: Mirage web popup + chunk save → optional Flash detailed alert (**settings**, default OFF) → required Flash **1-hour** summary → required Flash **dead-hand** summary as **last work** before video/phase end.

Design evolution: `architecture-decisions/` (ADR-002 chunks, ADR-003 Flash).
