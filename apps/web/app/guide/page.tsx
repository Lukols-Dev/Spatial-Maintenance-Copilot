import type { Metadata } from "next";

import { GuidePage } from "@/components/guide/guide-page";

export const metadata: Metadata = {
  title: "Guide",
  description: "Frames of a camera or a video localised as they come: the move, the hidden target, and the agent.",
};

export default function Page() {
  return <GuidePage />;
}
