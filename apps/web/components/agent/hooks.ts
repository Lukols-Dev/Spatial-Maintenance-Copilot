"use client";

import { useSyncExternalStore } from "react";

import { sessionStore } from "@/components/locate/hooks";
import { answerApproval, chooseView, getSession, startSession } from "@/lib/agent/api";
import { NO_VIEW, createAgentStore, type AgentView } from "@/lib/agent/store";

/** The sessions of the Agent page in this tab. */
export const agent = createAgentStore({
  calls: { start: startSession, choose: chooseView, approve: answerApproval, get: getSession },
  storage: sessionStore,
  now: () => new Date().toISOString(),
});

/** The session under `key`. The prerendered HTML shows none. */
export function useAgentView(key: string): AgentView {
  return useSyncExternalStore(
    agent.subscribe,
    () => agent.view(key),
    () => NO_VIEW,
  );
}
