import { afterEach, describe, expect, it, vi } from "vitest";

import clicksExample from "./annotate/clicks.example.json";
import type { ClicksFile, Pixel } from "./annotate/core";
import { API_URL } from "./api";
import boardExample from "./api-examples/board.json";
import measurementExample from "./api-examples/board-measurement.json";
import clicksSummaryExample from "./api-examples/clicks-summary.json";
import viewSetSummaryExample from "./api-examples/view-set-summary.json";
import emptyExample from "./api-examples/workspace-empty.json";
import workspaceExample from "./api-examples/workspace.json";
import {
  atlasReadiness,
  matchingCameras,
  squareFromSpan,
  type BoardMeasurement,
  type Camera,
  type Workspace,
} from "./workspace";

/** A copy of an example, typed as the model it is an example of, to change freely. */
function copy<T>(example: unknown): T {
  return structuredClone(example) as T;
}

function workspace(example: unknown = workspaceExample): Workspace {
  return copy<Workspace>(example);
}

const CAMERA = "iphone11-1x-1080p-portrait";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("squareFromSpan", () => {
  it("divides a reading across several squares by their number", () => {
    expect(squareFromSpan(100.08, 4)).toBe(25.02);
    expect(squareFromSpan(25.02, 1)).toBe(25.02);
  });

  it("keeps micrometres, without binary noise", () => {
    expect(72.12 / 3).not.toBe(24.04);
    expect(squareFromSpan(72.12, 3)).toBe(24.04);
    expect(squareFromSpan(100.1, 3)).toBe(33.367);
  });

  it("refuses a reading or a count that cannot be right", () => {
    for (const [length, squares] of [
      [0, 4],
      [-100, 4],
      [Number.NaN, 4],
      [Number.POSITIVE_INFINITY, 4],
      [100, 0],
      [100, -4],
      [100, 2.5],
    ]) {
      expect(squareFromSpan(length, squares)).toBeNull();
    }
  });
});

describe("matchingCameras", () => {
  it("finds the cameras whose image size is the set's, as the service does", () => {
    const data = workspace();
    const matching = matchingCameras(data, "cabinet").map((camera) => camera.camera_id);
    expect(matching).toEqual([CAMERA]);
    expect(matching).toEqual(data.view_sets[0].camera_ids);
  });

  it("finds none for images of another size, of mixed sizes, or an unknown set", () => {
    const data = workspace();
    data.view_sets[0].image_size = [1920, 1080];
    expect(matchingCameras(data, "cabinet")).toEqual([]);
    data.view_sets[0].image_size = null;
    data.view_sets[0].mixed_sizes = true;
    expect(matchingCameras(data, "cabinet")).toEqual([]);
    expect(matchingCameras(workspace(), "no-such-set")).toEqual([]);
  });

  it("leaves out a calibration file that cannot be read", () => {
    const data = workspace();
    const broken: Camera = { ...data.cameras[0], file: "broken.yml", camera_id: "broken", error: "not a calibration" };
    data.cameras.push(broken);
    expect(matchingCameras(data, "cabinet").map((camera) => camera.file)).toEqual([data.cameras[0].file]);
  });
});

