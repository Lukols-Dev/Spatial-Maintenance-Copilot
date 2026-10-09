import type { Metadata } from "next";

import { LocatePage } from "@/components/locate/locate-page";
import { SITE } from "@/lib/site";

// The root layout's title template does not apply to its own segment, so the
// home page writes the whole title the template gives every other page.
export const metadata: Metadata = {
  title: { absolute: `Locate · ${SITE.name}` },
  description: "Locate the target of an atlas in a recorded viewpoint, with its uncertainty region and the decision.",
};

export default function HomePage() {
  return <LocatePage />;
}
