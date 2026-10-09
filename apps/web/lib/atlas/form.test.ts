import { describe, expect, it } from "vitest";

import requestExample from "../api-examples/atlas-build-request.json";
import atlasExample from "../api-examples/atlas.json";
import emptyExample from "../api-examples/workspace-empty.json";
import locateExample from "../api-examples/workspace-locate.json";
import workspaceExample from "../api-examples/workspace.json";
import type { AtlasDetail, Camera, Workspace } from "../workspace";
import {
  boardOptions,
  cameraOptions,
  checkForm,
  initialForm,
  nextVersion,
  previousBuild,
  setOptions,
  targetOptions,
  withViewSet,
  type AtlasForm,
  type FormDraft,
} from "./form";

const CAMERA = "iphone11-1x-1080p-portrait";
const NOTHING: [string, string, string] = ["", "", ""];

/** A copy of an example, typed as the model it is an example of, to change freely. */
function copy<T>(example: unknown): T {
  return structuredClone(example) as T;
}

function workspace(example: unknown = workspaceExample): Workspace {
  return copy<Workspace>(example);
}

/** atlas.json: home-cabinet v1, built from the set cabinet with the drone as target. */
function atlas(): AtlasDetail & { report: NonNullable<AtlasDetail["report"]> } {
  return copy(atlasExample);
}

function missingOf(data: Workspace, draft: FormDraft, details: AtlasDetail[] = []): string[] {
  return checkForm(data, initialForm(data, details, draft)).missing.map((item) => item.text);
}

describe("initialForm", () => {
  it("opens on the newest set, the camera of its clicks, a measured board on the asset and the drone", () => {
    expect(initialForm(workspace(), [])).toEqual<AtlasForm>({
      view_set: "cabinet",
      camera_id: CAMERA,
      board: "rig_board_a",
      target_id: "drone",
      target_extent_mm: NOTHING,
      // No atlas read yet: the set's own name.
      asset_id: "cabinet",
      version: "1",
      click_sigma_px: "2",
      target_centre_sigma_mm: "5",
      samples: "200",
      seed: "0",
      target_measured_mm: NOTHING,
    });
  });

  it("repeats the last atlas built from the set: its asset id, extent and settings, and counts its version up", () => {
    const last = atlas();
    last.report.request = {
      ...last.report.request,
      click_sigma_px: 1.5,
      target_centre_sigma_mm: 8,
      samples: 500,
      seed: 3,
      target_measured_mm: [95, 160, -205.5],
    };
    expect(initialForm(workspace(), [last])).toMatchObject<Partial<AtlasForm>>({
      view_set: "cabinet",
      asset_id: "home-cabinet",
      version: "2",
      target_extent_mm: ["300", "300", "100"],
      click_sigma_px: "1.5",
      target_centre_sigma_mm: "8",
      samples: "500",
      seed: "3",
      target_measured_mm: ["95", "160", "-205.5"],
    });
  });

  it("opens on the repository as it is today: no set yet and the rig board not measured", () => {
    expect(initialForm(workspace(emptyExample), [])).toMatchObject<Partial<AtlasForm>>({
      view_set: "",
      camera_id: CAMERA,
      board: "rig_board_a",
      target_id: "",
      asset_id: "",
      version: "1",
    });
  });

  it("takes the newest set", () => {
    expect(initialForm(workspace(locateExample), []).view_set).toBe("cabinet-test");
  });

  it("chooses the target this asset had, else the drone, else the target of the newest atlas", () => {
    const last = atlas();
    last.report.request.target_id = "handle";
    expect(initialForm(workspace(), [last]).target_id).toBe("handle");

    const data = workspace();
    data.view_sets[0].clicks!.point_views = { hinge_top: 3, handle: 2 };
    data.atlases[0].target_id = "handle";
    expect(initialForm(data, []).target_id).toBe("handle");
    data.atlases = [];
    expect(initialForm(data, []).target_id).toBe("");
  });

  it("prefers a board on the asset that is measured, and the board of the last build", () => {
    const data = workspace(emptyExample);
    data.rig.boards[2] = { ...data.rig.boards[2], square_measured_mm: 25.02, measured: true };
    expect(initialForm(data, []).board).toBe("rig_board_b");
    const last = atlas();
    last.report.request.board = "calibration_board";
    expect(initialForm(workspace(), [last]).board).toBe("calibration_board");
  });

  it("keeps what was typed", () => {
    const draft: FormDraft = { asset_id: "cabinet-2", version: "7", target_extent_mm: ["1", "2", "3"], samples: "50" };
    expect(initialForm(workspace(), [atlas()], draft)).toMatchObject(draft);
  });
});

describe("the form's helpers", () => {
  it("counts a whole version up and leaves any other as it is", () => {
    expect(["1", "41", "v1", "1.2", ""].map(nextVersion)).toEqual(["2", "42", "v1", "1.2", ""]);
  });

  it("finds the newest atlas built from a set, by its report", () => {
    const older = atlas();
    const newer = atlas();
    newer.atlas.asset_id = "cabinet-again";
    newer.report.built_at = "2026-10-07T09:00:00+02:00";
    const written: AtlasDetail = { ...atlas(), report: null };
    expect(previousBuild([older, newer, written], "cabinet")?.atlas.asset_id).toBe("cabinet-again");
    expect(previousBuild([older, newer], "cabinet-2")).toBeUndefined();
  });

  it("lets the fields of a set follow another set, and keeps the rest", () => {
    const draft: FormDraft = {
      view_set: "cabinet",
      camera_id: CAMERA,
      target_id: "drone",
      asset_id: "home-cabinet",
      version: "3",
      board: "rig_board_b",
      target_extent_mm: ["300", "300", "100"],
    };
    expect(withViewSet(draft, "cabinet-2")).toEqual({
      view_set: "cabinet-2",
      board: "rig_board_b",
      target_extent_mm: ["300", "300", "100"],
    });
  });
});

