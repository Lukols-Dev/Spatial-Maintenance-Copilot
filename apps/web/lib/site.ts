// What the site is called and which pages it lists, in one place.

export const SITE = {
  name: "Spatial Maintenance Copilot",
  description: "Locate a component you cannot see, from the parts of the object you can.",
  repository: "https://github.com/Lukols-Dev/Spatial-Maintenance-Copilot",
} as const;

export interface NavEntry {
  href: string;
  title: string;
}

/** The pages the sidebar lists: only pages that work. */
export const NAV: NavEntry[] = [
  { href: "/", title: "Demo" },
  { href: "/localise", title: "Localise" },
  { href: "/atlas", title: "Atlas" },
];

/** A page reached from inside another, which the sidebar does not list: it marks its parent instead. */
export interface SubPage extends NavEntry {
  parent: string;
}

/** Marking the points of a view set by hand is one step of building an atlas. */
export const SUB_PAGES: SubPage[] = [{ href: "/atlas/annotate", title: "Annotate", parent: "/atlas" }];

/** "/atlas/" and "/atlas" are the same page; the export uses trailing slashes. */
export function normalisePath(path: string): string {
  return path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
}

/** The sub-page at this path, if it is one. */
export function subPageFor(path: string): SubPage | undefined {
  const page = normalisePath(path);
  return SUB_PAGES.find((entry) => entry.href === page);
}

/** The sidebar entry this path belongs to: its own, or its parent's for a sub-page. */
export function sectionFor(path: string): string | undefined {
  const page = normalisePath(path);
  return NAV.find((entry) => entry.href === page)?.href ?? subPageFor(page)?.parent;
}

/** The heading of the page at this path. */
export function titleFor(path: string): string {
  const page = normalisePath(path);
  return NAV.find((entry) => entry.href === page)?.title ?? subPageFor(page)?.title ?? "Not found";
}
