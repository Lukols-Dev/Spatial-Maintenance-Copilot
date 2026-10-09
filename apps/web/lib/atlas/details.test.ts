import { afterEach, describe, expect, it, vi } from "vitest";

import { API_URL } from "../api";
import atlasExample from "../api-examples/atlas.json";
import type { AtlasDetail } from "../workspace";

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

const SUMMARY = { asset_id: "home-cabinet", built_at: "2026-10-06T14:25:03+02:00" };
const LATER = { ...SUMMARY, built_at: "2026-10-07T09:00:00+02:00" };

function jsonAnswer(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function detail(version = "1"): AtlasDetail {
  const copy = structuredClone(atlasExample) as unknown as AtlasDetail;
  copy.atlas.version = version;
  return copy;
}

/** The module as on a fresh page: nothing read yet. */
async function freshModule() {
  vi.resetModules();
  return import("./details");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the atlases read", () => {
  it("reads an atlas once per build time, and keeps it on screen while a newer build is read", async () => {
    const newer = Promise.withResolvers<Response>();
    const fetch = vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer(detail("1"))).mockReturnValueOnce(newer.promise);
    vi.stubGlobal("fetch", fetch);
    const { atlasRead, readAtlas, readAtlases } = await freshModule();

    readAtlas(SUMMARY);
    expect(atlasRead("home-cabinet")).toEqual({ status: "loading" });
    expect(fetch.mock.calls[0][0]).toBe(`${API_URL}/atlases/home-cabinet`);
    await vi.waitFor(() => expect(atlasRead("home-cabinet")?.status).toBe("ready"));
    // The same time, however the service writes it: not read again.
    readAtlas(SUMMARY);
    readAtlas({ ...SUMMARY, built_at: "2026-10-06T12:25:03Z" });
    expect(fetch).toHaveBeenCalledOnce();

    readAtlas(LATER);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(atlasRead("home-cabinet")).toEqual({ status: "ready", detail: detail("1") });
    newer.resolve(jsonAnswer(detail("2")));
    await vi.waitFor(() => expect(readAtlases().map((read) => read.atlas.version)).toEqual(["2"]));
  });

  it("keeps a failed read failed until Retry", async () => {
    const fetch = vi
      .fn<Fetch>()
      .mockResolvedValueOnce(jsonAnswer({ detail: "data/atlas/home-cabinet.json is not an atlas" }, 409))
      .mockResolvedValueOnce(jsonAnswer(detail()));
    vi.stubGlobal("fetch", fetch);
    const { atlasRead, readAtlas } = await freshModule();

    readAtlas(SUMMARY);
    await vi.waitFor(() =>
      expect(atlasRead("home-cabinet")).toEqual({ status: "error", message: "data/atlas/home-cabinet.json is not an atlas" }),
    );
    readAtlas(SUMMARY);
    expect(fetch).toHaveBeenCalledOnce();
    readAtlas(SUMMARY, true);
    expect(atlasRead("home-cabinet")).toEqual({ status: "loading" });
    await vi.waitFor(() => expect(atlasRead("home-cabinet")?.status).toBe("ready"));
  });

  it("does not let an older answer replace a newer one", async () => {
    const older = Promise.withResolvers<Response>();
    const fetch = vi.fn<Fetch>().mockReturnValueOnce(older.promise).mockResolvedValueOnce(jsonAnswer(detail("2")));
    vi.stubGlobal("fetch", fetch);
    const { atlasRead, readAtlas } = await freshModule();

    readAtlas(SUMMARY);
    readAtlas(LATER);
    await vi.waitFor(() => expect(atlasRead("home-cabinet")?.status).toBe("ready"));
    older.resolve(jsonAnswer(detail("1")));
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(atlasRead("home-cabinet")).toEqual({ status: "ready", detail: detail("2") });
  });

  it("shows a build's answer as it came, and reads nothing while the build runs", async () => {
    const fetch = vi.fn<Fetch>();
    vi.stubGlobal("fetch", fetch);
    const { atlasRead, buildingAtlas, readAtlas, rememberAtlas } = await freshModule();

    buildingAtlas("home-cabinet");
    readAtlas(SUMMARY);
    expect(fetch).not.toHaveBeenCalled();
    rememberAtlas(detail());
    expect(atlasRead("home-cabinet")).toEqual({ status: "ready", detail: detail() });
    // The workspace then lists the atlas with the build's time: nothing to read.
    readAtlas(SUMMARY);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps what was read before a build that failed", async () => {
    vi.stubGlobal("fetch", vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer(detail())));
    const { atlasRead, buildFailed, buildingAtlas, readAtlas } = await freshModule();

    readAtlas(SUMMARY);
    await vi.waitFor(() => expect(atlasRead("home-cabinet")?.status).toBe("ready"));
    buildingAtlas("home-cabinet");
    buildFailed("home-cabinet");
    expect(atlasRead("home-cabinet")).toEqual({ status: "ready", detail: detail() });

    buildingAtlas("cabinet-2");
    buildFailed("cabinet-2");
    expect(atlasRead("cabinet-2")).toBeUndefined();
  });
});
