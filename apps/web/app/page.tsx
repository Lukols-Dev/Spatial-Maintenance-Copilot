import type { Metadata } from "next";

import { AgentPage } from "@/components/agent/agent-page";
import { SITE } from "@/lib/site";

// The root layout's title template does not apply to its own segment, so the
// home page writes the whole title the template gives every other page.
export const metadata: Metadata = {
  title: { absolute: `Demo · ${SITE.name}` },
  description:
    "The agent's loop on recorded viewpoints of the cabinet: the geometry localises the hidden target and decides, the agent asks for a view, the operator chooses.",
};

export default function HomePage() {
  return <AgentPage />;
}
