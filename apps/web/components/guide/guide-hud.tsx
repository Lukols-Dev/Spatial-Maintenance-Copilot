"use client";

import {
  Activity,
  ArrowRight,
  CircleCheck,
  Hand,
  LoaderCircle,
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
import type { Step } from "@/lib/guide/store";
import type { FrameAnswer } from "@/lib/guide/types";
import type { Action } from "@/lib/locate/types";
import { cn } from "@/lib/utils";

/** Said and spoken while the phone is held sideways. */
export const SIDEWAYS_WORDS = "Hold the phone upright";

// The move over the video, large enough to read at arm's length: the policy's
// arrow, the move in words beside it, and the fact the move follows from. A
// reliable result shows a check instead.
// Once the panel is open and the target's tag is in sight, no move is left to
// make: the tag is held against the prediction in its place. A live camera's
// step is said above the instruction: while it moves or settles, the last
// instruction is shown faded, as it was given before.

/** What the operator does at each step: the first words before any instruction was given. */
const STEPS: Record<Exclude<Step, "ready">, { words: string; first?: string; icon: typeof Activity; spin?: boolean }> = {
  moving: { words: "Moving", first: "Point the camera at the cabinet's markers", icon: Activity },
  settling: { words: "Hold the phone still", icon: Hand },
  analysing: { words: "Analysing this view", icon: LoaderCircle, spin: true },
};

/** A ring filling as the camera nears still: the steady time, or the fallback while the hand trembles. */
function Ring({ share }: { share: number }) {
  const r = 7;
  const length = 2 * Math.PI * r;
  return (
    <svg viewBox="0 0 18 18" aria-hidden className="size-4 -rotate-90">
      <circle cx="9" cy="9" r={r} className="fill-none stroke-white/25" strokeWidth="2.5" />
      <circle
        cx="9"
        cy="9"
        r={r}
        className="fill-none stroke-emerald-400"
        strokeWidth="2.5"
        strokeDasharray={`${length * share} ${length}`}
      />
    </svg>
  );
}

function StepLine({ step, settle, first }: { step: Exclude<Step, "ready">; settle: number | null; first: boolean }) {
  const { words, first: firstWords, icon: Icon, spin } = STEPS[step];
  return (
    <p data-part="step" className="flex items-center gap-2 text-sm font-medium text-white/90">
      {step === "settling" && settle !== null ? (
        <Ring share={settle} />
      ) : (
        <Icon aria-hidden className={cn("size-4", spin && "animate-spin motion-reduce:animate-none")} />
      )}
      {first && firstWords ? firstWords : words}
    </p>
  );
}

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

/** The instruction as a card: the step a live camera is at, then the move or the target in sight. */
export function CueCard({
  frame,
  steady,
  sighted,
  step,
  settle = null,
  className,
}: {
  frame: FrameAnswer | null;
  steady: Cue | null;
  /** The last frame with the tag, shown while a frame or two miss it. */
  sighted: FrameAnswer | null;
  step: Step | null;
  /** How far a live camera is toward still, 0 to 1. */
  settle?: number | null;
  className?: string;
}) {
  const cue = steady ?? (frame ? cueOf(frame) : null);
  const waiting = step !== null && step !== "ready" ? step : null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-cue={cue ?? ""}
      data-step={step ?? ""}
      className={cn("space-y-2 rounded-xl bg-black/70 p-3 text-white backdrop-blur-sm", className)}
    >
      {waiting && <StepLine step={waiting} settle={settle} first={frame === null} />}
      {frame && cue !== null && (
        <div className={cn(waiting && waiting !== "analysing" && "opacity-50")}>
          {cue === IN_SIGHT ? (
            <InSight frame={frame.sighting ? frame : (sighted ?? frame)} />
          ) : (
            <NextMove action={cue} frame={frame} />
          )}
        </div>
      )}
    </div>
  );
}

/** The card over the video's lower edge. */
export function GuideHud(props: Omit<Parameters<typeof CueCard>[0], "className">) {
  return <CueCard {...props} className="absolute inset-x-3 bottom-3" />;
}

/** What the page shows while a phone's frames come turned: none is sent, so there is no move to show. */
export function SidewaysHud({
  size,
  expected,
  className = "absolute inset-x-3 bottom-3",
}: {
  size: { width: number; height: number };
  expected: { width: number; height: number };
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      data-cue="SIDEWAYS"
      className={cn("flex items-center gap-3 rounded-xl bg-black/70 p-3 text-white backdrop-blur-sm", className)}
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
