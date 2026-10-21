import { describe, expect, it } from "vitest";

import reliableExample from "../api-examples/localise-result-reliable.json";
import moveExample from "../api-examples/localise-result.json";
import type { TraceStep } from "../locate/trace";
import type { LocaliseResult } from "../locate/types";
import { summarise } from "./summary";
import type { EventKind, TraceEvent } from "./types";

const result = (example: unknown) => structuredClone(example) as LocaliseResult;

function event(step: number, kind: EventKind, node: string, summary: string, data: Record<string, unknown> = {}): TraceEvent {
  return { step, kind, node, summary, data };
}

// A session as the evaluation's traces record one: a view the policy asks to leave, the model gives no
// answer so the policy's words go out, the operator chooses another view, the policy accepts it, the
// agent puts the next step, and the operator approves.
const EVENTS: TraceEvent[] = [
  event(1, "perception", "localise", "localised B1_close.png", { view: "B1_close.png" }),
  event(2, "decision", "localise", "not reliable: MOVE_LEFT", {
    reliable: false,
    action: "MOVE_LEFT",
    move_reason: "landmarks side_bottom, side_top face away from the camera, seen from further left",
    reasons: ["4 inliers, needs ≥ 6"],
  }),
  event(3, "fallback", "guide", "the model gave no answer: unavailable", { reason: "unavailable" }),
  event(4, "agent", "guide", "asked for MOVE_LEFT", { action: "MOVE_LEFT", views: ["B2_1_close.png"] }),
  event(5, "human", "await_view", "the operator chose B2_1_close.png", { view: "B2_1_close.png" }),
  event(6, "perception", "localise", "localised B2_1_close.png", { view: "B2_1_close.png" }),
  event(7, "decision", "localise", "reliable", { reliable: true, action: "ACCEPT", move_reason: "", reasons: [] }),
  event(8, "guard", "present", "dropped digits from the explanation"),
  event(9, "agent", "present", "presented the result for approval", { next_step: "Open the flap" }),
  event(10, "human", "await_approval", "the operator approved", { approved: true }),
];

const TRUTH = { source_view: "B1_open.png", target_px: [540, 1100] as [number, number], error_px: 2.5, inside_95: true };
const STEPS: TraceStep[] = [
  {
    n: 1,
    at: "2026-10-20T10:00:00Z",
    view: "B1_close.png",
    truthView: "B1_open.png",
    result: { ...result(moveExample), truth: TRUTH },
  },
  { n: 2, at: "2026-10-20T10:00:05Z", view: "B2_1_close.png", truthView: null, result: result(reliableExample) },
];

describe("a session's summary", () => {
  it("puts each view's measurement, decision, agent and operator in one row", () => {
    const summary = summarise(EVENTS, STEPS);

    expect(summary.rows.map((row) => [row.n, row.view, row.operator])).toEqual([
      [1, "B1_close.png", "Chose B2_1_close.png"],
      [2, "B2_1_close.png", "Approved"],
    ]);
    expect(summary.rows[0].decision).toEqual({
      reliable: false,
      action: "MOVE_LEFT",
      reason: "landmarks side_bottom, side_top face away from the camera, seen from further left",
    });
    expect(summary.rows[0].agent).toEqual({ did: "Asked: move left", words: "policy", corrected: false });
    expect(summary.rows[1].agent).toEqual({ did: "Proposed: Open the flap", words: "model", corrected: true });
    expect(summary.rows[0].measured?.inliers).toBe(STEPS[0].result.localisation.quality?.inliers);
    expect(summary.rows[0].measured?.check).toEqual({ label: "truth", errorPx: 2.5, inside95: true });
    // No truth view was asked for the second: none is shown.
    expect(summary.rows[1].measured?.check).toBeNull();
  });

  it("says where the policy accepted, whether the operator approved, and how the region changed", () => {
    const summary = summarise(EVENTS, STEPS);

    expect(summary.acceptedAt).toBe(2);
    expect(summary.approved).toBe(true);
    expect(summary.region).toEqual({
      first: STEPS[0].result.localisation.uncertainty?.ellipse.semi_major_px,
      last: STEPS[1].result.localisation.uncertainty?.ellipse.semi_major_px,
    });
  });

  it("keeps a row without its localisation when the session no longer has it, and waits for the operator", () => {
    const summary = summarise(EVENTS.slice(0, 4), []);

    expect(summary.rows).toHaveLength(1);
    expect(summary.rows[0].measured).toBeNull();
    expect(summary.rows[0].operator).toBeNull();
    expect(summary).toMatchObject({ acceptedAt: null, approved: null, region: null });
  });
});
