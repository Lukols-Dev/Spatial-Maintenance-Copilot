import type { SessionStart, SessionTurn, Turn } from "@/lib/agent/types";
import { errorMessage } from "@/lib/api";
import { StillnessMeter, pictureChange, type Look } from "@/lib/guide/motion";
import { IN_SIGHT, cueOf, moveOf, type Cue } from "@/lib/guide/moves";
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
//
// A phone's camera gives frames in the orientation the phone is held in, and
// turns them when the phone turns, tilted toward the floor included. Frames of
// the calibration's size turned by a quarter are not sent: the page says the
// phone is sideways and waits for upright frames. Any other size stops the run.
//
// A live camera goes step by step (lib/guide/motion): while it moves no frame
// is sent and the last instruction stays; once it has held still, frames are
// sent until a cue holds for a few in a row, and that cue is the instruction
// until the camera moves again. A hand's tremor sends nothing, and a camera
// that stopped gets one instruction, spoken once and handed to the agent once.
// A video file cannot hold still on request, so its frames are all sent.

/** The view set name of the frames, for the agent's session. */
export const LIVE = "live";
/** The agent is told of a new steady move at most this often: its model allows a few calls a minute. */
export const AGENT_GAP_MS = 4000;
/** Between two looks at a camera held sideways: no frame is sent, so none needs to be encoded at full rate. */
export const SIDEWAYS_PAUSE_MS = 300;
/** Frames sent from one stop without a cue holding: the last one's cue is then the instruction. */
export const MAX_ANALYSED = 6;
/** The session's log keeps this many instructions, the newest. */
export const MAX_LOG = 50;

/**
 * One instruction of the session, for its summary: the frame it was decided on,
 * what the agent did with it, and what the operator did next.
 */
export interface LogEntry {
  /** 1 for the first instruction of the run. */
  n: number;
  /** When it was given, ms since the run started. */
  at: number;
  cue: Cue;
  frame: FrameAnswer;
  agent: { did: string; words: "model" | "policy"; corrected: boolean } | null;
  operator: string | null;
}

/** Where frames come from: a camera, or a video stepped through. */
export interface FrameSource {
  /** A camera, whose frames turn with the phone; a video file's size never changes. */
  live: boolean;
  /** The size of the frames, once known. */
  size(): { width: number; height: number } | null;
  /** The next frame to localise; null once the source has ended. */
  next(signal: AbortSignal): Promise<Blob | null>;
  /** A live camera's next picture, small and grey, to tell its motion by; a source without it is not stepped. */
  look?(signal: AbortSignal): Promise<Look | null>;
  stop(): void;
}

/**
 * Where a live camera's step stands: moving, settling (still, not yet for long
 * enough), analysing (frames sent from where it stopped), ready (the
 * instruction holds until it moves). Null for a source that is not stepped.
 */
export type Step = "moving" | "settling" | "analysing" | "ready";

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
  /** The size of a camera's frames while they come turned by a quarter: the phone is held sideways. */
  sideways: { width: number; height: number } | null;
  frame: FrameAnswer | null;
  frames: number;
  /** The cue that has held for a few frames: the decision's move, or the target in sight. */
  steady: Cue | null;
  /** Counts the instructions given, the same cue again included: each is spoken. */
  instruction: number;
  step: Step | null;
  /** How far a live camera is toward still, 0 to 1, in tenths; null when it is not stepped. */
  settle: number | null;
  /** A live camera's change between frames (lib/guide/motion), in tenths; null when it is not stepped. */
  motion: number | null;
  /** Every instruction of the run, the newest last. */
  log: LogEntry[];
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
  sideways: null,
  frame: null,
  frames: 0,
  steady: null,
  instruction: 0,
  step: null,
  settle: null,
  motion: null,
  log: [],
  sighted: null,
  agent: { turn: null, model: null, busy: false, failure: null },
  approved: null,
  confirmed: null,
  second: { answer: null, busy: false, failure: null },
};

