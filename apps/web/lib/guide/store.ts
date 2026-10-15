import type { SessionStart, SessionTurn, Turn } from "@/lib/agent/types";
import { errorMessage } from "@/lib/api";
import { IN_SIGHT, cueOf, type Cue } from "@/lib/guide/moves";
import { Steady } from "@/lib/guide/steady";
import type { FrameAnswer, FrameQuery, InspectAnswer, TargetSighting } from "@/lib/guide/types";

// The Guide page's loop, outside React: frames of a camera or a video go to
// the service one at a time, each answer is drawn, and its cue, once steady,
// is spoken: the decision's move, which the agent is handed, or the target in
// sight once the panel is open and its tag found, of which the agent is told
// nothing. The agent's session runs on the frames (view set "live"): it asks
// for the move, then for approval of the next step, opening the panel. Once
// approved, the target's tag in a frame confirms the prediction, and the
// vision model is asked for a second opinion, once.

/** The view set name of the frames, for the agent's session. */
export const LIVE = "live";
/** The agent is told of a new steady move at most this often: its model allows a few calls a minute. */
export const AGENT_GAP_MS = 4000;

/** Where frames come from: a camera, or a video stepped through. */
export interface FrameSource {
  /** The size of the frames, once known. */
  size(): { width: number; height: number } | null;
  /** The next frame to localise; null once the source has ended. */
  next(signal: AbortSignal): Promise<Blob | null>;
  stop(): void;
}

type Options = { signal: AbortSignal };

export interface GuideCalls {
  postFrame(image: Blob, query: FrameQuery, options: Options): Promise<FrameAnswer>;
  inspect(frameId: string, options: Options): Promise<InspectAnswer>;
  start(body: SessionStart, options: Options): Promise<SessionTurn>;
  choose(id: string, view: string, options: Options): Promise<SessionTurn>;
  approve(id: string, approved: boolean, options: Options): Promise<SessionTurn>;
}

export type Phase = "idle" | "running" | "ended" | "failed";

export interface GuideState {
  phase: Phase;
  /** Why the frames stopped; null when nothing failed. */
  failure: string | null;
  frame: FrameAnswer | null;
  frames: number;
  /** The cue that has held for a few frames: the decision's move, or the target in sight. */
  steady: Cue | null;
  /** The last frame the target's tag was found in, kept while the steady cue is the target in sight. */
  sighted: FrameAnswer | null;
  agent: { turn: Turn | null; model: string | null; busy: boolean; failure: string | null };
  /** The operator's answer to the agent's next step; null until given. */
  approved: boolean | null;
  /** The target's tag as last seen once the next step was approved. */
  confirmed: TargetSighting | null;
  second: { answer: InspectAnswer | null; busy: boolean; failure: string | null };
}

export const IDLE: GuideState = {
  phase: "idle",
  failure: null,
  frame: null,
  frames: 0,
  steady: null,
  sighted: null,
  agent: { turn: null, model: null, busy: false, failure: null },
  approved: null,
  confirmed: null,
  second: { answer: null, busy: false, failure: null },
};

export interface GuideStore {
  state(): GuideState;
  subscribe(listener: () => void): () => void;
  /** Localise the source's frames against the atlas; frames of another size than expected stop it. */
  start(source: FrameSource, query: FrameQuery, expected: { width: number; height: number }): void;
  stop(): void;
  /** The operator's answer to the next step the agent proposed. */
  answer(approved: boolean): void;
  /** Ask the vision model about the target's region of the latest frame. */
  inspect(): void;
}

