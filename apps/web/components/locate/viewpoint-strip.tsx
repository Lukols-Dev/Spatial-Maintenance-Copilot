"use client";

import { Crosshair, LoaderCircle, OctagonX } from "lucide-react";
import Image from "next/image";

import { ActionIcon } from "@/components/locate/action-icon";
import { Badge } from "@/components/ui/badge";
import { thumbnailUrl } from "@/lib/locate/api";
import { count, failureLabel, outcomeOf } from "@/lib/locate/format";
import type { TraceStep } from "@/lib/locate/trace";
import type { Viewpoint } from "@/lib/locate/viewpoints";
import { cn } from "@/lib/utils";

/** The badge of a view's latest result in this session. */
export function OutcomeBadge({ step, className }: { step: TraceStep; className?: string }) {
  const outcome = outcomeOf(step.result);
  const failure = step.result.localisation.failure;
  return (
    <Badge
      variant="outline"
      title={failure ? failureLabel(failure) : undefined}
      className={cn(
        outcome.kind === "reliable" &&
          "border-emerald-600/30 bg-emerald-500/10 text-emerald-800 dark:border-emerald-400/30 dark:text-emerald-300",
        outcome.kind === "move" &&
          "border-amber-600/40 bg-amber-500/10 text-amber-900 dark:border-amber-400/30 dark:text-amber-300",
        outcome.kind === "failure" && "border-destructive/30 bg-destructive/10 text-destructive",
        className,
      )}
    >
      {outcome.kind === "failure" ? <OctagonX aria-hidden /> : <ActionIcon action={step.result.decision.action} />}
      {outcome.label}
    </Badge>
  );
}

function ViewpointButton({
  set,
  viewpoint,
  current,
  busy,
  latest,
  onSelect,
}: {
  set: string;
  viewpoint: Viewpoint;
  current: boolean;
  busy: boolean;
  latest: TraceStep | undefined;
  onSelect: (view: string) => void;
}) {
  const { file, width, height } = viewpoint;
  return (
    <button
      type="button"
      onClick={() => onSelect(file)}
      aria-current={current ? "true" : undefined}
      aria-busy={busy ? "true" : undefined}
      data-view={file}
      className={cn(
        "flex w-60 shrink-0 items-start gap-3 rounded-lg border bg-card p-2 text-left transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid @5xl:w-full",
        current && "border-primary/60 bg-muted ring-1 ring-primary/40",
      )}
    >
      <span
        className="relative block w-12 shrink-0 overflow-hidden rounded-md bg-muted"
        style={{ aspectRatio: width && height ? `${width} / ${height}` : "9 / 16" }}
      >
        <Image src={thumbnailUrl(set, file)} alt="" fill sizes="48px" className="object-cover" />
        {busy && (
          <span className="absolute inset-0 flex items-center justify-center bg-black/50">
            <LoaderCircle aria-hidden className="size-5 animate-spin text-white motion-reduce:animate-none" />
          </span>
        )}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1.5 py-0.5">
        <span className="truncate text-sm font-medium" title={file}>
          {file}
        </span>
        <span className="flex flex-wrap gap-1">
          <Badge variant="secondary" className="tabular-nums">
            {count(viewpoint.landmarks, "landmark")}
          </Badge>
          {viewpoint.truth && (
            <Badge variant="outline" className="border-fuchsia-500/40 text-fuchsia-700 dark:text-fuchsia-300">
              <Crosshair aria-hidden />
              Truth
            </Badge>
          )}
          {latest && <OutcomeBadge step={latest} />}
        </span>
      </span>
    </button>
  );
}

/**
 * The recorded viewpoints of the set: a row to scroll on a narrow screen, a
 * column beside the image on a wide one. Each says how many atlas landmarks
 * are clicked in it, whether the target is, and its latest result here.
 */
export function ViewpointStrip({
  set,
  viewpoints,
  current,
  busy,
  latest,
  onSelect,
  className,
}: {
  set: string;
  viewpoints: Viewpoint[];
  /** The view on screen. */
  current: string | null;
  /** The view being localised. */
  busy: string | null;
  /** The latest step of each view in this session. */
  latest: Map<string, TraceStep>;
  onSelect: (view: string) => void;
  className?: string;
}) {
  return (
    <section aria-labelledby="viewpoints-heading" className={cn("flex min-h-0 flex-col bg-card", className)}>
      <h2 id="viewpoints-heading" className="px-4 pt-3 pb-2 text-sm font-semibold">
        Viewpoints <span className="font-normal text-muted-foreground tabular-nums">({viewpoints.length})</span>
      </h2>
      <ul className="flex min-h-0 gap-2 overflow-x-auto px-3 pt-1 pb-3 @5xl:flex-1 @5xl:flex-col @5xl:overflow-x-visible @5xl:overflow-y-auto">
        {viewpoints.map((viewpoint) => (
          <li key={viewpoint.file} className="flex">
            <ViewpointButton
              set={set}
              viewpoint={viewpoint}
              current={viewpoint.file === current}
              busy={viewpoint.file === busy}
              latest={latest.get(viewpoint.file)}
              onSelect={onSelect}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
