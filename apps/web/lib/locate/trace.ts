import type { LocaliseResult, Truth } from "@/lib/locate/types";

// The steps of a session: every localisation it ran, in order, each with its
// whole answer, so it can be shown again and compared with the step before.

export interface TraceStep {
  /** 1, 2, 3… within its trace. */
  n: number;
  /** ISO 8601: when the answer came. */
  at: string;
  view: string;
  /** The image the truth was asked from; null: none. */
  truthView: string | null;
  result: LocaliseResult;
}

/** Just what the page needs of sessionStorage, so tests can give a stand-in. */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** Semi-major axis of the 95 % region; null when the localisation gave none. */
export function regionPx(result: LocaliseResult): number | null {
  return result.localisation.uncertainty?.ellipse.semi_major_px ?? null;
}

/** How the region of a step compares with the step before. */
export type Change =
  /** Nothing to compare: the first step, or neither step has a region. */
  | { kind: "none" }
  /** A region where the step before had none. */
  | { kind: "found" }
  /** No region where the step before had one. */
  | { kind: "lost" }
  /** percent: the change of the semi-major axis; a smaller region is a better localisation. */
  | { kind: "ratio"; percent: number; verdict: "improved" | "worse" | "same" };

export function changeOf(previous: LocaliseResult | null, current: LocaliseResult): Change {
  const before = previous ? regionPx(previous) : null;
  const now = regionPx(current);
  if (before === null && now === null) return { kind: "none" };
  if (before === null) return previous ? { kind: "found" } : { kind: "none" };
  if (now === null) return { kind: "lost" };
  const percent = before > 0 ? ((now - before) / before) * 100 : now > 0 ? Number.POSITIVE_INFINITY : 0;
  // "same" is what reads as 0.0 % on the page.
  const verdict = Math.round(percent * 10) === 0 ? "same" : percent < 0 ? "improved" : "worse";
  return { kind: "ratio", percent, verdict };
}

/** The latest step of each view, for the badges of the viewpoints. */
export function latestByView(steps: readonly TraceStep[]): Map<string, TraceStep> {
  return new Map(steps.map((step) => [step.view, step]));
}

/**
 * The truth to show for a step. Without a truth view the service still takes
 * the view's own target click, but "None" was chosen: nothing is shown.
 */
export function shownTruth(step: Pick<TraceStep, "truthView" | "result">): Truth | null {
  return step.truthView === null ? null : step.result.truth;
}
