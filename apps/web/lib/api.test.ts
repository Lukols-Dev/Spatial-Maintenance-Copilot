import { afterEach, describe, expect, it, vi } from "vitest";

import { API_URL, ApiError, apiJson, errorMessage, imageUrl } from "./api";

function jsonAnswer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

/** fetch answering with this, or failing with it. */
function stubFetch(result: Response | Error) {
  const fetch = vi.fn<Fetch>(async () => {
    if (result instanceof Error) throw result;
    return result;
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

/** fetch that never answers, and fails the way fetch does when its signal aborts. */
function stubSilentService() {
  const fetch = vi.fn<Fetch>(
    (_url, init) =>
      new Promise((_, reject) => {
        init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
      }),
  );
  vi.stubGlobal("fetch", fetch);
}

/** How a call failed, as the page would say it. */
async function failure(call: Promise<unknown>): Promise<{ status: number | null; message: string }> {
  const error = await call.then(
    () => {
      throw new Error("the call succeeded");
    },
    (reason: unknown) => reason,
  );
  if (!(error instanceof ApiError)) throw error;
  return { status: error.status, message: errorMessage(error) };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("errorMessage", () => {
  it("gives the service's own words when detail is a string", async () => {
    stubFetch(jsonAnswer(409, { detail: "Board rig_board_a is not measured" }));
    expect(await failure(apiJson("/atlases"))).toEqual({ status: 409, message: "Board rig_board_a is not measured" });
  });

  it("turns a validation list into field: problem, one after the other", async () => {
    stubFetch(
      jsonAnswer(422, {
        detail: [
          { type: "greater_than", loc: ["body", "square_measured_mm"], msg: "Input should be greater than 0", input: -1 },
          {
            type: "value_error",
            loc: ["body"],
            msg: "Value error, marker_measured_mm must be smaller than square_measured_mm",
            input: {},
          },
          { type: "greater_than", loc: ["body", "target_extent_mm", 2], msg: "Input should be greater than 0", input: 0 },
        ],
      }),
    );
    expect(await failure(apiJson("/boards/rig_board_a/measurement"))).toEqual({
      status: 422,
      message:
        "square_measured_mm: Input should be greater than 0; " +
        "marker_measured_mm must be smaller than square_measured_mm; " +
        "target_extent_mm[2]: Input should be greater than 0",
    });
  });

  it("falls back to the HTTP status when the body explains nothing", async () => {
    stubFetch(new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway" }));
    expect(await failure(apiJson("/workspace"))).toEqual({ status: 502, message: "HTTP 502 Bad Gateway" });

    stubFetch(jsonAnswer(500, { detail: [] }));
    expect(await failure(apiJson("/workspace"))).toEqual({ status: 500, message: "HTTP 500" });
  });

  it("says the service cannot be reached when the connection fails", async () => {
    stubFetch(new TypeError("fetch failed"));
    expect(await failure(apiJson("/workspace"))).toEqual({
      status: null,
      message: `Cannot reach the perception service at ${API_URL}`,
    });
  });

  it("says how long it waited for a service that does not answer", async () => {
    stubSilentService();
    expect(await failure(apiJson("/workspace", { timeoutMs: 50 }))).toEqual({
      status: null,
      message: "No answer within 0.05 s",
    });
  });

  it("words anything else that was thrown", () => {
    expect(errorMessage(new Error("boom"))).toBe("boom");
    expect(errorMessage("plain text")).toBe("plain text");
  });
});

describe("apiJson", () => {
  it("calls the service under API_URL and returns the parsed answer", async () => {
    const fetch = stubFetch(jsonAnswer(200, { status: "ok" }));
    expect(await apiJson("/health", { cache: "no-store" })).toEqual({ status: "ok" });
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe(`${API_URL}/health`);
    expect(fetch.mock.calls[0][1]).toMatchObject({ cache: "no-store" });
  });

  it("refuses an answer that is not JSON", async () => {
    stubFetch(new Response("<html></html>", { status: 200 }));
    expect(await failure(apiJson("/workspace"))).toEqual({
      status: 200,
      message: `The answer from ${API_URL}/workspace is not JSON`,
    });
  });

  it("leaves the caller's own abort an abort, not a failure to show", async () => {
    stubSilentService();
    const controller = new AbortController();
    const call = apiJson("/view-sets/cabinet/clicks", { method: "PUT", signal: controller.signal });
    controller.abort();
    await expect(call).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("API_URL", () => {
  it("drops trailing slashes and spaces, and falls back to the local service", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", " https://api.example.com// ");
    vi.resetModules();
    expect((await import("./api")).API_URL).toBe("https://api.example.com");

    vi.stubEnv("NEXT_PUBLIC_API_URL", "  ");
    vi.resetModules();
    expect((await import("./api")).API_URL).toBe("http://localhost:8000");
  });
});

describe("imageUrl", () => {
  it("encodes the set and the file name separately", () => {
    expect(imageUrl("cabinet 2", "view #1.png")).toBe(`${API_URL}/view-sets/cabinet%202/images/view%20%231.png`);
  });
});
