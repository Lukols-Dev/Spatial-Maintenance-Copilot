import { useSyncExternalStore } from "react";

import { errorMessage } from "@/lib/api";
import { getAtlas, type AtlasDetail, type AtlasSummary } from "@/lib/workspace";

// The atlases read from the service, one GET /atlases/{id} each, kept for the
// whole page: the Result card shows one, the Build form repeats the settings of
// the last one built from a set. An atlas is read again once the workspace
// lists it with another build time, as it was built again meanwhile.

export type AtlasRead =
  | { status: "loading" }
  | { status: "ready"; detail: AtlasDetail }
  | { status: "error"; message: string };

interface Entry {
  builtAt: string;
  read: AtlasRead;
  /** Being built here: the build's answer is on its way, so the file is not read meanwhile. */
  building?: boolean;
}

const entries = new Map<string, Entry>();
let changes = 0;
const listeners = new Set<() => void>();

function publish() {
  changes++;
  listeners.forEach((listener) => listener());
}

/** The same moment, however the service wrote it. */
function sameTime(a: string, b: string): boolean {
  return a === b || Date.parse(a) === Date.parse(b);
}

function settle(id: string, entry: Entry, read: AtlasRead) {
  // A later read of this atlas took over: this answer may be of an older build.
  if (entries.get(id) !== entry) return;
  entries.set(id, { ...entry, read });
  publish();
}

/**
 * Read the atlas the summary lists, unless it is read already for that build
 * time. A failed read stays failed until `again` (a Retry) or another build
 * time. An atlas built again elsewhere stays on screen until its new build is read.
 */
export function readAtlas(summary: Pick<AtlasSummary, "asset_id" | "built_at">, again = false): void {
  const { asset_id: id, built_at: builtAt } = summary;
  const known = entries.get(id);
  if (!again && known && (known.building || sameTime(known.builtAt, builtAt))) return;
  const read: AtlasRead = !again && known?.read.status === "ready" ? known.read : { status: "loading" };
  const entry: Entry = { builtAt, read };
  entries.set(id, entry);
  publish();
  getAtlas(id).then(
    (detail) => settle(id, entry, { status: "ready", detail }),
    (error: unknown) => settle(id, entry, { status: "error", message: errorMessage(error) }),
  );
}

/** An atlas is being built under this id: its old file is not read again meanwhile. */
export function buildingAtlas(id: string): void {
  const known = entries.get(id);
  entries.set(id, { builtAt: known?.builtAt ?? "", read: known?.read ?? { status: "loading" }, building: true });
}

/** The build failed: what was read before stands, and the next listing decides whether to read again. */
export function buildFailed(id: string): void {
  const known = entries.get(id);
  if (!known?.building) return;
  if (known.builtAt === "") entries.delete(id);
  else entries.set(id, { builtAt: known.builtAt, read: known.read });
  publish();
}

/** A built atlas as the build answered it: shown at once, without reading it back. */
export function rememberAtlas(detail: AtlasDetail): void {
  const builtAt = detail.report?.built_at ?? "";
  entries.set(detail.atlas.asset_id, { builtAt, read: { status: "ready", detail } });
  publish();
}

export function atlasRead(id: string): AtlasRead | undefined {
  return entries.get(id)?.read;
}

/** Every atlas read so far. */
export function readAtlases(): AtlasDetail[] {
  return [...entries.values()].flatMap(({ read }) => (read.status === "ready" ? [read.detail] : []));
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Re-renders the component on every change of the atlases read; the number only counts the changes. */
export function useAtlasReads(): number {
  return useSyncExternalStore(subscribe, () => changes, () => 0);
}
