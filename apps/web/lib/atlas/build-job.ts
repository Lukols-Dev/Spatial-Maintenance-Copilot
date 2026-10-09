import { useSyncExternalStore } from "react";

import { ApiError, errorMessage } from "@/lib/api";
import { buildAtlas, type AtlasBuildRequest, type AtlasDetail } from "@/lib/workspace";

import { buildFailed, buildingAtlas, rememberAtlas } from "./details";

// The atlas being built. A build poses every image of the set and takes tens
// of seconds, so it lives here rather than in the page: a visit to another
// page and back finds it still running, then finds its answer.

export type BuildJob =
  | { status: "idle" }
  | { status: "building"; request: AtlasBuildRequest; startedAt: number }
  | { status: "built"; request: AtlasBuildRequest; detail: AtlasDetail; seconds: number }
  | { status: "failed"; request: AtlasBuildRequest; message: string; httpStatus: number | null };

const IDLE: BuildJob = { status: "idle" };

let job: BuildJob = IDLE;
const listeners = new Set<() => void>();

function publish(next: BuildJob) {
  job = next;
  listeners.forEach((listener) => listener());
}

/** Build an atlas. Resolves with it; with null when the service refused or another build is running. */
export async function startBuild(request: AtlasBuildRequest): Promise<AtlasDetail | null> {
  if (job.status === "building") return null;
  const startedAt = Date.now();
  buildingAtlas(request.asset_id);
  publish({ status: "building", request, startedAt });
  try {
    const detail = await buildAtlas(request);
    rememberAtlas(detail);
    publish({ status: "built", request, detail, seconds: Math.round((Date.now() - startedAt) / 1000) });
    return detail;
  } catch (error) {
    buildFailed(request.asset_id);
    const httpStatus = error instanceof ApiError ? error.status : null;
    publish({ status: "failed", request, message: errorMessage(error), httpStatus });
    return null;
  }
}

export function buildJob(): BuildJob {
  return job;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The build as it stands; the prerendered HTML has none. */
export function useBuildJob(): BuildJob {
  return useSyncExternalStore(subscribe, () => job, () => IDLE);
}
