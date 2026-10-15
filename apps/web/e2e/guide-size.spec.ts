import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { example, stubHealth, stubWorkspace } from "./helpers";

// The Guide page with Chrome's fake camera playing 640 × 480 frames, a size it
// cannot change on request: not the size the synthetic phone was calibrated
// at, so no frame is sent and the page says why.

function smallCamera(): string {
  const folder = join(tmpdir(), "smc-guide-e2e");
  mkdirSync(folder, { recursive: true });
  const path = join(folder, "grey-640x480.y4m");
  const frame = Buffer.concat([Buffer.from("FRAME\n"), Buffer.alloc(640 * 480 * 1.5, 128)]);
  writeFileSync(path, Buffer.concat([Buffer.from("YUV4MPEG2 W640 H480 F30:1 Ip A1:1 C420jpeg\n"), frame, frame]));
  return path;
}

test.use({
  permissions: ["camera"],
  launchOptions: {
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      `--use-file-for-fake-video-capture=${smallCamera()}`,
    ],
  },
});

test("frames of another size than the calibration are refused before they are sent", async ({ page }) => {
  await stubHealth(page);
  await stubWorkspace(page, example("workspace-agent.json"));
  let sent = 0;
  await page.route("**/frames?**", async (route) => {
    sent += 1;
    await route.fulfill({ status: 201, json: example("frame-answer.json") });
  });
  await page.goto("/guide");

  await page.getByRole("button", { name: "Camera" }).click();

  await expect(page.getByRole("alert").filter({ hasText: "calibrated" })).toHaveText(
    "The frames are 640 × 480 px; phone-1x-portrait was calibrated at 1080 × 1920 px",
  );
  expect(sent).toBe(0);
  await expect(page.getByRole("button", { name: "Camera" })).toBeVisible();
});
