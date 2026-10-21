import { describe, expect, it } from "vitest";

import { DEFAULT_SETTINGS, parseSettings } from "./settings";

describe("the Guide's settings as stored", () => {
  it("are the defaults when nothing or something unreadable is stored", () => {
    expect(parseSettings(null)).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("not json")).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("[1, 2]")).toEqual({ ...DEFAULT_SETTINGS });
    expect(DEFAULT_SETTINGS.voice).toBe(false);
    expect(Object.values(DEFAULT_SETTINGS.layers).every(Boolean)).toBe(true);
  });

  it("keep what was chosen, and take the default for what is missing or of the wrong kind", () => {
    const stored = JSON.stringify({ layers: { landmarks: false, region: "no", unknown: true }, voice: true });
    expect(parseSettings(stored)).toEqual({
      layers: { landmarks: false, occluder: true, target: true, region: true },
      voice: true,
    });
  });
});
