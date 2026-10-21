import { useSyncExternalStore } from "react";

// The Guide page's settings: which layers the overlay draws, and whether the
// instructions are spoken. They are this browser's conveniences, kept in
// localStorage; a private window or blocked storage gets the defaults, and the
// page works the same.

export type GuideLayer = "landmarks" | "occluder" | "target" | "region";

export interface GuideSettings {
  layers: Record<GuideLayer, boolean>;
  voice: boolean;
}

/** The layers in the order the settings list them, with their names there. */
export const GUIDE_LAYERS: { layer: GuideLayer; name: string }[] = [
  { layer: "landmarks", name: "Markers found" },
  { layer: "occluder", name: "Panel hiding the target" },
  { layer: "target", name: "Target's box" },
  { layer: "region", name: "95 % region" },
];

export const DEFAULT_SETTINGS: GuideSettings = {
  layers: { landmarks: true, occluder: true, target: true, region: true },
  voice: false,
};

const KEY = "smc-guide-settings:v1";

/** Settings read back from storage: what is missing or of the wrong kind takes its default. */
export function parseSettings(text: string | null): GuideSettings {
  if (!text) return DEFAULT_SETTINGS;
  let stored: unknown;
  try {
    stored = JSON.parse(text);
  } catch {
    return DEFAULT_SETTINGS;
  }
  if (typeof stored !== "object" || stored === null) return DEFAULT_SETTINGS;
  const { layers, voice } = stored as { layers?: Record<string, unknown>; voice?: unknown };
  const kept = { ...DEFAULT_SETTINGS.layers };
  for (const { layer } of GUIDE_LAYERS) {
    if (typeof layers?.[layer] === "boolean") kept[layer] = layers[layer];
  }
  return { layers: kept, voice: typeof voice === "boolean" ? voice : DEFAULT_SETTINGS.voice };
}

let current: GuideSettings | null = null;
const listeners = new Set<() => void>();

function read(): GuideSettings {
  if (current === null) {
    try {
      current = parseSettings(localStorage.getItem(KEY));
    } catch {
      current = DEFAULT_SETTINGS;
    }
  }
  return current;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Change some settings, keep them for the next visit, and show them at once. */
export function changeSettings(change: { layers?: Partial<Record<GuideLayer, boolean>>; voice?: boolean }) {
  const before = read();
  current = {
    layers: { ...before.layers, ...change.layers },
    voice: change.voice ?? before.voice,
  };
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Storage blocked: the settings last for this visit.
  }
  listeners.forEach((listener) => listener());
}

/** The settings as last chosen in this browser; the defaults while prerendering. */
export function useGuideSettings(): GuideSettings {
  return useSyncExternalStore(subscribe, read, () => DEFAULT_SETTINGS);
}
