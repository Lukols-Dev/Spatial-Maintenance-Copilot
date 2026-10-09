"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { errorMessage } from "@/lib/api";
import { localise } from "@/lib/locate/api";
import { createSession, IDLE, type Shown } from "@/lib/locate/session";
import { createTraceStore, type StorageLike, type TraceStep } from "@/lib/locate/trace";

/** sessionStorage, or null where the browser blocks it. */
export function sessionStore(): StorageLike | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** The traces of this tab, shared by every component that shows one. */
export const traces = createTraceStore(sessionStore);

/** The localisations of this page. */
export const session = createSession({ localise, traces, now: () => new Date().toISOString() });

const NO_STEPS: readonly TraceStep[] = [];

export function useTraceSteps(key: string): readonly TraceStep[] {
  return useSyncExternalStore(
    traces.subscribe,
    () => traces.steps(key),
    () => NO_STEPS,
  );
}

/** What the session shows for the trace under `key`. The prerendered HTML shows nothing. */
export function useShown(key: string): Shown {
  return useSyncExternalStore(
    session.subscribe,
    () => session.shown(key),
    () => IDLE,
  );
}

export type Loaded<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; message: string };

const LOADING = { status: "loading" } as const;

/**
 * What load(id) gives, read again when version changes (the workspace says
 * the thing changed on disk) and on retry(). While a new version is read the
 * last one stays on screen; a different id starts from "loading".
 */
export function useLoaded<T>(
  id: string | null,
  version: string,
  load: (id: string, signal: AbortSignal) => Promise<T>,
): { state: Loaded<T>; retry: () => void } {
  const [attempt, setAttempt] = useState(0);
  const key = id === null ? null : JSON.stringify([id, version, attempt]);
  const [settled, setSettled] = useState<{ id: string; key: string; state: Loaded<T> } | null>(null);

  useEffect(() => {
    if (id === null || key === null) return;
    const controller = new AbortController();
    load(id, controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setSettled({ id, key, state: { status: "ready", data } });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setSettled({ id, key, state: { status: "error", message: errorMessage(error) } });
      },
    );
    return () => controller.abort();
  }, [id, key, load]);

  const retry = useCallback(() => setAttempt((count) => count + 1), []);
  let state: Loaded<T> = LOADING;
  if (settled !== null && settled.key === key) state = settled.state;
  else if (settled !== null && settled.id === id && settled.state.status === "ready") state = settled.state;
  return { state, retry };
}

export interface Size {
  width: number;
  height: number;
}

/**
 * The size of an element on screen, null until it is first measured. The ref
 * goes on the element; one that mounts later, or is replaced, is measured too.
 */
export function useElementSize<T extends Element>(): [(element: T | null) => (() => void) | undefined, Size | null] {
  const [size, setSize] = useState<Size | null>(null);
  const ref = useCallback((element: T | null) => {
    if (!element) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize((previous) => (previous?.width === width && previous.height === height ? previous : { width, height }));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, size];
}
