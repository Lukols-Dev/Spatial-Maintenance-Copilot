"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { EventKind, TraceEvent } from "@/lib/agent/types";
import { sentence, words } from "@/lib/locate/format";
import { cn } from "@/lib/utils";

/** Who the event comes from, in the colour of its source. */
const KINDS: Record<EventKind, { label: string; className: string }> = {
  perception: { label: "Perception", className: "border-sky-500/40 text-sky-800 dark:text-sky-300" },
  decision: { label: "Decision", className: "border-violet-500/40 text-violet-800 dark:text-violet-300" },
  agent: { label: "Agent", className: "border-emerald-600/40 text-emerald-800 dark:text-emerald-300" },
  tool: { label: "Tool", className: "border-teal-500/40 text-teal-800 dark:text-teal-300" },
  human: { label: "Operator", className: "border-foreground/30 text-foreground" },
  guard: { label: "Guard", className: "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-300" },
  fallback: { label: "Fallback", className: "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-300" },
};

function KindBadge({ kind }: { kind: EventKind }) {
  const style = KINDS[kind] ?? { label: words(kind), className: "" };
  return (
    <Badge variant="outline" className={style.className}>
      {style.label}
    </Badge>
  );
}

/**
 * Every event of the session, numbered: what the camera saw, what the policy
 * decided, what the agent did and what the operator answered. Guards and
 * fallbacks are where the agent's output was held to the policy.
 */
export function AgentTrace({ events, className }: { events: readonly TraceEvent[]; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>
          <h2>
            Agent trace <span className="font-normal text-muted-foreground tabular-nums">({events.length})</span>
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-12">#</TableHead>
                <TableHead className="w-28">Source</TableHead>
                <TableHead className="w-36">Node</TableHead>
                <TableHead>Event</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((event) => (
                <TableRow
                  key={event.step}
                  data-kind={event.kind}
                  className={cn((event.kind === "guard" || event.kind === "fallback") && "bg-amber-500/5")}
                >
                  <TableCell className="tabular-nums">{event.step}</TableCell>
                  <TableCell>
                    <KindBadge kind={event.kind} />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{event.node}</TableCell>
                  <TableCell className="wrap-anywhere whitespace-normal">{sentence(event.summary)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
