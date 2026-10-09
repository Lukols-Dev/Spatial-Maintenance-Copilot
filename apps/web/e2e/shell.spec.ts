import { expect, test, type Page } from "@playwright/test";

import { NAV, SITE } from "../lib/site";
import { example, stubHealth, stubWorkspace } from "./helpers";

/** A mark on the window that a full page load would wipe: navigation must stay client-side. */
async function markWindow(page: Page) {
  await page.evaluate(() => {
    (window as unknown as { __mark?: number }).__mark = 1;
  });
}

async function windowStillMarked(page: Page) {
  return page.evaluate(() => (window as unknown as { __mark?: number }).__mark === 1);
}

function sidebar(page: Page) {
  return page.locator("[data-slot=sidebar]").first();
}

/** The sidebar link that says it is the page on screen. */
function current(page: Page) {
  return sidebar(page).locator("[aria-current=page]");
}

/** The pages call the API as soon as they open; every test answers for it, so none reaches a real service. */
async function stubApi(page: Page, online = true) {
  await stubHealth(page, online);
  await stubWorkspace(page, online ? example("workspace-empty.json") : "offline");
}

/** Where a page lives once exported: "/" for the home page, "/annotate/" for the rest. */
function urlOf(href: string) {
  return href === "/" ? /:\d+\/$/ : new RegExp(`${href}/$`);
}

test("the sidebar lists the working pages and reaches each one without a reload", async ({ page }) => {
  await stubApi(page);
  await page.goto("/");
  await expect(page).toHaveTitle(`Locate · ${SITE.name}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Locate");

  const pages = sidebar(page).getByRole("navigation", { name: "Pages" }).getByRole("link");
  await expect(pages).toHaveText(NAV.map((entry) => entry.title));
  // The home page is also the first entry; only that entry says it is current.
  await expect(current(page)).toHaveCount(1);
  await expect(current(page)).toHaveText("Locate");

  await markWindow(page);
  // Backwards, so the walk starts by leaving the home page and ends by coming back to it.
  for (const { href, title } of [...NAV].reverse()) {
    await pages.getByText(title, { exact: true }).click();
    await expect(page).toHaveURL(urlOf(href));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
    await expect(current(page)).toHaveCount(1);
    await expect(current(page)).toHaveText(title);
  }
  await pages.getByText("Atlas", { exact: true }).click();
  await sidebar(page).getByRole("link", { name: SITE.name }).click();
  await expect(page).toHaveURL(urlOf("/"));
  await expect(current(page)).toHaveText("Locate");
  expect(await windowStillMarked(page)).toBe(true);
});

test("the export redirects a folder to its slash, and unknown or removed pages are 404", async ({ page, request }) => {
  // The local server imitates an S3 website endpoint: a folder without its slash is redirected.
  for (const folder of ["/annotate", "/atlas"]) {
    const redirect = await request.get(folder, { maxRedirects: 0 });
    expect(redirect.status()).toBe(302);
    expect(redirect.headers().location).toBe(`${folder}/`);
  }

  await stubApi(page);
  for (const path of ["/no-such-page/", "/annotate/no-such-page/", "/atlas/no-such-page/", "/demo/", "/evaluation/"]) {
    const missing = await page.goto(path);
    expect(missing?.status()).toBe(404);
    await expect(page.getByText("Page not found")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Not found");
    await expect(current(page)).toHaveCount(0);
  }
});

test("the dark theme is kept across a reload", async ({ page }) => {
  await stubApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Colour theme" }).click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
});

test("the API status entry shows the live answer of /health", async ({ page }) => {
  await stubApi(page);
  await page.goto("/");
  await expect(sidebar(page).getByRole("button", { name: /^API online · v0\.1\.0\./ })).toBeVisible();
});

test("the API status entry says when the service cannot be reached, and checks again on click", async ({ page }) => {
  await stubApi(page, false);
  await page.goto("/");
  const status = sidebar(page).getByRole("button", { name: /^API (offline|online)/ });
  await expect(status).toHaveAccessibleName(/^API offline\./);

  await page.unroute("**/health");
  await stubHealth(page, true);
  await status.click();
  await expect(status).toHaveAccessibleName(/^API online · v0\.1\.0\./);
});

test("no page logs an error", async ({ page }) => {
  await stubApi(page);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  for (const path of ["/", "/annotate/", "/atlas/"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
  }
  expect(errors).toEqual([]);
});
