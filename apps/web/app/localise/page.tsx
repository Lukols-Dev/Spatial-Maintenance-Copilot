import type { Metadata } from "next";

import { GuidePage } from "@/components/guide/guide-page";

export const metadata: Metadata = {
  title: "Localise",
  description: "A live camera or a video file localised from its printed markers: the move, the hidden target, and the agent.",
};

export default function Page() {
  return <GuidePage />;
}
