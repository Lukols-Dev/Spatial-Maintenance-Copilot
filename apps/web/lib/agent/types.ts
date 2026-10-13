import type { Action, Decision, Localisation, LocaliseResult } from "@/lib/locate/types";

// The agent's sessions as the perception service answers them: the models of
// smc_agent.contracts and smc_perception.models.SessionTurn, field for field.

/** One viewpoint as the agent saw it: the geometry and the policy's verdict. */
export interface Located {
  view: string;
  localisation: Localisation;
  decision: Decision;
}

/** The result is not reliable: the operator is asked for another viewpoint. */
export interface ViewRequest {
  kind: "view";
  view: string;
  /** The policy's move. */
  action: Action;
  /** The policy's fact the move follows from. */
  move_reason: string;
  /** The agent's words to the operator; no numbers. */
  guidance: string;
  /** Recorded viewpoints that fit the move, best first. */
  suggested_views: string[];
}

/** The result is reliable: the operator approves the next maintenance step, or not. */
export interface ApprovalRequest {
  kind: "approval";
  view: string;
  explanation: string;
  next_step: string;
}

export type EventKind = "perception" | "decision" | "agent" | "tool" | "human" | "guard" | "fallback";

export interface TraceEvent {
  /** 1 for the first event of the session, then one more each. */
  step: number;
  kind: EventKind;
  /** The graph node that wrote it. */
  node: string;
  summary: string;
  data: Record<string, unknown>;
}

export interface Turn {
  session_id: string;
  asset_id: string;
  view_set: string;
  located: Located | null;
  /** Null once the session has ended. */
  awaiting: ViewRequest | ApprovalRequest | null;
  outcome: "accepted" | "declined" | null;
  /** The events the call added; all of them for GET /sessions/{id}. */
  events: TraceEvent[];
}

export interface SessionTurn {
  turn: Turn;
  /** The localisation of turn.located's viewpoint, as POST /localise answers it. */
  result: LocaliseResult | null;
  /** The language model that speaks for the agent, or why none does. */
  model: string;
}

export interface SessionStart {
  asset_id: string;
  view_set: string;
  view: string;
}