export function createGuideStore({ calls, now }: { calls: GuideCalls; now: () => number }): GuideStore {
  let current = IDLE;
  const listeners = new Set<() => void>();
  let run = 0;
  let controller: AbortController | null = null;
  let source: FrameSource | null = null;
  let query: FrameQuery | null = null;
  let lastAgentAt = Number.NEGATIVE_INFINITY;
  const steady = new Steady();

  function set(change: Partial<GuideState>) {
    current = { ...current, ...change };
    listeners.forEach((listener) => listener());
  }

  function setAgent(change: Partial<GuideState["agent"]>) {
    set({ agent: { ...current.agent, ...change } });
  }

  function ask(call: (signal: AbortSignal) => Promise<SessionTurn>) {
    const mine = run;
    const signal = controller?.signal;
    if (!signal) return;
    lastAgentAt = now();
    setAgent({ busy: true, failure: null });
    call(signal).then(
      (answer) => {
        if (mine === run) setAgent({ turn: answer.turn, model: answer.model, busy: false });
      },
      (error: unknown) => {
        if (mine === run && !signal.aborted) setAgent({ busy: false, failure: errorMessage(error) });
      },
    );
  }

  /** Tell the agent of a steady move: a new session, or the operator's new view. Not while the tag is in sight. */
  function agentStep(frame: FrameAnswer) {
    const decided = steady.value;
    if (current.agent.busy || current.approved !== null || decided === null || query === null) return;
    if (decided === IN_SIGHT || frame.sighting !== null) return;
    if (frame.decision.action !== decided || now() - lastAgentAt < AGENT_GAP_MS) return;
    const turn = current.agent.turn;
    const asset = query.asset_id;
    if (turn === null || turn.awaiting === null) {
      ask((signal) => calls.start({ asset_id: asset, view_set: LIVE, view: frame.frame_id }, { signal }));
    } else if (turn.awaiting.kind === "view" && turn.located?.decision.action !== decided) {
      const id = turn.session_id;
      ask((signal) => calls.choose(id, frame.frame_id, { signal }));
    }
  }

  async function loop(mine: number, frames: FrameSource, expected: { width: number; height: number }) {
    const signal = controller?.signal;
    if (!signal || !query) return;
    const asked = query;
    while (mine === run) {
      let image: Blob | null;
      let answer: FrameAnswer;
      try {
        image = await frames.next(signal);
        if (mine !== run) return;
        if (image === null) {
          set({ phase: "ended" });
          return;
        }
        const size = frames.size();
        if (size && (size.width !== expected.width || size.height !== expected.height)) {
          stopWith(
            `The frames are ${size.width} × ${size.height} px; ${asked.camera_id} was calibrated at ` +
              `${expected.width} × ${expected.height} px`,
          );
          return;
        }
        answer = await calls.postFrame(image, asked, { signal });
      } catch (error) {
        if (mine === run && !signal.aborted) stopWith(errorMessage(error));
        return;
      }
      if (mine !== run) return;
      const cue = steady.push(cueOf(answer)) ?? current.steady;
      set({
        frame: answer,
        frames: current.frames + 1,
        steady: cue,
        sighted: answer.sighting ? answer : cue === IN_SIGHT ? current.sighted : null,
        confirmed: current.approved === true && answer.sighting ? answer.sighting : current.confirmed,
      });
      if (current.approved === true && answer.sighting && !current.second.answer && !current.second.busy) {
        inspect();
      }
      agentStep(answer);
    }
  }

  function stopWith(failure: string | null) {
    run += 1;
    controller?.abort();
    controller = null;
    source?.stop();
    source = null;
    set({ phase: failure ? "failed" : "ended", failure, agent: { ...current.agent, busy: false } });
  }

  function inspect() {
    const frame = current.frame;
    const signal = controller?.signal;
    if (!frame || !signal || current.second.busy) return;
    const mine = run;
    set({ second: { ...current.second, busy: true, failure: null } });
    calls.inspect(frame.frame_id, { signal }).then(
      (answer) => {
        if (mine === run) set({ second: { answer, busy: false, failure: null } });
      },
      (error: unknown) => {
        if (mine === run && !signal.aborted) {
          set({ second: { ...current.second, busy: false, failure: errorMessage(error) } });
        }
      },
    );
  }

  return {
    state: () => current,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    start(frames, asked, expected) {
      stopWith(null);
      run += 1;
      controller = new AbortController();
      source = frames;
      query = asked;
      lastAgentAt = Number.NEGATIVE_INFINITY;
      steady.reset();
      current = { ...IDLE, phase: "running" };
      listeners.forEach((listener) => listener());
      void loop(run, frames, expected);
    },
    stop() {
      if (current.phase === "running") stopWith(null);
    },
    answer(approved) {
      const turn = current.agent.turn;
      if (!turn || turn.awaiting?.kind !== "approval" || current.agent.busy) return;
      const id = turn.session_id;
      set({ approved });
      ask((signal) => calls.approve(id, approved, { signal }));
    },
    inspect,
  };
}
