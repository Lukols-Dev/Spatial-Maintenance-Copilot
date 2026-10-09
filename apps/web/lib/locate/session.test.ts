import { describe, expect, it, vi } from "vitest";

import failureExample from "../api-examples/localise-result-failure.json";
import reliableExample from "../api-examples/localise-result-reliable.json";
import moveExample from "../api-examples/localise-result.json";
import { ApiError } from "../api";
import { createSession, IDLE, type SessionRequest } from "./session";
import { createTraceStore, traceKey, type StorageLike } from "./trace";
import type { LocaliseResult } from "./types";

function result(example: unknown): LocaliseResult {
  return structuredClone(example) as LocaliseResult;
}

class MemoryStorage implements StorageLike {
  readonly items = new Map<string, string>();
  getItem(key: string) {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.items.set(key, value);
  }
  removeItem(key: string) {
    this.items.delete(key);
  }
}

const KEY = traceKey("home-cabinet", "2026-10-06T16:05:40+02:00", "cabinet-test");
const OTHER = traceKey("home-cabinet", "2026-10-06T16:05:40+02:00", "cabinet");

function request(view: string, truth_view: string | null = null): SessionRequest {
  return { asset_id: "home-cabinet", view_set: "cabinet-test", view, truth_view };
}

/** A session whose calls to the service wait until the test answers them. */
function setup() {
  const storage = new MemoryStorage();
  const traces = createTraceStore(() => storage);
  const calls: (PromiseWithResolvers<LocaliseResult> & { body: SessionRequest; signal: AbortSignal })[] = [];
  let second = 0;
  const session = createSession({
    localise(body, { signal }) {
      const call = { ...Promise.withResolvers<LocaliseResult>(), body, signal };
      calls.push(call);
      return call.promise;
    },
    traces,
    now: () => `2026-10-09T10:00:0${second++}Z`,
  });
  return { session, traces, storage, calls };
}

/** Every promise callback has run. */
function settle() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("the session", () => {
  it("shows a request on its way, then its answer as the next step of the trace", async () => {
    const { session, traces, calls } = setup();
    const listener = vi.fn();
    session.subscribe(listener);
    expect(session.shown(KEY)).toBe(IDLE);

    session.run(KEY, request("frame_000010.png"));
    expect(session.shown(KEY)).toEqual({ status: "running", request: request("frame_000010.png") });
    expect(calls.map((call) => call.body)).toEqual([request("frame_000010.png")]);
    calls[0].resolve(result(moveExample));
    await settle();

    const shown = session.shown(KEY);
    if (shown.status !== "shown") throw new Error(`shown is ${shown.status}`);
    expect(shown.step).toEqual({
      n: 1,
      at: "2026-10-09T10:00:00Z",
      view: "frame_000010.png",
      truthView: null,
      result: result(moveExample),
    });
    expect(traces.steps(KEY)).toEqual([shown.step]);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("keeps the truth view asked for with the step", async () => {
    const { session, traces, calls } = setup();
    session.run(KEY, request("frame_000040.png", "frame_000040.png"));
    calls[0].resolve(result(reliableExample));
    await settle();
    expect(traces.steps(KEY)[0].truthView).toBe("frame_000040.png");
  });

  it("never lets a slow answer replace a newer request", async () => {
    const { session, traces, calls } = setup();
    session.run(KEY, request("frame_000010.png"));
    session.run(KEY, request("frame_000040.png", "frame_000040.png"));
    expect(calls[0].signal.aborted).toBe(true);

    calls[1].resolve(result(reliableExample));
    await settle();
    calls[0].resolve(result(moveExample));
    await settle();
    expect(traces.steps(KEY).map((step) => step.view)).toEqual(["frame_000040.png"]);
    expect(session.shown(KEY)).toMatchObject({ status: "shown", step: { n: 1, view: "frame_000040.png" } });
  });

  it("says why there is no answer, and a retry asks again", async () => {
    const { session, traces, calls } = setup();
    session.run(KEY, request("frame_000070.png"));
    calls[0].reject(new ApiError(null, "Cannot reach the perception service at http://localhost:8000"));
    await settle();
    expect(session.shown(KEY)).toEqual({
      status: "failed",
      request: request("frame_000070.png"),
      message: "Cannot reach the perception service at http://localhost:8000",
    });
    expect(traces.steps(KEY)).toEqual([]);

    session.run(KEY, request("frame_000070.png"));
    calls[1].resolve(result(failureExample));
    await settle();
    expect(session.shown(KEY)).toMatchObject({ status: "shown", step: { n: 1, view: "frame_000070.png" } });
  });

  it("shows a step again without asking the service, and drops a request on its way", async () => {
    const { session, traces, calls } = setup();
    session.run(KEY, request("frame_000010.png"));
    calls[0].resolve(result(moveExample));
    await settle();
    const [first] = traces.steps(KEY);

    session.run(KEY, request("frame_000040.png"));
    session.show(KEY, first);
    expect(calls[1].signal.aborted).toBe(true);
    expect(session.shown(KEY)).toEqual({ status: "shown", step: first });
    calls[1].resolve(result(reliableExample));
    await settle();
    expect(session.shown(KEY)).toEqual({ status: "shown", step: first });
    expect(traces.steps(KEY)).toHaveLength(1);
    expect(calls).toHaveLength(2);
  });

  it("shows nothing once its request is dropped", async () => {
    const { session, calls } = setup();
    session.run(KEY, request("frame_000010.png"));
    session.cancel();
    expect(calls[0].signal.aborted).toBe(true);
    calls[0].resolve(result(moveExample));
    await settle();
    expect(session.shown(KEY)).toBe(IDLE);
  });

  it("is on one trace at a time: another trace drops the request of the first", async () => {
    const { session, traces, calls } = setup();
    session.run(KEY, request("frame_000010.png"));
    expect(session.shown(OTHER)).toBe(IDLE);
    session.run(OTHER, { ...request("frame_000000.png"), view_set: "cabinet" });
    expect(calls[0].signal.aborted).toBe(true);
    expect(session.shown(KEY)).toBe(IDLE);

    calls[1].resolve(result(reliableExample));
    calls[0].resolve(result(moveExample));
    await settle();
    expect(traces.steps(KEY)).toEqual([]);
    expect(traces.steps(OTHER)).toHaveLength(1);
  });
});
