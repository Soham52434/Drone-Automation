# ADR-003: Gemini Flash — optional alert detail + required hour / dead-hand summaries

**Date:** 2026-11-23  
**Status:** Accepted  
**Related:** ADR-001 (stack), ADR-002 (event orchestration)

---

## Context

Decision 1 classifies alerts; Mirage supplies structured findings and the web popup. We still need readable period summaries with evidence timestamps, and an optional richer alert narrative without making every alert wait on an LLM. When a video or monitoring phase ends, something must produce a final summary before exit.

## Decision

1. **Optional detailed alert summary (Flash)**  
   - Controlled by a **frontend settings toggle** (default **OFF**).  
   - When ON, after ALERT + Mirage popup/chunk save, Flash writes a more detailed alert summary.  
   - Popup never blocks on Flash.

2. **Required 1-hour evidence summary (Flash)**  
   - At each hour boundary during a running session, Flash produces a **1-hour summary** from that hour’s Mirage JSON log + alert index.  
   - Summary must include **proper timestamps** and pointers to evidence (chunk files, seek offsets, event times).

3. **Dead-hand summary (Flash)**  
   - When an uploaded video ends, or a live/phase session stops, Flash is the **last job** before the phase ends.  
   - It summarizes the open/partial hour (or whole short session) with timestamps/evidence refs.  
   - Attempt once; on failure retry once; then write a failure record and allow exit.

4. Flash inputs for summaries prefer **structured logs + index metadata**, not uploading a full hour of video.

## Consequences

**Positive**

- Clear UX: fast Mirage popup; optional richness; always-on hourly narrative for reviewers  
- Clean lifecycle: no silent end of video without a final summary attempt  
- Period summaries without per-frame LLM cost  

**Tradeoffs**

- Hour + dead-hand Flash calls are mandatory cloud usage (still sparse vs per-frame)  
- Need reliable hour-boundary and shutdown hooks in the orchestrator  
- Settings state must be available to the backend when optional alert detail is ON  

## Links

- [`../00-current-architecture.md`](../00-current-architecture.md)  
- [`002-event-orchestration-chunks.md`](002-event-orchestration-chunks.md)
