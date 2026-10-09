import type { Change } from "@/lib/locate/trace";
import type { Check, LocaliseResult } from "@/lib/locate/types";

// How the Locate page writes numbers and names: units always, a true minus
// sign, and the service's identifiers in words.

const MINUS = "−";
export const NONE = "—";

/** Fixed decimals, with a true minus sign, and never "−0.0". */
export function fixed(value: number, digits: number): string {
  if (!Number.isFinite(value)) return value > 0 ? "∞" : value < 0 ? `${MINUS}∞` : NONE;
  const text = Math.abs(value).toFixed(digits);
  return value < 0 && Number(text) !== 0 ? `${MINUS}${text}` : text;
}

export function px(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? NONE : `${fixed(value, digits)} px`;
}

export function mm(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? NONE : `${fixed(value, digits)} mm`;
}

/** A fraction as a percentage. */
export function percent(fraction: number | null | undefined, digits = 1): string {
  return fraction === null || fraction === undefined ? NONE : `${fixed(fraction * 100, digits)} %`;
}

/** A percentage with its sign: "+12.0 %", "−39.5 %", "0.0 %". */
export function signedPercent(value: number, digits = 1): string {
  const text = fixed(value, digits);
  return value > 0 && Number(Math.abs(value).toFixed(digits)) !== 0 ? `+${text} %` : `${text} %`;
}

/** "1 landmark", "7 landmarks". */
export function count(value: number, noun: string): string {
  return `${value} ${noun}${value === 1 ? "" : "s"}`;
}

/** The first letter in upper case: the service writes its facts in lower case. */
export function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "too_few_correspondences" → "Too few correspondences"; any identifier the service adds reads the same way. */
export function words(identifier: string): string {
  return sentence(identifier.toLowerCase().replaceAll("_", " "));
}

/** "MOVE_LEFT" → "Move left", "ACCEPT" → "Accept". */
export function actionLabel(action: string): string {
  return words(action);
}

export function failureLabel(failure: string): string {
  return words(failure);
}

/** hh:mm:ss on the visitor's clock; empty for a time that cannot be read. */
export function clock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return [date.getHours(), date.getMinutes(), date.getSeconds()].map((part) => String(part).padStart(2, "0")).join(":");
}

interface CheckFormat {
  label: string;
  value: (value: number) => string;
  /** What the limit reads as, without the comparison, when it is not the value format. */
  limit?: string;
}

/** A count the service sends as a float, such as 5.0. */
function whole(value: number): string {
  return String(Math.round(value));
}

/** The checks of smc_core.policy in words; a check the service adds later is shown by its name. */
const CHECKS: Record<string, CheckFormat> = {
  landmarks: { label: "Landmarks matched", value: whole },
  inliers: { label: "Inliers", value: whole },
  inlier_ratio: { label: "Inlier ratio", value: (value) => fixed(value, 2) },
  rms_reprojection_px: { label: "RMS reprojection", value: (value) => px(value, 2) },
  image_coverage: { label: "Image coverage", value: (value) => percent(value) },
  target_in_frame: { label: "Target in frame", value: (value) => (value >= 1 ? "yes" : "no"), limit: "yes" },
  pose_stability: { label: "Failed samples", value: (value) => percent(value) },
  region_ratio: { label: "Region / target radius", value: (value) => fixed(value, 2) },
};

function formatOf(name: string): CheckFormat {
  return Object.hasOwn(CHECKS, name)
    ? CHECKS[name]
    : { label: words(name), value: (value) => String(Number(value.toPrecision(3))) };
}

export function checkLabel(name: string): string {
  return formatOf(name).label;
}

/** The measurement; a dash when it could not be computed. */
export function checkValue(check: Check): string {
  return check.value === null ? NONE : formatOf(check.name).value(check.value);
}

/** The threshold with its comparison: "≥ 6", "≤ 3.00 px". */
export function checkLimit(check: Check): string {
  const format = formatOf(check.name);
  if (format.limit !== undefined) return format.limit;
  return `${check.op === ">=" ? "≥" : "≤"} ${format.value(check.limit)}`;
}

/** The change of a trace step in two parts: the percentage, and the verdict in a word. */
export function changeText(change: Change): { amount: string; verdict: string } {
  switch (change.kind) {
    case "none":
      return { amount: NONE, verdict: "" };
    case "found":
      return { amount: NONE, verdict: "improved" };
    case "lost":
      return { amount: NONE, verdict: "worse" };
    case "ratio":
      return { amount: signedPercent(change.percent), verdict: change.verdict };
  }
}

/** What a result comes to, in a word: accepted, a move, or no localisation at all. */
export interface Outcome {
  kind: "reliable" | "move" | "failure";
  label: string;
}

export function outcomeOf(result: LocaliseResult): Outcome {
  if (result.localisation.failure !== null) return { kind: "failure", label: "Failed" };
  if (result.decision.reliable) return { kind: "reliable", label: "Reliable" };
  return { kind: "move", label: actionLabel(result.decision.action) };
}

/** The 95 % region of a trace step: its semi-major axis, or why there is none. */
export function regionText(result: LocaliseResult): string {
  const { failure, uncertainty } = result.localisation;
  if (uncertainty) return px(uncertainty.ellipse.semi_major_px);
  return failure === null ? NONE : failureLabel(failure);
}

export interface Measurement {
  label: string;
  value: string;
}

/**
 * The measurements of a result, each with its unit. After a failure only what
 * could be computed is there: the landmarks the view has.
 */
export function measurements(result: LocaliseResult): Measurement[] {
  const { quality, target, uncertainty } = result.localisation;
  const landmarks = result.decision.checks.find((check) => check.name === "landmarks")?.value;
  if (!quality) {
    return [{ label: "Landmarks matched", value: String(landmarks ?? result.observations.length) }];
  }
  const rows: Measurement[] = [
    { label: "Observed / inliers", value: `${quality.observed} / ${quality.inliers}` },
    { label: "Inlier ratio", value: fixed(quality.inlier_ratio, 2) },
    { label: "RMS reprojection", value: px(quality.rms_reprojection_px, 2) },
    { label: "Max reprojection", value: px(quality.max_reprojection_px, 2) },
    { label: "Image coverage", value: percent(quality.image_coverage) },
    { label: "Non-planarity", value: fixed(quality.non_planarity, 3) },
  ];
  if (uncertainty) {
    const { ellipse, pose_only } = uncertainty;
    rows.push(
      { label: "95 % region", value: `${fixed(ellipse.semi_major_px, 1)} × ${px(ellipse.semi_minor_px)}` },
      { label: "Pose-only semi-major", value: px(pose_only.semi_major_px) },
    );
  }
  if (target) {
    rows.push({ label: "Target radius", value: px(target.radius_px) }, { label: "Depth", value: mm(target.depth_mm) });
  }
  return rows;
}

/**
 * The heading of a page that has no workspace to show. The two messages of
 * lib/api for an answer that never came say the service cannot be reached;
 * anything else is the service's own answer.
 */
export function unavailableTitle(message: string): string {
  return /^(Cannot reach|No answer within)\b/.test(message) ? "Service unreachable" : "Workspace not read";
}
