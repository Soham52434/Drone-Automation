import type { Session } from "../api/types";
import type { EventSourceFactory, EventSourceLike } from "./feedHub";

/**
 * The session list, pushed by the server: once on connect, then on every create, status change,
 * or delete. Replaces polling. EventSource reconnects by itself and gets a fresh snapshot.
 */
export class SessionListStream {
  private source: EventSourceLike | null = null;

  constructor(private readonly factory: EventSourceFactory = (url) => new EventSource(url)) {}

  open(onSessions: (sessions: Session[]) => void): void {
    this.close();
    const source = this.factory("/api/sessions/stream");
    source.addEventListener("sessions", (message: MessageEvent) => {
      const sessions = parseSessions(message.data);
      if (sessions) onSessions(sessions);
    });
    this.source = source;
  }

  close(): void {
    this.source?.close();
    this.source = null;
  }
}

export function parseSessions(data: unknown): Session[] | null {
  try {
    const value = JSON.parse(String(data)) as unknown;
    return Array.isArray(value) ? (value as Session[]) : null;
  } catch {
    return null;
  }
}
