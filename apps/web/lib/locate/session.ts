import type { TraceStep } from "@/lib/locate/trace";
import type { LocaliseRequest } from "@/lib/locate/types";

// What a page shows of a session's localisation: one on its way, its answer
// (a step of the session), or why there is none.

/** The request of the page: one view, and the image the truth comes from. */
export type SessionRequest = Pick<LocaliseRequest, "asset_id" | "view_set" | "view"> & { truth_view: string | null };

export type Shown =
  /** Nothing asked yet: the page shows the latest step of the trace, if any. */
  | { status: "idle" }
  | { status: "running"; request: SessionRequest }
  | { status: "shown"; step: TraceStep }
  | { status: "failed"; request: SessionRequest; message: string };

export const IDLE: Shown = { status: "idle" };
