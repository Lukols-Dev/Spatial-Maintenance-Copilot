import { describe, expect, it, vi } from "vitest";

import acceptedExample from "../api-examples/session-turn-accepted.json";
import approvalExample from "../api-examples/session-turn-approval.json";
import moveExample from "../api-examples/session-turn-move.json";
import { ApiError } from "../api";
import type { StorageLike } from "../locate/trace";
import { sessionKey } from "./session";
import { NO_VIEW, createAgentStore, type AgentCalls } from "./store";
import type { SessionTurn } from "./types";

function answer(example: unknown): SessionTurn {
  return structuredClone(example) as SessionTurn;
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

const KEY = sessionKey("home-cabinet", "2026-10-13T09:00:00+02:00", "cabinet-agent");
const ID = "5d7c0a3e9b6f4c21a8e04f6b2d913c57";
const START = { kind: "start", asset: "home-cabinet", set: "cabinet-agent", view: "B_close.png" } as const;

type Call = PromiseWithResolvers<SessionTurn> & { name: string; args: unknown[]; signal: AbortSignal };

/** A store whose calls to the service wait until the test answers them. */
function setup() {
  const storage = new MemoryStorage();
  const calls: Call[] = [];
  function record(name: string) {
    return (...args: unknown[]) => {
      const { signal } = args.at(-1) as { signal: AbortSignal };
      const call = { ...Promise.withResolvers<SessionTurn>(), name, args: args.slice(0, -1), signal };
      calls.push(call);
      return call.promise;
    };
  }
  const store = createAgentStore({
    calls: {
      start: record("start"),
      choose: record("choose"),
      approve: record("approve"),
      get: record("get"),
    } as AgentCalls,
    storage: () => storage,
    now: () => "2026-10-13T10:00:00Z",
  });
  return { store, storage, calls };
}

function settle() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("the agent store", () => {
  it("starts a session: the call on its way, then its answer, and the id kept for a reload", async () => {
    const { store, storage, calls } = setup();
    const listener = vi.fn();
    store.subscribe(listener);
    expect(store.view(KEY)).toBe(NO_VIEW);

    store.run(KEY, START);
    expect(store.view(KEY).pending).toEqual(START);
    expect(calls.map((call) => [call.name, call.args])).toEqual([
      ["start", [{ asset_id: "home-cabinet", view_set: "cabinet-agent", view: "B_close.png" }]],
    ]);
    calls[0].resolve(answer(moveExample));
    await settle();

    const view = store.view(KEY);
    expect(view.pending).toBeNull();
    expect(view.session.sessionId).toBe(ID);
    expect(view.session.turn?.awaiting?.kind).toBe("view");
    expect(storage.getItem(KEY)).toBe(ID);
    expect(listener).toHaveBeenCalled();
  });

  it("answers the agent with the session's id, and adds the turn to the trace", async () => {
    const { store, calls } = setup();
    store.run(KEY, START);
    calls[0].resolve(answer(moveExample));
    await settle();

    store.run(KEY, { kind: "choose", view: "A_close.png" });
    expect(calls[1].name).toBe("choose");
    expect(calls[1].args).toEqual([ID, "A_close.png"]);
    calls[1].resolve(answer(approvalExample));
    await settle();
    store.run(KEY, { kind: "approve", approved: true });
    expect(calls[2].args).toEqual([ID, true]);
    calls[2].resolve(answer(acceptedExample));
    await settle();

    const { session } = store.view(KEY);
    expect(session.turn?.outcome).toBe("accepted");
    expect(session.events.map((event) => event.step)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect(session.steps.map((step) => step.view)).toEqual(["B_close.png", "A_close.png"]);
  });

  it("keeps the session when a call fails, with the reason and the call to try again", async () => {
    const { store, calls } = setup();
    store.run(KEY, START);
    calls[0].resolve(answer(moveExample));
    await settle();

    store.run(KEY, { kind: "choose", view: "A_close.png" });
    calls[1].reject(new ApiError(409, "session is not waiting for a view"));
    await settle();

    const view = store.view(KEY);
    expect(view.failure).toEqual({
      message: "session is not waiting for a view",
      action: { kind: "choose", view: "A_close.png" },
    });
    expect(view.session.turn?.awaiting?.kind).toBe("view");
    expect(view.pending).toBeNull();
  });

  it("reads back the session stored for the key, once", async () => {
    const { store, storage, calls } = setup();
    storage.setItem(KEY, ID);

    store.resume(KEY);
    store.resume(KEY);
    expect(calls.map((call) => [call.name, call.args])).toEqual([["get", [ID]]]);
    calls[0].resolve(answer(approvalExample));
    await settle();
    store.resume(KEY);

    expect(calls).toHaveLength(1);
    expect(store.view(KEY).session.turn?.awaiting?.kind).toBe("approval");
  });

  it("starts afresh, without an error, when the service no longer knows the session", async () => {
    const { store, storage, calls } = setup();
    storage.setItem(KEY, ID);

    store.resume(KEY);
    calls[0].reject(new ApiError(404, `no session '${ID}'`));
    await settle();

    expect(store.view(KEY)).toEqual(NO_VIEW);
    expect(storage.getItem(KEY)).toBeNull();
  });

  it("drops the answer of a call a newer one replaced", async () => {
    const { store, calls } = setup();

    store.run(KEY, START);
    store.run(KEY, { ...START, view: "C_close.png" });
    expect(calls[0].signal.aborted).toBe(true);
    calls[0].resolve(answer(approvalExample));
    calls[1].resolve(answer(moveExample));
    await settle();

    expect(store.view(KEY).session.turn).toEqual(answer(moveExample).turn);
  });

  it("forgets the session on reset, and the page left takes the call on its way with it", async () => {
    const { store, storage, calls } = setup();
    store.run(KEY, START);
    calls[0].resolve(answer(moveExample));
    await settle();

    store.run(KEY, { kind: "choose", view: "A_close.png" });
    store.cancel();
    expect(calls[1].signal.aborted).toBe(true);
    expect(store.view(KEY).pending).toBeNull();
    store.reset(KEY);

    expect(store.view(KEY)).toEqual(NO_VIEW);
    expect(storage.getItem(KEY)).toBeNull();
  });
});
