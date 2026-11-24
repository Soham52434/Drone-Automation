# ADR-002: Event orchestration, chunk windows, and alert path

**Date:** 2026-11-23  
**Status:** Accepted  
**Supersedes in part:** ADR-001 payload detail (Decision 1 now evaluates a short video window + Mirage JSON, not JSON-only by default)  
**Related:** ADR-001 (Mirage → Decision 1 → Flash stack remains)

---

## Context

Continuous video (live or upload) must be monitored. Mirage sees one frame at a time and has no temporal memory. Cloud Decision 1 can classify alerts well on multimodal input but must not receive the full continuous stream. Users need a clear alert UX and durable evidence (logs + seekable clips).

## Decision

1. **One orchestrator** for live stream and uploaded video.
2. **In-memory ring buffer** holds the last ~10–15 seconds of frames; no default continuous disk recording.
3. **Mirage** runs on sampled keyframes locally; every observation appends to an **hourly JSON log**.
4. **Decision windows** target **10 seconds**, hard max **15 seconds**, containing the video chunk + Mirage outputs (+ telemetry).
5. **Gemini Decision 1** is the only authority that classifies **ALERT vs NOT ALERT**.
6. On **ALERT**: web popup showing Mirage output; commit paired `.mp4` + `.json` with `seek_offset_sec`; debounce; background encode.
7. **Flash LLM** remains optional/sparse after alert (wording, Q&A, agent) — not required for the popup.
8. **Future research:** embedding-based event triggers (out of v1 scope).

## Consequences

**Positive**

- Clear time model despite Mirage’s lack of memory  
- Bounded cloud cost (short clips, not the whole stream)  
- Auditable hourly Mirage trail + seekable alert evidence  
- Clean UX: popup only when Decision 1 says alert  

**Tradeoffs**

- Short video clips leave the site for Decision 1 (hybrid privacy, not zero-cloud)  
- More orchestration complexity (buffer, sampler, debounce, background I/O)  
- Must tune sample rate, window packing, and debounce to avoid missed or duplicate alerts  

## Links

- [`../00-current-architecture.md`](../00-current-architecture.md)  
- [`001-mirage-decision1-flash-pipeline.md`](001-mirage-decision1-flash-pipeline.md)
