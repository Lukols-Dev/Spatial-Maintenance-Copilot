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

/** The pages the sidebar lists: only pages that work. The home page is reached by the site name. */
export const NAV: NavEntry[] = [{ href: "/annotate", title: "Annotate" }];

/** "/annotate/" and "/annotate" are the same page; the export uses trailing slashes. */
export function normalisePath(path: string): string {
  return path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
}

/** The heading of the page at this path. */
export function titleFor(path: string): string {
  const page = normalisePath(path);
  if (page === "/") return SITE.name;
  return NAV.find((entry) => entry.href === page)?.title ?? "Not found";
}
