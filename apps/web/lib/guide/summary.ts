import { summaryOf, type SessionSummary, type SummaryRow } from "@/lib/agent/summary";
import type { LogEntry } from "@/lib/guide/store";

// A camera's session as the Demo's is summarised: each instruction a row, with
// what the geometry measured on the frame it was decided on, the policy's
// decision, what the agent did and what the operator did next. Once the panel
// is open, the target's tag is the check of the prediction.

/** "0:07": minutes and seconds since the run started. */
export function clock(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function summariseLog(log: readonly LogEntry[]): SessionSummary {
  const rows: SummaryRow[] = log.map((entry) => {
    const { localisation, decision, sighting } = entry.frame;
    return {
      n: entry.n,
      view: clock(entry.at),
      measured: {
        inliers: localisation.quality?.inliers ?? null,
        rmsPx: localisation.quality?.rms_reprojection_px ?? null,
        regionPx: localisation.uncertainty?.ellipse.semi_major_px ?? null,
        check: sighting && { label: "tag", errorPx: sighting.error_px, inside95: sighting.inside_95 },
      },
      decision: {
        reliable: decision.reliable,
        action: decision.action,
        reason: decision.move_reason || decision.reasons[0] || "",
      },
      agent: entry.agent,
      operator: entry.operator,
    };
  });
  return summaryOf(rows);
}
