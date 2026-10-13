import type { Metadata } from "next";

import { AgentPage } from "@/components/agent/agent-page";

export const metadata: Metadata = {
  title: "Agent",
  description: "A session of the agent on recorded viewpoints: the move the policy chose, in the agent's words, and its trace.",
};

export default function Page() {
  return <AgentPage />;
}
