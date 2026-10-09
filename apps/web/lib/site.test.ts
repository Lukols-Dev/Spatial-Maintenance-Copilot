import { describe, expect, it } from "vitest";

import { NAV, normalisePath, titleFor } from "./site";

describe("normalisePath", () => {
  it("treats a path with and without its trailing slash as one page", () => {
    expect(normalisePath("/annotate/")).toBe("/annotate");
    expect(normalisePath("/annotate")).toBe("/annotate");
    expect(normalisePath("/")).toBe("/");
  });
});

describe("titleFor", () => {
  it("names the listed pages, the home page among them, and every other path", () => {
    for (const { href, title } of NAV) {
      expect(titleFor(href)).toBe(title);
      expect(titleFor(`${href}/`)).toBe(title);
    }
    expect(titleFor("/")).toBe("Locate");
    expect(titleFor("/demo/")).toBe("Not found");
    expect(titleFor("/annotate/no-such-page/")).toBe("Not found");
  });
});
