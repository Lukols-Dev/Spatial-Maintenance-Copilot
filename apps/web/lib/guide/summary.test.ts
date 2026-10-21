import { describe, expect, it } from "vitest";

import openExample from "../api-examples/frame-answer-open.json";
import moveExample from "../api-examples/frame-answer-move.json";
import type { LogEntry } from "./store";
import { clock, summariseLog } from "./summary";
import type { FrameAnswer } from "./types";

const frame = (example: unknown) => structuredClone(example) as FrameAnswer;

describe("a camera session's summary", () => {
  it("writes when each instruction came as minutes and seconds", () => {
    expect([clock(0), clock(7_400), clock(65_000)]).toEqual(["0:00", "0:07", "1:05"]);
  });

  it("is a row per instruction: the frame's measurements, the decision, the agent, the operator, and the tag once in sight", () => {
    const move = frame(moveExample);
    const open = frame(openExample);
    const log: LogEntry[] = [
      { n: 1, at: 3_000, cue: "MOVE_DOWN", frame: move, agent: { did: "Asked: move down", words: "model", corrected: false }, operator: "Moved" },
      { n: 2, at: 9_000, cue: "IN_SIGHT", frame: open, agent: null, operator: "Approved" },
    ];

    const summary = summariseLog(log);

    expect(summary.rows.map((row) => [row.n, row.view, row.operator])).toEqual([
      [1, "0:03", "Moved"],
      [2, "0:09", "Approved"],
    ]);
    expect(summary.rows[0].decision).toEqual({
      reliable: move.decision.reliable,
      action: move.decision.action,
      reason: move.decision.move_reason,
    });
    expect(summary.rows[0].measured?.inliers).toBe(move.localisation.quality?.inliers);
    expect(summary.rows[0].measured?.check).toBeNull();
    expect(summary.rows[1].measured?.check).toEqual({
      label: "tag",
      errorPx: open.sighting?.error_px,
      inside95: open.sighting?.inside_95,
    });
    expect(summary.approved).toBe(true);
  });
});
