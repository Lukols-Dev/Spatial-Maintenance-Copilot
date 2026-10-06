"use client";

import { Check, LoaderCircle, RotateCw } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import * as core from "@/lib/annotate/core";
import { ApiError, errorMessage } from "@/lib/api";
import { saveClicks } from "@/lib/workspace";

// Every change to the clicks of a view set goes to the perception service, so
// the work is on its disk rather than in one browser. Changes closer together
// than the debounce share a request, and one request is on its way at a time:
// two at once could be written in either order and leave the older on disk.

/** Edits closer together than this are saved in one request. */
const DEBOUNCE_MS = 800;

export type SaveStatus =
  /** Nothing changed since the set was opened. */
  | { kind: "idle" }
  /** A change waits for its request, or the request is on its way. */
  | { kind: "saving" }
  /** time: hh:mm:ss on the visitor's clock of savedAt, when the service wrote the file. */
  | { kind: "saved"; savedAt: string; time: string }
  | { kind: "failed"; reason: string }
  /** The service refuses every change; unsaved: it lacks some of them. */
  | { kind: "read-only"; unsaved: boolean };

interface Saver {
  change(state: core.AnnotationState): void;
  retry(): void;
  /**
   * The page or the annotator is going away: send what the service lacks now,
   * in a request that outlives the page. While unloading that cannot wait for
   * a request already on its way, which the browser may cancel.
   */
  leave(unloading: boolean): void;
  unsaved(): boolean;
  /** The same object until the status changes, as useSyncExternalStore needs. */
  status(): SaveStatus;
  subscribe(listener: () => void): () => void;
}

/** An ISO 8601 time as hh:mm:ss in the visitor's time zone; null when it cannot be read. */
function clockTime(iso: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const parts = [date.getHours(), date.getMinutes(), date.getSeconds()];
  return parts.map((part) => String(part).padStart(2, "0")).join(":");
}

function createSaver(set: string, initial: core.AnnotationState, readOnly: boolean): Saver {
  let latest = core.toJson(initial);
  let latestText = JSON.stringify(latest);
  // What the service has: the clicks the set was opened with, then each confirmed save.
  let confirmed = latestText;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let inFlight = 0;
  // Only the newest request may say what the service has.
  let sent = 0;
  // A save that came due while a request was on its way; it goes once that one is answered.
  let queued: { keepalive: boolean } | null = null;
  // Changes are refused: the workspace said so when the set was opened, or the service answered 403.
  let refused = readOnly;
  let failure: string | null = null;
  let saved: { savedAt: string; time: string } | null = null;
  const listeners = new Set<() => void>();
  let current: SaveStatus = { kind: "idle" };
  // Most edits leave the status as it was; the page is not rendered again for those.
  let currentKey = "";

  const unsaved = () => latestText !== confirmed;

  function compute(): SaveStatus {
    if (refused) return { kind: "read-only", unsaved: unsaved() };
    if (timer !== null || inFlight > 0) return { kind: "saving" };
    if (failure !== null && unsaved()) return { kind: "failed", reason: failure };
    if (saved !== null) return { kind: "saved", ...saved };
    return { kind: "idle" };
  }

  function publish() {
    const next = compute();
    const key = JSON.stringify(next);
    if (key === currentKey) return;
    current = next;
    currentKey = key;
    listeners.forEach((listener) => listener());
  }

  function cancelTimer() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }

  function schedule() {
    cancelTimer();
    timer = setTimeout(() => {
      timer = null;
      save(false);
    }, DEBOUNCE_MS);
  }

  function send(keepalive: boolean) {
    const body = latest;
    const text = latestText;
    const number = ++sent;
    inFlight += 1;
    failure = null;
    publish();
    saveClicks(set, body, { keepalive })
      .then(
        (summary) => {
          if (number !== sent) return;
          confirmed = text;
          const time = clockTime(summary.saved_at);
          saved = time === null ? saved : { savedAt: summary.saved_at, time };
        },
        (error: unknown) => {
          if (number !== sent) return;
          if (error instanceof ApiError && error.status === 403) refused = true;
          else failure = errorMessage(error);
        },
      )
      .finally(() => {
        inFlight -= 1;
        if (inFlight > 0) return;
        const next = queued;
        queued = null;
        if (next) save(next.keepalive);
        // A change undone while its save was on the way leaves the service with the undone state.
        else if (unsaved() && !refused && failure === null && timer === null) schedule();
        publish();
      });
  }

  /** Send the newest state unless the service has it, after any request already on its way. */
  function save(keepalive: boolean) {
    cancelTimer();
    if (refused || !unsaved()) {
      publish();
      return;
    }
    if (inFlight > 0) {
      queued = { keepalive: keepalive || queued?.keepalive === true };
      publish();
      return;
    }
    send(keepalive);
  }

  publish();
  return {
    change(state) {
      latest = core.toJson(state);
      latestText = JSON.stringify(latest);
      if (!unsaved()) cancelTimer();
      else if (!refused) schedule();
      publish();
    },
    retry() {
      save(false);
    },
    leave(unloading) {
      cancelTimer();
      if (refused || !unsaved()) return;
      if (inFlight > 0 && !unloading) queued = { keepalive: true };
      else send(true);
    },
    unsaved,
    status: () => current,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/**
 * Save every change of a view set's clicks: debounced, and at once when the
 * page is hidden, closed or left by a link. readOnly is what the workspace
 * said when the set was opened; a 403 from the service has the same effect.
 */
export function useAutosave(set: string, initial: core.AnnotationState, readOnly: boolean) {
  const [saver] = useState(() => createSaver(set, initial, readOnly));
  const status = useSyncExternalStore(saver.subscribe, saver.status, saver.status);

  useEffect(() => {
    const onVisibility = () => {
      // A hidden tab may be discarded without another event.
      if (document.visibilityState === "hidden") saver.leave(false);
    };
    const onPageHide = () => saver.leave(true);
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!saver.unsaved()) return;
      event.preventDefault();
      // For browsers that show the prompt only for a returnValue.
      event.returnValue = true;
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("beforeunload", onBeforeUnload);
      // A link inside the app removes the annotator without unloading the page.
      saver.leave(false);
    };
  }, [saver]);

  return { status, change: saver.change, retry: saver.retry };
}

/** Whether the latest change is on the service's disk, at the end of the toolbar. */
export function SaveIndicator({ status, onRetry }: { status: SaveStatus; onRetry: () => void }) {
  const problem =
    status.kind === "failed"
      ? `Not saved: ${status.reason}`
      : status.kind === "read-only" && status.unsaved
        ? "Read-only service: not saved"
        : "";

  return (
    <div className="ml-auto flex min-h-8 flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
      {status.kind === "saving" && (
        <span className="flex items-center gap-1.5">
          <LoaderCircle aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
          Saving…
        </span>
      )}
      {status.kind === "saved" && (
        <span className="flex items-center gap-1.5">
          <Check aria-hidden className="size-4 text-emerald-700 dark:text-emerald-400" />
          <span>
            Saved <time dateTime={status.savedAt}>{status.time}</time>
          </span>
        </span>
      )}
      {status.kind === "read-only" && !status.unsaved && <span>Read-only service</span>}
      {/* Always rendered, so screen readers announce the text when it appears. */}
      <p role="alert" className="max-w-md text-destructive empty:hidden">
        {problem}
      </p>
      {status.kind === "failed" && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCw /> Retry
        </Button>
      )}
    </div>
  );
}
