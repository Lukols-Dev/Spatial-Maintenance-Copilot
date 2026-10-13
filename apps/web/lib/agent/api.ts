import { apiJson } from "@/lib/api";
import type { SessionStart, SessionTurn } from "@/lib/agent/types";

// The calls of the Agent page. Each runs a turn of the agent: localising a
// viewpoint, and a call to the language model when one is configured.

/** A turn localises a view and may wait for the model; a slow machine takes tens of seconds. */
export const SESSION_TIMEOUT_MS = 2 * 60_000;

type Options = { signal?: AbortSignal };

function post(path: string, body: unknown, options: Options): Promise<SessionTurn> {
  return apiJson<SessionTurn>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: SESSION_TIMEOUT_MS,
    signal: options.signal,
  });
}

function sessionPath(id: string): string {
  return `/sessions/${encodeURIComponent(id)}`;
}

/** A new session at the operator's first viewpoint. */
export function startSession(body: SessionStart, options: Options = {}): Promise<SessionTurn> {
  return post("/sessions", body, options);
}

/** The viewpoint the operator chose, after the agent asked for one. */
export function chooseView(id: string, view: string, options: Options = {}): Promise<SessionTurn> {
  return post(`${sessionPath(id)}/view`, { view }, options);
}

/** The operator's answer to the next step the agent proposed; it ends the session. */
export function answerApproval(id: string, approved: boolean, options: Options = {}): Promise<SessionTurn> {
  return post(`${sessionPath(id)}/approval`, { approved }, options);
}

/** Where a session stands, with its whole trace. */
export function getSession(id: string, options: Options = {}): Promise<SessionTurn> {
  return apiJson<SessionTurn>(sessionPath(id), { timeoutMs: SESSION_TIMEOUT_MS, signal: options.signal });
}