describe("atlasReadiness", () => {
  const BUILD = { view_set: "cabinet", camera_id: CAMERA, board: "rig_board_a", target_id: "drone" };

  it("has nothing missing for the example workspace, chosen or not", () => {
    expect(atlasReadiness(workspace(), BUILD)).toEqual({});
    expect(atlasReadiness(workspace())).toEqual({});
  });

  it("names what the repository lacks today: views, and the rig board's measurement", () => {
    expect(atlasReadiness(workspace(emptyExample))).toEqual({ view_set: "No view set" });
    expect(atlasReadiness(workspace(emptyExample), { board: "rig_board_a" })).toEqual({
      view_set: "No view set",
      board: "Board not measured",
    });
  });

  it("checks the chosen board", () => {
    expect(atlasReadiness(workspace(), { ...BUILD, board: "rig_board_b" })).toEqual({ board: "Board not measured" });
    expect(atlasReadiness(workspace(), { ...BUILD, board: "rig_board_z" })).toEqual({ board: "Unknown board" });

    const data = workspace();
    data.rig = { dictionary: null, boards: [], error: "calib/rig.yaml not found" };
    expect(atlasReadiness(data)).toEqual({ board: "calib/rig.yaml not found" });
    data.rig = { ...workspace().rig, boards: workspace().rig.boards.map((board) => ({ ...board, measured: false })) };
    expect(atlasReadiness(data)).toEqual({ board: "No board measured" });
  });

  it("needs the target clicked in two images", () => {
    expect(atlasReadiness(workspace(), { ...BUILD, target_id: "corner_left" })).toEqual({
      target_id: "Marked in 1 image, needs 2",
    });
    expect(atlasReadiness(workspace(), { ...BUILD, target_id: "constructor" })).toEqual({ target_id: "Not marked" });

    const data = workspace();
    const clicks = data.view_sets[0].clicks!;
    clicks.ready_points = 0;
    clicks.point_views = { hinge_top: 1, handle: 1, corner_left: 1, drone: 0 };
    expect(atlasReadiness(data)).toEqual({ target_id: "No point marked in 2 images" });
  });

  it("needs a set of images of one size with points marked", () => {
    const data = workspace();
    data.view_sets[0].clicks = null;
    expect(atlasReadiness(data, BUILD)).toEqual({ view_set: "No points marked" });
    expect(atlasReadiness(data)).toEqual({ view_set: "No points marked" });

    data.view_sets[0].image_size = null;
    data.view_sets[0].mixed_sizes = true;
    expect(atlasReadiness(data, BUILD)).toEqual({ view_set: "Images differ in size" });
    expect(atlasReadiness(workspace(), { ...BUILD, view_set: "cabinet-2" })).toEqual({ view_set: "Unknown view set" });
  });

  it("takes the newest set that can be built from when none is chosen", () => {
    const data = workspace();
    const fresh = copy<Workspace["view_sets"][number]>(viewSetSummaryExample);
    data.view_sets.push(fresh);
    // cabinet-2 is newer but has no clicks yet.
    expect(atlasReadiness(data)).toEqual({});
    data.view_sets[0].clicks!.error = "clicks.json: views must be an object";
    expect(atlasReadiness(data)).toEqual({ view_set: "No points marked" });
  });

  it("needs the clicks made on the camera, and the camera's image size", () => {
    const data = workspace();
    data.view_sets[0].clicks!.camera_id = "phone-0.5x";
    expect(atlasReadiness(data)).toEqual({ camera_id: "Clicks are for phone-0.5x" });
    expect(atlasReadiness(data, BUILD)).toEqual({ camera_id: "Clicks are for phone-0.5x" });
    data.view_sets[0].clicks!.camera_id = "";
    expect(atlasReadiness(data)).toEqual({ camera_id: "Clicks have no camera id" });

    const landscape = workspace();
    landscape.cameras[0].image_width = 1920;
    landscape.cameras[0].image_height = 1080;
    expect(atlasReadiness(landscape, BUILD)).toEqual({ camera_id: "Camera is 1920×1080, images 1080×1920" });
    landscape.view_sets[0].clicks!.camera_id = "phone-0.5x";
    expect(atlasReadiness(landscape)).toEqual({ camera_id: "No camera for 1080×1920" });
  });

  it("needs a calibration that can be read", () => {
    const data = workspace();
    data.cameras = [];
    expect(atlasReadiness(data)).toEqual({ camera_id: "No calibrated camera" });
    expect(atlasReadiness(data, BUILD)).toEqual({ camera_id: "Unknown camera" });

    data.cameras = [{ ...workspace().cameras[0], fx: null, error: "fx is missing" }];
    expect(atlasReadiness(data, BUILD)).toEqual({ camera_id: "fx is missing" });
  });
});

// ---- store and calls ------------------------------------------------------------

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

