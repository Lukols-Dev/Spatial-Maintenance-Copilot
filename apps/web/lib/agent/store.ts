import { NO_SESSION, applyAnswer, readSessionId, writeSessionId, type AgentState } from "@/lib/agent/session";
import type { SessionStart, SessionTurn } from "@/lib/agent/types";
import { ApiError, errorMessage } from "@/lib/api";
import { latestOnly } from "@/lib/locate/api";
import type { StorageLike } from "@/lib/locate/trace";

// The Agent page's sessions, one per atlas build and view set (the key). A
// call runs at a time: a newer one drops the answer of the one before, as on
// the Locate page. The session id is stored, so a reload asks the service
// where the session stands.

/** What the page is asking the service for, if anything. */
export type Pending =
  | { kind: "start"; asset: string; set: string; view: string }
  | { kind: "choose"; view: string }
  | { kind: "approve"; approved: boolean }
  | { kind: "resume"; id: string };

export interface AgentView {
  session: AgentState;
  pending: Pending | null;
  /** The last call failed: why, and the call, to try again. */
  failure: { message: string; action: Pending } | null;
}

export const NO_VIEW: AgentView = { session: NO_SESSION, pending: null, failure: null };

type Options = { signal: AbortSignal };

export interface AgentCalls {
  start(body: SessionStart, options: Options): Promise<SessionTurn>;
  choose(id: string, view: string, options: Options): Promise<SessionTurn>;
  approve(id: string, approved: boolean, options: Options): Promise<SessionTurn>;
  get(id: string, options: Options): Promise<SessionTurn>;
}

export interface AgentStore {
  /** The session under `key`: the same object until it changes. */
  view(key: string): AgentView;
  /** Ask the service; the answer updates the session under `key`. */
  run(key: string, action: Pending): void;
  /** Read back the session stored under `key`, unless one is on screen or asked for. */
  resume(key: string): void;
  /** Forget the session under `key`: the next view starts a new one. */
  reset(key: string): void;
  /** Drop the call on its way: the page has moved on. */
  cancel(): void;
  subscribe(listener: () => void): () => void;
}

export function createAgentStore({
  calls,
  storage,
  now,
}: {
  calls: AgentCalls;
  storage: () => StorageLike | null;
  /** ISO 8601 time of an answer. */
  now: () => string;
}): AgentStore {
  const views = new Map<string, AgentView>();
  const listeners = new Set<() => void>();
  const runner = latestOnly();

  const viewOf = (key: string) => views.get(key) ?? NO_VIEW;
  function set(key: string, view: AgentView) {
    views.set(key, view);
    listeners.forEach((listener) => listener());
  }

  function call(action: Pending, id: string, signal: AbortSignal): Promise<SessionTurn> {
    switch (action.kind) {
      case "start":
        return calls.start({ asset_id: action.asset, view_set: action.set, view: action.view }, { signal });
      case "choose":
        return calls.choose(id, action.view, { signal });
      case "approve":
        return calls.approve(id, action.approved, { signal });
      case "resume":
        return calls.get(action.id, { signal });
    }
  }

  async function run(key: string, action: Pending) {
    const id = viewOf(key).session.sessionId ?? "";
    set(key, { ...viewOf(key), pending: action, failure: null });
    const outcome = await runner.run((signal) => call(action, id, signal));
    if (outcome === null) return; // a newer call took over, or the page left
    const current = viewOf(key);
    if (!outcome.ok) {
      // The service restarted and forgot the session: the page starts afresh, quietly.
      if (action.kind === "resume" && outcome.error instanceof ApiError && outcome.error.status === 404) {
        writeSessionId(storage(), key, null);
        set(key, { ...current, pending: null });
        return;
      }
      set(key, { ...current, pending: null, failure: { message: errorMessage(outcome.error), action } });
      return;
    }
    const mode = action.kind === "start" ? "start" : action.kind === "resume" ? "resume" : "continue";
    set(key, { session: applyAnswer(current.session, outcome.value, now(), mode), pending: null, failure: null });
    writeSessionId(storage(), key, outcome.value.turn.session_id);
  }

  return {
    view: viewOf,
    run(key, action) {
      void run(key, action);
    },
    resume(key) {
      const view = viewOf(key);
      if (view.session.sessionId !== null || view.pending !== null) return;
      const id = readSessionId(storage(), key);
      if (id) void run(key, { kind: "resume", id });
    },
    reset(key) {
      runner.cancel();
      writeSessionId(storage(), key, null);
      set(key, NO_VIEW);
    },
    cancel() {
      runner.cancel();
      let changed = false;
      for (const [key, view] of views) {
        if (view.pending !== null) {
          views.set(key, { ...view, pending: null });
          changed = true;
        }
      }
      if (changed) listeners.forEach((listener) => listener());
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
