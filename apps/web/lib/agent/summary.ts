import type { TraceEvent } from "@/lib/agent/types";
import { moveOf } from "@/lib/guide/moves";
import { regionPx, type TraceStep } from "@/lib/locate/trace";
import type { Action } from "@/lib/locate/types";

// A session told step by step, from its trace: what the geometry measured in
// each view, what the policy decided from it, what the agent did with that
// decision, and what the operator did next. It is the trace's own events, put
// in rows, so a reader sees each measurement turn into the next action.

export interface SummaryRow {
  /** 1 for the first view of the session. */
  n: number;
  view: string;
  /** The localisation of the view, when the session kept it. */
  measured: {
    inliers: number | null;
    rmsPx: number | null;
    regionPx: number | null;
    /** The prediction held against the truth of a recorded view, or the target's tag in a live one. */
    check: { label: "truth" | "tag"; errorPx: number | null; inside95: boolean | null } | null;
  } | null;
  decision: { reliable: boolean; action: Action | null; reason: string } | null;
  /** What the agent did: asked for a move or put the next step to the operator; who chose the words. */
  agent: { did: string; words: "model" | "policy"; corrected: boolean } | null;
  /** What the operator did with it: chose a view, approved or declined; null while waiting. */
  operator: string | null;
}

export interface SessionSummary {
  rows: SummaryRow[];
  /** The step whose result the policy accepted, if one was. */
  acceptedAt: number | null;
  approved: boolean | null;
  /** The 95 % region's semi-major axis in the first and the last view that had one. */
  region: { first: number; last: number } | null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function measuredOf(step: TraceStep | undefined): SummaryRow["measured"] {
  if (!step) return null;
  const quality = step.result.localisation.quality;
  const truth = step.truthView === null ? null : step.result.truth;
  return {
    inliers: quality?.inliers ?? null,
    rmsPx: quality?.rms_reprojection_px ?? null,
    regionPx: regionPx(step.result),
    check: truth && { label: "truth", errorPx: truth.error_px, inside95: truth.inside_95 },
  };
}

/** Where the policy accepted, the operator's answer and the region's change, from the rows. */
export function summaryOf(rows: SummaryRow[]): SessionSummary {
  const accepted = rows.find((row) => row.decision?.reliable);
  const approval = rows.find((row) => row.operator === "Approved" || row.operator === "Declined");
  const regions = rows.map((row) => row.measured?.regionPx).filter((value): value is number => typeof value === "number");
  return {
    rows,
    acceptedAt: accepted?.n ?? null,
    approved: approval ? approval.operator === "Approved" : null,
    region: regions.length > 0 ? { first: regions[0], last: regions[regions.length - 1] } : null,
  };
}

/** The session's rows from its events, each matched with the localisation it kept of that view. */
export function summarise(events: readonly TraceEvent[], steps: readonly TraceStep[]): SessionSummary {
  const rows: SummaryRow[] = [];
  let used = 0;
  for (const event of events) {
    const row = rows.at(-1);
    switch (event.kind) {
      case "perception": {
        const view = text(event.data.view) ?? "";
        const index = steps.findIndex((step, i) => i >= used && step.view === view);
        if (index >= 0) used = index + 1;
        rows.push({
          n: rows.length + 1,
          view,
          measured: measuredOf(index >= 0 ? steps[index] : undefined),
          decision: null,
          agent: null,
          operator: null,
        });
        break;
      }
      case "decision":
        if (row) {
          const reasons = Array.isArray(event.data.reasons) ? event.data.reasons.filter((r) => typeof r === "string") : [];
          row.decision = {
            reliable: event.data.reliable === true,
            action: (text(event.data.action) as Action | null) ?? null,
            reason: text(event.data.move_reason) ?? reasons[0] ?? "",
          };
        }
        break;
      case "fallback":
        if (row) row.agent = { did: row.agent?.did ?? "", words: "policy", corrected: row.agent?.corrected ?? false };
        break;
      case "guard":
        if (row) row.agent = { did: row.agent?.did ?? "", words: row.agent?.words ?? "model", corrected: true };
        break;
      case "agent":
        if (row) {
          const action = text(event.data.action) as Action | null;
          const did =
            action !== null
              ? `Asked: ${moveOf(action).words.toLowerCase()}`
              : text(event.data.next_step)
                ? `Proposed: ${String(event.data.next_step)}`
                : event.summary;
          row.agent = { did, words: row.agent?.words ?? "model", corrected: row.agent?.corrected ?? false };
        }
        break;
      case "human":
        if (row) {
          const view = text(event.data.view);
          row.operator =
            view !== null ? `Chose ${view}` : event.data.approved === true ? "Approved" : event.data.approved === false ? "Declined" : event.summary;
        }
        break;
      default:
        break;
    }
  }
  return summaryOf(rows);
}
