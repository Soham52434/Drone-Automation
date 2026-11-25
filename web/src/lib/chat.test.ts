import { describe, expect, it } from "vitest";

import type { IndexedFrame } from "../api/types";
import { groupFramesByHour } from "./chat";

const frame = (id: string, hour: string, minute: string): IndexedFrame => ({
  observation_id: id,
  timestamp_ms: 0,
  day: "2026-11-24",
  hour,
  minute,
  summary: "",
  label: "",
  confidence: 0,
  classes: [],
  scene: "",
  alert: null,
});

describe("groupFramesByHour", () => {
  it("nests frames as hour → minute in order", () => {
    const groups = groupFramesByHour([
      frame("a", "14:00", "14:01"),
      frame("b", "14:00", "14:01"),
      frame("c", "14:00", "14:07"),
      frame("d", "15:00", "15:00"),
    ]);
    expect(groups.map((g) => [g.hour, g.frames.length])).toEqual([
      ["14:00", 3],
      ["15:00", 1],
    ]);
    expect(groups[0]!.minutes.map((m) => [m.label, m.frames.length])).toEqual([
      ["14:01", 2],
      ["14:07", 1],
    ]);
  });
});
