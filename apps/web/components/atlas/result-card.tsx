"use client";

import { RotateCw } from "lucide-react";
import { useEffect, useId, type ReactNode } from "react";

import { PlanView } from "@/components/atlas/plan-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { atlasRead, readAtlas, useAtlasReads } from "@/lib/atlas/details";
import { fixed, localTime, sentence } from "@/lib/atlas/format";
import { atlasesNewestFirst } from "@/lib/atlas/form";
import { planInput } from "@/lib/atlas/plan";
import { buildFacts, buildSet, figures, pointRows, skippedPoints } from "@/lib/atlas/result";
import type { AtlasDetail, AtlasSummary, Workspace } from "@/lib/workspace";

function atlasLabel(atlas: AtlasSummary): string {
  if (atlas.error) return `${atlas.asset_id} · unreadable`;
  return atlas.version === null ? atlas.asset_id : `${atlas.asset_id} v${atlas.version}`;
}

function Subheading({ id, children }: { id?: string; children: string }) {
  return (
    <h3 id={id} className="text-sm font-medium">
      {children}
    </h3>
  );
}

function Facts({ detail, summary, workspace }: { detail: AtlasDetail; summary: AtlasSummary; workspace: Workspace }) {
  const facts = buildFacts(detail, summary, buildSet(workspace, detail));
  const items: [string, string | null][] = [
    ["Set", facts.viewSet],
    ["Camera", facts.camera],
    ["Board", facts.board],
    ["Built", facts.builtAt === null ? null : localTime(facts.builtAt)],
  ];
  return (
    <div className="space-y-2">
      <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
        {items
          .filter((item): item is [string, string] => item[1] !== null)
          .map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="font-medium wrap-anywhere">{value}</dd>
            </div>
          ))}
      </dl>
      {facts.clicksChanged && <Badge variant="outline">Points saved after this build</Badge>}
    </div>
  );
}

