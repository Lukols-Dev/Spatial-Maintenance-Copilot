import { describe, expect, it } from "vitest";

import cabinetExample from "../api-examples/atlas-cabinet.json";
import atlasExample from "../api-examples/atlas.json";
import locateExample from "../api-examples/workspace-locate.json";
import workspaceExample from "../api-examples/workspace.json";
import type { AtlasDetail, Workspace } from "../workspace";
import { buildFacts, buildSet, clickedViews, figures, pointRows, skippedPoints } from "./result";

const CAMERA = "iphone11-1x-1080p-portrait";

function copy<T>(example: unknown): T {
  return structuredClone(example) as T;
}

/** atlas.json: home-cabinet v1 from the set cabinet, one point skipped and one view not posed. */
function built(): AtlasDetail & { report: NonNullable<AtlasDetail["report"]> } {
  return copy(atlasExample);
}

/** atlas-cabinet.json: written by the CLI, without a build report. */
function written(): AtlasDetail {
  return copy(cabinetExample);
}

describe("the build of an atlas", () => {
  it("names the set, the camera and the board of the build, and when it ran", () => {
    const data = copy<Workspace>(workspaceExample);
    const detail = built();
    const set = buildSet(data, detail);
    expect(set?.name).toBe("cabinet");
    expect(buildFacts(detail, data.atlases[0], set)).toEqual({
      viewSet: "cabinet",
      camera: CAMERA,
      board: "rig_board_a",
      builtAt: "2026-10-06T14:25:03+02:00",
      clicksChanged: false,
    });
  });

  it("says when the set's points were saved after the build", () => {
    const data = copy<Workspace>(workspaceExample);
    data.view_sets[0].clicks!.saved_at = "2026-10-06T14:30:00+02:00";
    const detail = built();
    expect(buildFacts(detail, data.atlases[0], buildSet(data, detail)).clicksChanged).toBe(true);
  });

  it("has only what the atlas file holds when the CLI wrote it", () => {
    const data = copy<Workspace>(locateExample);
    const detail = written();
    expect(buildSet(data, detail)).toBeUndefined();
    expect(buildFacts(detail, data.atlases[0])).toEqual({
      viewSet: null,
      camera: null,
      board: "rig_board_a",
      builtAt: "2026-10-06T16:05:40+02:00",
      clicksChanged: false,
    });
  });
});

describe("figures", () => {
  it("counts the landmarks, the posed of the clicked views and the skipped points; the target σ in mm", () => {
    const data = copy<Workspace>(workspaceExample);
    const detail = built();
    expect(figures(detail, buildSet(data, detail))).toEqual([
      { label: "Landmarks", value: "2" },
      { label: "Target σ", value: "5.21", unit: "mm" },
      { label: "Posed / clicked", value: "2 / 3", unit: "views" },
      { label: "Skipped points", value: "1" },
    ]);
  });

  it("adds the gap to the measured target when there is one", () => {
    const detail = built();
    detail.report.target_gap_mm = 12.345;
    expect(figures(detail, undefined).at(-1)).toEqual({ label: "Target gap", value: "12.3", unit: "mm" });
  });

  it("counts the posed views alone once the clicks no longer are those of the build", () => {
    const data = copy<Workspace>(workspaceExample);
    const detail = built();
    data.view_sets[0].clicks!.saved_at = "2026-10-06T15:00:00+02:00";
    expect(figures(detail, buildSet(data, detail))[2]).toEqual({ label: "Posed", value: "2", unit: "views" });
    expect(clickedViews(detail.report, buildSet(data, detail))).toBeNull();
    expect(clickedViews(detail.report, undefined)).toBeNull();
  });

  it("has the landmarks and the target σ of an atlas without a report", () => {
    expect(figures(written(), undefined)).toEqual([
      { label: "Landmarks", value: "7" },
      { label: "Target σ", value: "5.21", unit: "mm" },
    ]);
  });
});

describe("the points", () => {
  it("lists every point of the report by id, the target marked", () => {
    expect(pointRows(built())).toEqual([
      {
        id: "drone",
        position_mm: [95, 160.4, -210.8],
        sigma_mm: 5.21,
        views: 2,
        worst_px: 1.32,
        ray_angle_deg: 18.2,
        is_target: true,
      },
      { id: "handle", position_mm: [182.6, 95.3, 21.7], sigma_mm: 2.31, views: 2, worst_px: 0.87, ray_angle_deg: 17.9, is_target: false },
      { id: "hinge_top", position_mm: [-12.4, -310.2, 4.1], sigma_mm: 1.84, views: 2, worst_px: 0.64, ray_angle_deg: 18.6, is_target: false },
    ]);
  });

  it("lists the landmarks and the target of an atlas without a report, by id", () => {
    const rows = pointRows(written());
    expect(rows.map((row) => row.id)).toEqual([
      "corner_bottom_left",
      "corner_bottom_right",
      "corner_top_left",
      "corner_top_right",
      "drone",
      "handle",
      "hinge_bottom",
      "hinge_top",
    ]);
    expect(rows.filter((row) => row.is_target).map((row) => row.id)).toEqual(["drone"]);
    expect(rows.every((row) => row.views === null && row.worst_px === null && row.ray_angle_deg === null)).toBe(true);
  });

  it("lists the skipped points by id with the service's reasons", () => {
    const detail = built();
    detail.report.skipped = { zeta: "never clicked", corner_left: "seen in 1 posed view, needs 2" };
    expect(skippedPoints(detail.report)).toEqual([
      { id: "corner_left", reason: "seen in 1 posed view, needs 2" },
      { id: "zeta", reason: "never clicked" },
    ]);
  });
});
