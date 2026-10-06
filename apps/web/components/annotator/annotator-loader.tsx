"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";

function Placeholder() {
  return <Skeleton className="m-4 h-[calc(100svh-5.5rem)]" />;
}

// The annotator reads localStorage when it starts and draws on a canvas, so it
// only ever renders in the browser. ssr: false is allowed in a client file only.
const Annotator = dynamic(() => import("@/components/annotator/annotator").then((module) => module.Annotator), {
  ssr: false,
  loading: Placeholder,
});
const WorkspaceAnnotator = dynamic(
  () => import("@/components/annotator/workspace-annotator").then((module) => module.WorkspaceAnnotator),
  { ssr: false, loading: Placeholder },
);

/** ?set=<name> opens a view set of the workspace; without it, the annotator works on files from disk. */
function AnnotatorForUrl() {
  const set = useSearchParams().get("set");
  // A key per set: moving to another set, or to files from disk, starts afresh.
  return set === null ? <Annotator /> : <WorkspaceAnnotator key={set} set={set} />;
}

export function AnnotatorLoader() {
  // The exported HTML cannot know the query string: the page renders below this boundary in the browser.
  return (
    <Suspense fallback={<Placeholder />}>
      <AnnotatorForUrl />
    </Suspense>
  );
}
