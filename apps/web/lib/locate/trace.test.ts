import { describe, expect, it, vi } from "vitest";

import failureExample from "../api-examples/localise-result-failure.json";
import reliableExample from "../api-examples/localise-result-reliable.json";
import moveExample from "../api-examples/localise-result.json";
import {
  MAX_STEPS,
  changeOf,
  createTraceStore,
  latestByView,
  parseTrace,
  readSelection,
  regionPx,
  shownTruth,
  traceKey,
  withStep,
  writeSelection,
  type StorageLike,
  type TraceStep,
} from "./trace";
import type { LocaliseResult } from "./types";

function result(example: unknown): LocaliseResult {
  return structuredClone(example) as LocaliseResult;
}

const MOVE = () => result(moveExample);
const RELIABLE = () => result(reliableExample);
const FAILURE = () => result(failureExample);

function step(view: string, res: LocaliseResult, truthView: string | null = null): Omit<TraceStep, "n"> {
  return { at: "2026-10-06T16:45:00+02:00", view, truthView, result: res };
}

/** sessionStorage in memory, refusing writes over `quota` characters when one is given. */
class MemoryStorage implements StorageLike {
  readonly items = new Map<string, string>();
  constructor(private readonly quota = Number.POSITIVE_INFINITY) {}
  getItem(key: string) {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    if (value.length > this.quota) throw new DOMException("quota", "QuotaExceededError");
    this.items.set(key, value);
  }
  removeItem(key: string) {
    this.items.delete(key);
  }
}

const KEY = traceKey("home-cabinet", "2026-10-06T16:05:40+02:00", "cabinet-test");

describe("traceKey", () => {
  it("is one per build of an atlas and view set", () => {
    expect(KEY).toBe("smc-locate:trace:v1:home-cabinet@2026-10-06T16:05:40+02:00/cabinet-test");
    expect(traceKey("home-cabinet", "2026-10-07T09:00:00+02:00", "cabinet-test")).not.toBe(KEY);
  });
});

describe("the steps of a trace", () => {
  it("are numbered in order, and keep the newest when there are too many", () => {
    let steps: TraceStep[] = [];
    steps = withStep(steps, step("frame_000010.png", MOVE()));
    steps = withStep(steps, step("frame_000040.png", RELIABLE()));
    expect(steps.map((entry) => [entry.n, entry.view])).toEqual([
      [1, "frame_000010.png"],
      [2, "frame_000040.png"],
    ]);
    for (let index = 0; index < MAX_STEPS + 5; index += 1) steps = withStep(steps, step("frame_000070.png", FAILURE()));
    expect(steps).toHaveLength(MAX_STEPS);
    expect(steps[0].n).toBe(8);
    expect(steps.at(-1)?.n).toBe(MAX_STEPS + 7);
  });

  it("read back from storage, leaving out anything that is not a step", () => {
    const steps = withStep([], step("frame_000040.png", RELIABLE(), "frame_000040.png"));
    expect(parseTrace(JSON.stringify(steps))).toEqual(steps);
    expect(parseTrace(JSON.stringify([...steps, { n: 2, view: "x" }, null]))).toEqual(steps);
    expect(parseTrace("{not json")).toEqual([]);
    expect(parseTrace(JSON.stringify({ steps }))).toEqual([]);
    expect(parseTrace(null)).toEqual([]);
  });

  it("know the latest result of each view", () => {
    let steps: TraceStep[] = [];
    steps = withStep(steps, step("frame_000010.png", MOVE()));
    steps = withStep(steps, step("frame_000040.png", RELIABLE()));
    steps = withStep(steps, step("frame_000010.png", MOVE(), "frame_000040.png"));
    const latest = latestByView(steps);
    expect(latest.get("frame_000010.png")?.n).toBe(3);
    expect(latest.get("frame_000040.png")?.n).toBe(2);
    expect(latest.has("frame_000070.png")).toBe(false);
  });
});

describe("the change between steps", () => {
  it("is the change of the 95 % region's semi-major axis", () => {
    expect(regionPx(MOVE())).toBeCloseTo(23.094403883551426, 12);
    expect(regionPx(FAILURE())).toBeNull();
    const change = changeOf(MOVE(), RELIABLE());
    if (change.kind !== "ratio") throw new Error(`change is ${change.kind}`);
    expect(change.percent).toBeCloseTo((100 * (13.963260418642658 - 23.094403883551426)) / 23.094403883551426, 9);
    expect(change.percent).toBeCloseTo(-39.54, 2);
    expect(change.verdict).toBe("improved");
    expect(changeOf(RELIABLE(), MOVE())).toMatchObject({ kind: "ratio", verdict: "worse" });
  });

  it("is the same when it reads 0.0 %", () => {
    const close = RELIABLE();
    if (!close.localisation.uncertainty) throw new Error("the example has a region");
    close.localisation.uncertainty.ellipse.semi_major_px *= 1.0004;
    expect(changeOf(RELIABLE(), close)).toMatchObject({ kind: "ratio", verdict: "same" });
    expect(changeOf(RELIABLE(), RELIABLE())).toEqual({ kind: "ratio", percent: 0, verdict: "same" });
  });

  it("is a region lost or found when one of the two failed, and nothing for the first step", () => {
    expect(changeOf(RELIABLE(), FAILURE())).toEqual({ kind: "lost" });
    expect(changeOf(FAILURE(), MOVE())).toEqual({ kind: "found" });
    expect(changeOf(FAILURE(), FAILURE())).toEqual({ kind: "none" });
    expect(changeOf(null, MOVE())).toEqual({ kind: "none" });
  });
});

