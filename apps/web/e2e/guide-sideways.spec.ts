import { expect, test } from "@playwright/test";

import { example, stubCamera, stubHealth, stubWorkspace } from "./helpers";

// The Guide page with a camera giving 1920 × 1080 frames: the synthetic
// phone's calibration turned by a quarter, as a phone held sideways gives
// them. No frame is sent; the page asks for the phone upright and keeps the
// camera running, since turning the phone brings upright frames.

test.beforeEach(async ({ page }) => {
  await stubCamera(page, 1920, 1080);
});

test("a camera held sideways sends no frame and asks for the phone upright, still running", async ({ page }) => {
  await stubHealth(page);
  await stubWorkspace(page, example("workspace-agent.json"));
  let sent = 0;
  await page.route("**/frames?**", async (route) => {
    sent += 1;
    await route.fulfill({ status: 201, json: example("frame-answer.json") });
  });
  await page.goto("/localise");

  await page.getByRole("button", { name: "Camera" }).click();

  const notice = page.locator("[data-cue=SIDEWAYS]");
  await expect(notice).toContainText("Hold the phone upright");
  await expect(notice).toContainText("Frames 1920 × 1080 px, calibrated at 1080 × 1920 px");
  await expect(page.getByRole("alert").filter({ hasText: "calibrated" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  expect(sent).toBe(0);

  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.getByRole("button", { name: "Camera" })).toBeVisible();
});