function jsonAnswer(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** The module as on a fresh page: its store has not read anything yet. */
async function freshModule() {
  vi.resetModules();
  return import("./workspace");
}

const UNREACHABLE = `Cannot reach the perception service at ${API_URL}`;

describe("the workspace store", () => {
  it("keeps the last workspace on screen when a refresh fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<Fetch>()
        .mockResolvedValueOnce(jsonAnswer(workspaceExample))
        .mockRejectedValueOnce(new TypeError("fetch failed"))
        .mockResolvedValueOnce(jsonAnswer(emptyExample)),
    );
    const { refreshWorkspace, workspaceState } = await freshModule();
    expect(workspaceState()).toEqual({ status: "loading" });

    const first = refreshWorkspace();
    expect(workspaceState()).toEqual({ status: "loading" });
    await first;
    expect(workspaceState()).toEqual({ status: "ready", data: workspaceExample, refreshing: false });

    const second = refreshWorkspace();
    expect(workspaceState()).toEqual({ status: "ready", data: workspaceExample, refreshing: true });
    await second;
    expect(workspaceState()).toEqual({ status: "error", message: UNREACHABLE, data: workspaceExample });

    await refreshWorkspace();
    expect(workspaceState()).toEqual({ status: "ready", data: emptyExample, refreshing: false });
  });

  it("has no data to keep when the first read fails", async () => {
    vi.stubGlobal("fetch", vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer({ detail: "Workspace unreadable" }, 500)));
    const { refreshWorkspace, workspaceState } = await freshModule();
    await refreshWorkspace();
    expect(workspaceState()).toEqual({ status: "error", message: "Workspace unreadable" });
  });

  it("drops an older answer that arrives after a newer one", async () => {
    const slow = Promise.withResolvers<Response>();
    vi.stubGlobal(
      "fetch",
      vi
        .fn<Fetch>()
        .mockReturnValueOnce(slow.promise)
        .mockResolvedValueOnce(jsonAnswer(emptyExample)),
    );
    const { refreshWorkspace, workspaceState } = await freshModule();
    const older = refreshWorkspace();
    await refreshWorkspace();
    slow.resolve(jsonAnswer(workspaceExample));
    await older;
    expect(workspaceState()).toEqual({ status: "ready", data: emptyExample, refreshing: false });
  });
});

describe("calls that change the workspace", () => {
  it("a board measurement is sent as JSON and the workspace is read again", async () => {
    const fetch = vi
      .fn<Fetch>()
      .mockResolvedValueOnce(jsonAnswer(boardExample))
      .mockResolvedValueOnce(jsonAnswer(workspaceExample));
    vi.stubGlobal("fetch", fetch);
    const { measureBoard, workspaceState } = await freshModule();

    const measurement = copy<BoardMeasurement>(measurementExample);
    expect(await measureBoard("rig_board_b", measurement)).toEqual(boardExample);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe(`${API_URL}/boards/rig_board_b/measurement`);
    expect(init?.method).toBe("PUT");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual(measurementExample);
    expect(fetch.mock.calls[1][0]).toBe(`${API_URL}/workspace`);
    expect(workspaceState()).toEqual({ status: "ready", data: workspaceExample, refreshing: false });
  });

  it("a refused change is an ApiError and the workspace is not read again", async () => {
    const fetch = vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer({ detail: "The workspace is read-only" }, 403));
    vi.stubGlobal("fetch", fetch);
    const { measureBoard } = await freshModule();
    const call = measureBoard("rig_board_a", copy<BoardMeasurement>(measurementExample));
    // A fresh module has its own ApiError class, so the name is checked rather than instanceof.
    await expect(call).rejects.toMatchObject({ name: "ApiError", status: 403, message: "The workspace is read-only" });
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("saved clicks update their set in the store without reading the workspace again", async () => {
    const fetch = vi
      .fn<Fetch>()
      .mockResolvedValueOnce(jsonAnswer(workspaceExample))
      .mockResolvedValueOnce(jsonAnswer(clicksSummaryExample));
    vi.stubGlobal("fetch", fetch);
    const { refreshWorkspace, saveClicks, workspaceState } = await freshModule();
    await refreshWorkspace();

    const clicks = copy<ClicksFile>(clicksExample);
    expect(await saveClicks("cabinet", clicks)).toEqual(clicksSummaryExample);
    const [url, init] = fetch.mock.calls[1];
    expect(url).toBe(`${API_URL}/view-sets/cabinet/clicks`);
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual(clicksExample);
    expect(fetch).toHaveBeenCalledTimes(2);

    const state = workspaceState();
    if (state.status !== "ready") throw new Error(`state is ${state.status}`);
    expect(state.data.view_sets[0].clicks).toEqual(clicksSummaryExample);
    expect(state.data.view_sets[0].updated_at).toBe(clicksSummaryExample.saved_at);
  });

  it("asks for keepalive only while the browser accepts the body", async () => {
    const fetch = vi.fn<Fetch>().mockImplementation(async () => jsonAnswer(clicksSummaryExample));
    vi.stubGlobal("fetch", fetch);
    const { saveClicks } = await freshModule();
    const clicks = copy<ClicksFile>(clicksExample);

    await saveClicks("cabinet", clicks, { keepalive: true });
    expect(fetch.mock.calls[0][1]?.keepalive).toBe(true);

    const marked = Object.fromEntries(
      Array.from({ length: 200 }, (_, image) => [
        `frame_${String(image).padStart(6, "0")}.png`,
        Object.fromEntries(Array.from({ length: 20 }, (_, point) => [`point_${point}`, [512.25, 1024.75] as Pixel])),
      ]),
    );
    await saveClicks("cabinet", { ...clicks, views: marked }, { keepalive: true });
    expect(fetch.mock.calls[1][1]?.keepalive).toBe(false);
  });
});

/** Just enough of XMLHttpRequest to drive an upload from a test. */
class FakeXhr {
  static last: FakeXhr;
  upload: { onprogress?: (event: Partial<ProgressEvent>) => void; onload?: () => void } = {};
  onload?: () => void;
  onerror?: () => void;
  ontimeout?: () => void;
  timeout = 0;
  status = 0;
  statusText = "";
  responseText = "";
  method = "";
  url = "";
  body: FormData | null = null;

  constructor() {
    FakeXhr.last = this;
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  send(body: FormData) {
    this.body = body;
  }

  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total });
  }

  answer(status: number, body: unknown) {
    this.upload.onload?.();
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
}