describe("shownTruth", () => {
  it("is the truth the service gave for a chosen truth view", () => {
    expect(shownTruth({ truthView: "frame_000040.png", result: RELIABLE() })).toEqual(RELIABLE().truth);
    expect(shownTruth({ truthView: "frame_000040.png", result: MOVE() })).toBeNull();
  });

  it("is none when none was chosen, though the service falls back to the view's own click", () => {
    expect(shownTruth({ truthView: null, result: RELIABLE() })).toBeNull();
  });
});

describe("the trace store", () => {
  it("keeps the steps in the storage, so a reload reads them back", () => {
    const storage = new MemoryStorage();
    const store = createTraceStore(() => storage);
    const listener = vi.fn();
    store.subscribe(listener);
    expect(store.append(KEY, step("frame_000010.png", MOVE())).n).toBe(1);
    expect(store.append(KEY, step("frame_000040.png", RELIABLE(), "frame_000040.png")).n).toBe(2);
    expect(listener).toHaveBeenCalledTimes(2);

    const reloaded = createTraceStore(() => storage);
    expect(reloaded.steps(KEY).map((entry) => [entry.n, entry.view, entry.truthView])).toEqual([
      [1, "frame_000010.png", null],
      [2, "frame_000040.png", "frame_000040.png"],
    ]);
    expect(reloaded.steps(KEY)[1].result).toEqual(RELIABLE());
  });

  it("gives the same array until the trace changes", () => {
    const store = createTraceStore(() => new MemoryStorage());
    const empty = store.steps(KEY);
    expect(store.steps(KEY)).toBe(empty);
    store.append(KEY, step("frame_000010.png", MOVE()));
    const one = store.steps(KEY);
    expect(one).not.toBe(empty);
    expect(store.steps(KEY)).toBe(one);
  });

  it("keeps each atlas and set apart, and clears one", () => {
    const storage = new MemoryStorage();
    const store = createTraceStore(() => storage);
    const other = traceKey("home-cabinet", "2026-10-06T16:05:40+02:00", "cabinet");
    store.append(KEY, step("frame_000010.png", MOVE()));
    store.append(other, step("frame_000000.png", RELIABLE()));
    store.clear(KEY);
    expect(store.steps(KEY)).toEqual([]);
    expect(storage.items.has(KEY)).toBe(false);
    expect(store.steps(other)).toHaveLength(1);
    // Numbering starts again after a clear.
    expect(store.append(KEY, step("frame_000040.png", RELIABLE())).n).toBe(1);
  });

  it("stores the newest steps that fit when the storage is full, and keeps all of them for the page", () => {
    const one = JSON.stringify(withStep([], step("frame_000010.png", MOVE()))).length;
    const storage = new MemoryStorage(one * 2.5);
    const store = createTraceStore(() => storage);
    for (let index = 0; index < 4; index += 1) store.append(KEY, step(`frame_00000${index}.png`, MOVE()));
    expect(store.steps(KEY)).toHaveLength(4);
    expect(parseTrace(storage.getItem(KEY)).map((entry) => entry.n)).toEqual([3, 4]);
  });

  it("works without a storage, for the page only", () => {
    const store = createTraceStore(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(store.steps(KEY)).toEqual([]);
    store.append(KEY, step("frame_000010.png", MOVE()));
    expect(store.steps(KEY)).toHaveLength(1);
  });
});

describe("the selection of the tab", () => {
  it("is read back as written", () => {
    const storage = new MemoryStorage();
    expect(readSelection(storage)).toBeNull();
    writeSelection(storage, { asset: "home-cabinet", set: "cabinet-test" });
    expect(readSelection(storage)).toEqual({ asset: "home-cabinet", set: "cabinet-test" });
    writeSelection(storage, { asset: "home-cabinet", set: null });
    expect(readSelection(storage)).toEqual({ asset: "home-cabinet", set: null });
  });

  it("is nothing when the storage holds something else or cannot be read", () => {
    const storage = new MemoryStorage();
    storage.setItem("smc-locate:selection:v1", "[1, 2]");
    expect(readSelection(storage)).toBeNull();
    expect(readSelection(null)).toBeNull();
    expect(() => writeSelection(new MemoryStorage(1), { asset: "a", set: "b" })).not.toThrow();
  });
});
