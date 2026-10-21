"use client";

import { Fragment } from "react";

import { ActionIcon } from "@/components/locate/action-icon";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { SessionSummary, SummaryRow } from "@/lib/agent/summary";
import { moveOf } from "@/lib/guide/moves";
import { NONE, count, px } from "@/lib/locate/format";
import { cn } from "@/lib/utils";

/** The session in one line: steps, where the policy accepted, how the region changed, the operator's answer. */
function headline(summary: SessionSummary, unit: string): string[] {
  const facts = [count(summary.rows.length, unit)];
  facts.push(summary.acceptedAt === null ? "not accepted yet" : `accepted at ${unit} ${summary.acceptedAt}`);
  if (summary.region && summary.rows.length > 1) {
    facts.push(`95 % region ${px(summary.region.first)} → ${px(summary.region.last)}`);
  }
  if (summary.approved !== null) facts.push(summary.approved ? "next step approved" : "next step declined");
  return facts;
}

function Measured({ measured }: { measured: SummaryRow["measured"] }) {
  if (!measured) return <span className="text-muted-foreground">{NONE}</span>;
  const { inliers, rmsPx, regionPx, check } = measured;
  return (
    <div className="space-y-0.5 tabular-nums">
      <p>
        {inliers === null ? "no pose" : `${count(inliers, "inlier")} · RMS ${px(rmsPx, 2)}`}
      </p>
      <p className="text-muted-foreground">95 % region {px(regionPx)}</p>
      {check && check.errorPx !== null && (
        <p className="text-muted-foreground">
          {check.label} {px(check.errorPx)} off{check.inside95 === null ? "" : check.inside95 ? ", inside" : ", outside"}
        </p>
      )}
    </div>
  );
}

function Decision({ decision }: { decision: SummaryRow["decision"] }) {
  if (!decision) return <span className="text-muted-foreground">{NONE}</span>;
  const action = decision.action;
  return (
    <div className="space-y-0.5">
      <p
        className={cn(
          "flex items-center gap-1.5 font-medium",
          decision.reliable ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400",
        )}
      >
        {action && <ActionIcon action={action} className="size-4 shrink-0" />}
        {decision.reliable ? "Reliable" : action ? moveOf(action).words : "Not reliable"}
      </p>
      {decision.reason && <p className="text-muted-foreground">{decision.reason}</p>}
    </div>
  );
}

function Agent({ agent }: { agent: SummaryRow["agent"] }) {
  if (!agent) return <span className="text-muted-foreground">{NONE}</span>;
  return (
    <div className="space-y-0.5">
      <p>{agent.did}</p>
      {(agent.words === "policy" || agent.corrected) && (
        <p className="text-amber-700 dark:text-amber-400">
          {agent.words === "policy" ? "the policy's words: the model gave none" : "held to the policy by a guard"}
        </p>
      )}
    </div>
  );
}

/**
 * The session view by view: what OpenCV measured, what the policy decided from
 * it, what the agent did with that decision and what the operator did next.
 * Each row is the trace's events for one view, so the measurement can be read
 * turning into the next action.
 */
export function SessionSummaryCard({
  summary,
  model,
  unit = "view",
  first = "View",
  className,
}: {
  summary: SessionSummary;
  /** The model that speaks for the agent, or why none does. */
  model: string | null;
  /** What a row is, in the headline: a view of the Demo, an instruction of a camera. */
  unit?: string;
  /** The first column's heading: the view's name, or when the instruction was given. */
  first?: string;
  className?: string;
}) {
  if (summary.rows.length === 0) return null;
  return (
    <Card role="region" className={className} aria-labelledby="session-summary">
      <CardHeader>
        <CardTitle>
          <h2 id="session-summary">Session</h2>
        </CardTitle>
        <CardDescription data-part="session-headline">
          {headline(summary, unit).map((fact, index) => (
            <Fragment key={fact}>
              {index > 0 && " · "}
              <span className="whitespace-nowrap">{fact}</span>
            </Fragment>
          ))}
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <Table className="text-sm">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-10">#</TableHead>
              <TableHead>{first}</TableHead>
              <TableHead>Measured · OpenCV</TableHead>
              <TableHead>Decision · policy</TableHead>
              <TableHead>Agent{model ? ` · ${model}` : ""}</TableHead>
              <TableHead>Operator</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {summary.rows.map((row) => (
              <TableRow key={row.n} className="align-top" data-row={row.n}>
                <TableCell className="tabular-nums">{row.n}</TableCell>
                <TableCell className="font-medium whitespace-nowrap">{row.view}</TableCell>
                <TableCell className="whitespace-normal">
                  <Measured measured={row.measured} />
                </TableCell>
                <TableCell className="min-w-48 whitespace-normal">
                  <Decision decision={row.decision} />
                </TableCell>
                <TableCell className="min-w-40 whitespace-normal">
                  <Agent agent={row.agent} />
                </TableCell>
                <TableCell className="whitespace-normal">{row.operator ?? <span className="text-muted-foreground">waiting</span>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
