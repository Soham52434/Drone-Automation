import { describe, expect, it } from "vitest";

import { type EventSourceLike, SessionFeedHub } from "./feedHub";

class FakeSource implements EventSourceLike {
  closed = false;
  private readonly listeners = new Map<string, (event: MessageEvent) => void>();
  constructor(readonly url: string) {}
  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.set(type, listener);
  }
  close() {
    this.closed = true;
  }
  emit(type: string, data: unknown) {
    this.listeners.get(type)?.({ type, data: JSON.stringify(data) } as MessageEvent);
  }
}

function setup() {
  const sources: FakeSource[] = [];
  let now = 0;
  const hub = new SessionFeedHub(
    (url) => {
      const source = new FakeSource(url);
      sources.push(source);
      return source;
    },
    () => now,
    1000,
  );
  return { hub, sources, tick: (ms: number) => (now += ms) };
}

describe("SessionFeedHub", () => {
  it("opens one feed per session and closes feeds that are no longer wanted", () => {
    const { hub, sources } = setup();
    hub.sync([{ id: "a", kind: "live" }, { id: "b", kind: "upload" }]);
    hub.sync([{ id: "a", kind: "live" }]);
    expect(sources.map((source) => source.url)).toEqual(["/api/sessions/a/events", "/api/sessions/b/events"]);
    expect(sources[1]?.closed).toBe(true);
    expect(hub.watching("a")).toBe(true);
    expect(hub.watching("b")).toBe(false);
  });

  it("collects entries and notifies subscribers", () => {
    const { hub, sources } = setup();
    const seen: string[] = [];
    hub.subscribe((id) => seen.push(id));
    hub.sync([{ id: "a", kind: "live" }]);
    sources[0]!.emit("status", { status: "live", detail: "The vision model is watching" });
    sources[0]!.emit("observation", "not json");
    expect(hub.entries("a").map((entry) => entry.kind)).toEqual(["status"]);
    expect(seen).toEqual(["a"]);
  });

  it("keeps the latest pushed live stats without adding feed entries", () => {
    const { hub, sources } = setup();
    hub.sync([{ id: "a", kind: "live" }]);
    sources[0]!.emit("stats", { frames_received: 10, frames_buffered: 9, buffered_seconds: 1.5, latest_timestamp_ms: 5 });
    sources[0]!.emit("stats", { frames_received: 12, frames_buffered: 9, buffered_seconds: 1.6, latest_timestamp_ms: 6 });
    expect(hub.stats("a")?.frames_received).toBe(12);
    expect(hub.entries("a")).toEqual([]);
    expect(hub.stats("missing")).toBeNull();
  });

  it("treats the first moments after opening as replayed history", () => {
    const { hub, tick } = setup();
    hub.sync([{ id: "a", kind: "live" }]);
    expect(hub.isReplaying("a")).toBe(true);
    tick(1500);
    expect(hub.isReplaying("a")).toBe(false);
  });

  it("ignores events from a closed feed", () => {
    const { hub, sources } = setup();
    hub.sync([{ id: "a", kind: "live" }]);
    hub.closeAll();
    sources[0]!.emit("status", { status: "live" });
    expect(hub.entries("a")).toEqual([]);
  });
});
