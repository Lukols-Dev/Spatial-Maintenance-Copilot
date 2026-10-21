import { describe, expect, it } from "vitest";

import openExample from "../api-examples/frame-answer-open.json";
import moveExample from "../api-examples/frame-answer-move.json";
import reliableExample from "../api-examples/frame-answer.json";
import { IN_SIGHT, cueOf, moveOf, sightingWords, verdictOf, wordsOf } from "./moves";
import { landscape } from "./sources";
import { guideOverlayOf } from "./overlay";
import { Steady } from "./steady";
import type { FrameAnswer, TargetSighting } from "./types";

const answer = (example: unknown) => structuredClone(example) as FrameAnswer;
/** The open panel's frame as the policy refuses it: the tag found, a move still decided. */
const refusedOpen = (): FrameAnswer => ({ ...answer(openExample), decision: answer(moveExample).decision });
/** The open panel's frame with a 95 % region the policy finds too wide: any tag would lie inside it. */
function wideOpen(): FrameAnswer {
  const frame = answer(openExample);
  frame.decision.checks = frame.decision.checks.map((check) =>
    check.name === "region_ratio" ? { ...check, value: 3.2, passed: false } : check,
  );
  return frame;
}
/** The open panel's frame with its tag changed. */
function sightedOpen(change: Partial<TargetSighting>): FrameAnswer {
  const frame = answer(openExample);
  return { ...frame, sighting: { ...(frame.sighting as TargetSighting), ...change } };
}

describe("the camera's size as asked for", () => {
  it("is landscape whatever the calibration's orientation: phones turn it for a phone held upright", () => {
    expect(landscape({ width: 1080, height: 1920 })).toEqual({ width: 1920, height: 1080 });
    expect(landscape({ width: 1920, height: 1080 })).toEqual({ width: 1920, height: 1080 });
    expect(landscape({ width: 640, height: 480 })).toEqual({ width: 640, height: 480 });
  });
});

describe("the moves", () => {
  it("point the arrow the camera's way, and say it", () => {
    expect(moveOf("MOVE_LEFT")).toMatchObject({ words: "Move left", angle: 180 });
    expect(moveOf("MOVE_DOWN").angle).toBe(90);
    expect(moveOf("MOVE_CLOSER").angle).toBeNull();
    expect(moveOf("ACCEPT").words).toBe("Hold still");
    // A blurred frame asks for the same view again, and says why.
    expect(moveOf("HOLD_STILL")).toMatchObject({ words: "Hold steady, the frame is blurred", angle: null });
  });
});

describe("the target in sight", () => {
  it("is a frame's cue whenever its tag is found, whatever the policy decided", () => {
    expect(cueOf(refusedOpen())).toBe(IN_SIGHT);
    expect(cueOf(answer(openExample))).toBe(IN_SIGHT);
    expect(cueOf(answer(moveExample))).toBe("MOVE_DOWN");
    expect(wordsOf(IN_SIGHT)).toBe("Target in sight");
    expect(wordsOf("MOVE_LEFT")).toBe("Move left");
  });

  it("confirms the prediction only inside a 95 % region the policy finds tight, and says how far off it is", () => {
    const said = (frame: FrameAnswer) => [verdictOf(frame), sightingWords(frame)];
    expect(said(answer(openExample))).toEqual(["confirmed", "1.1 px from the prediction, inside the 95 % region"]);
    expect(said(refusedOpen())[0]).toBe("confirmed");
    expect(said(sightedOpen({ error_px: 12.04, inside_95: false }))).toEqual([
      "outside",
      "12.0 px from the prediction, outside the 95 % region",
    ]);
    expect(said(wideOpen())).toEqual(["uncertain", "1.1 px from the prediction, too uncertain to tell"]);
    expect(verdictOf(sightedOpen({ inside_95: null }))).toBe("uncertain");
    expect(said(sightedOpen({ error_px: null, inside_95: null }))).toEqual([
      "unlocalised",
      "Not localised in this frame: no prediction to compare",
    ]);
    expect(verdictOf(answer(moveExample))).toBeNull();
  });
});

describe("a steady decision", () => {
  it("is taken once it has held for three frames in a row", () => {
    const steady = new Steady();
    expect([steady.push("MOVE_LEFT"), steady.push("MOVE_LEFT"), steady.push("MOVE_LEFT")]).toEqual([
      null,
      null,
      "MOVE_LEFT",
    ]);
    expect(steady.value).toBe("MOVE_LEFT");
  });

  it("is not flipped by a frame or two, and changes only when another holds", () => {
    const steady = new Steady(2);
    steady.push("MOVE_LEFT");
    steady.push("MOVE_LEFT");
    expect(steady.push("ACCEPT")).toBeNull();
    expect(steady.push("MOVE_LEFT")).toBeNull();
    expect(steady.value).toBe("MOVE_LEFT");
    steady.push("ACCEPT");
    expect(steady.push("ACCEPT")).toBe("ACCEPT");
    steady.reset();
    expect(steady.value).toBeNull();
  });
});

describe("the overlay of a frame", () => {
  it("draws the panel the target is behind, and the box through it", () => {
    const overlay = guideOverlayOf(answer(reliableExample));
    expect(overlay.style).toBe("reliable");
    expect(overlay.occluder?.id).toBe("door");
    expect(overlay.target?.hidden).toBe(true);
    expect(overlay.target?.edges.match(/M/g)).toHaveLength(12);
    expect(overlay.marks).toHaveLength(24);
    expect(overlay.tag).toBeNull();
  });

  it("draws an unreliable frame in the warning style", () => {
    expect(guideOverlayOf(answer(moveExample)).style).toBe("unreliable");
  });

  it("shows the box in plain sight and its tag once the panel is open", () => {
    const overlay = guideOverlayOf(answer(openExample));
    expect(overlay.target?.hidden).toBe(false);
    expect(overlay.tag?.inside).toBe(true);
  });

  it("takes the tag's word over the policy's once it is in sight", () => {
    expect(guideOverlayOf(refusedOpen()).style).toBe("reliable");
    expect(guideOverlayOf(wideOpen()).style).toBe("unreliable");
    expect(guideOverlayOf(sightedOpen({ inside_95: false })).style).toBe("unreliable");
  });
});
