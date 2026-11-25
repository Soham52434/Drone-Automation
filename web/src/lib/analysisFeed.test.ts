import { describe, expect, it } from "vitest";

import { alertRecords, alertWriteUp, analysisEntry, openAlertCount, ruleLabel } from "./analysisFeed";
import { formatMediaTime, formatTimeline } from "./format";

describe("analysisEntry", () => {
  it("renders a vision observation", () => {
    const entry = analysisEntry(
      "observation",
      {
        timestamp_ms: 7_450,
        label: "package_dropped",
        confidence: 0.91,
        summary: "Delivery driver placed a brown box near the front door.",
      },
      1,
    );
    expect(entry?.text).toContain("brown box");
    expect(entry?.detail).toBe("");
    expect(entry?.meta).toContain("package_dropped");
    expect(entry?.meta).toContain("91%");
    expect(entry?.alert).toBe(false);
  });

  it("keeps a clear decision from opening an alert", () => {
    const entry = analysisEntry(
      "decision",
      { decision: { alert: false, confidence: 0.12, rules_fired: [], detail: "" } },
      2,
    );
    expect(entry?.kind).toBe("decision");
    expect(entry?.alert).toBe(false);
    expect(entry?.text).toContain("did not raise");
  });

  it("marks a debounced alert separately from a saved one", () => {
    const saved = analysisEntry(
      "alert",
      { debounced: false, observation: { label: "person", confidence: 0.8, summary: "A person is at the gate." } },
      3,
    );
    const skipped = analysisEntry("alert", { debounced: true, observation: { label: "person" } }, 4);
    expect(saved?.debounced).toBe(false);
    expect(saved?.text).toContain("gate");
    expect(skipped?.debounced).toBe(true);
  });

  it("shows vision reasoning and the parsed record", () => {
    const entry = analysisEntry(
      "observation",
      {
        timestamp_ms: 1_000,
        label: "blue square",
        confidence: 0.89,
        summary: "blue square",
        raw: {
          scene: { background: "black", style: "minimalist" },
          objects: [{ name: "blue square", score: 0.887, description: { color: "blue", shape: "square" } }],
          reasoning: "A blue square sits in the center of a black background.",
        },
      },
      5,
    );
    expect(entry?.text).toContain("blue square sits");
    expect(entry?.detail).toContain('"reasoning"');
    expect(entry?.detail).toContain("minimalist");
    expect(entry?.detail).toContain("blue square");
  });

  it("attaches the cropped timeframe video to an alert", () => {
    const entry = analysisEntry(
      "alert",
      {
        debounced: false,
        observation: { label: "boat", confidence: 0.9, summary: "A boat is alongside the dock." },
        video_url: "/api/sessions/s1/chunks/chunk_2000.mp4",
        chunk_start_ms: 2_000,
        chunk_end_ms: 12_000,
      },
      6,
      "upload",
    );
    expect(entry?.proofUrl).toContain("chunk_2000.mp4");
    expect(entry?.timeframe).toBe("0:02–0:12");
  });

  it("shows a live reading on the clock, not as a duration from zero", () => {
    const timestamp = Date.UTC(2026, 10, 24, 7, 24, 8);
    const entry = analysisEntry(
      "observation",
      { timestamp_ms: timestamp, label: "man", confidence: 0.57, summary: "A man is in the room." },
      7,
      "live",
    );
    expect(entry?.meta).toContain(formatTimeline("live", timestamp));
    expect(entry?.meta).not.toContain(formatMediaTime(timestamp));
  });

  it("keeps each raised alert, including one whose recording failed", () => {
    const raised = analysisEntry(
      "decision",
      { start_ms: 1_000, end_ms: 11_000, decision: { alert: true, confidence: 0.83, rules_fired: ["person_on_property"] } },
      1,
    );
    const failed = analysisEntry("error", { detail: "Could not save the alert clip" }, 2);
    const saved = analysisEntry(
      "alert",
      {
        debounced: false,
        observation: { summary: "A man is in the room." },
        video_url: "/api/sessions/s1/chunks/chunk_1.mp4",
        chunk_start_ms: 2_000,
        chunk_end_ms: 12_000,
      },
      3,
    );
    const records = alertRecords([raised, failed, saved].filter((entry) => entry !== null));
    expect(records).toHaveLength(2);
    expect(records[0]?.proofUrl).toBe("");
    expect(records[1]?.proofUrl).toContain("chunk_1.mp4");
  });

  it("names rules for people", () => {
    expect(ruleLabel("person_on_property")).toBe("Person");
  });

  it("carries classes and location on a reading", () => {
    const entry = analysisEntry(
      "observation",
      {
        timestamp_ms: 1_000,
        label: "man",
        confidence: 0.8,
        summary: "A man at the gate.",
        classes: [{ name: "person", score: 0.8, count: 2 }],
        location: "driveway",
      },
      1,
    );
    expect(entry?.classes).toEqual([{ name: "person", score: 0.8, count: 2 }]);
    expect(entry?.location).toBe("driveway");
  });

  it("finds the LLM write-up for an alert", () => {
    const writeUp = analysisEntry("summary", { kind: "alert", alert_key: "window-1000", status: "ok", text: "Details." }, 1)!;
    const failed = analysisEntry("summary", { kind: "alert", alert_key: "window-2000", status: "failed", text: "x" }, 2)!;
    expect(alertWriteUp([writeUp, failed], "window-1000")).toBe("Details.");
    expect(alertWriteUp([writeUp, failed], "window-2000")).toBe("");
  });
});

