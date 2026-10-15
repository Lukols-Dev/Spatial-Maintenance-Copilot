"use client";

import { ArrowRight, CircleCheck, Minimize2, Maximize2, ScanEye, TriangleAlert } from "lucide-react";

import {
  IN_SIGHT,
  cueOf,
  moveOf,
  progressShown,
  progressTone,
  sightingWords,
  verdictOf,
  wordsOf,
  type Cue,
} from "@/lib/guide/moves";
import type { FrameAnswer } from "@/lib/guide/types";
import type { Action } from "@/lib/locate/types";
import { cn } from "@/lib/utils";

// The move over the video, large enough to read at arm's length: an arrow
// that fills as the camera nears the guide view, the move in words beside it,
// and the fact the move follows from. A reliable result shows a check instead.
// Once the panel is open and the target's tag is in sight, no move is left to
// make: the tag is held against the prediction in its place.

const TONE = {
  far: "bg-amber-400",
  near: "bg-yellow-300",
  there: "bg-emerald-400",
} as const;

function Arrow({ action }: { action: Action }) {
  const move = moveOf(action);
  if (action === "ACCEPT") return <CircleCheck aria-hidden className="size-10 text-emerald-400" />;
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
  const shown = progressShown(action, frame.guidance?.progress ?? null);
  const tone = progressTone(shown);
  const reason = action === frame.decision.action ? frame.decision.move_reason : "";
  return (
    <>
      <div className="flex items-center gap-3">
        <Arrow action={action} />
        <div className="min-w-0 flex-1">
          <p className="text-xl font-semibold">{wordsOf(action)}</p>
          {reason && <p className="truncate text-sm text-white/80">{reason}</p>}
        </div>
      </div>
      {shown !== null && (
        <div
          className="mt-2 h-2 overflow-hidden rounded-full bg-white/20"
          role="progressbar"
          aria-label="Toward the guide view"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(shown * 100)}
        >
          <div className={cn("h-full rounded-full transition-[width]", TONE[tone])} style={{ width: `${shown * 100}%` }} />
        </div>
      )}
    </>
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
