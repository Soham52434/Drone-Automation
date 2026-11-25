import { describe, expect, it } from "vitest";

import type { Chunk } from "../api/types";
import { chunkPlaybackUrl, describeChunk, formatMediaTime, formatTimeline } from "./format";

const chunk: Chunk = {
  chunk_file: "chunk_2000.mp4",
  chunk_start_ms: 2000,
  chunk_end_ms: 12000,
  detection_ms: 10000,
  seek_offset_sec: 8,
  duration_sec: 10,
  frame_count: 150,
  fps: 15,
  trigger: "manual",
  created_ms: 0,
  video_url: "/api/sessions/s1/chunks/chunk_2000.mp4",
  metadata_url: "/api/sessions/s1/chunks/chunk_2000.json",
};

describe("formatMediaTime", () => {
  it.each([
    [0, "0:00"],
    [9_500, "0:09"],
    [75_000, "1:15"],
    [3_725_000, "1:02:05"],
  ])("formats %i ms as %s", (ms, expected) => {
    expect(formatMediaTime(ms)).toBe(expected);
  });
});

describe("timeline formatting", () => {
  it("uses media position for uploads", () => {
    expect(formatTimeline("upload", 75_000)).toBe("1:15");
  });

  it("uses clock time for live sessions", () => {
    expect(formatTimeline("live", Date.UTC(2026, 0, 1, 12, 30, 5), "en-GB")).toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it("describes a saved upload clip", () => {
    expect(describeChunk("upload", chunk)).toBe("Clip saved at 0:10 · 10.0 s · 150 frames");
  });

  it("builds a playback URL that seeks to the detection", () => {
    expect(chunkPlaybackUrl(chunk)).toBe("/api/sessions/s1/chunks/chunk_2000.mp4#t=8.00");
  });
});
