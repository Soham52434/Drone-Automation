import type { Session } from "../api/types";

export interface SessionGroup {
  label: string;
  sessions: Session[];
}

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(ms: number): number {
  const date = new Date(ms);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

function labelFor(createdMs: number, todayStart: number): string {
  if (createdMs >= todayStart) return "Today";
  if (createdMs >= todayStart - DAY_MS) return "Yesterday";
  if (createdMs >= todayStart - 7 * DAY_MS) return "Previous 7 days";
  return "Older";
}

/** Groups sessions like a chat sidebar, newest first within each group. */
export function groupSessions(sessions: Session[], nowMs: number = Date.now()): SessionGroup[] {
  const todayStart = startOfDay(nowMs);
  const groups = new Map<string, Session[]>();
  const sorted = [...sessions].sort((a, b) => b.created_ms - a.created_ms);
  for (const session of sorted) {
    const label = labelFor(session.created_ms, todayStart);
    groups.set(label, [...(groups.get(label) ?? []), session]);
  }
  return [...groups.entries()].map(([label, items]) => ({ label, sessions: items }));
}
