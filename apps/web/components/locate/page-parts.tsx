"use client";

import { Boxes, OctagonX, RotateCw, ShieldCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { actionLabel, count, failureLabel, px } from "@/lib/locate/format";
import type { Shown } from "@/lib/locate/session";
import { regionPx } from "@/lib/locate/trace";
import type { LocaliseResult } from "@/lib/locate/types";
import { cn } from "@/lib/utils";
import { refreshWorkspace, type AtlasSummary } from "@/lib/workspace";

// The frame of the pages that show a viewpoint and its localisation, Locate
// and Agent: the toolbar, the grid, the states in place of a result, and the
// verdict written on the picture.

// On a wide container the page fills the window under the header, so a
// portrait view fits its height; the viewpoints and layers, the image and the
// decision stand side by side. Narrower, they stack: viewpoints, image,
// decision, layers.
export const FRAME = "flex flex-col @5xl:h-[calc(100svh-3.5rem)] @5xl:min-h-[36rem]";
export const GRID =
  "grid min-h-0 flex-1 grid-cols-1 @5xl:grid-cols-[15rem_minmax(0,1fr)_24rem] @5xl:grid-rows-[minmax(0,1fr)_auto]";
export const AREA = {
  strip: "border-b @5xl:col-start-1 @5xl:row-start-1 @5xl:border-r @5xl:border-b-0",
  image: "@5xl:col-start-2 @5xl:row-span-2 @5xl:row-start-1",
  panel: "@5xl:col-start-3 @5xl:row-span-2 @5xl:row-start-1 @5xl:min-h-0 @5xl:overflow-y-auto @5xl:border-l",
  layers: "border-t @5xl:col-start-1 @5xl:row-start-2 @5xl:border-r",
};
export const IMAGE_BOX = "relative h-[70svh] min-h-80 bg-neutral-950 @5xl:h-auto @5xl:min-h-0 @5xl:flex-1";

export function Page({ toolbar, children, below }: { toolbar: ReactNode; children: ReactNode; below?: ReactNode }) {
  return (
    <div className="@container">
      <div className={FRAME}>
        {toolbar}
        {children}
      </div>
      {below}
    </div>
  );
}

export function Field({ label, htmlFor, facts, children }: { label: string; htmlFor: string; facts?: string | null; children: ReactNode }) {
  return (
    <div className="min-w-0 space-y-1">
      <Label htmlFor={htmlFor} className="text-xs text-muted-foreground">
        {label}
      </Label>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {children}
        {facts && <span className="text-xs text-muted-foreground tabular-nums">{facts}</span>}
      </div>
    </div>
  );
}

export function Toolbar({ children, problem }: { children: ReactNode; problem?: string | null }) {
  return (
    <>
      {problem && (
        <div role="alert" className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b bg-amber-500/10 px-3 py-2 text-sm">
          <TriangleAlert aria-hidden className="size-4 shrink-0 text-amber-700 dark:text-amber-400" />
          <span className="min-w-0 flex-1 wrap-anywhere">Workspace not refreshed: {problem}</span>
          <Button size="sm" variant="outline" onClick={() => void refreshWorkspace()}>
            <RotateCw aria-hidden /> Retry
          </Button>
        </div>
      )}
      <div className="flex flex-wrap items-end gap-x-8 gap-y-3 border-b p-3">{children}</div>
    </>
  );
}

export function BodySkeleton() {
  return (
    <div className={GRID} aria-busy="true">
      <div className={cn("flex gap-2 overflow-hidden p-3 @5xl:flex-col", AREA.strip)}>
        {[0, 1, 2].map((index) => (
          <Skeleton key={index} className="h-28 w-60 shrink-0 @5xl:w-full" />
        ))}
      </div>
      <div className={cn("flex flex-col", AREA.image)}>
        <div className="h-12 border-b bg-card" />
        <div className={IMAGE_BOX}>
          <Skeleton className="absolute inset-y-6 left-1/2 aspect-[9/16] max-w-[90%] -translate-x-1/2 bg-neutral-800" />
        </div>
      </div>
      <div className={cn("space-y-4 p-4", AREA.panel)}>
        <Skeleton className="h-6 w-28" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-56 w-full" />
      </div>
      <div className={cn("p-3", AREA.layers)}>
        <Skeleton className="h-36 w-full" />
      </div>
    </div>
  );
}

export function PageSkeleton() {
  return (
    <Page
      toolbar={
        <Toolbar>
          {["Asset", "Viewpoints"].map((label) => (
            <div key={label} className="space-y-1">
              <span className="text-xs font-medium text-muted-foreground">{label}</span>
              <Skeleton className="h-8 w-52" />
            </div>
          ))}
        </Toolbar>
      }
    >
      <BodySkeleton />
    </Page>
  );
}

/** A state of the page in a few words, next to what resolves it. */
export function State({ icon, title, detail, alert, action }: {
  icon: ReactNode;
  title: string;
  detail?: string | null;
  alert?: boolean;
  action: ReactNode;
}) {
  return (
    <div className="flex flex-1 items-center justify-center p-6 py-16">
      <Empty className="max-w-lg border">
        <EmptyHeader role={alert ? "alert" : undefined}>
          <EmptyMedia variant="icon">{icon}</EmptyMedia>
          <EmptyTitle>{title}</EmptyTitle>
          {detail && <EmptyDescription className="wrap-anywhere">{detail}</EmptyDescription>}
        </EmptyHeader>
        <EmptyContent>{action}</EmptyContent>
      </Empty>
    </div>
  );
}

export function AtlasLink() {
  return (
    <Button asChild>
      <Link href="/atlas">
        <Boxes aria-hidden /> Atlas
      </Link>
    </Button>
  );
}

export function RetryButton({ onRetry }: { onRetry: () => void }) {
  return (
    <Button onClick={onRetry}>
      <RotateCw aria-hidden /> Retry
    </Button>
  );
}

export function atlasFacts(atlas: AtlasSummary): string {
  if (atlas.error) return atlas.error;
  const facts = [atlas.version && `v${atlas.version}`, atlas.landmarks !== null && count(atlas.landmarks, "landmark")];
  if (atlas.target_id) facts.push(`target ${atlas.target_id}`);
  return facts.filter(Boolean).join(" · ");
}

/** What the picture says, for those who cannot see it. */
export function pictureLabel(view: string, result: LocaliseResult | null): string {
  if (!result) return view;
  const { decision, localisation } = result;
  if (localisation.failure) return `${view}: ${failureLabel(localisation.failure)}, no target region`;
  const region = regionPx(result);
  return `${view}: ${count(result.observations.length, "landmark")} observed, target region ${px(region)}, ${
    decision.reliable ? "reliable" : "not reliable"
  }`;
}

/** The verdict on the picture itself, so it is never read without it. */
export function ImageChip({ shown }: { shown: Shown }) {
  if (shown.status === "running") {
    return <span className="rounded-md bg-black/70 px-2 py-1 text-xs font-medium text-white">Locating…</span>;
  }
  if (shown.status !== "shown") return null;
  const { decision, localisation } = shown.step.result;
  if (localisation.failure) {
    return (
      <span className="flex items-center gap-1.5 rounded-md bg-black/75 px-2 py-1 text-xs font-medium text-red-300">
        <OctagonX aria-hidden className="size-3.5" />
        {failureLabel(localisation.failure)}
      </span>
    );
  }
  if (decision.reliable) {
    return (
      <span className="flex items-center gap-1.5 rounded-md bg-black/75 px-2 py-1 text-xs font-medium text-emerald-300">
        <ShieldCheck aria-hidden className="size-3.5" />
        Reliable
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 rounded-md bg-black/75 px-2 py-1 text-xs font-medium text-amber-300">
      <TriangleAlert aria-hidden className="size-3.5" />
      {`Not reliable · ${actionLabel(decision.action)}`}
    </span>
  );
}
