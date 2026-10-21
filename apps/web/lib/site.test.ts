import { describe, expect, it } from "vitest";

import { NAV, SUB_PAGES, normalisePath, sectionFor, subPageFor, titleFor } from "./site";

describe("normalisePath", () => {
  it("treats a path with and without its trailing slash as one page", () => {
    expect(normalisePath("/atlas/annotate/")).toBe("/atlas/annotate");
    expect(normalisePath("/atlas/annotate")).toBe("/atlas/annotate");
    expect(normalisePath("/")).toBe("/");
  });
});

describe("titleFor", () => {
  it("names the listed pages, the home page among them, their sub-pages, and every other path", () => {
    for (const { href, title } of [...NAV, ...SUB_PAGES]) {
      expect(titleFor(href)).toBe(title);
      expect(titleFor(`${href}/`)).toBe(title);
    }
    expect(titleFor("/")).toBe("Demo");
    expect(titleFor("/localise/")).toBe("Localise");
    expect(titleFor("/atlas/annotate/")).toBe("Annotate");
    expect(titleFor("/annotate/")).toBe("Not found");
    expect(titleFor("/demo/")).toBe("Not found");
    // The pages Demo and Localise replaced are gone.
    expect(titleFor("/agent/")).toBe("Not found");
    expect(titleFor("/guide/")).toBe("Not found");
    expect(titleFor("/atlas/no-such-page/")).toBe("Not found");
  });
});

describe("sectionFor", () => {
  it("is the page itself for a listed page, the parent for a sub-page, and nothing otherwise", () => {
    expect(sectionFor("/")).toBe("/");
    expect(sectionFor("/localise/")).toBe("/localise");
    expect(sectionFor("/atlas/")).toBe("/atlas");
    expect(sectionFor("/atlas/annotate/")).toBe("/atlas");
    expect(sectionFor("/atlas/no-such-page/")).toBeUndefined();
    expect(sectionFor("/annotate/")).toBeUndefined();
  });

  it("lists Annotate under Atlas, not in the sidebar", () => {
    expect(NAV.map((entry) => entry.title)).not.toContain("Annotate");
    expect(subPageFor("/atlas/annotate")?.parent).toBe("/atlas");
    for (const sub of SUB_PAGES) expect(NAV.some((entry) => entry.href === sub.parent)).toBe(true);
  });
});
