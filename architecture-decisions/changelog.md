# Design evolution changelog

Newest first. Captures **thought process**, not just final APIs.

---

## 2026-11-23 — Gemini Flash roles locked (optional alert detail + hour / dead hand)

**Decision (clear):**

1. **Optional:** Flash writes a **detailed alert summary** only when a **frontend setting** is ON (default OFF). Web popup still shows Mirage immediately and does not wait on Flash.
2. **Required:** Flash writes a **1-hour evidence summary** at each hour boundary, with **timestamps** pointing at Mirage events / chunk evidence.
3. **Required dead hand:** When a video or monitoring phase ends, Flash runs as the **last work** before exit — final summary for the partial hour / session, then shutdown.

**Artifacts:** `00-current-architecture.md`, ADR-003, `FEATURES.md`, skill architecture map

---

## 2026-11-23 — Event orchestration locked (chunks + Decision 1 alerts)

**Decision (clear):**

1. Live stream and uploaded video share one orchestrator.
2. Ring buffer holds ~10–15s of frames in memory; Mirage samples keyframes locally.
3. All Mirage outputs append to an **hourly JSON log**.
4. Decision 1 receives a **~10s window (max 15s)** = video chunk + Mirage JSON for that window, and **classifies ALERT vs NOT ALERT**.
5. On alert only: **web popup** (Mirage output), save paired chunk `.mp4` + `.json` with seek offset, debounce, background write.
6. Flash roles later refined in ADR-003 (optional alert detail; required hour + dead-hand summaries). Embedding-based triggers = future research.

**Privacy update:** short Decision windows may include video; continuous stream still does not go to the cloud.

**Artifacts:** `00-current-architecture.md` (rewrite), ADR-002, `FEATURES.md`, skill `architecture-map.md`

---

## 2026-11-23 — Agentic project skill + always-on rule

Added `.cursor/skills/drone-security-agent/` (outcome, architecture map, coding standards, test/run gate, inventory template), `docs/code-inventory.md`, `.cursor/rules/drone-security-agent.mdc` (`alwaysApply: true`), and root `AGENTS.md`. Agents must survey inventory, keep neat classes/data, and only finish after tests pass + smoke run.

---

## 2026-11-23 — Clarified on-site vs cloud (privacy boundary)

**Question raised:** If frame analysis should be on-site, are we non-compliant by using cloud Decision 1 + Flash?

**Resolution:** **No for frame analysis; yes if someone expected zero-cloud.**

- On-site promise = **continuous looking at pixels** stays with Mirage locally.
- Decision 1 / Flash = sparse cloud helpers on **structured summaries** (and rare escalations), not streaming every frame.
- FEATURES + current architecture state the on-site boundary clearly: frame analysis stays local; this is not an air-gapped product.
- Fully local stack (rules/Needle instead of Google) noted as a future path.

**Artifacts:** `00-current-architecture.md` (privacy section), `../FEATURES.md`

---

## 2026-11-23 — Three-layer gate: Mirage → Decision 1 → Flash

**Decision:** Adopt a staged pipeline so LLM calls only happen when something is worth reporting.

**Thought process**

1. The product needs perception, event memory, alerts, and readable summaries.
2. Sending every frame to a chat or vision API does not scale for a dock that monitors all day.
3. **Cactus-Compute/Mirage** is a local ~22 MB structured vision model: continuous perception without a per-frame cloud vision bill.
4. **Gemini Decision 1** scores closed yes/no, choice, and rubric questions in one pass, with cheap input pricing and no output tokens.
5. Combined path: **Mirage sees always → Decision 1 decides if it matters → Flash writes summaries only when needed.**
6. Flash is a small generative layer, not a frontier model on every frame.

**Why not all-cloud vision?** Weak fit for continuous monitoring cost and privacy.

**Why not Mirage alone?** Weak at open-ended storytelling; alerts and hour summaries still need a language model.

**Artifacts:** `00-current-architecture.md`, ADR-001

---

## 2026-11-23 — Plain-language feature checklist

Wrote non-technical must-haves for property owners (watch, notice people/vehicles, remember/search, alert, answer simple questions, prefer on-site analysis). Keeps product intent stable while architecture evolves.

**Artifact:** `../FEATURES.md`

---

## 2026-11-23 — Mirage deep research (cost thesis)

Confirmed Mirage is a structured on-device perceiver (not a chat VLM). Quantified continuous cloud vision cost vs local perception. Hybrid Mirage + sparse LLM emerged as the durable pattern; Decision 1 later became the explicit “sparse” gate.

**Artifact:** `../reports/Cactus Mirage cost reduction.md`

---

## Pre-log — Starting point

Blank slate for a docked-drone security analyst: perception, alerts, and memory, with cost and on-site video analysis as first-class constraints.
