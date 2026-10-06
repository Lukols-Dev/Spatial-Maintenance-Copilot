import { describe, expect, it } from "vitest";

import example from "./clicks.example.json";
import {
  addPoint,
  centreOfPixel,
  clickAt,
  countsPerPoint,
  createState,
  fitView,
  fromJson,
  fromOpenCv,
  imageToScreen,
  markedInImage,
  nextUnplaced,
  panBy,
  place,
  removePoint,
  renamePoint,
  restore,
  screenToImage,
  stepPoint,
  toJson,
  toOpenCv,
  unplace,
  zoomAt,
  type AnnotationState,
} from "./core";

function withPoints(...names: string[]): AnnotationState {
  let state = createState();
  for (const name of names) {
    const outcome = addPoint(state, name);
    if (!outcome.ok) throw new Error(outcome.error);
    state = outcome.state;
  }
  return state;
}

describe("view", () => {
  it("fitView centres the whole image in the canvas", () => {
    const view = fitView(1080, 1920, 800, 600);
    expect(view.scale).toBeCloseTo(600 / 1920, 12);
    expect(view.y).toBeCloseTo(0, 12);
    expect(view.x).toBeCloseTo((800 - 1080 * view.scale) / 2, 12);
  });

  it("screen and image coordinates are inverses of each other", () => {
    const view = { scale: 2.5, x: -130, y: 42 };
    const [sx, sy] = imageToScreen(view, 523.4, 1201.7);
    const [ix, iy] = screenToImage(view, sx, sy);
    expect(ix).toBeCloseTo(523.4, 9);
    expect(iy).toBeCloseTo(1201.7, 9);
  });

  it("zoomAt keeps the image point under the cursor where it was", () => {
    const view = { scale: 0.4, x: 100, y: 20 };
    const before = screenToImage(view, 300, 200);
    const zoomed = zoomAt(view, 3, 300, 200, 0.1, 40);
    const after = screenToImage(zoomed, 300, 200);
    expect(after[0]).toBeCloseTo(before[0], 9);
    expect(after[1]).toBeCloseTo(before[1], 9);
    expect(zoomed.scale).toBeCloseTo(1.2, 12);
  });

  it("zoomAt stops at the limits", () => {
    const view = { scale: 30, x: 0, y: 0 };
    expect(zoomAt(view, 10, 0, 0, 0.1, 40).scale).toBe(40);
    expect(zoomAt(view, 1e-9, 0, 0, 0.1, 40).scale).toBe(0.1);
  });

  it("panBy moves the image without scaling it", () => {
    expect(panBy({ scale: 2, x: 10, y: 10 }, 5, -3)).toEqual({ scale: 2, x: 15, y: 7 });
  });

  it("a click on the centre of the first pixel is (0, 0) in OpenCV", () => {
    expect(toOpenCv(0.5, 0.5)).toEqual([0, 0]);
    expect(fromOpenCv(0, 0)).toEqual([0.5, 0.5]);
    const [x, y] = fromOpenCv(...toOpenCv(12.25, 99.75));
    expect(x).toBeCloseTo(12.25, 12);
    expect(y).toBeCloseTo(99.75, 12);
  });

  it("centreOfPixel moves a whole-pixel mouse position to the pixel centre", () => {
    expect(centreOfPixel(10)).toBe(10.5);
    expect(centreOfPixel(10.25)).toBe(10.25);
  });
});

