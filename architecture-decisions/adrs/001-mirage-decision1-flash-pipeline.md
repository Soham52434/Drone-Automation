# ADR-001: Mirage → Decision 1 → Flash pipeline

**Date:** 2026-11-23  
**Status:** Accepted (stack); payload detail refined by ADR-002  
**Deciders:** Project owner

---

## Context

We are building a Drone Security Analyst for a docked drone that monitors a fixed property. The system processes telemetry and video, logs objects and events, raises alerts, and keeps a searchable index. Continuous frame analysis through a frontier chat or vision API is a poor fit for always-on dock monitoring.

This ADR is the stable contract for the model stack while details (exact Flash model ID, thresholds) stay open.

## Decision

Use a **three-layer pipeline**:

1. **Cactus-Compute/Mirage** — local structured perception on sampled frames  
2. **Google Gemini Decision 1** — closed-set gate: is this worth reporting / which rule / severity / confidence  
3. **Google Flash-class LLM (free tier for now)** — generative layer only for accepted events (alerts, summaries, Q&A / agent)

Supporting pieces: frame/event indexing, telemetry join, tests. Optional deterministic rules may sit next to Decision 1.

## Alternatives considered

| Option | Why not (for now) |
|--------|-------------------|
| Every frame → Flash / GPT VLM | Continuous cost; no smart gate; weak innovation story |
| Mirage only | Insufficient for narrative alerts and follow-up answers |
| Mirage → Flash (skip Decision 1) | Still too many generative calls; Decision 1 is purpose-built for multi-rule scoring + confidence |
| All local (Mirage + Needle) | Attractive later; v1 keeps a small Google Flash model for summaries |
| Frontier LLM for everything | Overkill and expensive; contradicts cost-reduction thesis |

## Consequences

**Positive**

- LLM calls become **event-driven**, not frame-driven  
- Clear story for cost, privacy, and layered design  
- Covers vision, alerts, summaries, and indexing  
- Confidence from Decision 1 gives a natural escalate / human-review hook  

**Negative / risks**

- More moving parts (three vendors/APIs + local runtime)  
- Mirage quality on security scenes is not fully proven — gate quality depends on Layer 1  
- Decision 1 needs carefully written rules/rubrics  
- Free-tier Flash limits may throttle demos — monitor quotas  
- Integration glue (LangChain tools wrapping Mirage / Decision 1) is DIY  
- **Not zero-cloud:** Decision 1 + Flash still send data (preferably Mirage JSON, not continuous video) to Google — fine for hybrid privacy, insufficient for air-gapped sites 

**Follow-ups**

- Lock Flash model ID and Decision 1 question bank  
- Define confidence thresholds and sample rate  
- Document measured cost: frames processed vs Flash calls made

## Links

- Current architecture: [`../00-current-architecture.md`](../00-current-architecture.md)  
- Changelog: [`../changelog.md`](../changelog.md)  
- Product features: [`../../FEATURES.md`](../../FEATURES.md)
