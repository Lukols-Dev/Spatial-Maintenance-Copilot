"use client";

import {
  ArrowRight,
  CircleCheck,
  Hand,
  Minimize2,
  Maximize2,
  ScanEye,
  Smartphone,
  TriangleAlert,
} from "lucide-react";

import {
  IN_SIGHT,
  cueOf,
  moveOf,
  sightingWords,
  verdictOf,
  wordsOf,
  type Cue,
} from "@/lib/guide/moves";
import type { FrameAnswer } from "@/lib/guide/types";
import type { Action } from "@/lib/locate/types";

/** Said and spoken while the phone is held sideways. */
export const SIDEWAYS_WORDS = "Hold the phone upright";

// The move over the video, large enough to read at arm's length: the policy's
// arrow, the move in words beside it, and the fact the move follows from. A
// reliable result shows a check instead.
// Once the panel is open and the target's tag is in sight, no move is left to
// make: the tag is held against the prediction in its place.

function Arrow({ action }: { action: Action }) {
  const move = moveOf(action);
  if (action === "ACCEPT") return <CircleCheck aria-hidden className="size-10 text-emerald-400" />;
  if (action === "HOLD_STILL") return <Hand aria-hidden className="size-10 text-amber-400" />;
  if (action === "MOVE_CLOSER") return <Maximize2 aria-hidden className="size-10 text-white" />;
  if (action === "MOVE_BACK") return <Minimize2 aria-hidden className="size-10 text-white" />;
  return <ArrowRight aria-hidden className="size-10 text-white" style={{ transform: `rotate(${move.angle ?? 0}deg)` }} />;
}

/** A confirmed prediction a check, a tag outside the region a warning, and the tag alone otherwise. */
function VerdictIcon({ frame }: { frame: FrameAnswer }) {
  const verdict = verdictOf(frame);
  if (verdict === "confirmed") return <CircleCheck aria-hidden className="size-10 text-emerald-400" />;
  if (verdict === "outside") return <TriangleAlert aria-hidden className="size-10 text-amber-400" />;
  return <ScanEye aria-hidden className="size-10 text-white" />;
}

function NextMove({ action, frame }: { action: Action; frame: FrameAnswer }) {
  const reason = action === frame.decision.action ? frame.decision.move_reason : "";
  return (
    <div className="flex items-center gap-3">
      <Arrow action={action} />
      <div className="min-w-0 flex-1">
        <p className="text-xl font-semibold">{wordsOf(action)}</p>
        {reason && <p className="truncate text-sm text-white/80">{reason}</p>}
      </div>
    </div>
  );
}

function InSight({ frame }: { frame: FrameAnswer }) {
  return (
    <div className="flex items-center gap-3">
      <VerdictIcon frame={frame} />
      <div className="min-w-0 flex-1">
        <p className="text-xl font-semibold">{wordsOf(IN_SIGHT)}</p>
        <p className="text-sm text-white/80">{sightingWords(frame)}</p>
      </div>
    </div>
  );
}

export function GuideHud({
  frame,
  steady,
  sighted,
}: {
  frame: FrameAnswer;
  steady: Cue | null;
  /** The last frame with the tag, shown while a frame or two miss it. */
  sighted: FrameAnswer | null;
}) {
  const cue = steady ?? cueOf(frame);
  return (
    <div
      role="status"
      aria-live="polite"
      data-cue={cue}
      className="absolute inset-x-3 bottom-3 rounded-xl bg-black/70 p-3 text-white backdrop-blur-sm"
    >
      {cue === IN_SIGHT ? (
        <InSight frame={frame.sighting ? frame : (sighted ?? frame)} />
      ) : (
        <NextMove action={cue} frame={frame} />
      )}
    </div>
  );
}

/** What the page shows while a phone's frames come turned: none is sent, so there is no move to show. */
export function SidewaysHud({
  size,
  expected,
}: {
  size: { width: number; height: number };
  expected: { width: number; height: number };
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      data-cue="SIDEWAYS"
      className="absolute inset-x-3 bottom-3 flex items-center gap-3 rounded-xl bg-black/70 p-3 text-white backdrop-blur-sm"
    >
      <Smartphone aria-hidden className="size-10 shrink-0 text-amber-400" />
      <div className="min-w-0">
        <p className="text-lg leading-tight font-semibold">{SIDEWAYS_WORDS}</p>
        <p className="text-sm text-white/80 tabular-nums">
          Frames {size.width} × {size.height} px, calibrated at {expected.width} × {expected.height} px
        </p>
      </div>
    </div>
  );
}
