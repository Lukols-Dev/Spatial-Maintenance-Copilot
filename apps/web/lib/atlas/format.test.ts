import { describe, expect, it } from "vitest";

import { caliper, count, fixed, localTime, megabytes, sentence, signedPercent, size } from "./format";

describe("fixed", () => {
  it("writes exact decimals with a true minus sign, and never a negative zero", () => {
    expect(fixed(2, 2)).toBe("2.00");
    expect(fixed(-310.24, 1)).toBe("−310.2");
    expect(fixed(-0.04, 1)).toBe("0.0");
    expect(fixed(0.05, 1)).toBe("0.1");
  });
});

describe("caliper", () => {
  it("keeps the micrometres a value has, and at least the hundredths", () => {
    expect([25.04, 25, 33.367, 0.01, 18.1].map(caliper)).toEqual(["25.04", "25.00", "33.367", "0.01", "18.10"]);
  });
});

describe("signedPercent", () => {
  it("always shows the sign of a difference, and none for one that rounds to zero", () => {
    expect(signedPercent((25.04 / 25 - 1) * 100)).toBe("+0.16 %");
    expect(signedPercent(-0.16)).toBe("−0.16 %");
    expect(signedPercent(0.001)).toBe("0.00 %");
    expect(signedPercent(-0.001)).toBe("0.00 %");
  });
});

describe("words and sizes", () => {
  it("counts in words", () => {
    expect([count(1, "image"), count(3, "image"), count(0, "view")]).toEqual(["1 image", "3 images", "0 views"]);
  });

  it("writes decimal megabytes and image sizes", () => {
    expect(megabytes(245_312_345)).toBe("245.3 MB");
    expect(size(1080, 1920)).toBe("1080×1920");
    expect(size(null, 1920)).toBe("size unknown");
  });

  it("starts the service's reasons with a capital", () => {
    expect(sentence("seen in 1 posed view, needs 2")).toBe("Seen in 1 posed view, needs 2");
    expect(sentence("")).toBe("");
  });
});

describe("localTime", () => {
  it("writes a time to the minute in the reader's zone, and leaves what is not a time as it is", () => {
    // Without an offset the time is read in the local zone, so this holds wherever the test runs.
    expect(localTime("2026-10-06T14:25:03")).toBe("2026-10-06 14:25");
    expect(localTime("2026-10-06T14:25:03+02:00")).toMatch(/^2026-10-0\d \d\d:\d\d$/);
    expect(localTime("soon")).toBe("soon");
  });
});