function Figures({ detail, workspace }: { detail: AtlasDetail; workspace: Workspace }) {
  return (
    <dl className="grid grid-cols-[repeat(auto-fit,minmax(7.5rem,1fr))] gap-2">
      {figures(detail, buildSet(workspace, detail)).map((figure) => (
        <div key={figure.label} className="min-w-0 rounded-lg border px-3 py-2">
          <dt className="text-xs text-muted-foreground">{figure.label}</dt>
          <dd className="text-xl font-semibold tabular-nums">
            {figure.value}
            {figure.unit && <span className="text-sm font-normal text-muted-foreground"> {figure.unit}</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Points({ detail }: { detail: AtlasDetail }) {
  const heading = useId();
  const rows = pointRows(detail);
  const reported = detail.report !== null;
  const numeric = "text-right tabular-nums";
  return (
    <section className="min-w-0 space-y-2">
      <Subheading id={heading}>Points</Subheading>
      <Table aria-labelledby={heading}>
        <TableHeader>
          <TableRow>
            <TableHead>Point</TableHead>
            <TableHead className="text-right">x mm</TableHead>
            <TableHead className="text-right">y mm</TableHead>
            <TableHead className="text-right">z mm</TableHead>
            <TableHead className="text-right">σ mm</TableHead>
            {reported && (
              <>
                <TableHead className="text-right">Views</TableHead>
                <TableHead className="text-right">Worst px</TableHead>
                <TableHead className="text-right">Ray angle °</TableHead>
              </>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id} data-point={row.id}>
              <TableCell className="font-medium">
                <span className="flex items-center gap-2">
                  {row.id}
                  {row.is_target && <Badge variant="secondary">Target</Badge>}
                </span>
              </TableCell>
              {row.position_mm.map((value, axis) => (
                <TableCell key={axis} className={numeric}>
                  {fixed(value, 1)}
                </TableCell>
              ))}
              <TableCell className={numeric}>{fixed(row.sigma_mm, 2)}</TableCell>
              {reported && (
                <>
                  <TableCell className={numeric}>{row.views}</TableCell>
                  <TableCell className={numeric}>{row.worst_px === null ? "" : fixed(row.worst_px, 2)}</TableCell>
                  <TableCell className={numeric}>
                    {row.ray_angle_deg === null ? "" : fixed(row.ray_angle_deg, 1)}
                  </TableCell>
                </>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}

function Leftovers({ detail }: { detail: AtlasDetail }) {
  const { report } = detail;
  if (!report) return null;
  const skipped = skippedPoints(report);
  const unposed = report.unposed_views;
  if (skipped.length === 0 && unposed.length === 0) return null;
  return (
    <div className="grid gap-4 @md:grid-cols-2">
      {skipped.length > 0 && (
        <section className="min-w-0 space-y-2">
          <Subheading>Skipped points</Subheading>
          <ul className="space-y-1 text-sm">
            {skipped.map(({ id, reason }) => (
              <li key={id} data-skipped={id} className="wrap-anywhere">
                <span className="font-medium">{id}</span>
                <span className="text-muted-foreground"> · {sentence(reason)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {unposed.length > 0 && (
        <section className="min-w-0 space-y-2">
          <Subheading>Unposed views</Subheading>
          <ul className="flex flex-wrap gap-1.5">
            {unposed.map((file) => (
              <li key={file}>
                <Badge variant="outline" className="font-mono">
                  {file}
                </Badge>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Shown({ detail, summary, workspace }: { detail: AtlasDetail; summary: AtlasSummary; workspace: Workspace }) {
  const { atlas } = detail;
  const plan = planInput(detail, workspace.rig.boards);
  const label = `Plan of ${atlas.asset_id} v${atlas.version}: ${atlas.landmarks.length} landmarks and the target ${atlas.target.id}${
    plan.board ? ` on ${plan.board.id}` : ""
  }`;
  return (
    <div className="@container space-y-5">
      <Facts detail={detail} summary={summary} workspace={workspace} />
      <Figures detail={detail} workspace={workspace} />
      {/* Side by side once the card is wide, as it is when the service is read-only. */}
      <div className="grid gap-5 @4xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] @4xl:items-start">
        <section className="min-w-0 space-y-2">
          <Subheading>Plan</Subheading>
          <PlanView input={plan} label={label} />
        </section>
        <Points detail={detail} />
      </div>
      <Leftovers detail={detail} />
    </div>
  );
}

function Loading() {
  return (
    <div className="space-y-5" aria-busy>
      <Skeleton className="h-10" />
      <div className="grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-2">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-16" />
        ))}
      </div>
      <Skeleton className="h-72" />
      <Skeleton className="h-32" />
    </div>
  );
}

/**
 * One atlas of the workspace: how it was built, the numbers to judge it by,
 * its plan and its points. Opens on the newest atlas.
 */
export function ResultCard({
  workspace,
  selected,
  onSelect,
}: {
  workspace: Workspace;
  /** The atlas the reader chose; the newest one when null or no longer listed. */
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  useAtlasReads();
  const atlases = atlasesNewestFirst(workspace);
  const summary = atlases.find((atlas) => atlas.asset_id === selected) ?? atlases[0];

  useEffect(() => {
    if (summary) readAtlas(summary);
  }, [summary]);

  const read = summary ? atlasRead(summary.asset_id) : undefined;

  let body: ReactNode;
  if (!summary) {
    body = <p className="text-sm text-muted-foreground">No atlas yet</p>;
  } else if (read?.status === "ready") {
    body = <Shown detail={read.detail} summary={summary} workspace={workspace} />;
  } else if (read?.status === "error") {
    body = (
      <div className="flex flex-wrap items-center gap-3">
        <p role="alert" className="min-w-0 flex-1 text-sm text-destructive wrap-anywhere">
          {read.message}
        </p>
        <Button type="button" variant="outline" onClick={() => readAtlas(summary, true)}>
          <RotateCw /> Retry
        </Button>
      </div>
    );
  } else {
    body = <Loading />;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Result</h2>
        </CardTitle>
        {summary && (
          <CardAction>
            <Select value={summary.asset_id} onValueChange={onSelect}>
              <SelectTrigger aria-label="Atlas" className="max-w-56 min-w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper" align="end">
                {atlases.map((atlas) => (
                  <SelectItem key={atlas.asset_id} value={atlas.asset_id}>
                    {atlasLabel(atlas)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
}
