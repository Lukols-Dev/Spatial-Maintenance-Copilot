import type { FrameAnswer } from "@/lib/guide/types";
import type { Action } from "@/lib/locate/types";

// The policy's moves as the Guide page shows and speaks them. A move is the
// camera's, as the operator holds it: MOVE_LEFT brings what lies beyond the
// left edge of the frame into view. Once the panel is open and the target's
// tag is in the frame, the page says so in place of any move: the tag is held
// against the prediction, and there is nothing left to move toward.

export interface Move {
  action: Action;
  /** On screen, and spoken. */
  words: string;
  /** Where the arrow points, degrees from the image's x axis towards y; null for a move along the view. */
  angle: number | null;
}

const MOVES: Record<Action, Move> = {
  ACCEPT: { action: "ACCEPT", words: "Hold still", angle: null },
  HOLD_STILL: { action: "HOLD_STILL", words: "Hold steady, the frame is blurred", angle: null },
  MOVE_LEFT: { action: "MOVE_LEFT", words: "Move left", angle: 180 },
  MOVE_RIGHT: { action: "MOVE_RIGHT", words: "Move right", angle: 0 },
  MOVE_UP: { action: "MOVE_UP", words: "Move up", angle: 270 },
  MOVE_DOWN: { action: "MOVE_DOWN", words: "Move down", angle: 90 },
  MOVE_CLOSER: { action: "MOVE_CLOSER", words: "Move closer", angle: null },
  MOVE_BACK: { action: "MOVE_BACK", words: "Step back", angle: null },
};

export function moveOf(action: Action): Move {
  return MOVES[action];
}

/** What the page says in place of a move while the target's tag is in sight. */
export const IN_SIGHT = "IN_SIGHT";

/** What the page shows and speaks of a frame: the policy's move, or the target in sight. */
export type Cue = Action | typeof IN_SIGHT;

/** A frame's cue: the target in sight whenever its tag is found, whatever the policy decided. */
export function cueOf(frame: FrameAnswer): Cue {
  return frame.sighting ? IN_SIGHT : frame.decision.action;
}

/** A cue in words, on screen and spoken. */
export function wordsOf(cue: Cue): string {
  return cue === IN_SIGHT ? "Target in sight" : moveOf(cue).words;
}

/** What the target's tag in a frame says of the prediction. */
export type Verdict = "confirmed" | "outside" | "uncertain" | "unlocalised";

/** The policy's checks on the 95 % region itself: stable, and tight enough to hold a tag against. */
const REGION_CHECKS = new Set(["pose_stability", "region_ratio"]);

/**
 * What the target's tag in a frame says of the prediction, null without the tag:
 * confirmed inside a 95 % region the policy finds stable and tight, outside the
 * region, uncertain with a region too wide or none, unlocalised with no
 * prediction at all. Any tag lies inside a wide enough region.
 */
export function verdictOf(frame: FrameAnswer): Verdict | null {
  const { sighting } = frame;
  if (sighting === null) return null;
  if (sighting.error_px === null) return "unlocalised";
  if (sighting.inside_95 === false) return "outside";
  const tight = frame.decision.checks.every((check) => check.passed || !REGION_CHECKS.has(check.name));
  return sighting.inside_95 === true && tight ? "confirmed" : "uncertain";
}

/** A frame's tag held against the prediction, in words: how far off, and what that says. */
export function sightingWords(frame: FrameAnswer): string {
  const verdict = verdictOf(frame);
  const error = frame.sighting?.error_px ?? null;
  if (verdict === null) return "No tag in this frame";
  if (error === null) return "Not localised in this frame: no prediction to compare";
  const off = `${error.toFixed(1)} px from the prediction`;
  if (verdict === "confirmed") return `${off}, inside the 95 % region`;
  if (verdict === "outside") return `${off}, outside the 95 % region`;
  return `${off}, too uncertain to tell`;
}