describe("points and clicks", () => {
  it("place stores OpenCV pixels rounded to a hundredth", () => {
    const state = place(withPoints("corner"), "a.png", "corner", 100.5 + 0.123456, 200.5 + 0.987654);
    expect(clickAt(state, "a.png", "corner")).toEqual([100.12, 200.99]);
  });

  it("place ignores a point that does not exist", () => {
    const state = withPoints("corner");
    expect(place(state, "a.png", "ghost", 1, 1)).toBe(state);
  });

  it("changes return a new state and leave the old one alone", () => {
    const before = withPoints("a");
    const after = place(before, "v.png", "a", 10.5, 20.5);
    expect(before.clicks).toEqual({});
    expect(clickAt(after, "v.png", "a")).toEqual([10, 20]);
  });

  it("point names are checked", () => {
    const state = withPoints("corner_top-left.1");
    expect(addPoint(createState(), "  corner_top-left.1 ")).toMatchObject({ ok: true, name: "corner_top-left.1" });
    expect(addPoint(state, "corner_top-left.1").ok).toBe(false);
    expect(addPoint(state, "").ok).toBe(false);
    expect(addPoint(state, "two words").ok).toBe(false);
    expect(addPoint(state, "_leading").ok).toBe(false);
  });

  it("renamePoint carries the clicks along and refuses a taken name", () => {
    const state = place(withPoints("a", "b"), "v.png", "a", 10.5, 20.5);
    expect(renamePoint(state, "a", "b").ok).toBe(false);
    const outcome = renamePoint(state, "a", "c");
    if (!outcome.ok) throw new Error(outcome.error);
    expect(outcome.state.points).toEqual(["c", "b"]);
    expect(clickAt(outcome.state, "v.png", "c")).toEqual([10, 20]);
    expect(clickAt(outcome.state, "v.png", "a")).toBeNull();
  });

  it("renamePoint refuses a point that does not exist", () => {
    expect(renamePoint(withPoints("a"), "ghost", "b")).toEqual({ ok: false, error: '"ghost" does not exist.' });
  });

  it("removePoint deletes its clicks and drops images left empty", () => {
    let state = withPoints("a", "b");
    state = place(state, "one.png", "a", 1, 1);
    state = place(state, "two.png", "a", 1, 1);
    state = place(state, "two.png", "b", 2, 2);
    state = removePoint(state, "a");
    expect(state.points).toEqual(["b"]);
    expect(Object.keys(state.clicks)).toEqual(["two.png"]);
    expect(Object.keys(state.clicks["two.png"])).toEqual(["b"]);
  });

  it("unplace removes one click", () => {
    const state = unplace(place(withPoints("a"), "v.png", "a", 5, 5), "v.png", "a");
    expect(clickAt(state, "v.png", "a")).toBeNull();
    expect(state.clicks).toEqual({});
  });

  it("countsPerPoint counts the images a point is marked in", () => {
    let state = withPoints("a", "b", "c");
    state = place(state, "1.png", "a", 1, 1);
    state = place(state, "2.png", "a", 1, 1);
    state = place(state, "2.png", "b", 1, 1);
    expect(countsPerPoint(state)).toEqual({ a: 2, b: 1, c: 0 });
    expect(markedInImage(state, "2.png")).toEqual(["a", "b"]);
  });

  it("stepPoint wraps round in both directions", () => {
    const state = withPoints("a", "b", "c");
    expect(stepPoint(state, "c", 1)).toBe("a");
    expect(stepPoint(state, "a", -1)).toBe("c");
    expect(stepPoint(createState(), null, 1)).toBeNull();
  });

  it("stepPoint without a current point starts at the first or the last", () => {
    const state = withPoints("a", "b", "c");
    expect(stepPoint(state, null, 1)).toBe("a");
    expect(stepPoint(state, null, -1)).toBe("c");
  });

  it("nextUnplaced skips points already marked in the image", () => {
    let state = withPoints("a", "b", "c", "d");
    state = place(state, "v.png", "a", 1, 1);
    state = place(state, "v.png", "b", 1, 1);
    expect(nextUnplaced(state, "v.png", "b")).toBe("c");
    state = place(state, "v.png", "c", 1, 1);
    expect(nextUnplaced(state, "v.png", "c")).toBe("d");
    state = place(state, "v.png", "d", 1, 1);
    expect(nextUnplaced(state, "v.png", "d")).toBeNull();
  });
});

