"use client";

import { useEffect, useState } from "react";

// The recordings a judge can localise without the asset or its phone: clips of
// the calibrated camera, served beside the site (tools/judge_recordings.py),
// since a canvas draws only a video of the page's own origin. Where none are
// served, as in local development, the page offers none.

/** Where the recordings and their index are served, beside the page. */
export const RECORDINGS_URL = "/recordings";

export interface Recording {
  file: string;
  title: string;
  seconds: number;
}

/** The index's recordings, those with a file, a title and a length; anything else is left out. */
export function parseRecordings(index: unknown): Recording[] {
  if (typeof index !== "object" || index === null || !("recordings" in index)) return [];
  const listed = (index as { recordings: unknown }).recordings;
  if (!Array.isArray(listed)) return [];
  return listed.filter(
    (entry): entry is Recording =>
      typeof entry === "object" &&
      entry !== null &&
      typeof entry.file === "string" &&
      /^[\w.-]+\.mp4$/.test(entry.file) &&
      typeof entry.title === "string" &&
      entry.title.length > 0 &&
      typeof entry.seconds === "number",
  );
}

export function recordingUrl(recording: Recording): string {
  return `${RECORDINGS_URL}/${recording.file}`;
}

/** The served recordings, read once; none while they load or where the index is missing. */
export function useRecordings(): Recording[] {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${RECORDINGS_URL}/index.json`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((index: unknown) => setRecordings(parseRecordings(index)))
      .catch(() => setRecordings([]));
    return () => controller.abort();
  }, []);
  return recordings;
}
