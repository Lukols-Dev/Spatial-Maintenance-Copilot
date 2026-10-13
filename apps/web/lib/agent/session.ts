import type { SessionTurn, TraceEvent, Turn } from "@/lib/agent/types";
import type { StorageLike, TraceStep } from "@/lib/locate/trace";
import type { Viewpoint } from "@/lib/locate/viewpoints";

// What the Agent page keeps of a session: the latest turn, the whole trace of
// events, and every localisation it showed, as steps the Locate panels read.
// Only the session id is stored, per atlas build and view set, so a reload
// asks the service where the session stands.

export interface AgentState {
  sessionId: string | null;
  turn: Turn | null;
  events: TraceEvent[];
  /** One per viewpoint the agent localised, in order. */
  steps: TraceStep[];
  /** The model that speaks for the agent, as the service named it. */
  model: string | null;
}

export const NO_SESSION: AgentState = { sessionId: null, turn: null, events: [], steps: [], model: null };

/**
 * The state after an answer.
 *
 * - "start": a new session; nothing of the one before stays.
 * - "continue": the answer to the operator's view or approval; its events follow the ones before.
 * - "resume": GET /sessions/{id}, whose events are the whole trace.
 *
 * A turn that localised a viewpoint (it has a perception event, or it is a
 * resume) adds a step with the localisation to draw.
 */
export function applyAnswer(
  state: AgentState,
  answer: SessionTurn,
  at: string,
  mode: "start" | "continue" | "resume",
): AgentState {
  const { turn, result, model } = answer;
  const base = mode === "continue" ? state : NO_SESSION;
  const events = mode === "continue" ? [...state.events, ...turn.events] : turn.events;
  const localised = mode === "resume" || turn.events.some((event) => event.kind === "perception");
  const steps =
    localised && result
      ? [
          ...base.steps,
          { n: base.steps.length + 1, at, view: result.request.view, truthView: result.request.truth_view, result },
        ]
      : base.steps;
  return { sessionId: turn.session_id, turn, events, steps, model };
}

/** The viewpoints a session can be on: landmarks clicked, the target not, so it is hidden. */
export function agentViewpoints(viewpoints: readonly Viewpoint[]): Viewpoint[] {
  return viewpoints.filter((viewpoint) => !viewpoint.truth);
}

/** What choosing a viewpoint does now: start a session, answer the agent, or nothing. */
export function viewpointAction(turn: Turn | null): "start" | "choose" | null {
  if (turn === null || turn.outcome !== null) return "start";
  return turn.awaiting?.kind === "view" ? "choose" : null;
}

const SESSION_PREFIX = "smc-agent:session:v1:";

/** One session per build of an atlas and view set, like the traces of Locate. */
export function sessionKey(asset: string, builtAt: string, set: string): string {
  return `${SESSION_PREFIX}${asset}@${builtAt}/${set}`;
}

export function readSessionId(storage: StorageLike | null, key: string): string | null {
  try {
    const value = storage?.getItem(key) ?? null;
    return value && /^[0-9a-f]{32}$/.test(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeSessionId(storage: StorageLike | null, key: string, id: string | null): void {
  try {
    if (id === null) storage?.removeItem(key);
    else storage?.setItem(key, id);
  } catch {
    // Storage blocked or full: the session is only lost on reload.
  }
}
