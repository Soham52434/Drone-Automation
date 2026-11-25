import type { AlertRecord } from "./analysisFeed";

/** Remembers which incidents each session has already shown, so only new ones pop up. */
export class AlertWatcher {
  private readonly known = new Map<string, Set<string>>();

  /**
   * Record what the session shows now. Returns the incidents that are new since the last call,
   * or nothing while the feed is still replaying history.
   */
  update(sessionId: string, records: readonly AlertRecord[], replaying: boolean): AlertRecord[] {
    const seen = this.known.get(sessionId) ?? new Set<string>();
    this.known.set(sessionId, seen);
    const fresh = records.filter((record) => !seen.has(record.key));
    for (const record of fresh) seen.add(record.key);
    return replaying ? [] : fresh;
  }

  forget(sessionId: string): void {
    this.known.delete(sessionId);
  }
}
