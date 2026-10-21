import { expect, test, type Page } from "@playwright/test";

import type { FrameAnswer } from "../lib/guide/types";
import { example, routeJson, stubCamera, stubHealth, stubWorkspace } from "./helpers";

// The Guide on a phone: a running camera takes the whole screen, as an app,
// with Exit and the settings over its top and the instruction, the agent and
// its buttons over its bottom. The service answers with the examples; the
// agent's first turn asks for approval, so its buttons show.

const PHONE = { width: 390, height: 844 };

async function serve(page: Page) {
  await stubHealth(page);
  await stubWorkspace(page, example("workspace-agent.json"));
  await page.route("**/frames?**", (route) => route.fulfill({ status: 201, json: example<FrameAnswer>("frame-answer.json") }));
  await routeJson(page, "POST", "**/sessions", example("session-turn-approval.json"), 201);
  await routeJson(page, "POST", "**/sessions/*/approval", example("session-turn-accepted.json"));
}

function screen(page: Page) {
  return page.locator("[data-fullscreen=true]");
}

test.describe("on a phone", () => {
  test.use({ viewport: PHONE, isMobile: true, hasTouch: true });

  test.beforeEach(async ({ page }) => {
    await stubCamera(page, 1080, 1920);
    await serve(page);
  });

  test("the running camera fills the screen, nothing scrolls, and its buttons are over the picture", async ({ page }) => {
    await page.goto("/localise");
    await page.getByRole("button", { name: "Camera" }).click();

    await expect(screen(page)).toBeVisible();
    expect(await screen(page).boundingBox()).toEqual({ x: 0, y: 0, ...PHONE });
    await page.mouse.wheel(0, 600);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);

    // The instruction once the camera has held still, then the agent's question and its buttons.
    const cue = screen(page).getByRole("status");
    await expect(cue).toHaveAttribute("data-cue", "ACCEPT");
    const approve = screen(page).getByRole("button", { name: "Approve" });
    await expect(approve).toBeVisible();
    for (const element of [cue, approve, screen(page).getByRole("button", { name: "Exit" })]) {
      const box = await element.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height).toBeLessThanOrEqual(PHONE.height);
    }
    // The measurements beside the picture on a wide screen are not on the phone's.
    await expect(page.getByText(/^Frame \d+$/)).toBeHidden();

    await approve.click();
    await expect(screen(page).getByText("Next step approved")).toBeVisible();
  });

  test("the settings hide a layer of the overlay, and are kept", async ({ page }) => {
    await page.goto("/localise");
    await page.getByRole("button", { name: "Camera" }).click();
    const marks = screen(page).locator("[data-part=landmark]");
    await expect(marks.first()).toBeVisible();

    await screen(page).getByRole("button", { name: "Settings" }).click();
    const sheet = page.getByRole("dialog", { name: "Settings" });
    // The camera's motion as measured now, against the thresholds it is held to.
    await expect(sheet.locator("[data-part=camera-motion]")).toHaveText(
      /^Camera motion \d+\.\d · steady below 2\.5 · moving above 3\.5$/,
    );
    await sheet.getByRole("checkbox", { name: "Markers found" }).uncheck();
    await page.keyboard.press("Escape");

    await expect(marks).toHaveCount(0);
    await expect(screen(page).locator("[data-part=region]")).toHaveCount(1);
    expect(await page.evaluate(() => localStorage.getItem("smc-guide-settings:v1"))).toContain('"landmarks":false');
  });

  test("Exit stops the camera and gives the page back, with the session's summary", async ({ page }) => {
    await page.goto("/localise");
    await page.getByRole("button", { name: "Camera" }).click();
    await expect(screen(page)).toBeVisible();
    // The instruction holds once three frames agreed on it.
    await expect(screen(page).getByRole("status")).toHaveAttribute("data-step", "ready");

    await screen(page).getByRole("button", { name: "Exit" }).click();

    await expect(screen(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Camera" })).toBeVisible();
    expect(await page.evaluate(() => document.querySelector("video")?.srcObject ?? null)).toBeNull();
    const summary = page.getByRole("region", { name: "Session" });
    await expect(summary.locator("[data-part=session-headline]")).toContainText("1 instruction · accepted at instruction 1");
    await expect(summary.locator("tbody tr")).toHaveCount(1);
    await expect(summary.locator("tbody tr").first()).toContainText("Reliable");
  });
});

test.describe("on a wide screen", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the running camera stays beside the measurements", async ({ page }) => {
    await stubCamera(page, 1080, 1920);
    await serve(page);
    await page.goto("/localise");
    await page.getByRole("button", { name: "Camera" }).click();

    await expect(page.getByText(/^Frame \d+$/)).toBeVisible();
    await expect(page.locator("[data-fullscreen=true]")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Exit" })).toHaveCount(0);
  });
});
