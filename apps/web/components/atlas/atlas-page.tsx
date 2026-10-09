"use client";

import { RotateCw } from "lucide-react";
import { useState, type ReactNode } from "react";

import { BuildCard } from "@/components/atlas/build-card";
import { ResultCard } from "@/components/atlas/result-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Empty, EmptyContent, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { keepAtlas, keptAtlas } from "@/lib/atlas/draft";
import { cn } from "@/lib/utils";
import { refreshWorkspace, useWorkspace } from "@/lib/workspace";

function Retry() {
  return (
    <Button type="button" variant="outline" onClick={() => void refreshWorkspace()}>
      <RotateCw /> Retry
    </Button>
  );
}

function SkeletonCard({ blocks }: { blocks: number }) {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-24" />
      </CardHeader>
      <CardContent className="space-y-3">
        {Array.from({ length: blocks }, (_, index) => (
          <Skeleton key={index} className="h-24" />
        ))}
      </CardContent>
    </Card>
  );
}

function Loading() {
  return (
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]" aria-busy>
      <SkeletonCard blocks={3} />
      <SkeletonCard blocks={4} />
    </div>
  );
}

/**
 * Build an atlas from a view set of the workspace, and look at the atlases it
 * holds. A read-only service shows the atlases only.
 */
export function AtlasPage() {
  const state = useWorkspace();
  const [selected, setSelected] = useState<string | null>(keptAtlas);

  function select(id: string) {
    keepAtlas(id);
    setSelected(id);
  }

  const data = state.status === "loading" ? undefined : state.data;
  let content: ReactNode;
  if (state.status === "loading") {
    content = <Loading />;
  } else if (!data) {
    content = (
      <Empty>
        <EmptyHeader role="alert">
          <EmptyTitle className="wrap-anywhere">{state.status === "error" ? state.message : ""}</EmptyTitle>
        </EmptyHeader>
        <EmptyContent>
          <Retry />
        </EmptyContent>
      </Empty>
    );
  } else {
    content = (
      <>
        {state.status === "error" && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2">
            <p role="alert" className="min-w-0 flex-1 text-sm text-destructive wrap-anywhere">
              {state.message}
            </p>
            <Retry />
          </div>
        )}
        <div
          className={cn("grid items-start gap-4", !data.read_only && "xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]")}
        >
          {!data.read_only && <BuildCard workspace={data} onBuilt={select} />}
          <ResultCard workspace={data} selected={selected} onSelect={select} />
        </div>
      </>
    );
  }

  return <div className="mx-auto w-full max-w-7xl space-y-4 p-4 md:p-6">{content}</div>;
}
