import type { Metadata } from "next";

import { AnnotatorLoader } from "@/components/annotator/annotator-loader";

export const metadata: Metadata = {
  title: "Annotate",
  description: "Mark landmarks and the target in views of an object, from disk or a view set of the workspace.",
};

export default function AnnotatePage() {
  return <AnnotatorLoader />;
}
