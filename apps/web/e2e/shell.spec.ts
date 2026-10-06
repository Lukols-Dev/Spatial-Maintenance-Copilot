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

test("the sidebar lists the working pages and reaches each one without a reload", async ({ page }) => {
  await stubHealth(page);
  await page.goto("/");
  await expect(page).toHaveTitle(SITE.name);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(SITE.name);

  const pages = sidebar(page).getByRole("navigation", { name: "Pages" }).getByRole("link");
  await expect(pages).toHaveText(NAV.map((entry) => entry.title));
  await expect(current(page)).toHaveCount(1);
  await expect(current(page)).toHaveAccessibleName(SITE.name);

  await markWindow(page);
  for (const { href, title } of NAV) {
    await pages.getByText(title, { exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${href}/$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
    await expect(current(page)).toHaveCount(1);
    await expect(current(page)).toHaveText(title);
  }
  await sidebar(page).getByRole("link", { name: SITE.name }).click();
  await expect(page).toHaveURL(/:\d+\/$/);
  await page.getByRole("main").getByRole("link", { name: "Annotate" }).click();
  await expect(page).toHaveURL(/\/annotate\/$/);
  expect(await windowStillMarked(page)).toBe(true);
});

test("the export redirects a folder to its slash, and unknown or removed pages are 404", async ({ page, request }) => {
  // The local server imitates an S3 website endpoint: a folder without its slash is redirected.
  const redirect = await request.get("/annotate", { maxRedirects: 0 });
  expect(redirect.status()).toBe(302);
  expect(redirect.headers().location).toBe("/annotate/");

  await stubHealth(page);
  for (const path of ["/no-such-page/", "/annotate/no-such-page/", "/demo/", "/evaluation/"]) {
    const missing = await page.goto(path);
    expect(missing?.status()).toBe(404);
    await expect(page.getByText("Page not found")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Not found");
    await expect(current(page)).toHaveCount(0);
  }
});

test("the dark theme is kept across a reload", async ({ page }) => {
  await stubHealth(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Colour theme" }).click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
});

test("the API status entry shows the live answer of /health", async ({ page }) => {
  await stubHealth(page, true);
  await page.goto("/");
  await expect(sidebar(page).getByRole("button", { name: /^API online · v0\.1\.0\./ })).toBeVisible();
});

test("the API status entry says when the service cannot be reached, and checks again on click", async ({ page }) => {
  await stubHealth(page, false);
  await page.goto("/");
  const status = sidebar(page).getByRole("button", { name: /^API (offline|online)/ });
  await expect(status).toHaveAccessibleName(/^API offline\./);

  await page.unroute("**/health");
  await stubHealth(page, true);
  await status.click();
  await expect(status).toHaveAccessibleName(/^API online · v0\.1\.0\./);
});

test("no page logs an error", async ({ page }) => {
  await stubHealth(page);
  await stubWorkspace(page, example("workspace.json"));
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  for (const path of ["/", "/annotate/"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
  }
  expect(errors).toEqual([]);
});
