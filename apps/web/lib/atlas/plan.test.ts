import { describe, expect, it } from "vitest";

import atlasExample from "../api-examples/atlas.json";
import workspaceExample from "../api-examples/workspace.json";
import type { AtlasDetail, Board, Workspace } from "../workspace";
import {
  frameBoard,
  labelBox,
  layoutPlan,
  niceLength,
  placeLabels,
  planBoard,
  planInput,
  type Box,
  type Plan,
  type PlanInput,
} from "./plan";

const WIDTH = 600;
const MAX_HEIGHT = 560;
const BOARD = { id: "rig_board_a", squares_x: 4, squares_y: 6, square_mm: 25 };

/** Three landmarks around a 4×6 board, and a target box below it. */
function input(change: Partial<PlanInput> = {}): PlanInput {
  return {
    landmarks: [
      { id: "top", position_mm: [50, -200, 0], sigma_mm: 2 },
      { id: "bottom", position_mm: [50, 400, 0], sigma_mm: 3 },
      { id: "right", position_mm: [300, 75, 0], sigma_mm: 2 },
    ],
    target: { id: "drone", position_mm: [150, 200, 240], sigma_mm: 5, extent_mm: [200, 100, 50] },
    board: BOARD,
    ...change,
  };
}

function point(plan: Plan, id: string) {
  const found = [plan.target, ...plan.landmarks].find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no point ${id}`);
  return found;
}

function overlap(a: Box, b: Box): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

describe("layoutPlan", () => {
  it("maps millimetres to pixels by one scale and one offset: x to the right, y down", () => {
    const plan = layoutPlan(input(), WIDTH, MAX_HEIGHT);
    const top = point(plan, "top");
    const bottom = point(plan, "bottom");
    const right = point(plan, "right");
    // y grows downward on the page as in the board frame: no flip.
    expect(bottom.y).toBeGreaterThan(top.y);
    expect(bottom.y - top.y).toBeCloseTo(600 * plan.scale, 9);
    expect(right.x - top.x).toBeCloseTo(250 * plan.scale, 9);
    expect(bottom.x).toBeCloseTo(top.x, 9);
    // The origin is where (0, 0) is.
    expect(top.x - plan.origin.x).toBeCloseTo(50 * plan.scale, 9);
    expect(top.y - plan.origin.y).toBeCloseTo(-200 * plan.scale, 9);
    expect(right.y - plan.origin.y).toBeCloseTo(75 * plan.scale, 9);
  });

  it("draws the board from its squares at the measured size, its top-left corner on the origin", () => {
    const plan = layoutPlan(input(), WIDTH, MAX_HEIGHT);
    const board = plan.board!;
    expect(board.x).toBeCloseTo(plan.origin.x, 9);
    expect(board.y).toBeCloseTo(plan.origin.y, 9);
    expect(board.width).toBeCloseTo(4 * 25 * plan.scale, 9);
    expect(board.height).toBeCloseTo(6 * 25 * plan.scale, 9);

    // The lines between the squares: 3 down the board, 5 across it.
    const down = board.grid.filter((line) => line.x1 === line.x2);
    const across = board.grid.filter((line) => line.y1 === line.y2);
    expect(down).toHaveLength(3);
    expect(across).toHaveLength(5);
    expect(down.map((line) => (line.x1 - board.x) / plan.scale)).toEqual([25, 50, 75].map((mm) => expect.closeTo(mm, 9)));
    expect(across[0].y1 - board.y).toBeCloseTo(25 * plan.scale, 9);
    for (const line of down) expect(line.y2 - line.y1).toBeCloseTo(board.height, 9);
  });

  it("draws the axes from the origin along x and y, their names outside the board", () => {
    const plan = layoutPlan(input(), WIDTH, MAX_HEIGHT);
    const { x, y } = plan.axes;
    expect([x.x1, x.y1, y.x1, y.y1]).toEqual([plan.origin.x, plan.origin.y, plan.origin.x, plan.origin.y]);
    expect(x.x2).toBeGreaterThan(x.x1);
    expect(x.y2).toBe(x.y1);
    expect(y.y2).toBeGreaterThan(y.y1);
    expect(y.x2).toBe(y.x1);
    expect([x.label.text, y.label.text]).toEqual(["x", "y"]);
    const board = plan.board!;
    for (const label of [x.label, y.label]) expect(overlap(labelBox(label), board)).toBe(false);
  });

  it("draws the target as its extent box and its σ circle, the landmarks with theirs, all at one scale", () => {
    const plan = layoutPlan(input(), WIDTH, MAX_HEIGHT);
    const { target } = plan;
    expect(target.box.width).toBeCloseTo(200 * plan.scale, 9);
    expect(target.box.height).toBeCloseTo(100 * plan.scale, 9);
    expect(target.box.x + target.box.width / 2).toBeCloseTo(target.x, 9);
    expect(target.box.y + target.box.height / 2).toBeCloseTo(target.y, 9);
    expect(target.r).toBeCloseTo(5 * plan.scale, 9);
    expect(point(plan, "bottom").r).toBeCloseTo(3 * plan.scale, 9);
  });

  it("fits everything in the width and at most the height it is given", () => {
    for (const width of [320, 600, 1100]) {
      const plan = layoutPlan(input(), width, MAX_HEIGHT);
      expect(plan.width).toBe(width);
      expect(plan.height).toBeLessThanOrEqual(MAX_HEIGHT);
      const boxes = [plan.target.box, plan.board!];
      for (const { x, y, r } of [plan.target, ...plan.landmarks]) boxes.push({ x: x - r, y: y - r, width: 2 * r, height: 2 * r });
      for (const box of boxes) {
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.y).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width);
        expect(box.y + box.height).toBeLessThanOrEqual(plan.height);
      }
    }
  });

  it("keeps the origin in view without a board", () => {
    const far = input({
      board: null,
      landmarks: [{ id: "far", position_mm: [500, 600, 0], sigma_mm: 2 }],
      target: { id: "drone", position_mm: [700, 800, 0], sigma_mm: 5, extent_mm: [100, 100, 100] },
    });
    const plan = layoutPlan(far, WIDTH, MAX_HEIGHT);
    expect(plan.board).toBeNull();
    expect(plan.origin.x).toBeGreaterThan(0);
    expect(plan.origin.y).toBeGreaterThan(0);
    expect(point(plan, "far").x).toBeGreaterThan(plan.origin.x);
  });

  it("names every point clear of the others, and inside the drawing", () => {
    const plan = layoutPlan(input(), WIDTH, MAX_HEIGHT);
    const labels = [plan.target, ...plan.landmarks].map((placed) => placed.label);
    expect(labels.map((label) => label?.text)).toEqual(["drone", "top", "bottom", "right"]);
    const boxes = labels.map((label) => labelBox(label!));
    for (const [index, box] of boxes.entries()) {
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(plan.width);
      for (const other of boxes.slice(index + 1)) expect(overlap(box, other)).toBe(false);
    }
  });

  it("has a scale bar of a round length under the drawing", () => {
    const plan = layoutPlan(input(), WIDTH, MAX_HEIGHT);
    const bar = plan.scaleBar;
    expect([1, 2, 5].map((step) => step * 10 ** Math.floor(Math.log10(bar.mm)))).toContain(bar.mm);
    expect(bar.x2 - bar.x1).toBeCloseTo(bar.mm * plan.scale, 9);
    expect(bar.y1).toBeGreaterThan(Math.max(...plan.landmarks.map((placed) => placed.y)));
    expect(bar.label.text).toBe(`${bar.mm} mm`);
    expect(bar.label.x).toBeGreaterThan(bar.x2);
  });
});

describe("placeLabels", () => {
  const AREA = { x: 0, y: 0, width: 400, height: 300 };

  it("puts a label right of its dot, else left, below or above", () => {
    const [right, left] = placeLabels(
      [
        { x: 100, y: 100, text: "a" },
        { x: 395, y: 200, text: "edge" },
      ],
      AREA,
    );
    expect(right).toMatchObject({ anchor: "start", text: "a" });
    expect(right!.x).toBeGreaterThan(100);
    expect(left).toMatchObject({ anchor: "end", text: "edge" });
    expect(left!.x).toBeLessThan(395);
  });

  it("gives way when the dots crowd: no label covers another or a dot", () => {
    const crowd = Array.from({ length: 6 }, (_, index) => ({ x: 200, y: 150 + index, text: `point_${index}` }));
    const labels = placeLabels(crowd, AREA);
    expect(labels.filter((label) => label === null).length).toBeGreaterThan(0);
    const boxes = labels.flatMap((label) => (label ? [labelBox(label)] : []));
    for (const [index, box] of boxes.entries()) {
      for (const other of boxes.slice(index + 1)) expect(overlap(box, other)).toBe(false);
    }
  });

  it("keeps clear of what is already taken", () => {
    const [label] = placeLabels([{ x: 100, y: 100, text: "a" }], AREA, [{ x: 105, y: 90, width: 50, height: 20 }]);
    expect(label?.anchor).toBe("end");
  });
});

describe("labelBox", () => {
  it("covers the text from its anchor", () => {
    const start = labelBox({ x: 10, y: 20, anchor: "start", text: "abcd" });
    const middle = labelBox({ x: 10, y: 20, anchor: "middle", text: "abcd" });
    const end = labelBox({ x: 10, y: 20, anchor: "end", text: "abcd" });
    expect(start.x).toBe(10);
    expect(middle.x + middle.width / 2).toBeCloseTo(10, 9);
    expect(end.x + end.width).toBeCloseTo(10, 9);
    expect(start.y).toBeLessThan(20);
    expect(start.y + start.height).toBeGreaterThan(20);
  });
});

describe("niceLength", () => {
  it("is the largest 1, 2 or 5 times a power of ten within the limit", () => {
    expect([229, 99, 12, 1, 0.7, 1000, 4999].map(niceLength)).toEqual([200, 50, 10, 1, 0.5, 1000, 2000]);
  });
});

describe("the board and the points of an atlas", () => {
  const rig = (workspaceExample as unknown as Workspace).rig.boards;

  it("outlines a board at its measured square, and no board that is not measured", () => {
    const [calibration, boardA, boardB] = rig;
    expect(planBoard(boardA)).toEqual({ id: "rig_board_a", squares_x: 4, squares_y: 6, square_mm: 25.04 });
    expect(planBoard(calibration)?.square_mm).toBe(30);
    expect(planBoard(boardB)).toBeNull();
    expect(planBoard(undefined)).toBeNull();
  });

  it("reads the board from the frame", () => {
    expect(frameBoard("board:rig_board_a")).toBe("rig_board_a");
    expect(frameBoard("board:")).toBeNull();
    expect(frameBoard("world")).toBeNull();
  });

  it("takes the atlas's points and the board its build named", () => {
    const detail = structuredClone(atlasExample) as unknown as AtlasDetail;
    const plan = planInput(detail, rig);
    expect(plan.board).toEqual({ id: "rig_board_a", squares_x: 4, squares_y: 6, square_mm: 25.04 });
    expect(plan.landmarks).toEqual([
      { id: "handle", position_mm: [182.6, 95.3, 21.7], sigma_mm: 2.31 },
      { id: "hinge_top", position_mm: [-12.4, -310.2, 4.1], sigma_mm: 1.84 },
    ]);
    expect(plan.target).toEqual({ id: "drone", position_mm: [95, 160.4, -210.8], sigma_mm: 5.21, extent_mm: [300, 300, 100] });

    // Without a report, the frame names the board; a board without a measurement is not drawn.
    const written = { ...detail, report: null, atlas: { ...detail.atlas, frame: "board:rig_board_b" } };
    expect(planInput(written, rig).board).toBeNull();
    const measured: Board[] = rig.map((board) => (board.id === "rig_board_b" ? { ...board, square_measured_mm: 25.02 } : board));
    expect(planInput(written, measured).board?.square_mm).toBe(25.02);
  });
});
