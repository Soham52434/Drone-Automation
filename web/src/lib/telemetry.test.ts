import { describe, expect, it } from "vitest";

import { formatDuration, matchesClasses } from "./telemetry";

describe("telemetry helpers", () => {
  it("formats durations", () => {
    expect(formatDuration(45_000)).toBe("45 s");
    expect(formatDuration(200_000)).toBe("3 min 20 s");
    expect(formatDuration(3_840_000)).toBe("1 h 04 min");
  });

  it("filters readings by class", () => {
    const tags: [string, number][] = [["person", 0.8], ["structure", 0.4]];
    expect(matchesClasses(tags, new Set())).toBe(true);
    expect(matchesClasses(tags, new Set(["person"]))).toBe(true);
    expect(matchesClasses(tags, new Set(["vehicle"]))).toBe(false);
  });
});
