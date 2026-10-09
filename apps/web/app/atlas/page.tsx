import type { Metadata } from "next";

import { AtlasPage } from "@/components/atlas/atlas-page";

export const metadata: Metadata = {
  title: "Atlas",
  description: "Build an atlas of an object from a view set of the workspace, and inspect its points.",
};

export default function Page() {
  return <AtlasPage />;
}
