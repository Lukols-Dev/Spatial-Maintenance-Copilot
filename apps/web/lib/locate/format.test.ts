import { describe, expect, it } from "vitest";

import failureExample from "../api-examples/localise-result-failure.json";
import reliableExample from "../api-examples/localise-result-reliable.json";
import moveExample from "../api-examples/localise-result.json";
import {
  actionLabel,
  changeText,
  checkLabel,
  checkLimit,
  checkValue,
  clock,
  count,
  failureLabel,
  fixed,
  measurements,
  mm,
  outcomeOf,
  percent,
  px,
  regionText,
  sentence,
  signedPercent,
  unavailableTitle,
} from "./format";
import type { Check, LocaliseResult } from "./types";

const MOVE = moveExample as unknown as LocaliseResult;
const RELIABLE = reliableExample as unknown as LocaliseResult;
const FAILURE = failureExample as unknown as LocaliseResult;

describe("numbers", () => {
  it("have their unit and a true minus sign, never −0", () => {
    expect(px(23.094403883551426)).toBe("23.1 px");
    expect(px(0.468048590362685, 2)).toBe("0.47 px");
    expect(px(null)).toBe("—");
    expect(mm(1407.992246301255)).toBe("1408 mm");
    expect(percent(0.20029285819760187)).toBe("20.0 %");
    expect(percent(undefined)).toBe("—");
    expect(fixed(-39.54, 1)).toBe("−39.5");
    expect(fixed(-0.04, 1)).toBe("0.0");
    expect(fixed(Number.POSITIVE_INFINITY, 1)).toBe("∞");
  });

  it("count things in words", () => {
    expect(count(1, "landmark")).toBe("1 landmark");
    expect(count(7, "landmark")).toBe("7 landmarks");
    expect(count(0, "viewpoint")).toBe("0 viewpoints");
  });

  it("show the sign of a change", () => {
    expect(signedPercent(-39.539)).toBe("−39.5 %");
    expect(signedPercent(12)).toBe("+12.0 %");
    expect(signedPercent(0.04)).toBe("0.0 %");
    expect(signedPercent(-0.04)).toBe("0.0 %");
  });
});

describe("names", () => {
  it("of actions and failures are words", () => {
    expect(actionLabel("MOVE_LEFT")).toBe("Move left");
    expect(actionLabel("MOVE_CLOSER")).toBe("Move closer");
    expect(actionLabel("ACCEPT")).toBe("Accept");
    expect(failureLabel("too_few_correspondences")).toBe("Too few correspondences");
    expect(failureLabel("target_behind_camera")).toBe("Target behind camera");
  });

  it("start the service's facts with a capital", () => {
    expect(sentence("landmarks extend beyond the left edge of the frame")).toBe(
      "Landmarks extend beyond the left edge of the frame",
    );
    expect(sentence("")).toBe("");
  });

  it("give a time on the visitor's clock", () => {
    expect(clock("2026-10-06T16:45:07+02:00")).toMatch(/^\d\d:\d\d:07$/);
    expect(clock("not a time")).toBe("");
  });
});

describe("checks", () => {
  function rows(result: LocaliseResult) {
    return result.decision.checks.map((check) => [checkLabel(check.name), checkValue(check), checkLimit(check)]);
  }

  it("keep the measurement and the threshold apart, each with its unit", () => {
    expect(rows(MOVE)).toEqual([
      ["Landmarks matched", "5", "≥ 4"],
      ["Inliers", "5", "≥ 6"],
      ["Inlier ratio", "1.00", "≥ 0.75"],
      ["RMS reprojection", "0.47 px", "≤ 3.00 px"],
      ["Image coverage", "20.0 %", "≥ 5.0 %"],
      ["Target in frame", "yes", "yes"],
      ["Failed samples", "0.0 %", "≤ 5.0 %"],
      ["Region / target radius", "0.11", "≤ 0.50"],
    ]);
  });

  it("show a dash for what a failure left uncomputed", () => {
    expect(rows(FAILURE).map(([, value]) => value)).toEqual(["3", "—", "—", "—", "—", "—", "—", "—"]);
  });

  it("show a check the service adds later by its name", () => {
    const check: Check = { name: "ray_angle_deg", value: 12.3456, limit: 5, op: ">=", passed: true };
    expect([checkLabel(check.name), checkValue(check), checkLimit(check)]).toEqual(["Ray angle deg", "12.3", "≥ 5"]);
  });
});

describe("changeText", () => {
  it("gives the change and its verdict", () => {
    expect(changeText({ kind: "ratio", percent: -39.539, verdict: "improved" })).toEqual({
      amount: "−39.5 %",
      verdict: "improved",
    });
    expect(changeText({ kind: "ratio", percent: 0, verdict: "same" })).toEqual({ amount: "0.0 %", verdict: "same" });
    expect(changeText({ kind: "found" })).toEqual({ amount: "—", verdict: "improved" });
    expect(changeText({ kind: "lost" })).toEqual({ amount: "—", verdict: "worse" });
    expect(changeText({ kind: "none" })).toEqual({ amount: "—", verdict: "" });
  });
});

describe("a result in a word", () => {
  it("is reliable, a move, or a failure", () => {
    expect(outcomeOf(RELIABLE)).toEqual({ kind: "reliable", label: "Reliable" });
    expect(outcomeOf(MOVE)).toEqual({ kind: "move", label: "Move left" });
    expect(outcomeOf(FAILURE)).toEqual({ kind: "failure", label: "Failed" });
  });

  it("has a region, or the failure that left it without one", () => {
    expect(regionText(MOVE)).toBe("23.1 px");
    expect(regionText(RELIABLE)).toBe("14.0 px");
    expect(regionText(FAILURE)).toBe("Too few correspondences");
  });
});

describe("measurements", () => {
  it("give every quantity the decision rests on, with its unit", () => {
    expect(measurements(MOVE)).toEqual([
      { label: "Observed / inliers", value: "5 / 5" },
      { label: "Inlier ratio", value: "1.00" },
      { label: "RMS reprojection", value: "0.47 px" },
      { label: "Max reprojection", value: "0.77 px" },
      { label: "Image coverage", value: "20.0 %" },
      { label: "Non-planarity", value: "0.013" },
      { label: "95 % region", value: "23.1 × 18.6 px" },
      { label: "Pose-only semi-major", value: "17.9 px" },
      { label: "Target radius", value: "212.0 px" },
      { label: "Depth", value: "1408 mm" },
    ]);
  });

  it("give what could be computed after a failure", () => {
    expect(measurements(FAILURE)).toEqual([{ label: "Landmarks matched", value: "3" }]);
  });
});

describe("unavailableTitle", () => {
  it("says the service cannot be reached when no answer came", () => {
    expect(unavailableTitle("Cannot reach the perception service at http://localhost:8000")).toBe("Service unreachable");
    expect(unavailableTitle("No answer within 15 s")).toBe("Service unreachable");
    expect(unavailableTitle("HTTP 500 Internal Server Error")).toBe("Workspace not read");
  });
});
