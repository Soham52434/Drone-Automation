import { describe, expect, it } from "vitest";

import { AckStore, DEFAULT_PREFERENCES, MemoryStorage, PreferenceStore } from "./preferences";

describe("PreferenceStore", () => {
  it("defaults to popups and sound on, desktop off", () => {
    expect(new PreferenceStore(new MemoryStorage()).load()).toEqual(DEFAULT_PREFERENCES);
  });

  it("round-trips and honours the old mute flag", () => {
    const storage = new MemoryStorage();
    storage.setItem("drone-alert-mute", "1");
    const store = new PreferenceStore(storage);
    expect(store.load().sound).toBe(false);
    store.save({ popups: false, sound: true, desktop: true });
    expect(store.load()).toEqual({ popups: false, sound: true, desktop: true });
  });

  it("survives corrupt storage", () => {
    const storage = new MemoryStorage();
    storage.setItem("drone-alert-preferences", "{bad");
    expect(new PreferenceStore(storage).load()).toEqual(DEFAULT_PREFERENCES);
  });
});

describe("AckStore", () => {
  it("adds keys per session", () => {
    const acks = new AckStore(new MemoryStorage());
    acks.add("s", ["a"]);
    expect([...acks.add("s", ["b"])]).toEqual(["a", "b"]);
    expect(acks.load("t").size).toBe(0);
  });
});
