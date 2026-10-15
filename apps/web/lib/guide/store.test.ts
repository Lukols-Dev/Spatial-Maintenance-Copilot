import { describe, expect, it, vi } from "vitest";

import approvalExample from "../api-examples/session-turn-approval.json";
import acceptedExample from "../api-examples/session-turn-accepted.json";
import moveTurnExample from "../api-examples/session-turn-move.json";
import inspectExample from "../api-examples/inspect-answer.json";
import openExample from "../api-examples/frame-answer-open.json";
import moveExample from "../api-examples/frame-answer-move.json";
import reliableExample from "../api-examples/frame-answer.json";
import type { SessionTurn } from "../agent/types";
import { IN_SIGHT } from "./moves";
import { AGENT_GAP_MS, LIVE, createGuideStore, type FrameSource, type GuideCalls, type GuideStore } from "./store";
import type { FrameAnswer, InspectAnswer } from "./types";

const clone = <T>(value: unknown) => structuredClone(value) as T;
const SIZE = { width: 1080, height: 1920 };
const QUERY = { asset_id: "home-cabinet", camera_id: "phone-1x-portrait" };

/** A source of `count` frames of the given size, then the end: a video file unless `live`. */
function source(count: number, size = SIZE, live = false): FrameSource & { stopped: boolean } {
  let left = count;
  return {
    stopped: false,
    live,
    size: () => size,
    next: async () => (left-- > 0 ? new Blob(["frame"], { type: "image/jpeg" }) : null),
    stop() {
      this.stopped = true;
    },
  };
}

function calls(frames: FrameAnswer[], turns: Partial<Record<"start" | "choose" | "approve", SessionTurn>> = {}) {
  let index = 0;
  return {
    postFrame: vi.fn<GuideCalls["postFrame"]>(async () => frames[Math.min(index++, frames.length - 1)]),
    inspect: vi.fn<GuideCalls["inspect"]>(async () => clone<InspectAnswer>(inspectExample)),
    start: vi.fn<GuideCalls["start"]>(async () => turns.start ?? clone<SessionTurn>(moveTurnExample)),
    choose: vi.fn<GuideCalls["choose"]>(async () => turns.choose ?? clone<SessionTurn>(approvalExample)),
    approve: vi.fn<GuideCalls["approve"]>(async () => turns.approve ?? clone<SessionTurn>(acceptedExample)),
  } satisfies GuideCalls;
}

