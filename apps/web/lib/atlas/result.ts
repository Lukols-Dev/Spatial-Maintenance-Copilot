import type { AtlasBuildReport, AtlasDetail, AtlasSummary, Vec3, ViewSetSummary, Workspace } from "@/lib/workspace";

import { fixed } from "./format";
import { frameBoard } from "./plan";

// What the Result card shows of an atlas: the facts of its build, the numbers
// to judge it by, and one row per point. An atlas written by the CLI has no
// build report; for it the card shows what the atlas file holds, nothing more.

export interface BuildFacts {
  viewSet: string | null;
  camera: string | null;
  board: string | null;
  /** ISO 8601: the report's build time, else the file's. */
  builtAt: string | null;
  /** The set's points were saved after the build: the atlas does not have them. */
  clicksChanged: boolean;
}

/** One number of the card: a count, or a measurement with its unit. */
export interface Figure {
  label: string;
  value: string;
  unit?: string;
}

export interface PointRow {
  id: string;
  position_mm: Vec3;
  sigma_mm: number;
  /** Null without a build report, here and below. */
  views: number | null;
  worst_px: number | null;
  ray_angle_deg: number | null;
  is_target: boolean;
}

/** The view set an atlas was built from, as the workspace lists it now. */
export function buildSet(workspace: Workspace, detail: AtlasDetail): ViewSetSummary | undefined {
  const name = detail.report?.request.view_set;
  return name === undefined ? undefined : workspace.view_sets.find((set) => set.name === name);
}

/** The set's clicks are newer than the build. */
function clicksAfter(report: AtlasBuildReport, set: ViewSetSummary | undefined): boolean {
  const clicks = set?.clicks;
  return !!clicks && !clicks.error && Date.parse(clicks.saved_at) > Date.parse(report.built_at);
}

export function buildFacts(detail: AtlasDetail, summary: AtlasSummary | undefined, set?: ViewSetSummary): BuildFacts {
  const { atlas, report } = detail;
  return {
    viewSet: report?.request.view_set ?? null,
    camera: report?.request.camera_id ?? null,
    board: report?.request.board ?? frameBoard(atlas.frame),
    builtAt: report?.built_at ?? summary?.built_at ?? null,
    clicksChanged: report !== null && clicksAfter(report, set),
  };
}

/**
 * The clicked views of the build and how many of them were posed. The report
 * names the clicked views that were not posed; the set's clicks say how many
 * views were clicked, as long as they were not saved again after the build.
 */
export function clickedViews(report: AtlasBuildReport, set: ViewSetSummary | undefined): { posed: number; clicked: number } | null {
  const clicks = set?.clicks;
  if (!clicks || clicks.error || clicksAfter(report, set)) return null;
  const clicked = clicks.marked_images;
  return { posed: Math.max(0, clicked - report.unposed_views.length), clicked };
}

/** Landmarks, the target's σ, posed of clicked views, skipped points, and the target's gap when it was measured. */
export function figures(detail: AtlasDetail, set: ViewSetSummary | undefined): Figure[] {
  const { atlas, report } = detail;
  const list: Figure[] = [
    { label: "Landmarks", value: String(atlas.landmarks.length) },
    { label: "Target σ", value: fixed(atlas.target.sigma_mm, 2), unit: "mm" },
  ];
  if (!report) return list;
  const views = clickedViews(report, set);
  list.push(
    views
      ? { label: "Posed / clicked", value: `${views.posed} / ${views.clicked}`, unit: "views" }
      : { label: "Posed", value: String(report.posed_views.length), unit: "views" },
    { label: "Skipped points", value: String(Object.keys(report.skipped).length) },
  );
  if (report.target_gap_mm !== null) list.push({ label: "Target gap", value: fixed(report.target_gap_mm, 1), unit: "mm" });
  return list;
}

/** Every point of the atlas, target included, by id: with the build's numbers when the report is there. */
export function pointRows(detail: AtlasDetail): PointRow[] {
  const { atlas, report } = detail;
  if (report) {
    return report.points.map((point) => ({
      id: point.id,
      position_mm: point.position_mm,
      sigma_mm: point.sigma_mm,
      views: point.views,
      worst_px: point.worst_px,
      ray_angle_deg: point.ray_angle_deg,
      is_target: point.is_target,
    }));
  }
  const rows = [...atlas.landmarks, atlas.target].map((point) => ({
    id: point.id,
    position_mm: point.position_mm,
    sigma_mm: point.sigma_mm,
    views: null,
    worst_px: null,
    ray_angle_deg: null,
    is_target: point.id === atlas.target.id,
  }));
  return rows.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

/** The points the build left out, by id, each with the service's reason. */
export function skippedPoints(report: AtlasBuildReport): { id: string; reason: string }[] {
  return Object.keys(report.skipped)
    .sort()
    .map((id) => ({ id, reason: report.skipped[id] }));
}
