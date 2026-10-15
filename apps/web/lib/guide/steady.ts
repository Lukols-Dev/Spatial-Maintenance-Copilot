import type { Cue } from "@/lib/guide/moves";

// A camera's frames change their cue often: a decision at the edges of a
// threshold, a tag at the edge of being found. The page speaks a cue, and the
// agent is told of a move, only once it has held for a few frames in a row,
// so a single frame does not flip what the operator hears.

/** Frames in a row a cue must hold before it is the page's. */
export const STEADY_FRAMES = 3;

export class Steady {
  private candidate: Cue | null = null;
  private count = 0;
  private current: Cue | null = null;

  constructor(private readonly frames: number = STEADY_FRAMES) {}

  /** The steady cue, once one is. */
  get value(): Cue | null {
    return this.current;
  }

  /** Take a frame's cue; returns the new steady cue when this frame made it change, else null. */
  push(cue: Cue): Cue | null {
    if (cue === this.candidate) {
      this.count += 1;
    } else {
      this.candidate = cue;
      this.count = 1;
    }
    if (this.count >= this.frames && cue !== this.current) {
      this.current = cue;
      return cue;
    }
    return null;
  }

  reset(): void {
    this.candidate = null;
    this.count = 0;
    this.current = null;
  }
}
