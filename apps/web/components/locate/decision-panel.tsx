"use client";

import { Check, CircleAlert, LoaderCircle, Minus, OctagonX, RotateCw, ShieldCheck, TriangleAlert, X } from "lucide-react";
import type { ReactNode } from "react";

import { ActionIcon } from "@/components/locate/action-icon";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  actionLabel,
  changeText,
  checkLabel,
  checkLimit,
  checkValue,
  clock,
  failureLabel,
  measurements,
  px,
  sentence,
} from "@/lib/locate/format";
import type { Shown } from "@/lib/locate/session";
import { changeOf, regionPx, shownTruth, type TraceStep } from "@/lib/locate/trace";
import type { Check as CheckResult } from "@/lib/locate/types";
import { cn } from "@/lib/utils";

/** The step shown, found in the trace by its number and time: the trace may have been cleared since. */
function previousOf(steps: readonly TraceStep[], step: TraceStep): TraceStep | null {
  const index = steps.findIndex((candidate) => candidate.n === step.n && candidate.at === step.at);
  return index > 0 ? steps[index - 1] : null;
}

export function VerdictText({ verdict, children }: { verdict: string; children?: ReactNode }) {
  return (
    <span
      className={cn(
        verdict === "improved" && "text-emerald-700 dark:text-emerald-400",
        verdict === "worse" && "text-destructive",
        (verdict === "same" || verdict === "") && "text-muted-foreground",
      )}
    >
      {children ?? verdict}
    </span>
  );
}

function StatusBadge({ reliable }: { reliable: boolean }) {
  return reliable ? (
    <Badge className="h-6 bg-emerald-700 px-2.5 text-sm text-white dark:bg-emerald-500 dark:text-emerald-950">
      <ShieldCheck aria-hidden />
      Reliable
    </Badge>
  ) : (
    <Badge className="h-6 bg-amber-400 px-2.5 text-sm text-amber-950 dark:bg-amber-400">
      <TriangleAlert aria-hidden />
      Not reliable
    </Badge>
  );
}

