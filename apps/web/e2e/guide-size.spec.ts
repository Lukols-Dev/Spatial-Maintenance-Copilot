import { expect, test } from "@playwright/test";

import { example, stubCamera, stubHealth, stubWorkspace } from "./helpers";

// The Guide page with a camera giving 640 × 480 frames, a size no way of
// holding it turns into the one the synthetic phone was calibrated at, so no
// frame is sent and the page says why.

test.beforeEach(async ({ page }) => {
  await stubCamera(page, 640, 480);
});

test("frames of another size than the calibration are refused before they are sent", async ({ page }) => {
  await stubHealth(page);
  await stubWorkspace(page, example("workspace-agent.json"));
  let sent = 0;
  await page.route("**/frames?**", async (route) => {
    sent += 1;
    await route.fulfill({ status: 201, json: example("frame-answer.json") });
  });
  await page.goto("/localise");

  await page.getByRole("button", { name: "Camera" }).click();

  await expect(page.getByRole("alert").filter({ hasText: "calibrated" })).toHaveText(
    "The frames are 640 × 480 px; phone-1x-portrait was calibrated at 1080 × 1920 px",
  );
  expect(sent).toBe(0);
  await expect(page.getByRole("button", { name: "Camera" })).toBeVisible();
});
