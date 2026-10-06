"use client";

import { FolderOpen, RotateCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Annotator } from "@/components/annotator/annotator";
import { SaveIndicator, useAutosave } from "@/components/annotator/autosave";
import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Progress } from "@/components/ui/progress";
import * as core from "@/lib/annotate/core";
import { apiFetch, errorMessage, imageUrl } from "@/lib/api";
import {
  getViewSet,
  matchingCameras,
  refreshWorkspace,
  workspaceState,
  type ViewSet,
  type ViewSetImage,
} from "@/lib/workspace";

/** The service's rule for a view set name: one safe path segment. */
const SET_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
/** Images asked for at once: enough to keep the connection busy, few enough for the progress to move. */
const PARALLEL_IMAGES = 4;

/** A view set read from the service, ready to annotate. */
interface Opened {
  state: core.AnnotationState;
  files: File[];
  /** Facts about the set's clicks to say once its images are open. */
  notices: string[];
  /** The workspace refuses changes. */
  readOnly: boolean;
}

type Load =
  | { phase: "set" }
  | { phase: "images"; done: number; total: number }
  | { phase: "ready"; opened: Opened }
  | { phase: "failed"; message: string };

/**
 * The state the set's clicks give. Clicks on files that are not images of the
 * set are left out, as the service would refuse to save them.
 */
function clicksState(viewSet: ViewSet): Pick<Opened, "state" | "notices"> {
  const clicks = viewSet.clicks;
  if (!clicks) return { state: core.createState(), notices: [] };
  const images = new Set(viewSet.images.map((image) => image.file));
  const strays = Object.keys(clicks.views).filter((file) => !images.has(file));
  const views = Object.fromEntries(Object.entries(clicks.views).filter(([file]) => images.has(file)));
  try {
    return {
      state: core.fromJson(core.createState(), { ...clicks, views }).state,
      notices:
        strays.length > 0
          ? [`Left out the clicks on ${strays.length} file(s) not in ${viewSet.name}: ${strays.join(", ")}.`]
          : [],
    };
  } catch (error) {
    throw new Error(`clicks.json: ${errorMessage(error)}`);
  }
}

/** Every image of the set as a File, in the set's order. The first failure stops the rest. */
async function fetchImages(
  set: string,
  images: ViewSetImage[],
  signal: AbortSignal,
  progress: (done: number, total: number) => void,
): Promise<File[]> {
  const files: File[] = [];
  const stop = new AbortController();
  const either = AbortSignal.any([signal, stop.signal]);
  let next = 0;
  let done = 0;

  const worker = async () => {
    while (next < images.length) {
      const index = next++;
      const { file } = images[index];
      try {
        const blob = await apiFetch(imageUrl(set, file), { signal: either }, (response) => response.blob());
        files[index] = new File([blob], file, { type: blob.type });
      } catch (error) {
        stop.abort();
        throw new Error(`${file}: ${errorMessage(error)}`);
      }
      progress(++done, images.length);
    }
  };
  progress(0, images.length);
  await Promise.all(Array.from({ length: Math.min(PARALLEL_IMAGES, images.length) }, worker));
  return files;
}

/**
 * Read the set, its clicks and its images. The workspace is read alongside:
 * without a camera in the clicks, the set's is the only calibrated camera of
 * its image size, and the workspace says whether it takes changes.
 */
async function openSet(
  set: string,
  signal: AbortSignal,
  progress: (done: number, total: number) => void,
): Promise<Opened> {
  const workspaceRead = refreshWorkspace();
  const viewSet = await getViewSet(set, { signal });
  if (viewSet.clicks_error) throw new Error(viewSet.clicks_error);
  const { state, notices } = clicksState(viewSet);
  const files = await fetchImages(set, viewSet.images, signal, progress);

  await workspaceRead;
  const workspace = workspaceState();
  const data = workspace.status === "loading" ? undefined : workspace.data;
  const cameras = data ? matchingCameras(data, set) : [];
  const cameraId = state.cameraId || (cameras.length === 1 ? (cameras[0].camera_id ?? "") : "");
  return { state: { ...state, cameraId }, files, notices, readOnly: data?.read_only ?? false };
}

/** The annotator on view set `set` of the workspace: images from the service, every change saved to it. */
export function WorkspaceAnnotator({ set }: { set: string }) {
  const valid = SET_NAME.test(set);
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState<Load>({ phase: "set" });

  useEffect(() => {
    if (!valid) return;
    const controller = new AbortController();
    const { signal } = controller;
    openSet(set, signal, (done, total) => {
      if (!signal.aborted) setLoad({ phase: "images", done, total });
    }).then(
      (opened) => {
        if (!signal.aborted) setLoad({ phase: "ready", opened });
      },
      (error: unknown) => {
        if (!signal.aborted) setLoad({ phase: "failed", message: errorMessage(error) });
      },
    );
    return () => controller.abort();
  }, [set, valid, attempt]);

  function retry() {
    setLoad({ phase: "set" });
    setAttempt((count) => count + 1);
  }

  if (!valid) return <OpenFailed title="Invalid view set name" detail={set} />;
  if (load.phase === "failed") return <OpenFailed title={`Cannot open ${set}`} detail={load.message} onRetry={retry} />;
  if (load.phase !== "ready") return <Opening set={set} load={load} />;
  return <Session set={set} opened={load.opened} />;
}

function Session({ set, opened }: { set: string; opened: Opened }) {
  const autosave = useAutosave(set, opened.state, opened.readOnly);
  return (
    <Annotator
      workspace={{
        set,
        initial: opened.state,
        files: opened.files,
        notices: opened.notices,
        onChange: autosave.change,
        status: <SaveIndicator status={autosave.status} onRetry={autosave.retry} />,
      }}
    />
  );
}

function Opening({ set, load }: { set: string; load: Extract<Load, { phase: "set" | "images" }> }) {
  const images = load.phase === "images" ? load : null;
  const percent = images && images.total > 0 ? (100 * images.done) / images.total : null;
  return (
    <div className="flex h-[calc(100svh-3.5rem)] min-h-144 flex-col items-center justify-center gap-3 p-6">
      <h2 className="text-sm font-semibold">{set}</h2>
      <p className="text-sm text-muted-foreground tabular-nums">
        {images ? `Loading ${images.done} / ${images.total}` : "Loading…"}
      </p>
      {/* The ui Progress uses value for its bar only, so the numbers are given to assistive technology here. */}
      <Progress
        className="w-64 max-w-full"
        value={percent}
        aria-label="Images loaded"
        aria-valuenow={images?.done}
        aria-valuemax={images?.total}
        aria-valuetext={images ? `${images.done} of ${images.total}` : undefined}
      />
    </div>
  );
}

function OpenFailed({ title, detail, onRetry }: { title: string; detail: string; onRetry?: () => void }) {
  return (
    <div className="flex h-[calc(100svh-3.5rem)] min-h-144 items-center justify-center p-6">
      <Empty>
        <EmptyHeader role="alert">
          <EmptyTitle>{title}</EmptyTitle>
          <EmptyDescription className="wrap-anywhere">{detail}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent className="flex-row flex-wrap justify-center">
          {onRetry && (
            <Button onClick={onRetry}>
              <RotateCw /> Retry
            </Button>
          )}
          <Button asChild variant="outline">
            <Link href="/annotate">
              <FolderOpen /> Local files
            </Link>
          </Button>
        </EmptyContent>
      </Empty>
    </div>
  );
}
