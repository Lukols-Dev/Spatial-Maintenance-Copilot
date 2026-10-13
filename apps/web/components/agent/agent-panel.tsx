"use client";

import { Bot, CircleAlert, LoaderCircle, Play, RotateCw, ShieldCheck, SquarePlus, ThumbsDown } from "lucide-react";

import { ActionIcon } from "@/components/locate/action-icon";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Pending } from "@/lib/agent/store";
import type { ApprovalRequest, Turn, ViewRequest } from "@/lib/agent/types";
import { actionLabel, sentence } from "@/lib/locate/format";
import { cn } from "@/lib/utils";

function pendingText(pending: Pending): string {
  switch (pending.kind) {
    case "start":
      return `Starting at ${pending.view}…`;
    case "choose":
      return `Agent on ${pending.view}…`;
    case "approve":
      return pending.approved ? "Approving…" : "Declining…";
    case "resume":
      return "Reading the session…";
  }
}

function MoveRequest({
  request,
  disabled,
  onChoose,
}: {
  request: ViewRequest;
  disabled: boolean;
  onChoose: (view: string) => void;
}) {
  return (
    <section aria-labelledby="request-heading" data-request="view" className="space-y-3">
      <div className="flex items-center gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3">
        <ActionIcon action={request.action} className="size-9 shrink-0 text-amber-700 dark:text-amber-400" />
        <h3 id="request-heading" className="min-w-0 text-base font-semibold">
          {actionLabel(request.action)}
        </h3>
      </div>
      <blockquote data-guidance className="border-l-2 pl-3 text-sm leading-relaxed">
        {request.guidance}
      </blockquote>
      {request.suggested_views.length > 0 && (
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium text-muted-foreground">Suggested viewpoints</h4>
          <ul className="flex flex-wrap gap-1.5">
            {request.suggested_views.map((view) => (
              <li key={view}>
                <Button size="sm" variant="outline" disabled={disabled} onClick={() => onChoose(view)}>
                  {view}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function ApprovalAsk({
  request,
  disabled,
  onApprove,
}: {
  request: ApprovalRequest;
  disabled: boolean;
  onApprove: (approved: boolean) => void;
}) {
  return (
    <section aria-labelledby="request-heading" data-request="approval" className="space-y-3">
      <div className="flex items-center gap-3 rounded-xl border border-emerald-600/30 bg-emerald-500/10 p-3">
        <ShieldCheck aria-hidden className="size-9 shrink-0 text-emerald-700 dark:text-emerald-400" />
        <h3 id="request-heading" className="text-base font-semibold">
          Localised
        </h3>
      </div>
      <p data-explanation className="text-sm leading-relaxed">
        {request.explanation}
      </p>
      <div className="space-y-1">
        <h4 className="text-xs font-medium text-muted-foreground">Next step</h4>
        <p data-next-step className="text-sm font-medium">
          {request.next_step}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button disabled={disabled} onClick={() => onApprove(true)}>
          <ShieldCheck aria-hidden /> Approve
        </Button>
        <Button variant="outline" disabled={disabled} onClick={() => onApprove(false)}>
          <ThumbsDown aria-hidden /> Decline
        </Button>
      </div>
    </section>
  );
}

/**
 * The agent's side of the session: what it asks the operator, and the
 * operator's answers. The policy's move is shown with the agent's words; the
 * decision and its measurements are in the panel below.
 */
export function AgentPanel({
  turn,
  model,
  pending,
  error,
  firstView,
  onStart,
  onChoose,
  onApprove,
  onNewSession,
  onRetry,
  className,
}: {
  turn: Turn | null;
  model: string | null;
  pending: Pending | null;
  error: string | null;
  /** The viewpoint a new session starts at. */
  firstView: string;
  onStart: (view: string) => void;
  onChoose: (view: string) => void;
  onApprove: (approved: boolean) => void;
  onNewSession: () => void;
  onRetry: () => void;
  className?: string;
}) {
  const busy = pending !== null;
  const awaiting = turn?.awaiting ?? null;
  const status = busy ? "pending" : turn === null ? "none" : (turn.outcome ?? awaiting?.kind ?? "none");
  return (
    <section aria-labelledby="agent-heading" data-status={status} className={cn("flex flex-col gap-4 bg-card p-4", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="agent-heading" className="flex items-center gap-1.5 text-sm font-semibold">
          <Bot aria-hidden className="size-4" /> Agent
        </h2>
        {model && (
          <span className="truncate text-xs text-muted-foreground" title={model}>
            {model}
          </span>
        )}
      </div>

      {/* Always there, so what happens is announced. */}
      <div role="status" className="empty:hidden">
        {pending && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
            {pendingText(pending)}
          </p>
        )}
        {!pending && turn?.outcome && (
          <Badge
            className={cn(
              "h-6 px-2.5 text-sm",
              turn.outcome === "accepted"
                ? "bg-emerald-700 text-white dark:bg-emerald-500 dark:text-emerald-950"
                : "bg-muted text-foreground",
            )}
          >
            {sentence(turn.outcome)}
          </Badge>
        )}
      </div>

      {error && (
        <div className="space-y-3">
          <Alert variant="destructive">
            <CircleAlert aria-hidden />
            <AlertTitle>No answer</AlertTitle>
            <AlertDescription className="wrap-anywhere">{error}</AlertDescription>
          </Alert>
          <Button onClick={onRetry}>
            <RotateCw aria-hidden /> Retry
          </Button>
        </div>
      )}

      {awaiting?.kind === "view" && <MoveRequest request={awaiting} disabled={busy} onChoose={onChoose} />}
      {awaiting?.kind === "approval" && <ApprovalAsk request={awaiting} disabled={busy} onApprove={onApprove} />}

      {turn === null && !busy && !error && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">No session</p>
          <Button onClick={() => onStart(firstView)}>
            <Play aria-hidden /> Start at {firstView}
          </Button>
        </div>
      )}
      {turn?.outcome && !busy && (
        <Button variant="outline" className="self-start" onClick={onNewSession}>
          <SquarePlus aria-hidden /> New session
        </Button>
      )}
    </section>
  );
}
