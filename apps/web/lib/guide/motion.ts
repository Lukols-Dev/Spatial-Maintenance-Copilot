// Whether a live camera is moving, told in the browser from its own picture,
// so a phone held in the hand gets one instruction per place it stops at
// rather than one per frame. Each video frame is drawn small and grey, and its
// change from the frame before measures the motion: the mean absolute
// difference of the two pictures, each less its own mean brightness, since a
// phone facing a white cabinet keeps changing its exposure.
//
// On the cabinet walk-arounds (demo_1 and demo_2, 1673 pairs of consecutive
// frames with markers; tools/motion_limit.py) the change ranks the pairs as
// the markers' own motion does (Spearman 0.94): a median of about 0.6 for
// markers moving under 1 px a frame, 1.9 for 2 to 4 px, 3.0 for 4 to 8 px and
// 4.6 for 8 to 16 px. Those videos come from the Camera app, which steadies
// the picture; a browser's camera does not, and a hand holding a phone "still"
// moves it a few pixels a frame. So the camera counts as moving only over
// MOVING_ABOVE (89 % of the pairs whose markers moved 8 px or more), and as
// steady under STILL_BELOW (94 % of those that moved under 4 px). The change is the median
// over the last WINDOW_MS, so one shaken frame is no move. Steady for
// SETTLE_MS, or not moving for FALLBACK_MS whatever its tremor, the camera is
// still and its view is analysed.

/** The longer side of the small picture motion is measured on, in pixels. */
export const SAMPLE_LONG_SIDE = 160;
/** Change below which the camera counts as steady. */
export const STILL_BELOW = 2.5;
/** Change above which the camera counts as moving. */
export const MOVING_ABOVE = 3.5;
/** The change is the median over this long a stretch of frames. */
export const WINDOW_MS = 300;
/** How long the camera must stay steady before its view is analysed. */
export const SETTLE_MS = 600;
/** Not moving for this long, the view is analysed, steady or not. */
export const FALLBACK_MS = 2000;

/** A camera's picture, small and grey, and when it was taken (ms). */
export interface Look {
  pixels: Uint8ClampedArray;
  at: number;
}

/** "moving": over the threshold; "settling": not moving, not yet for long enough; "still": analyse. */
export type Stillness = "moving" | "settling" | "still";

/** The size of the small picture for a frame of this size: the longer side SAMPLE_LONG_SIDE, the aspect kept. */
export function sampleSize(width: number, height: number): { width: number; height: number } {
  const scale = SAMPLE_LONG_SIDE / Math.max(width, height, 1);
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** Grey levels of RGBA pixels, as the luma of BT.601. */
export function grey(rgba: Uint8ClampedArray): Uint8ClampedArray {
  const out = new Uint8ClampedArray(rgba.length / 4);
  for (let i = 0, j = 0; j < out.length; i += 4, j += 1) {
    out[j] = 0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2];
  }
  return out;
}

function mean(values: Uint8ClampedArray): number {
  let sum = 0;
  for (const value of values) sum += value;
  return sum / values.length;
}

/**
 * The change between two grey pictures: the mean absolute difference of each less its mean, so a
 * change of exposure alone is none. Infinite when their sizes differ.
 */
export function pictureChange(a: Uint8ClampedArray, b: Uint8ClampedArray): number {
  if (a.length !== b.length || a.length === 0) return Number.POSITIVE_INFINITY;
  const shift = mean(b) - mean(a);
  let sum = 0;
  for (let i = 0; i < a.length; i += 1) sum += Math.abs(b[i] - a[i] - shift);
  return sum / a.length;
}

function median(values: number[]): number {
  const sorted = [...values].sort((x, y) => x - y);
  const middle = sorted.length >> 1;
  return sorted.length % 2 === 1 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

export interface MotionLimits {
  stillBelow: number;
  movingAbove: number;
  windowMs: number;
  settleMs: number;
  fallbackMs: number;
}

export const MOTION_LIMITS: MotionLimits = {
  stillBelow: STILL_BELOW,
  movingAbove: MOVING_ABOVE,
  windowMs: WINDOW_MS,
  settleMs: SETTLE_MS,
  fallbackMs: FALLBACK_MS,
};

/** The camera's stillness from the change between its frames, as a median over a short window. */
export class StillnessMeter {
  private state: Stillness = "moving";
  private since = Number.NaN;
  private movedAt = Number.NaN;
  private recent: { change: number; at: number }[] = [];
  private smoothed: number | null = null;

  constructor(private readonly limits: MotionLimits = MOTION_LIMITS) {}

  get value(): Stillness {
    return this.state;
  }

  /** The median change over the last window, as last measured; null before the first. */
  get change(): number | null {
    return this.smoothed;
  }

  /** How far toward still the camera is, 0 to 1: the steady time or the fallback, whichever is further on. */
  progress(at: number): number {
    if (this.state === "still") return 1;
    if (this.state === "moving") return 0;
    const steady = (at - this.since) / this.limits.settleMs;
    const unmoved = (at - this.movedAt) / this.limits.fallbackMs;
    return Math.min(1, Math.max(steady, unmoved, 0));
  }

  /** Take the change since the frame before, at time `at` (ms); returns the stillness after it. */
  push(change: number, at: number): Stillness {
    const { stillBelow, movingAbove, windowMs, settleMs, fallbackMs } = this.limits;
    if (Number.isNaN(this.movedAt)) this.movedAt = at;
    this.recent = [...this.recent.filter((sample) => at - sample.at < windowMs), { change, at }];
    const smoothed = median(this.recent.map((sample) => sample.change));
    this.smoothed = smoothed;

    if (smoothed > movingAbove) {
      this.state = "moving";
      this.movedAt = at;
      return this.state;
    }
    if (this.state === "moving") {
      this.state = "settling";
      this.since = at;
    }
    if (this.state === "settling") {
      // A tremor over the steady threshold starts the steady time again; the fallback runs on.
      if (smoothed >= stillBelow) this.since = at;
      else if (at - this.since >= settleMs) this.state = "still";
      if (at - this.movedAt >= fallbackMs) this.state = "still";
    }
    return this.state;
  }
}
