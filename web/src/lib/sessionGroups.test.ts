import { describe, expect, it } from "vitest";

import type { Session } from "../api/types";
import { groupSessions } from "./sessionGroups";

const DAY = 24 * 60 * 60 * 1000;
const now = new Date(2026, 10, 24, 15, 0, 0).getTime();

function session(id: string, createdMs: number): Session {
  return {
    id,
    kind: "live",
    title: id,
    status: "idle",
    llm: { enabled: false, summary_interval_minutes: 60, detailed_alerts: false, advanced_analytics: false },
    created_ms: createdMs,
    duration_ms: null,
    source_url: null,
    watch_brief: "Person detection, vehicle detection, and other alarms.",
  };
}

describe("groupSessions", () => {
  it("buckets sessions by recency in chat-sidebar order", () => {
    const groups = groupSessions(
      [session("old", now - 30 * DAY), session("today", now - 60_000), session("yesterday", now - DAY), session("week", now - 3 * DAY)],
      now,
    );
    expect(groups.map((g) => g.label)).toEqual(["Today", "Yesterday", "Previous 7 days", "Older"]);
    expect(groups.map((g) => g.sessions[0].id)).toEqual(["today", "yesterday", "week", "old"]);
  });

  it("sorts newest first within a group", () => {
    const groups = groupSessions([session("a", now - 3_600_000), session("b", now - 60_000)], now);
    expect(groups[0].sessions.map((s) => s.id)).toEqual(["b", "a"]);
  });

  it("returns no groups for no sessions", () => {
    expect(groupSessions([], now)).toEqual([]);
  });
});
