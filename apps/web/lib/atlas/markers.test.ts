import { describe, expect, it } from "vitest";

import answerExample from "../api-examples/markers-answer.json";
import requestExample from "../api-examples/markers-request.json";
import atlasExample from "../api-examples/atlas.json";
import emptyExample from "../api-examples/workspace-empty.json";
import workspaceExample from "../api-examples/workspace.json";
import type { AtlasDetail, MarkersAnswer, ViewSetSummary, Workspace } from "../workspace";
import {
  DEFAULT_TARGET,
  answerText,
  checkMarkers,
  initialMarkers,
  landmarkMarkers,
  markerCounts,
  movingMarkers,
  replacedText,
} from "./markers";

const CAMERA = "iphone11-1x-1080p-portrait";

function copy<T>(example: unknown): T {
  return structuredClone(example) as T;
}

function workspace(example: unknown = workspaceExample): Workspace {
  return copy<Workspace>(example);
}

/** The set cabinet of workspace.json, its points clicked by hand. */
function cabinet(): ViewSetSummary {
  return workspace().view_sets[0];
}

/** atlas.json built from cabinet, its first two landmarks turned into the corners of marker 50 on the flap. */
function markerAtlas(): AtlasDetail & { report: NonNullable<AtlasDetail["report"]> } {
  const detail = copy<AtlasDetail & { report: NonNullable<AtlasDetail["report"]> }>(atlasExample);
  detail.atlas.landmarks = detail.atlas.landmarks.map((landmark, index) =>
    index < 2 ? { ...landmark, id: `m50_${index}`, moves_with: "flap" } : landmark,
  );
  detail.atlas.landmarks.push({ ...detail.atlas.landmarks[0], id: "m52_0", moves_with: null });
  return detail;
}

describe("landmarkMarkers", () => {
  it("lists the rig's landmark markers in order, and none without printed markers", () => {
    expect(landmarkMarkers(workspace().rig)).toEqual([50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60]);
    expect(landmarkMarkers(workspace(emptyExample).rig)).toEqual([]);
  });
});

describe("movingMarkers", () => {
  it("names the markers whose corners move with a panel", () => {
    expect(movingMarkers(markerAtlas())).toEqual([50]);
    expect(movingMarkers(copy(atlasExample))).toEqual([]);
  });
});

describe("initialMarkers", () => {
  it("starts from the form's camera and target, and the moving markers of the set's last atlas", () => {
    expect(initialMarkers(cabinet(), [markerAtlas()], { camera_id: CAMERA, target_id: "drone" })).toEqual({
      camera_id: CAMERA,
      target_id: "drone",
      moving: [50],
    });
  });

  it("falls back to a camera that fits the set, the last build's target, then the default one", () => {
    expect(initialMarkers(cabinet(), [markerAtlas()], { camera_id: "other", target_id: "" })).toMatchObject({
      camera_id: CAMERA,
      target_id: "drone",
    });
    expect(initialMarkers(cabinet(), [], { camera_id: "", target_id: "" })).toEqual({
      camera_id: CAMERA,
      target_id: DEFAULT_TARGET,
      moving: [],
    });
  });
});

describe("checkMarkers", () => {
  const form = { camera_id: CAMERA, target_id: " target ", moving: [50, 51, 52, 53] };

  it("makes the request of the example, replacing the clicks the set has", () => {
    expect(checkMarkers(form, cabinet(), workspace().rig)).toEqual({ request: requestExample, problems: [] });
    const fresh = { ...cabinet(), clicks: null };
    expect(checkMarkers(form, fresh, workspace().rig).request).toMatchObject({ replace: false });
  });

  it("names what keeps it from searching", () => {
    expect(checkMarkers(form, cabinet(), workspace(emptyExample).rig).problems).toEqual([
      "calib/rig.yaml names no printed markers",
    ]);
    expect(checkMarkers({ ...form, target_id: " " }, cabinet(), workspace().rig).problems).toEqual(["Target point missing"]);
    expect(checkMarkers({ ...form, camera_id: "" }, cabinet(), workspace().rig).problems).toEqual(["No camera chosen"]);
    const small = { ...cabinet(), image_size: [64, 48] as [number, number], camera_ids: [] };
    expect(checkMarkers(form, small, workspace().rig).problems).toEqual(["No camera calibrated at 64×48"]);
    expect(checkMarkers(form, { ...cabinet(), image_count: 0 }, workspace().rig).problems).toEqual(["No images in the set"]);
  });
});

describe("what the dialog says", () => {
  it("says what a search replaces, and nothing for a set without clicks", () => {
    expect(replacedText(cabinet())).toBe("Replaces 4 points marked in 3 images");
    expect(replacedText({ ...cabinet(), clicks: null })).toBeNull();
  });

  it("says how many images had markers and the tag, and each marker's images", () => {
    const answer = copy<MarkersAnswer>(answerExample);
    expect(answerText(answer)).toBe("Markers in 287 of 290 images · tag in 149");
    const counts = markerCounts(answer);
    expect(counts[0]).toEqual({ marker: 50, text: "98 images", missing: false });
    expect(counts.at(-1)).toEqual({ marker: 60, text: "not found", missing: true });
  });
});
