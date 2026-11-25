import type { LiveStats, SessionKind } from "../api/types";
import { type AnalysisEntry, analysisEntry } from "./analysisFeed";

export interface EventSourceLike {
  addEventListener(type: string, listener: (event: MessageEvent) => void): void;
  close(): void;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

export interface WatchedSession {
  id: string;
  kind: SessionKind;
}

const EVENT_NAMES = ["observation", "decision", "alert", "status", "error", "summary", "stats"] as const;
const MAX_OBSERVATIONS = 600;

interface Feed {
  source: EventSourceLike;
  kind: SessionKind;
  entries: AnalysisEntry[];
  seq: number;
  openedAt: number;
  /** Latest live buffer readout, pushed once a second while a camera streams. */
  stats: LiveStats | null;
}

/**
 * One Server-Sent Events connection per watched session, shared by the whole UI.
 *
 * The server replays its recent events when a connection opens; entries that arrive
 * inside `replayMs` of opening are history, not news, so they never raise a popup.
 */
export class SessionFeedHub {
  private readonly feeds = new Map<string, Feed>();
  private readonly listeners = new Set<(sessionId: string) => void>();

  constructor(
    private readonly factory: EventSourceFactory = (url) => new EventSource(url),
    private readonly clock: () => number = () => Date.now(),
    private readonly replayMs = 1200,
  ) {}

  /** Open feeds for these sessions and close every other one. */
  sync(sessions: readonly WatchedSession[]): void {
    const wanted = new Map(sessions.map((session) => [session.id, session]));
    for (const id of [...this.feeds.keys()]) {
      if (!wanted.has(id)) this.close(id);
    }
    for (const session of wanted.values()) {
      if (!this.feeds.has(session.id)) this.open(session);
    }
  }

  entries(sessionId: string): readonly AnalysisEntry[] {
    return this.feeds.get(sessionId)?.entries ?? [];
  }

  stats(sessionId: string): LiveStats | null {
    return this.feeds.get(sessionId)?.stats ?? null;
  }

  watching(sessionId: string): boolean {
    return this.feeds.has(sessionId);
  }

  isReplaying(sessionId: string): boolean {
    const feed = this.feeds.get(sessionId);
    return feed !== undefined && this.clock() - feed.openedAt < this.replayMs;
  }

  subscribe(listener: (sessionId: string) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  close(sessionId: string): void {
    this.feeds.get(sessionId)?.source.close();
    this.feeds.delete(sessionId);
  }

  closeAll(): void {
    for (const id of [...this.feeds.keys()]) this.close(id);
  }

  private open(session: WatchedSession): void {
    const source = this.factory(`/api/sessions/${session.id}/events`);
    const feed: Feed = { source, kind: session.kind, entries: [], seq: 0, openedAt: this.clock(), stats: null };
    this.feeds.set(session.id, feed);
    const onEvent = (message: MessageEvent) => this.receive(session.id, feed, message);
    for (const name of EVENT_NAMES) source.addEventListener(name, onEvent);
  }

  private receive(sessionId: string, feed: Feed, message: MessageEvent): void {
    if (this.feeds.get(sessionId) !== feed) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(String(message.data));
    } catch {
      return;
    }
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return;
    const data = parsed as Record<string, unknown>;
    if (message.type === "stats") {
      feed.stats = data as unknown as LiveStats;
      for (const listener of this.listeners) listener(sessionId);
      return;
    }
    const entry = analysisEntry(message.type, data, feed.seq, feed.kind);
    feed.seq += 1;
    if (!entry) return;
    feed.entries = trimObservations([...feed.entries, entry]);
    for (const listener of this.listeners) listener(sessionId);
  }
}

function trimObservations(entries: AnalysisEntry[]): AnalysisEntry[] {
  let excess = entries.filter((entry) => entry.kind === "observation").length - MAX_OBSERVATIONS;
  if (excess <= 0) return entries;
  return entries.filter((entry) => {
    if (excess > 0 && entry.kind === "observation") {
      excess -= 1;
      return false;
    }
    return true;
  });
}
