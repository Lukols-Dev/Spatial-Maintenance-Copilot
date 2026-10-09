import { describe, expect, it } from "vitest";

import boardExample from "../api-examples/board.json";
import emptyExample from "../api-examples/workspace-empty.json";
import type { Board, Workspace } from "../workspace";
import { checkMeasurement, DEFAULT_SQUARES, initialReading, sideText, type SpanReading } from "./measure";

/** rig_board_a as the repository has it today: 25 mm squares, not measured yet. */
const BOARD = (structuredClone(emptyExample) as unknown as Workspace).rig.boards[1];

function reading(change: Partial<SpanReading> = {}): SpanReading {
  return { ...initialReading(BOARD), ...change };
}

describe("checkMeasurement", () => {
  it("makes one square of a span: the length and its error divided by the squares", () => {
    const checked = checkMeasurement(reading({ length: "100.16", uncertainty: "0.04" }), BOARD);
    expect(checked.problems).toEqual([]);
    expect(checked.side).toMatchObject({ square_mm: 25.04, uncertainty_mm: 0.01, plausible: true });
    expect(checked.side!.vs_nominal_pct).toBeCloseTo(0.16, 9);
    expect(sideText(checked.side!)).toBe("Square side 25.04 ± 0.01 mm · +0.16 % vs nominal");
    expect(checked.body).toEqual({
      square_measured_mm: 25.04,
      measurement_uncertainty_mm: 0.01,
      marker_measured_mm: null,
      substrate: null,
    });
  });

  it("shows the square as soon as the length is typed, and sends nothing before its uncertainty", () => {
    const checked = checkMeasurement(reading({ length: "99.8" }), BOARD);
    expect(sideText(checked.side!)).toBe("Square side 24.95 mm · −0.20 % vs nominal");
    expect(checked.body).toBeNull();
    expect(checked.problems).toEqual(["Length uncertainty missing"]);
  });

  it("keeps micrometres, as the service stores them", () => {
    const checked = checkMeasurement(reading({ length: "100.1", squares: "3", uncertainty: "0.05" }), BOARD);
    expect(checked.body).toMatchObject({ square_measured_mm: 33.367, measurement_uncertainty_mm: 0.017 });
  });

  it("marks a span typed as one square, which the service refuses", () => {
    const checked = checkMeasurement(reading({ length: "100.16", squares: "1", uncertainty: "0.04" }), BOARD);
    expect(checked.side).toMatchObject({ square_mm: 100.16, plausible: false });
    expect(sideText(checked.side!)).toBe("Square side 100.16 ± 0.04 mm · +300.64 % vs nominal");
    // The service is the judge: the reading can still be sent, and its answer is shown.
    expect(checked.body).not.toBeNull();
  });

  it("sends the marker side and the substrate when they are given", () => {
    const checked = checkMeasurement(
      reading({ length: "100.08", uncertainty: "0.08", marker: "18.02", substrate: "  A4 print on foam board " }),
      boardExample as Board,
    );
    expect(checked.body).toEqual({
      square_measured_mm: 25.02,
      measurement_uncertainty_mm: 0.02,
      marker_measured_mm: 18.02,
      substrate: "A4 print on foam board",
    });
  });

  it("names what keeps the reading from being sent", () => {
    const cases: [Partial<SpanReading>, string[]][] = [
      [{}, ["Length missing", "Length uncertainty missing"]],
      [{ length: "0", uncertainty: "0.04" }, ["Length 0 mm, needs > 0"]],
      [{ length: "100", squares: "0", uncertainty: "0.04" }, ["Squares 0, needs ≥ 1"]],
      [{ length: "100", squares: "2.5", uncertainty: "0.04" }, ["Squares 2.5, needs a whole number"]],
      [{ length: "100", uncertainty: "-0.1" }, ["Length uncertainty -0.1 mm, needs ≥ 0"]],
      [{ length: "100", uncertainty: "0.04", marker: "25" }, ["Marker side 25 mm, needs < square 25.00 mm"]],
      [{ length: "100", uncertainty: "0.04", marker: "0" }, ["Marker side 0 mm, needs > 0"]],
      [{ length: "100", uncertainty: "0.04", substrate: "x".repeat(201) }, ["Substrate over 200 characters"]],
    ];
    for (const [change, problems] of cases) {
      const checked = checkMeasurement(reading(change), BOARD);
      expect(checked.problems).toEqual(problems);
      expect(checked.body).toBeNull();
    }
  });
});

describe("initialReading", () => {
  it("opens on a span of four squares, with what the rig says of the marker and the substrate", () => {
    expect(DEFAULT_SQUARES).toBe(4);
    expect(initialReading(BOARD)).toEqual({ length: "", squares: "4", uncertainty: "", marker: "", substrate: "" });
    const measured: Board = { ...(boardExample as Board), marker_measured_mm: 18.02 };
    expect(initialReading(measured)).toEqual({
      length: "",
      squares: "4",
      uncertainty: "",
      marker: "18.02",
      substrate: "A4 print on foam board",
    });
  });
});
