"use client";

import { Check, Trash2, X } from "lucide-react";

import { VerdictText } from "@/components/locate/decision-panel";
import { ActionIcon } from "@/components/locate/action-icon";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { actionLabel, changeText, NONE, px, regionText } from "@/lib/locate/format";
import { changeOf, shownTruth, type TraceStep } from "@/lib/locate/trace";
import { cn } from "@/lib/utils";

function isShown(step: TraceStep, shown: TraceStep | null): boolean {
  return shown !== null && shown.n === step.n && shown.at === step.at;
}

function Row({
  step,
  previous,
  current,
  onShow,
}: {
  step: TraceStep;
  previous: TraceStep | null;
  current: boolean;
  onShow: (step: TraceStep) => void;
}) {
  const { decision, localisation } = step.result;
  const change = previous ? changeText(changeOf(previous.result, step.result)) : null;
  const truth = shownTruth(step);
  return (
    <TableRow
      data-step={step.n}
      data-state={current ? "selected" : undefined}
      aria-current={current ? "true" : undefined}
      onClick={() => onShow(step)}
      className="cursor-pointer"
    >
      <TableCell className="w-12">
        <Button
          variant="ghost"
          size="xs"
          className="tabular-nums focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
          aria-label={`Show step ${step.n}`}
          onClick={(event) => {
            // The row would show it a second time.
            event.stopPropagation();
            onShow(step);
          }}
        >
          {step.n}
        </Button>
      </TableCell>
      <TableCell className="font-medium">{step.view}</TableCell>
      <TableCell>
        <span className="inline-flex items-center gap-1.5">
          <ActionIcon action={decision.action} className="size-4 text-muted-foreground" />
          {actionLabel(decision.action)}
        </span>
      </TableCell>
      <TableCell>
        {decision.reliable ? (
          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
            <Check aria-hidden className="size-4" /> Yes
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
            <X aria-hidden className="size-4" /> No
          </span>
        )}
      </TableCell>
      <TableCell className={cn("text-right tabular-nums", localisation.failure && "text-destructive")}>
        {regionText(step.result)}
      </TableCell>
      <TableCell className="tabular-nums">
        {change && (change.amount !== NONE || change.verdict) ? (
          <>
            {change.amount !== NONE && `${change.amount} `}
            <VerdictText verdict={change.verdict} />
          </>
        ) : (
          <span className="text-muted-foreground">{NONE}</span>
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {truth ? (
          <span className={cn(truth.inside_95 === false && "font-semibold text-destructive")}>
            {px(truth.error_px)}
            {truth.inside_95 !== null && (
              <>
                {" "}
                <span className="text-xs font-normal text-muted-foreground">{truth.inside_95 ? "inside" : "outside"}</span>
              </>
            )}
          </span>
        ) : (
          <span className="text-muted-foreground">{NONE}</span>
        )}
      </TableCell>
    </TableRow>
  );
}

/** Every localisation of this atlas and set in this tab, in order, with how each step changed the region. */
export function TraceCard({
  steps,
  shown,
  onShow,
  onClear,
  className,
}: {
  steps: readonly TraceStep[];
  /** The step on screen, to mark its row. */
  shown: TraceStep | null;
  onShow: (step: TraceStep) => void;
  onClear: () => void;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>
          <h2>
            Trace <span className="font-normal text-muted-foreground tabular-nums">({steps.length})</span>
          </h2>
        </CardTitle>
        <CardAction>
          <Button variant="outline" size="sm" onClick={onClear} disabled={steps.length === 0}>
            <Trash2 aria-hidden /> Clear trace
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {steps.length === 0 ? (
          <p className="text-sm text-muted-foreground">No steps</p>
        ) : (
          <Table className="tabular-nums">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>#</TableHead>
                <TableHead>View</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Reliable</TableHead>
                <TableHead className="text-right">95 % region</TableHead>
                <TableHead>Change</TableHead>
                <TableHead className="text-right">Truth error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {steps.map((step, index) => (
                <Row
                  key={`${step.n}-${step.at}`}
                  step={step}
                  previous={index > 0 ? steps[index - 1] : null}
                  current={isShown(step, shown)}
                  onShow={onShow}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