export interface GuideStore {
  state(): GuideState;
  subscribe(listener: () => void): () => void;
  /**
   * Localise the source's frames against the atlas. A camera's frames turned by a quarter wait for the
   * phone to be upright; frames of any other size than expected stop it.
   */
  start(source: FrameSource, query: FrameQuery, expected: { width: number; height: number }): void;
  stop(): void;
  /** The operator's answer to the next step the agent proposed. */
  answer(approved: boolean): void;
  /** Ask the vision model about the target's region of the latest frame. */
  inspect(): void;
}

/** A pause that ends early, rejecting, when the signal aborts. */
function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) reject(signal.reason);
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

export function createGuideStore({
  calls,
  now,
  wait = pause,
}: {
  calls: GuideCalls;
  now: () => number;
  /** The pause between looks at a sideways camera; the tests make it instant. */
  wait?: (ms: number, signal: AbortSignal) => Promise<void>;
}): GuideStore {
  let current = IDLE;
  const listeners = new Set<() => void>();
  let run = 0;
  let controller: AbortController | null = null;
  let source: FrameSource | null = null;
  let query: FrameQuery | null = null;
  let lastAgentAt = Number.NEGATIVE_INFINITY;
  const steady = new Steady();
  // The frame of an instruction the agent is not told of yet: it was busy, or told too recently.
  // A stepped camera sends no further frame to tell it with, so the store tells it later.
  let pending: FrameAnswer | null = null;
  let startedAt = 0;
  let retrying = false;
  // When the last retry was scheduled: a clock that has not moved since gets no other.
  let retriedAt = Number.NaN;

  function set(change: Partial<GuideState>) {
    current = { ...current, ...change };
    listeners.forEach((listener) => listener());
  }

  function setAgent(change: Partial<GuideState["agent"]>) {
    set({ agent: { ...current.agent, ...change } });
  }

  /** The log with its newest entry changed; the same log when it is empty. */
  function withLast(change: (entry: LogEntry) => LogEntry): LogEntry[] {
    const last = current.log.at(-1);
    return last ? [...current.log.slice(0, -1), change(last)] : current.log;
  }

  /** What the agent's answer did with the newest instruction, for the session's log. */
  function logAgent(answer: SessionTurn) {
    const awaiting = answer.turn.awaiting;
    const did =
      awaiting?.kind === "view"
        ? `Asked: ${moveOf(awaiting.action).words.toLowerCase()}`
        : awaiting?.kind === "approval"
          ? `Proposed: ${awaiting.next_step}`
          : null;
    if (did === null) return;
    const kinds = new Set(answer.turn.events.map((event) => event.kind));
    set({
      log: withLast((entry) => ({
        ...entry,
        agent: { did, words: kinds.has("fallback") ? "policy" : "model", corrected: kinds.has("guard") },
      })),
    });
  }

  function ask(call: (signal: AbortSignal) => Promise<SessionTurn>) {
    const mine = run;
    const signal = controller?.signal;
    if (!signal) return;
    lastAgentAt = now();
    setAgent({ busy: true, failure: null });
    call(signal).then(
      (answer) => {
        if (mine !== run) return;
        setAgent({ turn: answer.turn, model: answer.model, busy: false });
        logAgent(answer);
        if (pending) agentStep(pending);
      },
      (error: unknown) => {
        if (mine === run && !signal.aborted) setAgent({ busy: false, failure: errorMessage(error) });
      },
    );
  }

  /** Tell the agent of the pending instruction once its gap has passed, if nothing replaced it by then. */
  function retryAfter(ms: number) {
    const signal = controller?.signal;
    if (retrying || !signal) return;
    retrying = true;
    const mine = run;
    wait(ms, signal).then(
      () => {
        retrying = false;
        if (mine === run && current.phase === "running" && pending) agentStep(pending);
      },
      () => {
        retrying = false;
      },
    );
  }

  /** Tell the agent of a steady move: a new session, or the operator's new view. Not while the tag is in sight. */
  function agentStep(frame: FrameAnswer) {
    pending = null;
    const decided = steady.value;
    if (current.approved !== null || decided === null || query === null) return;
    if (decided === IN_SIGHT || frame.sighting !== null) return;
    if (frame.decision.action !== decided) return;
    if (current.agent.busy) {
      pending = frame;
      return;
    }
    const left = AGENT_GAP_MS - (now() - lastAgentAt);
    if (left > 0) {
      pending = frame;
      if (now() !== retriedAt) {
        retriedAt = now();
        retryAfter(left);
      }
      return;
    }
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
    const look = frames.live ? frames.look?.bind(frames) : undefined;
    const meter = new StillnessMeter();
    let previous: Uint8ClampedArray | null = null;
    // Frames sent since the camera stopped, and whether its instruction holds.
    let analysed = 0;
    let held = false;
    while (mine === run) {
      let image: Blob | null;
      let answer: FrameAnswer;
      try {
        if (look) {
          const seen = await look(signal);
          if (mine !== run) return;
          if (seen === null) {
            set({ phase: "ended" });
            return;
          }
          const change = previous === null ? Number.POSITIVE_INFINITY : pictureChange(previous, seen.pixels);
          previous = seen.pixels;
          const stillness = meter.push(change, seen.at);
          // In tenths, so the page is drawn again when a figure it shows changes, not on every frame.
          const motion = meter.change === null || !Number.isFinite(meter.change) ? null : Math.round(meter.change * 10) / 10;
          const settle = Math.floor(meter.progress(seen.at) * 10) / 10;
          if (motion !== current.motion || settle !== current.settle) set({ motion, settle });
          if (stillness !== "still") {
            if (held || analysed > 0) {
              held = false;
              analysed = 0;
              steady.reset();
            }
            if (current.step !== stillness) set({ step: stillness });
            continue;
          }
          if (held) continue;
        }
        image = await frames.next(signal);
        if (mine !== run) return;
        if (image === null) {
          set({ phase: "ended" });
          return;
        }
        const size = frames.size();
        if (size && (size.width !== expected.width || size.height !== expected.height)) {
          const turned = size.width === expected.height && size.height === expected.width;
          if (!frames.live || !turned) {
            stopWith(
              `The frames are ${size.width} × ${size.height} px; ${asked.camera_id} was calibrated at ` +
                `${expected.width} × ${expected.height} px`,
            );
            return;
          }
          if (current.sideways === null) set({ sideways: size });
          await wait(SIDEWAYS_PAUSE_MS, signal);
          continue;
        }
        if (current.sideways !== null) set({ sideways: null });
        if (look && current.step !== "analysing") set({ step: "analysing" });
        answer = await calls.postFrame(image, asked, { signal });
      } catch (error) {
        if (mine === run && !signal.aborted) stopWith(errorMessage(error));
        return;
      }
      if (mine !== run) return;
      const changed = steady.push(cueOf(answer));
      let settled = changed;
      if (look) {
        analysed += 1;
        // Frames from one stop that never agree: the last one decides, so the operator is not left waiting.
        if (settled === null && analysed >= MAX_ANALYSED) settled = cueOf(answer);
        held = settled !== null;
      }
      const cue = settled ?? current.steady;
      if (settled !== null) {
        // A live camera got here because the operator moved and stopped; a video's frames just came.
        const before = look ? withLast((entry) => ({ ...entry, operator: entry.operator ?? "Moved" })) : current.log;
        const entry: LogEntry = {
          n: (current.log.at(-1)?.n ?? 0) + 1,
          at: now() - startedAt,
          cue: settled,
          frame: answer,
          agent: null,
          operator: null,
        };
        set({ log: [...before, entry].slice(-MAX_LOG) });
      }
      set({
        frame: answer,
        frames: current.frames + 1,
        steady: cue,
        instruction: settled !== null ? current.instruction + 1 : current.instruction,
        step: look ? (held ? "ready" : "analysing") : null,
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
      pending = null;
      startedAt = now();
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
      set({ approved, log: withLast((entry) => ({ ...entry, operator: approved ? "Approved" : "Declined" })) });
      ask((signal) => calls.approve(id, approved, { signal }));
    },
    inspect,
  };
}