describe("importViews", () => {
  it("uploads the files as a form, reports progress and reads the workspace again", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const fetch = vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer(workspaceExample));
    vi.stubGlobal("fetch", fetch);
    const { importViews, workspaceState } = await freshModule();

    const progress: number[] = [];
    const files = [new File(["png"], "view_0.png", { type: "image/png" }), new File(["png"], "view_1.png")];
    const call = importViews({ name: "cabinet-2", window: 10, files }, (fraction) => progress.push(fraction));
    const xhr = FakeXhr.last;
    expect([xhr.method, xhr.url, xhr.timeout]).toEqual(["POST", `${API_URL}/view-sets`, 600_000]);
    expect(xhr.body?.get("name")).toBe("cabinet-2");
    expect(xhr.body?.get("window")).toBe("10");
    expect(xhr.body?.getAll("files").map((file) => (file as File).name)).toEqual(["view_0.png", "view_1.png"]);

    xhr.progress(512, 1024);
    xhr.answer(201, viewSetSummaryExample);
    expect(await call).toEqual(viewSetSummaryExample);
    expect(progress).toEqual([0.5, 1]);
    expect(fetch).toHaveBeenCalledOnce();
    expect(workspaceState()).toMatchObject({ status: "ready", data: workspaceExample });
  });

  it("fails with the service's words, or with the fact that it cannot be reached", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const { importViews } = await freshModule();
    const input = { name: "cabinet", files: [new File(["png"], "view_0.png")] };

    const refused = importViews(input);
    expect(FakeXhr.last.body?.has("window")).toBe(false);
    FakeXhr.last.answer(409, { detail: "data/views/cabinet already exists" });
    await expect(refused).rejects.toMatchObject({ status: 409, message: "data/views/cabinet already exists" });

    const lost = importViews(input);
    FakeXhr.last.onerror?.();
    await expect(lost).rejects.toMatchObject({ status: null, message: UNREACHABLE });

    const slow = importViews(input);
    FakeXhr.last.ontimeout?.();
    await expect(slow).rejects.toMatchObject({ status: null, message: "No answer within 600 s" });
  });
});
