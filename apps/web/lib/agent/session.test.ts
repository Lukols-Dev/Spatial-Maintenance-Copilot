import { describe, expect, it } from "vitest";

import acceptedExample from "../api-examples/session-turn-accepted.json";
import approvalExample from "../api-examples/session-turn-approval.json";
import moveExample from "../api-examples/session-turn-move.json";
import type { StorageLike } from "../locate/trace";
import type { Viewpoint } from "../locate/viewpoints";
import {
  NO_SESSION,
  agentViewpoints,
  applyAnswer,
  readSessionId,
  sessionKey,
  viewpointAction,
  writeSessionId,
} from "./session";
import type { SessionTurn, Turn } from "./types";

function answer(example: unknown): SessionTurn {
  return structuredClone(example) as SessionTurn;
}

const MOVE = answer(moveExample);
const APPROVAL = answer(approvalExample);
const ACCEPTED = answer(acceptedExample);
const ID = "5d7c0a3e9b6f4c21a8e04f6b2d913c57";

describe("applying an answer", () => {
  it("starts a session with the turn's events and the localisation it showed", () => {
    const state = applyAnswer(NO_SESSION, MOVE, "2026-10-13T10:00:00Z", "start");

    expect(state.sessionId).toBe(ID);
    expect(state.turn).toEqual(MOVE.turn);
    expect(state.model).toBe("anthropic.claude-opus-5-5 (eu-central-1)");
    expect(state.events.map((event) => event.kind)).toEqual(["perception", "decision", "tool", "agent"]);
    expect(state.steps).toEqual([
      { n: 1, at: "2026-10-13T10:00:00Z", view: "B_close.png", truthView: null, result: MOVE.result },
    ]);
  });

  it("continues with the next turn's events after the ones before, and its localisation as the next step", () => {
    const started = applyAnswer(NO_SESSION, MOVE, "2026-10-13T10:00:00Z", "start");

    const state = applyAnswer(started, APPROVAL, "2026-10-13T10:00:05Z", "continue");

    expect(state.events.map((event) => event.step)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(state.steps.map((step) => [step.n, step.view, step.truthView])).toEqual([
      [1, "B_close.png", null],
      [2, "A_close.png", "A_open.png"],
    ]);
  });

  it("adds no step for a turn that localised nothing, such as the operator's approval", () => {
    const started = applyAnswer(NO_SESSION, MOVE, "t1", "start");
    const approved = applyAnswer(applyAnswer(started, APPROVAL, "t2", "continue"), ACCEPTED, "t3", "continue");

    expect(approved.steps).toHaveLength(2);
    expect(approved.events.at(-1)?.kind).toBe("human");
    expect(approved.turn?.outcome).toBe("accepted");
  });

  it("resumes with the whole trace the service sends, and the localisation on screen", () => {
    const whole = answer(acceptedExample);
    whole.turn.events = [...MOVE.turn.events, ...APPROVAL.turn.events, ...ACCEPTED.turn.events];

    const state = applyAnswer(NO_SESSION, whole, "t", "resume");

    expect(state.events).toHaveLength(9);
    expect(state.steps.map((step) => step.view)).toEqual(["A_close.png"]);
  });

  it("starts afresh, whatever session came before", () => {
    const old = applyAnswer(NO_SESSION, APPROVAL, "t1", "start");

    const state = applyAnswer(old, MOVE, "t2", "start");

    expect(state.events).toEqual(MOVE.turn.events);
    expect(state.steps).toHaveLength(1);
  });
});

describe("the viewpoints of a session", () => {
  const viewpoint = (file: string, truth: boolean): Viewpoint => ({ file, landmarks: 4, truth, width: 1080, height: 1920 });

  it("are the views with the target hidden", () => {
    const views = [viewpoint("A_close.png", false), viewpoint("A_open.png", true), viewpoint("B_close.png", false)];

    expect(agentViewpoints(views).map((view) => view.file)).toEqual(["A_close.png", "B_close.png"]);
  });

  it("start a session, answer the agent's request for a view, or wait", () => {
    const turn = (patch: Partial<Turn>): Turn => ({ ...MOVE.turn, ...patch });

    expect(viewpointAction(null)).toBe("start");
    expect(viewpointAction(MOVE.turn)).toBe("choose");
    expect(viewpointAction(APPROVAL.turn)).toBeNull();
    expect(viewpointAction(turn({ awaiting: null, outcome: "declined" }))).toBe("start");
  });
});

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

describe("the stored session id", () => {
  const KEY = sessionKey("home-cabinet", "2026-10-13T09:00:00+02:00", "cabinet-agent");

  it("is kept per atlas build and view set", () => {
    expect(KEY).toBe("smc-agent:session:v1:home-cabinet@2026-10-13T09:00:00+02:00/cabinet-agent");
  });

  it("is written, read back and removed", () => {
    const storage = new MemoryStorage();

    writeSessionId(storage, KEY, ID);
    expect(readSessionId(storage, KEY)).toBe(ID);
    writeSessionId(storage, KEY, null);
    expect(readSessionId(storage, KEY)).toBeNull();
  });

  it("is only ever a session id the service made", () => {
    const storage = new MemoryStorage();
    storage.setItem(KEY, "../../atlases/home-cabinet");

    expect(readSessionId(storage, KEY)).toBeNull();
  });

  it("is lost, not an error, where the browser blocks the storage", () => {
    const blocked: StorageLike = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };

    expect(readSessionId(blocked, KEY)).toBeNull();
    expect(() => writeSessionId(blocked, KEY, ID)).not.toThrow();
    expect(readSessionId(null, KEY)).toBeNull();
  });
});