async function settle(store: GuideStore) {
  for (let i = 0; i < 50 && store.state().phase === "running"; i += 1) await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("the frames of a source", () => {
  it("are localised one by one until the source ends, the last answer shown", async () => {
    const service = calls([clone(moveExample), clone(reliableExample)]);
    const store = createGuideStore({ calls: service, now: () => 0 });

    store.start(source(2), QUERY, SIZE);
    await settle(store);

    expect(service.postFrame).toHaveBeenCalledTimes(2);
    expect(service.postFrame.mock.calls[0][1]).toEqual(QUERY);
    expect(store.state()).toMatchObject({ phase: "ended", frames: 2, failure: null });
    expect(store.state().frame?.frame_id).toBe("a1b2c3d4e5f6");
  });

  it("stop at a frame of another size than the camera's calibration, and say so", async () => {
    const service = calls([clone(reliableExample)]);
    const store = createGuideStore({ calls: service, now: () => 0 });
    const frames = source(3, { width: 640, height: 480 });

    store.start(frames, QUERY, SIZE);
    await settle(store);

    expect(service.postFrame).not.toHaveBeenCalled();
    expect(store.state().phase).toBe("failed");
    expect(store.state().failure).toBe(
      "The frames are 640 × 480 px; phone-1x-portrait was calibrated at 1080 × 1920 px",
    );
    expect(frames.stopped).toBe(true);
  });

  it("send nothing while a camera is held sideways, say so, and go on once it is upright", async () => {
    const service = calls([clone(reliableExample)]);
    const store = createGuideStore({ calls: service, now: () => 0, wait: async () => {} });
    const sideways = { width: 1920, height: 1080 };
    const sizes = [sideways, sideways, SIZE, SIZE];
    let shown = SIZE;
    const seen: (typeof sideways | null)[] = [];
    const camera: FrameSource = {
      live: true,
      size: () => shown,
      next: async () => {
        seen.push(store.state().sideways);
        const next = sizes.shift();
        if (!next) return null;
        shown = next;
        return new Blob(["frame"]);
      },
      stop() {},
    };

    store.start(camera, QUERY, SIZE);
    await settle(store);

    expect(service.postFrame).toHaveBeenCalledTimes(2);
    // Asked for the third frame while sideways, for the end once upright again.
    expect(seen).toEqual([null, sideways, sideways, null, null]);
    expect(store.state()).toMatchObject({ phase: "ended", failure: null, sideways: null, frames: 2 });
  });

  it("stop at a video file of turned frames: its size will not change", async () => {
    const service = calls([clone(reliableExample)]);
    const store = createGuideStore({ calls: service, now: () => 0, wait: async () => {} });

    store.start(source(3, { width: 1920, height: 1080 }), QUERY, SIZE);
    await settle(store);

    expect(service.postFrame).not.toHaveBeenCalled();
    expect(store.state().failure).toBe(
      "The frames are 1920 × 1080 px; phone-1x-portrait was calibrated at 1080 × 1920 px",
    );
  });

  it("stop at a camera of another size than the calibration turned: no way of holding it fits", async () => {
    const service = calls([clone(reliableExample)]);
    const store = createGuideStore({ calls: service, now: () => 0, wait: async () => {} });

    store.start(source(3, { width: 640, height: 480 }, true), QUERY, SIZE);
    await settle(store);

    expect(store.state().phase).toBe("failed");
    expect(service.postFrame).not.toHaveBeenCalled();
  });

  it("stop when the service refuses a frame, with its words", async () => {
    const service = calls([]);
    service.postFrame.mockRejectedValue(new Error("calib/rig.yaml names no printed markers"));
    const store = createGuideStore({ calls: service, now: () => 0 });

    store.start(source(3), QUERY, SIZE);
    await settle(store);

    expect(store.state()).toMatchObject({ phase: "failed", failure: "calib/rig.yaml names no printed markers" });
  });
});

describe("the agent on the frames", () => {
  it("starts a session on the frame that made a decision steady", async () => {
    const service = calls([clone(moveExample)]);
    const store = createGuideStore({ calls: service, now: () => 0 });

    store.start(source(3), QUERY, SIZE);
    await settle(store);

    expect(store.state().steady).toBe("MOVE_DOWN");
    expect(service.start).toHaveBeenCalledTimes(1);
    expect(service.start.mock.calls[0][0]).toEqual({ asset_id: "home-cabinet", view_set: LIVE, view: "0f1e2d3c4b5a" });
    expect(store.state().agent.turn?.awaiting?.kind).toBe("view");
  });

  it("is told of a new steady decision with the operator's frame, no sooner than its gap", async () => {
    let clock = 0;
    const frames = [...Array(3).fill(clone(moveExample)), ...Array(6).fill(clone(reliableExample))];
    const service = calls(frames);
    const store = createGuideStore({ calls: service, now: () => clock });
    const slow: FrameSource = {
      live: true,
      size: () => SIZE,
      next: async () => {
        clock += AGENT_GAP_MS / 2;
        return frames.length > 0 ? new Blob(["f"]) : null;
      },
      stop() {},
    };
    let left = 9;
    store.start({ ...slow, next: async (signal) => (left-- > 0 ? slow.next(signal) : null) }, QUERY, SIZE);
    await settle(store);

    expect(service.start).toHaveBeenCalledTimes(1);
    expect(service.choose).toHaveBeenCalledTimes(1);
    expect(service.choose.mock.calls[0][1]).toBe("a1b2c3d4e5f6");
    expect(store.state().agent.turn?.awaiting?.kind).toBe("approval");
  });

  it("asks nothing more once the operator answered, and confirms the target with a second opinion", async () => {
    const service = calls([clone(reliableExample)], { start: clone(approvalExample) });
    const store = createGuideStore({ calls: service, now: () => 0 });
    store.start(source(3), QUERY, SIZE);
    await settle(store);
    expect(store.state().agent.turn?.awaiting?.kind).toBe("approval");

    store.answer(true);
    await new Promise((r) => setTimeout(r, 0));
    expect(service.approve).toHaveBeenCalledWith(expect.any(String), true, expect.anything());
    expect(store.state().agent.turn?.outcome).toBe("accepted");

    service.postFrame.mockResolvedValue(clone(openExample));
    store.start(source(1), QUERY, SIZE);
    await settle(store);
    // A new start is a new session: what was approved before does not carry over.
    expect(store.state().approved).toBeNull();
  });

  it("checks the open panel's tag only after approval, and asks the vision model once", async () => {
    const service = calls([clone(reliableExample)], { start: clone(approvalExample) });
    const store = createGuideStore({ calls: service, now: () => 0 });
    let opened = false;
    let left = 8;
    store.start(
      {
        live: true,
        size: () => SIZE,
        next: async () => {
          await new Promise((r) => setTimeout(r, 0));
          if (store.state().agent.turn?.awaiting?.kind === "approval" && store.state().approved === null) {
            store.answer(true);
            opened = true;
          }
          return left-- > 0 ? new Blob(["f"]) : null;
        },
        stop() {},
      },
      QUERY,
      SIZE,
    );
    service.postFrame.mockImplementation(async () => clone(opened ? openExample : reliableExample));
    await settle(store);

    expect(store.state().approved).toBe(true);
    expect(store.state().confirmed?.inside_95).toBe(true);
    expect(service.inspect).toHaveBeenCalledTimes(1);
    expect(store.state().second.answer?.verdict).toBe("yes");
  });
});

describe("the target in sight", () => {
  /** The open panel's frame as the policy refuses it: the tag found, a move still decided. */
  const refusedOpen = (): FrameAnswer => ({
    ...clone<FrameAnswer>(openExample),
    decision: clone<FrameAnswer>(moveExample).decision,
  });

  it("takes the move's place once its tag has held, the agent told nothing from the first frame with it", async () => {
    let clock = 0;
    const frames = [...Array(3).fill(clone(moveExample)), ...Array(4).fill(refusedOpen())];
    const service = calls(frames);
    const store = createGuideStore({ calls: service, now: () => (clock += AGENT_GAP_MS) });

    store.start(source(frames.length), QUERY, SIZE);
    await settle(store);

    // The steady move started a session; the frames with the tag asked nothing, though the policy still moves.
    expect(service.start).toHaveBeenCalledTimes(1);
    expect(service.choose).not.toHaveBeenCalled();
    expect(store.state().steady).toBe(IN_SIGHT);
    expect(store.state().sighted?.sighting?.inside_95).toBe(true);
  });

  it("holds through a frame or two without the tag, the last frame with it kept, until a move holds", async () => {
    const frames = [refusedOpen(), refusedOpen(), refusedOpen(), clone<FrameAnswer>(moveExample)];
    async function after(count: number) {
      const store = createGuideStore({ calls: calls(frames), now: () => 0 });
      store.start(source(count), QUERY, SIZE);
      await settle(store);
      return store.state();
    }

    expect(await after(5)).toMatchObject({ steady: IN_SIGHT, sighted: { sighting: { inside_95: true } } });
    expect(await after(6)).toMatchObject({ steady: "MOVE_DOWN", sighted: null });
  });
});
