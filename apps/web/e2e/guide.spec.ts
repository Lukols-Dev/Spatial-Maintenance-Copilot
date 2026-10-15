import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import type { FrameAnswer } from "../lib/guide/types";
import { example, routeJson, stubHealth, stubWorkspace, type Stub } from "./helpers";

// The Guide page with Chrome's fake camera, which plays a .y4m file: grey
// frames at the size the synthetic phone was calibrated at, written here. The
// service is stubbed: its frame answers are the examples, the move first, then
// the reliable frame, then the open panel with the target's tag.

function y4m(width: number, height: number, frames: number): string {
  const folder = join(tmpdir(), "smc-guide-e2e");
  mkdirSync(folder, { recursive: true });
  const path = join(folder, `grey-${width}x${height}.y4m`);
  const header = Buffer.from(`YUV4MPEG2 W${width} H${height} F30:1 Ip A1:1 C420jpeg\n`);
  const frame = Buffer.concat([
    Buffer.from("FRAME\n"),
    Buffer.alloc(width * height, 128),
    Buffer.alloc((width / 2) * (height / 2) * 2, 128),
  ]);
  writeFileSync(path, Buffer.concat([header, ...Array<Buffer>(frames).fill(frame)]));
  return path;
}

const CAMERA = y4m(1080, 1920, 2);

function fakeCamera(file?: string) {
  return {
    permissions: ["camera"],
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        ...(file ? [`--use-file-for-fake-video-capture=${file}`] : []),
      ],
    },
  };
}

interface Service {
  frames: { count: number; answer: FrameAnswer };
  start: Stub;
  view: Stub;
  approval: Stub;
  inspect: Stub;
}

async function serve(page: Page): Promise<Service> {
  await stubHealth(page);
  await stubWorkspace(page, example("workspace-agent.json"));
  const frames = { count: 0, answer: example<FrameAnswer>("frame-answer-move.json") };
  await page.route("**/frames?**", async (route) => {
    frames.count += 1;
    await route.fulfill({ status: 201, json: frames.answer });
  });
  return {
    frames,
    start: await routeJson(page, "POST", "**/sessions", example("session-turn-move.json"), 201),
    view: await routeJson(page, "POST", "**/sessions/*/view", example("session-turn-approval.json")),
    approval: await routeJson(page, "POST", "**/sessions/*/approval", example("session-turn-accepted.json")),
    inspect: await routeJson(page, "POST", "**/frames/*/inspect", example("inspect-answer.json")),
  };
}

function hud(page: Page) {
  return page.getByRole("status");
}

test.use(fakeCamera(CAMERA));

test("the camera's frames are guided to a reliable result, approved, and the target confirmed", async ({ page }) => {
  test.setTimeout(60_000);
  const service = await serve(page);
  await page.goto("/guide");

  await page.getByRole("button", { name: "Camera" }).click();

  await expect(hud(page)).toHaveAttribute("data-cue", "MOVE_DOWN");
  await expect(hud(page)).toContainText("Move down");
  await expect(page.getByRole("progressbar", { name: "Toward the guide view" })).toBeVisible();
  const overlay = page.locator("svg[data-frame]");
  await expect(overlay.locator("[data-part=guide-outline]")).toHaveCount(1);
  await expect(overlay.locator("[data-part=occluder-label]")).toHaveText("Target behind: door");
  await expect(overlay.locator("[data-part=target-box]")).toHaveAttribute("data-hidden", "true");
  // The agent is told of the steady move with the frame that made it steady.
  await expect.poll(() => service.start.bodies.length).toBe(1);
  expect(service.start.bodies[0]).toEqual({ asset_id: "home-cabinet", view_set: "live", view: "0f1e2d3c4b5a" });

  service.frames.answer = example<FrameAnswer>("frame-answer.json");
  await expect(hud(page)).toHaveAttribute("data-cue", "ACCEPT");
  await expect(hud(page)).toContainText("Hold still");
  await expect.poll(() => service.view.bodies.length, { timeout: 15_000 }).toBe(1);
  expect(service.view.bodies[0]).toEqual({ view: "a1b2c3d4e5f6" });

  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Next step approved")).toBeVisible();
  expect(service.approval.bodies).toEqual([{ approved: true }]);

  service.frames.answer = example<FrameAnswer>("frame-answer-open.json");
  const target = page.locator("[data-part=sighting]");
  await expect(target).toContainText("Inside the 95 % region");
  await expect(target).toContainText("yes");
  await expect(page.locator("[data-part=second-opinion]")).toHaveAttribute("data-verdict", "yes");
  await expect(overlay.locator("[data-part=tag]")).toHaveAttribute("data-inside", "true");
  expect(service.inspect.bodies).toHaveLength(1);
  // Over the video, the tag takes the move's place.
  await expect(hud(page)).toHaveAttribute("data-cue", "IN_SIGHT");
  await expect(hud(page)).toContainText("Target in sight");
  await expect(hud(page)).toContainText("1.1 px from the prediction, inside the 95 % region");
  await expect(page.getByRole("progressbar", { name: "Toward the guide view" })).toHaveCount(0);

  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.getByRole("button", { name: "Camera" })).toBeVisible();
});
