import { describe, expect, it } from "vitest";

import type { EventSourceLike } from "./feedHub";
import { SessionListStream, parseSessions } from "./sessionStream";

class FakeSource implements EventSourceLike {
  closed = false;
  listener: ((event: MessageEvent) => void) | null = null;
  constructor(readonly url: string) {}
  addEventListener(_type: string, listener: (event: MessageEvent) => void) {
    this.listener = listener;
  }
  close() {
    this.closed = true;
  }
}

describe("SessionListStream", () => {
  it("delivers each pushed list and ignores bad payloads", () => {
    const sources: FakeSource[] = [];
    const stream = new SessionListStream((url) => {
      const source = new FakeSource(url);
      sources.push(source);
      return source;
    });
    const seen: number[] = [];
    stream.open((sessions) => seen.push(sessions.length));
    sources[0]!.listener!({ data: JSON.stringify([{ id: "a" }, { id: "b" }]) } as MessageEvent);
    sources[0]!.listener!({ data: "{oops" } as MessageEvent);
    expect(sources[0]!.url).toBe("/api/sessions/stream");
    expect(seen).toEqual([2]);
    stream.close();
    expect(sources[0]!.closed).toBe(true);
  });

  it("parses only arrays", () => {
    expect(parseSessions("[]")).toEqual([]);
    expect(parseSessions('{"id": 1}')).toBeNull();
  });
});
