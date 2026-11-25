import { describe, expect, it } from "vitest";

import { AlertWatcher } from "./alertWatcher";
import type { AlertRecord } from "./analysisFeed";

const record = (key: string) => ({ key }) as AlertRecord;

describe("AlertWatcher", () => {
  it("returns only incidents it has not seen", () => {
    const watcher = new AlertWatcher();
    expect(watcher.update("s", [record("a")], false).map((r) => r.key)).toEqual(["a"]);
    expect(watcher.update("s", [record("a"), record("b")], false).map((r) => r.key)).toEqual(["b"]);
  });

  it("does not pop replayed history but remembers it", () => {
    const watcher = new AlertWatcher();
    expect(watcher.update("s", [record("old")], true)).toEqual([]);
    expect(watcher.update("s", [record("old"), record("new")], false).map((r) => r.key)).toEqual(["new"]);
  });

  it("keeps sessions apart and can forget one", () => {
    const watcher = new AlertWatcher();
    watcher.update("s", [record("a")], false);
    expect(watcher.update("t", [record("a")], false)).toHaveLength(1);
    watcher.forget("s");
    expect(watcher.update("s", [record("a")], true)).toEqual([]);
  });
});
