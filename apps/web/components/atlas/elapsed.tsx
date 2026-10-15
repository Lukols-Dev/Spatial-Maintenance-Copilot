"use client";

import { useSyncExternalStore } from "react";

function everySecond(onTick: () => void) {
  const timer = setInterval(onTick, 250);
  return () => clearInterval(timer);
}

function currentSecond() {
  return Math.floor(Date.now() / 1000);
}

/** Whole seconds since `since` (ms), counting while shown. */
export function Elapsed({ since }: { since: number }) {
  const start = Math.floor(since / 1000);
  const now = useSyncExternalStore(everySecond, currentSecond, () => start);
  return <span className="tabular-nums">{Math.max(0, now - start)} s</span>;
}