describe("files", () => {
  it("toJson writes the clicks file layout, sorted, without empty images", () => {
    let state = withPoints("badge", "drone");
    state = { ...state, cameraId: "phone-1x" };
    state = place(state, "view_2.png", "drone", 300.5, 400.5);
    state = place(state, "view_1.png", "drone", 10.5, 20.5);
    state = place(state, "view_1.png", "badge", 50.5, 60.5);
    const json = toJson(state);
    expect(Object.keys(json.views)).toEqual(["view_1.png", "view_2.png"]);
    expect(Object.keys(json)).toEqual(["camera_id", "points", "views"]);
    expect(json).toEqual({
      camera_id: "phone-1x",
      points: ["badge", "drone"],
      views: {
        "view_1.png": { badge: [50, 60], drone: [10, 20] },
        "view_2.png": { drone: [300, 400] },
      },
    });
  });

  it("toJson lists every point, in its order, also those not marked anywhere", () => {
    let state = withPoints("zeta", "alpha", "middle");
    state = place(state, "v.png", "middle", 1.5, 2.5);
    expect(toJson(state).points).toEqual(["zeta", "alpha", "middle"]);
  });

  it("a clicks file reads back as the state it was written from", () => {
    let state = { ...withPoints("zeta", "alpha", "middle", "spare"), cameraId: "phone-1x" };
    state = place(state, "b.png", "middle", 10.5, 20.5);
    state = place(state, "a.png", "alpha", 30.25, 40.75);
    state = place(state, "a.png", "middle", 50.5, 60.5);
    const file = JSON.parse(JSON.stringify(toJson(state)));
    const result = fromJson(createState(), file);
    expect(result.state).toEqual(state);
    expect(result.state.points).toEqual(["zeta", "alpha", "middle", "spare"]);
    expect(result.pointsAdded).toBe(4);
  });

  it("toJson matches the example the Python atlas builder is tested against", () => {
    // packages/smc_core is checked against the same file (tests/test_clicks_example.py),
    // so a change in either format breaks one of the two suites.
    let state = { ...withPoints("corner_top_left", "drone"), cameraId: "phone-1x-portrait" };
    state = place(state, "view_0.png", "corner_top_left", 100.5, 200.5);
    state = place(state, "view_0.png", "drone", 300.25, 400.75);
    state = place(state, "view_1.png", "drone", 310.5, 410.5);
    expect(toJson(state)).toEqual(example);
    expect(fromJson(createState(), example).state).toEqual(state);
  });

  it("fromJson merges clicks and adds the points it meets", () => {
    const result = fromJson(withPoints("badge"), {
      camera_id: "phone-1x",
      views: { "a.png": { badge: [1.5, 2.5], drone: [3, 4] } },
    });
    expect(result.images).toBe(1);
    expect(result.pointsAdded).toBe(1);
    expect(result.state.points).toEqual(["badge", "drone"]);
    expect(result.state.cameraId).toBe("phone-1x");
    expect(clickAt(result.state, "a.png", "drone")).toEqual([3, 4]);
  });

  it("fromJson takes the points list first, then clicked points it does not name", () => {
    const result = fromJson(withPoints("handle"), {
      camera_id: "phone-1x",
      points: ["hinge", "handle", "unmarked"],
      views: { "a.png": { stray: [1, 2], hinge: [3, 4] }, "b.png": { other: [5, 6] } },
    });
    expect(result.state.points).toEqual(["handle", "hinge", "unmarked", "stray", "other"]);
    expect(result.pointsAdded).toBe(4);
    expect(clickAt(result.state, "a.png", "stray")).toEqual([1, 2]);
  });

  it("fromJson reads a file without a points list, as older files are", () => {
    const result = fromJson(createState(), {
      camera_id: "phone-1x",
      views: { "a.png": { drone: [3, 4], badge: [1, 2] }, "b.png": { corner: [5, 6] } },
    });
    expect(result.state.points).toEqual(["drone", "badge", "corner"]);
    expect(result.images).toBe(2);
  });

  it("fromJson refuses a malformed points list and leaves the state alone", () => {
    const state = withPoints("badge");
    const file = (points: unknown) => ({ camera_id: "", points, views: { "a.png": { badge: [1, 2] } } });
    expect(() => fromJson(state, file("badge"))).toThrow('"points": expected a list of point names.');
    expect(() => fromJson(state, file(null))).toThrow('"points": expected a list of point names.');
    expect(() => fromJson(state, file(["badge", 7]))).toThrow('"points": expected a list of point names.');
    expect(() => fromJson(state, file(["badge", ""]))).toThrow('"points": expected a list of point names.');
    expect(() => fromJson(state, file(["drone", "badge", "drone"]))).toThrow('"points": "drone" is listed twice.');
    expect(state).toEqual(withPoints("badge"));
  });

  it("fromJson refuses a file clicked on another camera", () => {
    const state = { ...createState(), cameraId: "phone-1x" };
    expect(() => fromJson(state, { camera_id: "phone-0.5x", views: {} })).toThrow(
      /for camera "phone-0.5x", but this session is for "phone-1x"/,
    );
  });

  it("fromJson accepts the same camera, ignoring surrounding spaces", () => {
    const state = { ...createState(), cameraId: " phone-1x" };
    const result = fromJson(state, { camera_id: "phone-1x ", views: { "a.png": { p: [1, 2] } } });
    expect(result.state.cameraId).toBe(" phone-1x");
    expect(clickAt(result.state, "a.png", "p")).toEqual([1, 2]);
  });

  it("fromJson refuses malformed files", () => {
    const state = withPoints("badge");
    expect(() => fromJson(state, {})).toThrow(/views/);
    expect(() => fromJson(state, { views: [] })).toThrow(/views/);
    expect(() => fromJson(state, { views: { "a.png": { badge: [1] } } })).toThrow(/expected \[x, y\]/);
    expect(() => fromJson(state, { views: { "a.png": { badge: [1, "x"] } } })).toThrow(/expected \[x, y\]/);
    expect(() => fromJson(state, { views: { "a.png": 7 } })).toThrow(/expected \{point/);
    expect(state.clicks).toEqual({});
  });

  it("a saved state restores to the same state", () => {
    let state = { ...withPoints("a", "b"), cameraId: "phone-1x" };
    state = place(state, "v.png", "a", 10.5, 20.5);
    expect(restore(JSON.parse(JSON.stringify(state)))).toEqual(state);
  });

  it("restore refuses a malformed saved state", () => {
    expect(restore({ cameraId: 1, points: [] })).toBeNull();
    expect(restore({ cameraId: "", points: [7] })).toBeNull();
    expect(restore({ cameraId: "", points: ["a", "a"] })).toBeNull();
    expect(restore({ cameraId: "", points: [], clicks: { "a.png": { x: "no" } } })).toBeNull();
    expect(restore("nonsense")).toBeNull();
  });
});