describe("alertRecords", () => {
  const reading = (seq: number, at: number) =>
    analysisEntry(
      "observation",
      { timestamp_ms: at, label: "man", confidence: 0.8, summary: "x", raw: { reasoning: `Man at the gate ${seq}` } },
      seq,
    )!;
  const raised = (seq: number, start: number) =>
    analysisEntry(
      "decision",
      {
        start_ms: start,
        end_ms: start + 10_000,
        decision: { alert: true, confidence: 0.9, rules_fired: ["person_on_property"], severity: "warn", detail: "Person by the gate" },
      },
      seq,
    )!;
  const saved = (seq: number, url: string) =>
    analysisEntry(
      "alert",
      { debounced: false, observation: { summary: "Man at the gate" }, video_url: url, chunk_start_ms: 1, chunk_end_ms: 2 },
      seq,
    )!;

  it("pops the vision reading at once and keeps the key once the clip is saved", () => {
    const pending = alertRecords([reading(0, 5_000), raised(1, 1_000)]);
    expect(pending).toHaveLength(1);
    expect(pending[0]?.clip).toBe("saving");
    expect(pending[0]?.text).toContain("Man at the gate 0");
    expect(pending[0]?.note).toBe("Person by the gate");

    const done = alertRecords([reading(0, 5_000), raised(1, 1_000), saved(2, "/c.mp4")]);
    expect(done[0]?.key).toBe(pending[0]?.key);
    expect(done[0]?.clip).toBe("saved");
    expect(done[0]?.rule).toBe("person_on_property");
    expect(done[0]?.note).toBe("Person by the gate");
  });

  it("does not drop an earlier incident when a second clip arrives", () => {
    const records = alertRecords([raised(1, 1_000), saved(2, "/a.mp4"), raised(3, 11_000), saved(4, "/b.mp4")]);
    expect(records.map((record) => record.proofUrl)).toEqual(["/a.mp4", "/b.mp4"]);
    expect(new Set(records.map((record) => record.key)).size).toBe(2);
  });

  it("marks cooldown and unrelated errors correctly", () => {
    const cooldown = analysisEntry("alert", { debounced: true }, 2)!;
    expect(alertRecords([raised(1, 1_000), cooldown])[0]?.clip).toBe("cooldown");
    const visionError = analysisEntry("error", { detail: "The vision model failed: timeout" }, 2)!;
    expect(alertRecords([raised(1, 1_000), visionError])[0]?.clip).toBe("saving");
  });

  it("ignores a clear decision", () => {
    const clear = analysisEntry("decision", { start_ms: 0, end_ms: 10_000, decision: { alert: false } }, 1)!;
    expect(alertRecords([clear])).toEqual([]);
  });

  it("counts open incidents against acknowledged keys", () => {
    const records = alertRecords([raised(1, 1_000), raised(2, 11_000)]);
    expect(openAlertCount(records, new Set([records[0]!.key]))).toBe(1);
  });
});

describe("time rule labels", () => {
  it("names the predefined rules", () => {
    expect(ruleLabel("loitering")).toBe("Loitering");
    expect(ruleLabel("after_hours")).toBe("After hours");
  });
});
