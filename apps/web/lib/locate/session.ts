import { errorMessage } from "@/lib/api";
import { latestOnly } from "@/lib/locate/api";
import type { TraceStep, TraceStore } from "@/lib/locate/trace";
import type { LocaliseRequest, LocaliseResult } from "@/lib/locate/types";

// What the Locate page shows for the trace it is on: a localisation on its
// way, its answer (a step of the trace), or why there is none. Only the
// newest request may answer, so a slow answer never replaces a newer choice,
// and every answer becomes a step of the trace it was asked for.

/** The request of the page: one view, and the image the truth comes from. */
export type SessionRequest = Pick<LocaliseRequest, "asset_id" | "view_set" | "view"> & { truth_view: string | null };

export type Shown =
  /** Nothing asked yet: the page shows the latest step of the trace, if any. */
  | { status: "idle" }
  | { status: "running"; request: SessionRequest }
  | { status: "shown"; step: TraceStep }
  | { status: "failed"; request: SessionRequest; message: string };

export const IDLE: Shown = { status: "idle" };

export interface LocateSession {
  /** What is shown for the trace under `key`: the same object until it changes. */
  shown(key: string): Shown;
  /** Localise for the trace under `key`. The answer is added to that trace and shown, unless a newer request came first. */
  run(key: string, request: SessionRequest): void;
  /** Show a step of the trace again; a request on its way is dropped. */
  show(key: string, step: TraceStep): void;
  /** Drop the request on its way, if any: the page has moved on. */
  cancel(): void;
  subscribe(listener: () => void): () => void;
}

export interface SessionDeps {
  localise: (body: SessionRequest, options: { signal: AbortSignal }) => Promise<LocaliseResult>;
  traces: TraceStore;
  /** ISO 8601 time of an answer. */
  now: () => string;
}

/** One session per page: the page is on one trace at a time. */
export function createSession({ localise, traces, now }: SessionDeps): LocateSession {
  let current: { key: string; shown: Shown } = { key: "", shown: IDLE };
  const runner = latestOnly();
  const listeners = new Set<() => void>();

  function set(key: string, shown: Shown) {
    current = { key, shown };
    listeners.forEach((listener) => listener());
  }

  return {
    shown(key) {
      return current.key === key ? current.shown : IDLE;
    },
    run(key, request) {
      const running: Shown = { status: "running", request };
      set(key, running);
      void runner
        .run((signal) => localise(request, { signal }))
        .then((outcome) => {
          if (outcome === null) {
            // Dropped. Unless something newer is shown, there is nothing left to show.
            if (current.shown === running) set(key, IDLE);
            return;
          }
          if (!outcome.ok) {
            set(key, { status: "failed", request, message: errorMessage(outcome.error) });
            return;
          }
          const step = traces.append(key, {
            at: now(),
            view: request.view,
            truthView: request.truth_view,
            result: outcome.value,
          });
          set(key, { status: "shown", step });
        });
    },
    show(key, step) {
      runner.cancel();
      set(key, { status: "shown", step });
    },
    cancel() {
      runner.cancel();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
