import { describe, expect, it } from "vitest";

import failureExample from "../api-examples/localise-result-failure.json";
import reliableExample from "../api-examples/localise-result-reliable.json";
import moveExample from "../api-examples/localise-result.json";
import { labelBox, overlayOf, placeLabels, type Box, type Overlay } from "./overlay";
import type { LocaliseResult, Vec2 } from "./types";

function result(example: unknown): LocaliseResult {
  return structuredClone(example) as LocaliseResult;
}

const MOVE = () => result(moveExample);
const RELIABLE = () => result(reliableExample);
const FAILURE = () => result(failureExample);

function expectPoint(actual: Vec2 | null | undefined, [x, y]: Vec2) {
  expect(actual?.[0]).toBeCloseTo(x, 9);
  expect(actual?.[1]).toBeCloseTo(y, 9);
}

describe("the overlay of a result", () => {
  it("draws an accepted result in the reliable style: target, regions and truth half a pixel on", () => {
    const reliable = RELIABLE();
    const overlay = overlayOf(reliable, reliable.truth, 20);
    expect(overlay.style).toBe("reliable");
    expect([overlay.width, overlay.height]).toEqual([1080, 1920]);
    expect(overlay.target?.outline).toBe("M688.234 1241.302 L377.288 1241.428 L380.194 931.235 L685.789 931.136 Z");
    expectPoint(overlay.target?.centre, [533.3206781773437, 1084.5045963785394]);
    expect(overlay.region).toEqual({
      cx: 533.3206781773437,
      cy: 1084.5045963785394,
      rx: 13.963260418642658,
      ry: 13.762833940757762,
      angle: 146.6159796831742,
    });
    expect(overlay.poseOnly).toMatchObject({ rx: 7.23125367089357, ry: 5.470631746617997, angle: 171.23569634015146 });
    expectPoint(overlay.truth, [532.03, 1084.81]);
    expect(overlay.observed.map((mark) => mark.kind)).toEqual(Array(7).fill("inlier"));
    expect(overlay.unobserved).toEqual([]);
  });

  it("draws a result the decision does not accept in the warning style", () => {
    expect(overlayOf(MOVE(), null, 20).style).toBe("unreliable");
    expect(overlayOf(FAILURE(), null, 20).style).toBe("unreliable");
  });

  it("pairs each click with where the pose puts it, and its error", () => {
    const handle = overlayOf(MOVE(), null, 20).observed.find((mark) => mark.id === "handle");
    expectPoint(handle?.at, [59.32, 985.08]);
    expectPoint(handle?.reprojection, [59.31, 985.37]);
    expect(handle?.kind).toBe("inlier");
    expect(handle?.errorPx).toBe(0.2890119008120772);
  });

  it("marks an outlier, and a click without a pose as neither", () => {
    const move = MOVE();
    const handle = move.observations.find((observation) => observation.landmark_id === "handle");
    if (!handle) throw new Error("the example observes the handle");
    handle.inlier = false;
    expect(overlayOf(move, null, 20).observed.find((mark) => mark.id === "handle")?.kind).toBe("outlier");

    const failed = overlayOf(FAILURE(), null, 20);
    expect(failed.observed.map((mark) => [mark.id, mark.kind, mark.reprojection, mark.errorPx])).toEqual([
      ["corner_bottom_right", "unposed", null, null],
      ["hinge_bottom", "unposed", null, null],
      ["handle", "unposed", null, null],
    ]);
    expect([failed.target, failed.region, failed.poseOnly, failed.truth]).toEqual([null, null, null, null]);
    expect(failed.unobserved).toEqual([]);
  });

  it("points at the landmarks beyond the left edge from the left border, along the line from the centre", () => {
    const overlay = overlayOf(MOVE(), null, 20);
    expect(overlay.unobserved.map((mark) => mark.id)).toEqual(["corner_top_left", "corner_bottom_left"]);
    const [top, bottom] = overlay.unobserved;
    for (const mark of overlay.unobserved) {
      expect(mark.at).toBeNull();
      expect(mark.edge?.at[0]).toBeCloseTo(20, 9);
    }
    // corner_top_left is at (−92.48, 391.11): left of the frame and above its centre.
    expect(top.edge?.angle).toBeLessThan(-90);
    expect(top.edge?.angle).toBeGreaterThan(-180);
    // corner_bottom_left is at (−89.2, 1492.1): left and below.
    expect(bottom.edge?.angle).toBeGreaterThan(90);
    expect(bottom.edge?.angle).toBeLessThan(180);
  });

  it("draws an unclicked landmark in the frame where it lands, and none behind the camera", () => {
    const move = MOVE();
    move.projections[0].pixel = null;
    move.projections[2] = { ...move.projections[2], pixel: [100, 1500], in_frame: true };
    expect(overlayOf(move, null, 20).unobserved).toEqual([{ id: "corner_bottom_left", at: [100.5, 1500.5], edge: null }]);
  });

  it("draws no truth unless the page shows one", () => {
    expect(overlayOf(RELIABLE(), null, 20).truth).toBeNull();
  });
});

describe("the labels", () => {
  // A 1080 × 1920 view drawn 720 screen pixels high: 2.67 image pixels per screen pixel.
  const k = 1920 / 720;
  const font = 12 * k;

  function place(overlay: Overlay) {
    return placeLabels(overlay, font, 9 * k, 7 * k);
  }

  function inside(box: Box, overlay: Overlay) {
    return box.left >= 0 && box.top >= 0 && box.right <= overlay.width && box.bottom <= overlay.height;
  }

  function apart(a: Box, b: Box) {
    return a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top;
  }

  it("go right of their mark where there is room, and left of it near the right edge", () => {
    const labels = place(overlayOf(RELIABLE(), null, 14 * k));
    const handle = labels.find((label) => label.id === "handle");
    expect(handle).toMatchObject({ anchor: "start", faint: false });
    expect(handle?.x).toBeCloseTo(330.66 + 9 * k, 9);
    expect(labels.find((label) => label.id === "corner_top_right")?.anchor).toBe("end");
  });

  it("stay inside the image and clear of each other", () => {
    for (const example of [MOVE(), RELIABLE(), FAILURE()]) {
      const overlay = overlayOf(example, null, 14 * k);
      const boxes = place(overlay).map((label) => labelBox(label, font));
      expect(boxes).toHaveLength(overlay.observed.length + overlay.unobserved.length);
      for (const [index, box] of boxes.entries()) {
        expect(inside(box, overlay)).toBe(true);
        for (const other of boxes.slice(index + 1)) expect(apart(box, other)).toBe(true);
      }
    }
  });

  it("label a landmark beyond the frame beside its arrow, fainter", () => {
    const overlay = overlayOf(MOVE(), null, 14 * k);
    const label = place(overlay).find((candidate) => candidate.id === "corner_top_left");
    expect(label).toMatchObject({ anchor: "start", faint: true });
    expect(label?.x).toBeCloseTo(14 * k + 9 * k, 9);
  });
});
