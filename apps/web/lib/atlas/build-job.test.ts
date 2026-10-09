import { afterEach, describe, expect, it, vi } from "vitest";

import { API_URL } from "../api";
import requestExample from "../api-examples/atlas-build-request.json";
import atlasExample from "../api-examples/atlas.json";
import workspaceExample from "../api-examples/workspace.json";
import type { AtlasBuildRequest } from "../workspace";

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

const REQUEST = requestExample as AtlasBuildRequest;

function jsonAnswer(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** The modules as on a fresh page: no build yet, nothing read. */
async function freshModules() {
  vi.resetModules();
  return { ...(await import("./build-job")), ...(await import("./details")) };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the build", () => {
  it("runs one build at a time, then shows the atlas it answered", async () => {
    const answer = Promise.withResolvers<Response>();
    const fetch = vi
      .fn<Fetch>()
      .mockReturnValueOnce(answer.promise)
      .mockResolvedValueOnce(jsonAnswer(workspaceExample));
    vi.stubGlobal("fetch", fetch);
    const { atlasRead, buildJob, startBuild } = await freshModules();

    expect(buildJob()).toEqual({ status: "idle" });
    const build = startBuild(REQUEST);
    expect(buildJob()).toMatchObject({ status: "building", request: REQUEST });
    expect(await startBuild(REQUEST)).toBeNull();
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe(`${API_URL}/atlases`);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(requestExample);

    answer.resolve(jsonAnswer(atlasExample, 201));
    expect(await build).toEqual(atlasExample);
    expect(buildJob()).toMatchObject({ status: "built", request: REQUEST, detail: atlasExample });
    // The workspace is read again, and the atlas is shown without reading it back.
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(atlasRead("home-cabinet")).toEqual({ status: "ready", detail: atlasExample });
  });

  it("keeps the service's words when it refuses", async () => {
    const refusal = "board 'rig_board_a' is not measured: square_measured_mm is null";
    vi.stubGlobal("fetch", vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer({ detail: refusal }, 409)));
    const { atlasRead, buildJob, startBuild } = await freshModules();

    expect(await startBuild(REQUEST)).toBeNull();
    expect(buildJob()).toEqual({ status: "failed", request: REQUEST, message: refusal, httpStatus: 409 });
    expect(atlasRead("home-cabinet")).toBeUndefined();
  });
});
