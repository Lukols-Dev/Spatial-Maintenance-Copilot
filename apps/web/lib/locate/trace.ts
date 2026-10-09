import type { LocaliseResult, Truth } from "@/lib/locate/types";

// The trace of a session: every localisation the page ran for one atlas and
// one view set, in order. It lives in sessionStorage, so a reload keeps it and
// a new tab starts afresh. A step keeps the whole answer, to be shown again.

export interface TraceStep {
  /** 1, 2, 3… within its trace. */
  n: number;
  /** ISO 8601: when the answer came. */
  at: string;
  view: string;
  /** The image the truth was asked from; null: none. */
  truthView: string | null;
  result: LocaliseResult;
}

/** The oldest steps go first beyond this: each keeps a whole answer, and the storage is small. */
export const MAX_STEPS = 50;

const TRACE_PREFIX = "smc-locate:trace:v1:";
const SELECTION_KEY = "smc-locate:selection:v1";

/** Just what the page needs of sessionStorage, so tests can give a stand-in. */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/**
 * One trace per build of an atlas and view set. A rebuilt atlas starts a new
 * trace: its regions are not comparable with the old build's.
 */
export function traceKey(asset: string, builtAt: string, set: string): string {
  return `${TRACE_PREFIX}${asset}@${builtAt}/${set}`;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Enough of a step to show it; anything else in the storage is left out. */
function isStep(value: unknown): value is TraceStep {
  if (!isObject(value) || !isObject(value.result)) return false;
  const { result } = value;
  return (
    Number.isInteger(value.n) &&
    typeof value.at === "string" &&
    typeof value.view === "string" &&
    (value.truthView === null || typeof value.truthView === "string") &&
    isObject(result.decision) &&
    isObject(result.localisation) &&
    isObject(result.image) &&
    Array.isArray(result.observations) &&
    Array.isArray(result.projections)
  );
}

/** The steps stored under a key; nothing for a missing or broken value. */
export function parseTrace(raw: string | null): TraceStep[] {
  if (raw === null) return [];
  try {
    const value: unknown = JSON.parse(raw);
    return Array.isArray(value) ? value.filter(isStep) : [];
  } catch {
    return [];
  }
}

/** The steps with one more at the end, numbered after the last. */
export function withStep(steps: readonly TraceStep[], step: Omit<TraceStep, "n">): TraceStep[] {
  const n = (steps.at(-1)?.n ?? 0) + 1;
  return [...steps, { ...step, n }].slice(-MAX_STEPS);
}

/** Semi-major axis of the 95 % region; null when the localisation gave none. */
export function regionPx(result: LocaliseResult): number | null {
  return result.localisation.uncertainty?.ellipse.semi_major_px ?? null;
}

/** How the region of a step compares with the step before. */
export type Change =
  /** Nothing to compare: the first step, or neither step has a region. */
  | { kind: "none" }
  /** A region where the step before had none. */
  | { kind: "found" }
  /** No region where the step before had one. */
  | { kind: "lost" }
  /** percent: the change of the semi-major axis; a smaller region is a better localisation. */
  | { kind: "ratio"; percent: number; verdict: "improved" | "worse" | "same" };

export function changeOf(previous: LocaliseResult | null, current: LocaliseResult): Change {
  const before = previous ? regionPx(previous) : null;
  const now = regionPx(current);
  if (before === null && now === null) return { kind: "none" };
  if (before === null) return previous ? { kind: "found" } : { kind: "none" };
  if (now === null) return { kind: "lost" };
  const percent = before > 0 ? ((now - before) / before) * 100 : now > 0 ? Number.POSITIVE_INFINITY : 0;
  // "same" is what reads as 0.0 % on the page.
  const verdict = Math.round(percent * 10) === 0 ? "same" : percent < 0 ? "improved" : "worse";
  return { kind: "ratio", percent, verdict };
}

/** The latest step of each view, for the badges of the viewpoints. */
export function latestByView(steps: readonly TraceStep[]): Map<string, TraceStep> {
  return new Map(steps.map((step) => [step.view, step]));
}

/**
 * The truth to show for a step. Without a truth view the service still takes
 * the view's own target click, but "None" was chosen: nothing is shown.
 */
export function shownTruth(step: Pick<TraceStep, "truthView" | "result">): Truth | null {
  return step.truthView === null ? null : step.result.truth;
}

export interface TraceStore {
  /** The trace under a key: the same array until it changes, as useSyncExternalStore needs. */
  steps(key: string): readonly TraceStep[];
  append(key: string, step: Omit<TraceStep, "n">): TraceStep;
  clear(key: string): void;
  subscribe(listener: () => void): () => void;
}

/**
 * The traces of the page, read from the storage once per key and written back
 * on every change. The page keeps working when the storage refuses: a full one
 * keeps the newest steps that fit, and a blocked one none, for this page only.
 */
export function createTraceStore(storage: () => StorageLike | null): TraceStore {
  const traces = new Map<string, readonly TraceStep[]>();
  const listeners = new Set<() => void>();

  function storageOrNull(): StorageLike | null {
    try {
      return storage();
    } catch {
      return null;
    }
  }

  function steps(key: string): readonly TraceStep[] {
    let trace = traces.get(key);
    if (trace === undefined) {
      let raw: string | null = null;
      try {
        raw = storageOrNull()?.getItem(key) ?? null;
      } catch {
        // Blocked storage: an empty trace.
      }
      trace = parseTrace(raw);
      traces.set(key, trace);
    }
    return trace;
  }

  function persist(key: string, trace: readonly TraceStep[]) {
    const store = storageOrNull();
    if (!store) return;
    try {
      if (trace.length === 0) {
        store.removeItem(key);
        return;
      }
    } catch {
      return;
    }
    for (let kept = trace; kept.length > 0; kept = kept.slice(Math.ceil(kept.length / 2))) {
      try {
        store.setItem(key, JSON.stringify(kept));
        return;
      } catch {
        // Over the quota: try again with the newer half.
      }
    }
  }

  function change(key: string, trace: readonly TraceStep[]) {
    traces.set(key, trace);
    persist(key, trace);
    listeners.forEach((listener) => listener());
  }

  return {
    steps,
    append(key, step) {
      const next = withStep(steps(key), step);
      change(key, next);
      return next[next.length - 1];
    },
    clear(key) {
      change(key, []);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

/** The atlas and view set chosen last in this tab, so a reload shows the same trace. */
export interface Selection {
  asset: string;
  set: string | null;
}

export function readSelection(storage: StorageLike | null): Selection | null {
  try {
    const value: unknown = JSON.parse(storage?.getItem(SELECTION_KEY) ?? "null");
    if (!isObject(value) || typeof value.asset !== "string") return null;
    return { asset: value.asset, set: typeof value.set === "string" ? value.set : null };
  } catch {
    return null;
  }
}

export function writeSelection(storage: StorageLike | null, selection: Selection): void {
  try {
    storage?.setItem(SELECTION_KEY, JSON.stringify(selection));
  } catch {
    // Blocked or full: the choice lasts until the page is left.
  }
}
