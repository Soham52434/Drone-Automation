import { describe, expect, it } from "vitest";

import {
  SUMMARY_INTERVALS,
  VIDEO_ACCEPT,
  formatInterval,
  formatIntervalShort,
  intervalAt,
  intervalIndex,
  llmPayload,
} from "./sessionSetup";

describe("session setup", () => {
  it("offers 1 minute, then every 5 minutes up to 60", () => {
    expect(SUMMARY_INTERVALS[0]).toBe(1);
    expect(SUMMARY_INTERVALS.slice(1).every((m) => m % 5 === 0)).toBe(true);
    expect(SUMMARY_INTERVALS.at(-1)).toBe(60);
    expect(SUMMARY_INTERVALS).toHaveLength(13);
  });

  it("maps slider positions to minutes and back", () => {
    expect(intervalAt(0)).toBe(1);
    expect(intervalAt(1)).toBe(5);
    expect(intervalAt(99)).toBe(60);
    expect(intervalIndex(15)).toBe(3);
    expect(intervalIndex(7)).toBe(1);
  });

  it("formats and sends the interval", () => {
    expect(formatInterval(1)).toBe("1 minute");
    expect(formatInterval(60)).toBe("1 hour");
    expect(formatIntervalShort(15)).toBe("15 min");
    expect(llmPayload({ enabled: true, summaryIntervalMinutes: 12, detailedAlerts: true, advancedAnalytics: true })).toEqual({
      enabled: true,
      summary_interval_minutes: 10,
      detailed_alerts: true,
      advanced_analytics: true,
    });
    const off = llmPayload({ enabled: false, summaryIntervalMinutes: 30, detailedAlerts: true, advancedAnalytics: true });
    expect(off.detailed_alerts).toBe(false);
    expect(off.advanced_analytics).toBe(false);
  });
});

describe("video file picker", () => {
  it("lists .mov and other containers in both cases", () => {
    for (const ext of [".mov", ".MOV", ".mp4", ".MP4", ".webm"]) expect(VIDEO_ACCEPT.split(",")).toContain(ext);
    expect(VIDEO_ACCEPT.startsWith("video/*")).toBe(true);
  });
});
