import { squareFromSpan, type Board, type BoardMeasurement } from "@/lib/workspace";

import { caliper, signedPercent } from "./format";
import { readNumber } from "./rules";

// The board measurement: a caliper reading across several squares of the
// mounted board, as one square. The reading's error is that of one reading,
// so spread over N squares it is N times smaller on each.

export interface SpanReading {
  /** mm across `squares` squares */
  length: string;
  squares: string;
  /** ± mm of the reading */
  uncertainty: string;
  /** mm, optional */
  marker: string;
  substrate: string;
}

export interface SquareSide {
  square_mm: number;
  /** Null until the reading's uncertainty is typed. */
  uncertainty_mm: number | null;
  /** How far the square is from the size sent to the printer, in percent. */
  vs_nominal_pct: number;
  /** Within the range the service accepts; outside it, the span was most likely typed as one square. */
  plausible: boolean;
}

export interface CheckedMeasurement {
  /** What the reading gives so far: shown as it is typed. */
  side: SquareSide | null;
  /** Null while anything is missing. */
  body: BoardMeasurement | null;
  problems: string[];
}

/** A span of this many squares: long enough to divide the caliper's error, short enough for its jaws. */
export const DEFAULT_SQUARES = 4;
/** The service keeps at most this many characters of a substrate. */
const SUBSTRATE_MAX = 200;
/** The service refuses a square outside these multiples of the nominal size. */
const PLAUSIBLE_SCALE = [0.8, 1.25] as const;

function micrometres(value: number): number {
  return Math.round(value * 1000) / 1000;
}

/** The dialog as it opens: a span of four squares, and what the rig already says of the marker and the substrate. */
export function initialReading(board: Pick<Board, "marker_measured_mm" | "substrate">): SpanReading {
  return {
    length: "",
    squares: String(DEFAULT_SQUARES),
    uncertainty: "",
    marker: board.marker_measured_mm === null ? "" : caliper(board.marker_measured_mm),
    substrate: board.substrate ?? "",
  };
}

/** "Square side 25.04 ± 0.01 mm · +0.16 % vs nominal" */
export function sideText(side: SquareSide): string {
  const spread = side.uncertainty_mm === null ? "" : ` ± ${caliper(side.uncertainty_mm)}`;
  return `Square side ${caliper(side.square_mm)}${spread} mm · ${signedPercent(side.vs_nominal_pct)} vs nominal`;
}

/** One square of `board` from the reading, and the body of PUT /boards/{id}/measurement once it is complete. */
export function checkMeasurement(reading: SpanReading, board: Pick<Board, "square_nominal_mm">): CheckedMeasurement {
  const problems: string[] = [];
  const length = readNumber(reading.length, "Length", { above: 0, unit: "mm" });
  const squares = readNumber(reading.squares, "Squares", { integer: true, min: 1 });
  const spread = readNumber(reading.uncertainty, "Length uncertainty", { min: 0, unit: "mm" });
  for (const result of [length, squares, spread]) if ("problem" in result) problems.push(result.problem);

  let side: SquareSide | null = null;
  if ("value" in length && "value" in squares) {
    const square = squareFromSpan(length.value, squares.value);
    if (square !== null) {
      const ratio = square / board.square_nominal_mm;
      side = {
        square_mm: square,
        uncertainty_mm: "value" in spread ? micrometres(spread.value / squares.value) : null,
        vs_nominal_pct: (ratio - 1) * 100,
        plausible: ratio >= PLAUSIBLE_SCALE[0] && ratio <= PLAUSIBLE_SCALE[1],
      };
    }
  }

  let marker: number | null = null;
  if (reading.marker.trim() !== "") {
    const result = readNumber(reading.marker, "Marker side", { above: 0, unit: "mm" });
    if ("problem" in result) problems.push(result.problem);
    else if (side && result.value >= side.square_mm) {
      problems.push(`Marker side ${reading.marker.trim()} mm, needs < square ${caliper(side.square_mm)} mm`);
    } else marker = result.value;
  }
  const substrate = reading.substrate.trim();
  if (substrate.length > SUBSTRATE_MAX) problems.push(`Substrate over ${SUBSTRATE_MAX} characters`);

  if (problems.length > 0 || !side || side.uncertainty_mm === null) return { side, body: null, problems };
  return {
    side,
    body: {
      square_measured_mm: side.square_mm,
      measurement_uncertainty_mm: side.uncertainty_mm,
      marker_measured_mm: marker,
      substrate: substrate || null,
    },
    problems,
  };
}
