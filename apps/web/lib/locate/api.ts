import { apiJson, imageUrl } from "@/lib/api";
import type { LocaliseRequest, LocaliseResult } from "@/lib/locate/types";

// The calls of the Locate page, and the rule that keeps its answers in order:
// the page shows the answer to the latest selection only.

/** The service poses the view and runs the Monte Carlo region; a slow machine takes seconds. */
export const LOCALISE_TIMEOUT_MS = 2 * 60_000;
/** Wide enough for a thumbnail on a screen with two device pixels per CSS pixel. */
export const THUMBNAIL_WIDTH = 240;

/**
 * No cache mode is set: no browser caches the answer to a POST anyway, and with
 * "no-store" Chrome skips its CORS preflight cache, so every call would cost
 * one more round trip to the service.
 */
export function localise(body: LocaliseRequest, options: { signal?: AbortSignal } = {}): Promise<LocaliseResult> {
  return apiJson<LocaliseResult>("/localise", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: LOCALISE_TIMEOUT_MS,
    signal: options.signal,
  });
}

/** A JPEG of the image scaled down to `width` by the service (never up). */
export function thumbnailUrl(set: string, file: string, width = THUMBNAIL_WIDTH): string {
  return `${imageUrl(set, file)}?width=${width}`;
}

export type Outcome<T> = { ok: true; value: T } | { ok: false; error: unknown };

/** Runs calls for the latest selection only. */
export interface LatestOnly {
  /**
   * Start a call. The one before it is aborted, and resolves null whatever it
   * would have given, so a slow answer never replaces a newer one. The newest
   * call resolves with its value or its error.
   */
  run<T>(call: (signal: AbortSignal) => Promise<T>): Promise<Outcome<T> | null>;
  /** Abort the running call: it resolves null. */
  cancel(): void;
}

export function latestOnly(): LatestOnly {
  let current: AbortController | null = null;

  return {
    async run<T>(call: (signal: AbortSignal) => Promise<T>) {
      current?.abort();
      const controller = new AbortController();
      current = controller;
      let outcome: Outcome<T>;
      try {
        outcome = { ok: true, value: await call(controller.signal) };
      } catch (error) {
        outcome = { ok: false, error };
      }
      // A call that ignores its signal still settles; what it gives is dropped all the same.
      if (controller !== current || controller.signal.aborted) return null;
      current = null;
      return outcome;
    },
    cancel() {
      current?.abort();
      current = null;
    },
  };
}
