import { describe, expect, it } from "vitest";

import { NAME_PATTERN, nameProblem, readNumber } from "./rules";

describe("nameProblem", () => {
  it("accepts the names the service accepts", () => {
    for (const name of ["cabinet", "cabinet-2", "home_cabinet.v2", "0", "a".repeat(64)]) {
      expect(nameProblem(name, "Name")).toBeNull();
      expect(NAME_PATTERN.test(name)).toBe(true);
    }
  });

  it("says why any other cannot name a set or an atlas", () => {
    expect(nameProblem("", "Name")).toBe("Name missing");
    expect(nameProblem("a".repeat(65), "Name")).toBe("Name over 64 characters");
    expect(nameProblem("-cabinet", "Asset id")).toBe("Asset id needs a letter or digit first");
    expect(nameProblem(".hidden", "Name")).toBe("Name needs a letter or digit first");
    expect(nameProblem("my cabinet", "Name")).toBe("Name has characters other than A–Z a–z 0–9 . _ -");
    expect(nameProblem("szafka-ż", "Name")).toBe("Name has characters other than A–Z a–z 0–9 . _ -");
    expect(nameProblem("../etc", "Name")).toBe("Name needs a letter or digit first");
  });
});

describe("readNumber", () => {
  it("reads what is typed, spaces aside", () => {
    expect(readNumber(" 25.04 ", "Length")).toEqual({ value: 25.04 });
    expect(readNumber("-3", "Seed")).toEqual({ value: -3 });
    expect(readNumber("200", "Samples", { integer: true, min: 10, max: 2000 })).toEqual({ value: 200 });
  });

  it("says what keeps it from being a number the service takes", () => {
    expect(readNumber("", "Length")).toEqual({ problem: "Length missing" });
    expect(readNumber("1,5", "Length")).toEqual({ problem: "Length not a number" });
    expect(readNumber("0", "Length", { above: 0, unit: "mm" })).toEqual({ problem: "Length 0 mm, needs > 0" });
    expect(readNumber("-1", "σ", { min: 0, unit: "mm" })).toEqual({ problem: "σ -1 mm, needs ≥ 0" });
    expect(readNumber("3000", "Samples", { integer: true, min: 10, max: 2000 })).toEqual({
      problem: "Samples 3000, needs 10 to 2000",
    });
    expect(readNumber("7", "N", { max: 5 })).toEqual({ problem: "N 7, needs ≤ 5" });
    expect(readNumber("2.5", "Squares", { integer: true })).toEqual({ problem: "Squares 2.5, needs a whole number" });
  });
});
