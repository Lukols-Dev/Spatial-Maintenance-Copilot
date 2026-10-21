import { describe, expect, it } from "vitest";

import {
  FALLBACK_MS,
  MOVING_ABOVE,
  SETTLE_MS,
  STILL_BELOW,
  StillnessMeter,
  WINDOW_MS,
  grey,
  pictureChange,
  sampleSize,
} from "./motion";

describe("the small grey picture", () => {
  it("keeps the frame's aspect with its longer side 160 px", () => {
    expect(sampleSize(1080, 1920)).toEqual({ width: 90, height: 160 });
    expect(sampleSize(1920, 1080)).toEqual({ width: 160, height: 90 });
    expect(sampleSize(0, 0)).toEqual({ width: 1, height: 1 });
  });

  it("is the luma of each pixel", () => {
    const rgba = new Uint8ClampedArray([255, 255, 255, 255, 255, 0, 0, 255, 0, 0, 0, 255]);
    expect([...grey(rgba)]).toEqual([255, 76, 0]);
  });
});

describe("the change between two pictures", () => {
  const a = new Uint8ClampedArray([10, 20, 30, 40]);

  it("is the mean difference of their pixels", () => {
    expect(pictureChange(a, new Uint8ClampedArray([12, 18, 30, 40]))).toBe(1);
    expect(pictureChange(a, a)).toBe(0);
  });

  it("is none for a change of exposure alone, and infinite between pictures of two sizes", () => {
    expect(pictureChange(a, new Uint8ClampedArray([25, 35, 45, 55]))).toBe(0);
    expect(pictureChange(a, new Uint8ClampedArray(3))).toBe(Number.POSITIVE_INFINITY);
  });
});

describe("the camera's stillness", () => {
  const steady = STILL_BELOW / 2;
  const tremor = (STILL_BELOW + MOVING_ABOVE) / 2;
  const moving = MOVING_ABOVE * 2;
  /** Frames at 30 a second from `from`, each with this change, until `to`; returns the last state. */
  function frames(meter: StillnessMeter, change: number, from: number, to: number) {
    let state = meter.value;
    for (let at = from; at <= to; at += 33) state = meter.push(change, at);
    return state;
  }

  it("is moving over the threshold, then still once steady for the settling time", () => {
    const meter = new StillnessMeter();
    expect(frames(meter, moving, 0, 500)).toBe("moving");
    expect(frames(meter, steady, 533, 533 + WINDOW_MS)).toBe("settling");
    expect(frames(meter, steady, 866, 866 + SETTLE_MS)).toBe("still");
    expect(meter.progress(2000)).toBe(1);
  });

  it("counts a hand's tremor as not moving, and analyses after the fallback time", () => {
    const meter = new StillnessMeter();
    frames(meter, moving, 0, 500);
    expect(frames(meter, tremor, 533, 500 + FALLBACK_MS - 100)).toBe("settling");
    expect(frames(meter, tremor, 500 + FALLBACK_MS - 67, 500 + FALLBACK_MS + 400)).toBe("still");
  });

  it("does not take one shaken frame for a move", () => {
    const meter = new StillnessMeter();
    frames(meter, steady, 0, 1500);
    expect(meter.value).toBe("still");
    meter.push(moving, 1533);
    expect(meter.push(steady, 1566)).toBe("still");
    expect(meter.change).toBe(steady);
  });

  it("is moving again on a move, and says how far toward still it is", () => {
    const meter = new StillnessMeter();
    frames(meter, steady, 0, 1500);
    expect(frames(meter, moving, 1533, 1800)).toBe("moving");
    expect(meter.progress(1800)).toBe(0);
    frames(meter, steady, 1833, 2166);
    expect(meter.value).toBe("settling");
    expect(meter.progress(2166)).toBeGreaterThan(0);
    expect(meter.progress(2166)).toBeLessThan(1);
  });
});
