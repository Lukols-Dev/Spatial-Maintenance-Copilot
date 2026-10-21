import { describe, expect, it } from "vitest";

import failureExample from "../api-examples/localise-result-failure.json";
import reliableExample from "../api-examples/localise-result-reliable.json";
import moveExample from "../api-examples/localise-result.json";
import { changeOf, latestByView, regionPx, shownTruth, type TraceStep } from "./trace";
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


describe("the latest step of each view", () => {
  it("is the last one taken from that view", () => {
    const steps: TraceStep[] = [
      { n: 1, ...step("frame_000010.png", MOVE()) },
      { n: 2, ...step("frame_000040.png", RELIABLE()) },
      { n: 3, ...step("frame_000010.png", MOVE(), "frame_000040.png") },
    ];
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
