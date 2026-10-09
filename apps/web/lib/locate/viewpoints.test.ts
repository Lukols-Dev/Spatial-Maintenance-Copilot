import { describe, expect, it } from "vitest";

import atlasExample from "../api-examples/atlas.json";
import cabinetExample from "../api-examples/atlas-cabinet.json";
import viewpointsExample from "../api-examples/view-set-viewpoints.json";
import workspaceExample from "../api-examples/workspace-locate.json";
import type { AtlasDetail, AtlasSummary, ViewSet, ViewSetSummary, Workspace } from "../workspace";
import {
  atlasOptions,
  buildSetOf,
  defaultTruthView,
  pickAtlas,
  pickViewSet,
  truthViews,
  viewpointSets,
  viewpointsOf,
} from "./viewpoints";

/** A copy of an example, typed as the model it is an example of, to change freely. */
function copy<T>(example: unknown): T {
  return structuredClone(example) as T;
}

const workspace = () => copy<Workspace>(workspaceExample);
const cabinet = () => copy<AtlasDetail>(cabinetExample);
const viewSet = () => copy<ViewSet>(viewpointsExample);

function atlasSummary(asset_id: string, built_at: string, error: string | null = null): AtlasSummary {
  return { ...workspace().atlases[0], asset_id, file: `${asset_id}.json`, built_at, error };
}

function setSummary(name: string, updated_at: string, point_views: Record<string, number>): ViewSetSummary {
  const base = workspace().view_sets[0];
  return { ...base, name, updated_at, clicks: base.clicks && { ...base.clicks, point_views } };
}

describe("the atlas choice", () => {
  const atlases = [
    atlasSummary("old", "2026-10-01T10:00:00+02:00"),
    atlasSummary("broken", "2026-10-06T18:00:00+02:00", "atlas.json: invalid JSON"),
    atlasSummary("new", "2026-10-05T10:00:00+02:00"),
  ];

  it("lists every atlas newest first, the unreadable one too", () => {
    const data = workspace();
    data.atlases = atlases;
    expect(atlasOptions(data).map((atlas) => atlas.asset_id)).toEqual(["broken", "new", "old"]);
  });

  it("takes the newest atlas that can be read, or the one wanted", () => {
    expect(pickAtlas(atlases, null)).toBe("new");
    expect(pickAtlas(atlases, "old")).toBe("old");
    expect(pickAtlas(atlases, "broken")).toBe("new");
    expect(pickAtlas(atlases, "gone")).toBe("new");
    expect(pickAtlas([atlases[1]], null)).toBeNull();
    expect(pickAtlas([], null)).toBeNull();
  });
});

describe("the view sets with viewpoints", () => {
  it("are the sets marking a landmark of the atlas, newest first", () => {
    expect(viewpointSets(workspace(), cabinet().atlas).map((set) => set.name)).toEqual(["cabinet-test", "cabinet"]);
  });

  it("leave out a set that marks only the target, other points, or nothing, and a broken one", () => {
    const data = workspace();
    const marked = data.view_sets[1];
    data.view_sets = [
      setSummary("target-only", "2026-10-07T10:00:00+02:00", { drone: 3 }),
      setSummary("other-points", "2026-10-07T10:00:00+02:00", { door_knob: 2, corner_top_left: 0 }),
      { ...setSummary("broken", "2026-10-07T10:00:00+02:00", { handle: 3 }), error: "unreadable folder" },
      { ...marked, name: "no-clicks", clicks: null },
      marked,
    ];
    expect(viewpointSets(data, cabinet().atlas).map((set) => set.name)).toEqual(["cabinet-test"]);
  });

  it("names the set an atlas was built from when its report says so", () => {
    expect(buildSetOf(copy<AtlasDetail>(atlasExample))).toBe("cabinet");
    expect(buildSetOf(cabinet())).toBeNull();
  });
});

describe("pickViewSet", () => {
  const sets = viewpointSets(workspace(), cabinet().atlas);

  it("takes the newest set, unknown how the atlas was built", () => {
    expect(pickViewSet(sets, null, null)).toBe("cabinet-test");
  });

  it("takes the newest set that is not the atlas's build set", () => {
    expect(pickViewSet(sets, "cabinet-test", null)).toBe("cabinet");
    expect(pickViewSet(sets, "cabinet", null)).toBe("cabinet-test");
  });

  it("takes the build set when it is the only one", () => {
    expect(pickViewSet([sets[1]], "cabinet", null)).toBe("cabinet");
  });

  it("keeps the set wanted while it is offered", () => {
    expect(pickViewSet(sets, null, "cabinet")).toBe("cabinet");
    expect(pickViewSet(sets, null, "gone")).toBe("cabinet-test");
    expect(pickViewSet([], null, "cabinet")).toBeNull();
  });
});

describe("the viewpoints of a set", () => {
  it("are its images with atlas landmarks clicked, counted, with the target marked", () => {
    expect(viewpointsOf(viewSet(), cabinet().atlas)).toEqual([
      { file: "frame_000010.png", landmarks: 5, truth: false, width: 1080, height: 1920 },
      { file: "frame_000040.png", landmarks: 7, truth: true, width: 1080, height: 1920 },
      { file: "frame_000070.png", landmarks: 3, truth: false, width: 1080, height: 1920 },
    ]);
  });

  it("leave out an image with only the target clicked, which is still a truth", () => {
    const set = viewSet();
    set.images.push({ file: "frame_000041.png", width: 1080, height: 1920, format: "png", error: null });
    if (!set.clicks) throw new Error("the example has clicks");
    set.clicks.views["frame_000041.png"] = { drone: [530, 1080] };
    // A click on a file that is not an image of the set is no viewpoint either.
    set.clicks.views["gone.png"] = { handle: [1, 2] };
    expect(viewpointsOf(set, cabinet().atlas).map((view) => view.file)).toEqual([
      "frame_000010.png",
      "frame_000040.png",
      "frame_000070.png",
    ]);
    expect(truthViews(set, "drone")).toEqual(["frame_000040.png", "frame_000041.png"]);
  });

  it("are none without clicks", () => {
    const set = viewSet();
    set.clicks = null;
    expect(viewpointsOf(set, cabinet().atlas)).toEqual([]);
    expect(truthViews(set, "drone")).toEqual([]);
  });
});

describe("the truth of a viewpoint", () => {
  const truths = truthViews(viewSet(), "drone");

  it("is the view's own target click by default", () => {
    expect(truths).toEqual(["frame_000040.png"]);
    expect(defaultTruthView("frame_000040.png", truths)).toBe("frame_000040.png");
  });

  it("is none for a view without one, until a paired shot is chosen", () => {
    expect(defaultTruthView("frame_000010.png", truths)).toBeNull();
  });
});
