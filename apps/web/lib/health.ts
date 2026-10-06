import { useSyncExternalStore } from "react";

import { apiJson, errorMessage } from "@/lib/api";

// GET /health of the perception service, shared by every component that shows
// it, so the page asks once.

export type Health =
  | { state: "checking" }
  | { state: "online"; service: string; version: string }
  | { state: "offline"; error: string };

const CHECKING: Health = { state: "checking" };
const TIMEOUT_MS = 5000;

let current: Health = CHECKING;
let started = false;
const listeners = new Set<() => void>();

function publish(next: Health) {
  current = next;
  listeners.forEach((listener) => listener());
}

/** Ask the service again; every subscriber sees the result. */
export function refreshHealth(): void {
  publish(CHECKING);
  apiJson<unknown>("/health", { cache: "no-store", timeoutMs: TIMEOUT_MS })
    .then((body) => {
      const fields = (body ?? {}) as Record<string, unknown>;
      if (fields.status !== "ok") throw new Error(`status is ${JSON.stringify(fields.status)}`);
      publish({
        state: "online",
        service: String(fields.service ?? "?"),
        version: String(fields.version ?? "?"),
      });
    })
    .catch((error: unknown) => publish({ state: "offline", error: errorMessage(error) }));
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!started) {
    started = true;
    refreshHealth();
  }
  return () => {
    listeners.delete(listener);
  };
}

/** The last known health. The prerendered HTML always says "checking". */
export function useHealth(): Health {
  return useSyncExternalStore(subscribe, () => current, () => CHECKING);
}