describe("what the selects offer", () => {
  it("lists the sets newest first with their image counts", () => {
    expect(setOptions(workspace(locateExample)).map((option) => option.label)).toEqual([
      "cabinet-test · 3 images",
      "cabinet · 5 images",
    ]);
  });

  it("lists the boards of the rig with their measured square", () => {
    expect(boardOptions(workspace()).map((option) => option.label)).toEqual([
      "calibration_board · 30.00 mm",
      "rig_board_a · 25.04 mm",
      "rig_board_b · not measured",
    ]);
  });

  it("lists the cameras of the set's image size first; the others cannot be chosen and show their size", () => {
    const data = workspace();
    const landscape: Camera = { ...data.cameras[0], file: "landscape.yml", camera_id: "landscape", image_width: 1920, image_height: 1080 };
    const broken: Camera = { ...data.cameras[0], file: "broken.yml", camera_id: null, image_width: null, error: "not a calibration" };
    data.cameras = [landscape, broken, data.cameras[0]];
    expect(cameraOptions(data, "cabinet")).toEqual([
      { value: CAMERA, label: `${CAMERA} · 1080×1920`, disabled: false },
      { value: "landscape", label: "landscape · 1920×1080", disabled: true },
      { value: "broken.yml", label: "broken.yml · unreadable", disabled: true },
    ]);
  });

  it("lists the set's points with their views; one in fewer than two images cannot be the target", () => {
    expect(targetOptions(workspace(), "cabinet")).toEqual([
      { value: "hinge_top", label: "hinge_top · 3 views", disabled: false },
      { value: "handle", label: "handle · 2 views", disabled: false },
      { value: "corner_left", label: "corner_left · 1 view", disabled: true },
      { value: "drone", label: "drone · 2 views", disabled: false },
    ]);
    expect(targetOptions(workspace(), "no-such-set")).toEqual([]);
  });
});

describe("checkForm", () => {
  it("makes the request of the example when the form is filled that way", () => {
    const data = workspace();
    data.atlases = [];
    const form = initialForm(data, [], { asset_id: "home-cabinet", target_extent_mm: ["300", "300", "100"] });
    expect(checkForm(data, form)).toEqual({ request: requestExample, missing: [] });

    // The same from the atlas built before: its settings, with its version typed again.
    const again = initialForm(workspace(), [atlas()], { version: "1" });
    expect(checkForm(workspace(), again).request).toEqual(requestExample);
  });

  it("names what the empty workspace lacks", () => {
    const data = workspace(emptyExample);
    const checked = checkForm(data, initialForm(data, []));
    expect(checked.request).toBeNull();
    expect(checked.missing).toEqual([
      { field: "view_set", text: "No view set" },
      { field: "board", text: "Board not measured" },
      { field: "target_extent_mm", text: "Target extent missing" },
      { field: "asset_id", text: "Asset id missing" },
    ]);
  });

  it("names what the workspace says against the chosen set, board and target", () => {
    const filled: FormDraft = { target_extent_mm: ["300", "300", "100"] };
    expect(missingOf(workspace(), { ...filled, target_id: "corner_left" })).toEqual(["corner_left marked in 1 image, needs 2"]);
    expect(missingOf(workspace(), { ...filled, board: "rig_board_b" })).toEqual(["Board not measured"]);
    const data = workspace();
    data.view_sets[0].clicks = null;
    expect(missingOf(data, filled)).toEqual(["No points marked"]);
    expect(missingOf(workspace(), { ...filled, target_id: "" })).toEqual(["No target chosen"]);
  });

  it("checks what was typed against what the service accepts", () => {
    const filled: FormDraft = { target_extent_mm: ["300", "300", "100"] };
    const cases: [FormDraft, string][] = [
      [{ target_extent_mm: ["300", "0", "100"] }, "Target extent y 0 mm, needs > 0"],
      [{ target_extent_mm: ["300", "", "100"] }, "Target extent missing"],
      [{ asset_id: "home cabinet" }, "Asset id has characters other than A–Z a–z 0–9 . _ -"],
      [{ asset_id: "-cabinet" }, "Asset id needs a letter or digit first"],
      [{ asset_id: "cabinet.report" }, "Asset id ends in .report"],
      [{ version: " " }, "Version missing"],
      [{ click_sigma_px: "0" }, "Click σ 0 px, needs > 0"],
      [{ target_centre_sigma_mm: "-1" }, "Target centre σ -1 mm, needs ≥ 0"],
      [{ samples: "5" }, "Samples 5, needs 10 to 2000"],
      [{ samples: "20.5" }, "Samples 20.5, needs a whole number"],
      [{ seed: "-1" }, "Seed -1, needs ≥ 0"],
      [{ target_measured_mm: ["10", "", ""] }, "Measured target incomplete"],
      [{ target_measured_mm: ["10", "20", "far"] }, "Measured target z not a number"],
    ];
    for (const [draft, text] of cases) expect(missingOf(workspace(), { ...filled, ...draft })).toEqual([text]);
  });

  it("sends the measured target, and the asset id and version without spaces", () => {
    const data = workspace();
    const form = initialForm(data, [], {
      target_extent_mm: ["300", "300", "100"],
      target_measured_mm: ["10", "-20.5", "30"],
      asset_id: " home-cabinet ",
      version: " 2 ",
    });
    expect(checkForm(data, form).request).toMatchObject({
      asset_id: "home-cabinet",
      version: "2",
      target_measured_mm: [10, -20.5, 30],
    });
  });
});
