import { afterEach, describe, expect, it, vi } from "vitest";

import requestExample from "../api-examples/localise-request.json";
import resultExample from "../api-examples/localise-result.json";
import { API_URL } from "../api";
import { LOCALISE_TIMEOUT_MS, latestOnly, localise, thumbnailUrl } from "./api";
import type { LocaliseRequest } from "./types";

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

function jsonAnswer(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("localise", () => {
  it("posts the request as JSON and gives the answer", async () => {
    const fetch = vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer(resultExample));
    vi.stubGlobal("fetch", fetch);
    const body = structuredClone(requestExample) as LocaliseRequest;
    expect(await localise(body)).toEqual(resultExample);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe(`${API_URL}/localise`);
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual(requestExample);
  });

  it("leaves the cache mode alone, so the browser keeps the CORS preflight it was given", async () => {
    const fetch = vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer(resultExample));
    vi.stubGlobal("fetch", fetch);
    await localise(structuredClone(requestExample) as LocaliseRequest);
    expect(fetch.mock.calls[0][1]?.cache).toBeUndefined();
  });

  it("waits two minutes for the answer", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    vi.stubGlobal("fetch", vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer(resultExample)));
    await localise(structuredClone(requestExample) as LocaliseRequest);
    expect(LOCALISE_TIMEOUT_MS).toBe(120_000);
    expect(timeout).toHaveBeenCalledWith(120_000);
  });

  it("fails with the service's words", async () => {
    vi.stubGlobal("fetch", vi.fn<Fetch>().mockResolvedValueOnce(jsonAnswer({ detail: "no clicks in frame_000099.png" }, 409)));
    await expect(localise(structuredClone(requestExample) as LocaliseRequest)).rejects.toMatchObject({
      status: 409,
      message: "no clicks in frame_000099.png",
    });
  });
});

describe("thumbnailUrl", () => {
  it("asks the service for the image scaled to a width", () => {
    expect(thumbnailUrl("cabinet test", "frame 1.png")).toBe(
      `${API_URL}/view-sets/cabinet%20test/images/frame%201.png?width=240`,
    );
    expect(thumbnailUrl("cabinet-test", "frame_000010.png", 96)).toBe(
      `${API_URL}/view-sets/cabinet-test/images/frame_000010.png?width=96`,
    );
  });
});

describe("latestOnly", () => {
  it("drops a slow answer once a newer call has started, and aborts it", async () => {
    const latest = latestOnly();
    const slow = Promise.withResolvers<string>();
    const fast = Promise.withResolvers<string>();
    let slowSignal: AbortSignal | undefined;
    const first = latest.run((signal) => {
      slowSignal = signal;
      return slow.promise;
    });
    const second = latest.run(() => fast.promise);
    expect(slowSignal?.aborted).toBe(true);

    fast.resolve("frame_000040.png");
    expect(await second).toEqual({ ok: true, value: "frame_000040.png" });
    slow.resolve("frame_000010.png");
    expect(await first).toBeNull();
  });

  it("drops the older answer even when it comes first", async () => {
    const latest = latestOnly();
    const slow = Promise.withResolvers<string>();
    const first = latest.run(() => Promise.resolve("old"));
    const second = latest.run(() => slow.promise);
    expect(await first).toBeNull();
    slow.resolve("new");
    expect(await second).toEqual({ ok: true, value: "new" });
  });

  it("gives the newest call's error", async () => {
    const latest = latestOnly();
    const error = new Error("Cannot reach the perception service");
    expect(await latest.run(() => Promise.reject(error))).toEqual({ ok: false, error });
  });

  it("drops a cancelled call", async () => {
    const latest = latestOnly();
    const pending = Promise.withResolvers<string>();
    let seen: AbortSignal | undefined;
    const run = latest.run((signal) => {
      seen = signal;
      return pending.promise;
    });
    latest.cancel();
    expect(seen?.aborted).toBe(true);
    pending.resolve("late");
    expect(await run).toBeNull();
  });
});