/** The decision as the operator reads it: reliable or not, and the move as a big labelled arrow. */
function Verdict({ step, steps }: { step: TraceStep; steps: readonly TraceStep[] }) {
  const { decision, localisation } = step.result;
  const passed = decision.checks.filter((check) => check.passed).length;
  const region = regionPx(step.result);
  const previous = previousOf(steps, step);
  const change = previous ? changeText(changeOf(previous.result, step.result)) : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusBadge reliable={decision.reliable} />
        {localisation.failure && (
          <Badge variant="destructive" className="h-6 px-2.5 text-sm">
            <OctagonX aria-hidden />
            {failureLabel(localisation.failure)}
          </Badge>
        )}
      </div>

      <div
        data-action={decision.action}
        className={cn(
          "flex items-center gap-4 rounded-xl border p-3",
          decision.reliable
            ? "border-emerald-600/30 bg-emerald-500/10 dark:border-emerald-400/30"
            : "border-amber-500/50 bg-amber-400/10 dark:border-amber-400/40",
        )}
      >
        <span
          className={cn(
            "flex size-16 shrink-0 items-center justify-center rounded-lg",
            decision.reliable ? "bg-emerald-600 text-white dark:bg-emerald-500 dark:text-emerald-950" : "bg-amber-400 text-amber-950",
          )}
        >
          <ActionIcon action={decision.action} className="size-10" strokeWidth={decision.action === "ACCEPT" ? 3 : 2} />
        </span>
        <div className="min-w-0">
          <p className="text-2xl leading-tight font-semibold tracking-tight">{actionLabel(decision.action)}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {decision.move_reason ? sentence(decision.move_reason) : `${passed} of ${decision.checks.length} checks passed`}
          </p>
        </div>
      </div>

      {decision.reasons.length > 0 && (
        <ul aria-label="Reasons" className="space-y-1 text-sm">
          {decision.reasons.map((reason) => (
            <li key={reason} className="flex gap-2">
              <X aria-hidden className="mt-0.5 size-4 shrink-0 text-destructive" />
              {sentence(reason)}
            </li>
          ))}
        </ul>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg bg-muted/60 px-3 py-2">
        <div>
          <dt className="text-xs text-muted-foreground">95 % region</dt>
          <dd className="text-base font-semibold tabular-nums">{region === null ? "None" : px(region)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">{previous ? `Change vs #${previous.n}` : "Change"}</dt>
          <dd className="text-base font-semibold tabular-nums" data-verdict={change?.verdict ?? ""}>
            {change && (change.amount !== "—" || change.verdict) ? (
              <>
                {change.amount !== "—" && <span>{change.amount} </span>}
                <VerdictText verdict={change.verdict} />
              </>
            ) : (
              <span className="text-muted-foreground">First step</span>
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function CheckMark({ check }: { check: CheckResult }) {
  if (check.value === null) {
    return (
      <span className="text-muted-foreground">
        <Minus aria-hidden className="size-4" />
        <span className="sr-only">Not measured</span>
      </span>
    );
  }
  return check.passed ? (
    <span className="text-emerald-700 dark:text-emerald-400">
      <Check aria-hidden className="size-4" strokeWidth={3} />
      <span className="sr-only">Pass</span>
    </span>
  ) : (
    <span className="text-destructive">
      <X aria-hidden className="size-4" strokeWidth={3} />
      <span className="sr-only">Fail</span>
    </span>
  );
}

function Checks({ checks }: { checks: CheckResult[] }) {
  return (
    <section aria-labelledby="checks-heading">
      <h2 id="checks-heading" className="mb-1 text-sm font-semibold">
        Checks
      </h2>
      <Table className="tabular-nums">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-8 pl-0 text-xs font-normal text-muted-foreground">Check</TableHead>
            <TableHead className="h-8 text-right text-xs font-normal text-muted-foreground">Value</TableHead>
            <TableHead className="h-8 text-right text-xs font-normal text-muted-foreground">Limit</TableHead>
            <TableHead className="h-8 w-8 pr-0">
              <span className="sr-only">Result</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {checks.map((check) => (
            <TableRow
              key={check.name}
              data-check={check.name}
              data-passed={check.passed}
              className={cn("hover:bg-transparent", !check.passed && check.value !== null && "bg-destructive/5")}
            >
              <TableCell className="py-1.5 pl-0">{checkLabel(check.name)}</TableCell>
              <TableCell className={cn("py-1.5 text-right", !check.passed && check.value !== null && "font-semibold text-destructive")}>
                {checkValue(check)}
              </TableCell>
              <TableCell className="py-1.5 text-right text-muted-foreground">{checkLimit(check)}</TableCell>
              <TableCell className="py-1.5 pr-0">
                <CheckMark check={check} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}

function Measurements({ step }: { step: TraceStep }) {
  return (
    <section aria-labelledby="measurements-heading">
      <h2 id="measurements-heading" className="mb-2 text-sm font-semibold">
        Measurements
      </h2>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5">
        {measurements(step.result).map((row) => (
          <div key={row.label} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{row.label}</dt>
            <dd className="text-sm font-medium tabular-nums">{row.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function TruthFacts({ step }: { step: TraceStep }) {
  const truth = shownTruth(step);
  return (
    <section aria-labelledby="truth-heading">
      <h2 id="truth-heading" className="mb-2 text-sm font-semibold">
        Truth
      </h2>
      {truth ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5">
          <div>
            <dt className="text-xs text-muted-foreground">Error</dt>
            <dd className="text-sm font-medium tabular-nums">{px(truth.error_px)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">95 % region</dt>
            <dd className="text-sm font-medium">
              {truth.inside_95 === null ? (
                "—"
              ) : truth.inside_95 ? (
                <span className="text-emerald-700 dark:text-emerald-400">Inside</span>
              ) : (
                <span className="font-semibold text-destructive">Outside</span>
              )}
            </dd>
          </div>
          <div className="col-span-2 min-w-0">
            <dt className="text-xs text-muted-foreground">Clicked in</dt>
            <dd className="truncate text-sm font-medium">{truth.source_view}</dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">None</p>
      )}
    </section>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-5" aria-hidden>
      <Skeleton className="h-6 w-28" />
      <Skeleton className="h-24 w-full rounded-xl" />
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-56 w-full" />
    </div>
  );
}

/**
 * Everything the decision rests on, for the result on screen: the verdict
 * and the move, the checks against their limits, the measurements, and the
 * truth when one is known.
 */
export function DecisionPanel({
  shown,
  steps,
  onRetry,
  className,
}: {
  shown: Shown;
  steps: readonly TraceStep[];
  onRetry: () => void;
  className?: string;
}) {
  const step = shown.status === "shown" ? shown.step : null;
  const view = step?.view ?? (shown.status === "running" || shown.status === "failed" ? shown.request.view : undefined);
  return (
    <aside
      aria-labelledby="decision-heading"
      data-status={shown.status}
      data-view={view}
      data-step={step?.n}
      className={cn("flex flex-col gap-5 bg-card p-4", className)}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="decision-heading" className="text-sm font-semibold">
          Decision
        </h2>
        {step && (
          <span className="truncate text-xs text-muted-foreground tabular-nums">
            #{step.n} · {step.view} · <time dateTime={step.at}>{clock(step.at)}</time>
          </span>
        )}
      </div>

      {/* Always there, so the answer is announced when it comes. */}
      <div role="status" className="empty:hidden">
        {shown.status === "running" && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
            Locating {shown.request.view}…
          </p>
        )}
        {step && <Verdict step={step} steps={steps} />}
      </div>

      {shown.status === "failed" && (
        <div className="space-y-3">
          <Alert variant="destructive">
            <CircleAlert aria-hidden />
            <AlertTitle>{shown.request.view} not located</AlertTitle>
            <AlertDescription className="wrap-anywhere">{shown.message}</AlertDescription>
          </Alert>
          <Button onClick={onRetry}>
            <RotateCw aria-hidden /> Retry
          </Button>
        </div>
      )}

      {step ? (
        <>
          <Checks checks={step.result.decision.checks} />
          <Measurements step={step} />
          <TruthFacts step={step} />
        </>
      ) : (
        shown.status !== "failed" && <PanelSkeleton />
      )}
    </aside>
  );
}
