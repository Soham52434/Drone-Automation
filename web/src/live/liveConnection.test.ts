import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveConnection, LiveRegistry, waitForIceGathering } from "./liveConnection";

class FakeGatherer extends EventTarget {
  iceGatheringState: RTCIceGatheringState = "gathering";

  finish() {
    this.iceGatheringState = "complete";
    this.dispatchEvent(new Event("icegatheringstatechange"));
  }
}

afterEach(() => {
  vi.useRealTimers();
});

describe("waitForIceGathering", () => {
  it("resolves immediately when gathering is complete", async () => {
    const pc = new FakeGatherer();
    pc.iceGatheringState = "complete";
    await expect(waitForIceGathering(pc, 1000)).resolves.toBeUndefined();
  });

  it("resolves when gathering completes", async () => {
    const pc = new FakeGatherer();
    const done = waitForIceGathering(pc, 10_000);
    pc.finish();
    await expect(done).resolves.toBeUndefined();
  });

  it("resolves after the timeout if gathering stalls", async () => {
    vi.useFakeTimers();
    const pc = new FakeGatherer();
    const done = waitForIceGathering(pc, 3000);
    vi.advanceTimersByTime(3000);
    await expect(done).resolves.toBeUndefined();
  });
});

describe("LiveRegistry", () => {
  const fakeConnection = (sessionId: string) =>
    ({ sessionId, close: vi.fn() }) as unknown as LiveConnection;

  it("replaces and closes an existing connection for the same session", () => {
    const registry = new LiveRegistry();
    const first = fakeConnection("s1");
    const second = fakeConnection("s1");
    registry.add(first);
    registry.add(second);
    expect(first.close).toHaveBeenCalled();
    expect(registry.get("s1")).toBe(second);
  });

  it("closes everything on closeAll", () => {
    const registry = new LiveRegistry();
    const a = fakeConnection("a");
    const b = fakeConnection("b");
    registry.add(a);
    registry.add(b);
    registry.closeAll();
    expect(a.close).toHaveBeenCalled();
    expect(b.close).toHaveBeenCalled();
    expect(registry.get("a")).toBeUndefined();
  });
});
