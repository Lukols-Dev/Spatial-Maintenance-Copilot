import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "@playwright/test";

import type { ClicksFile } from "../lib/annotate/core";
import type { ViewSet, Workspace } from "../lib/workspace";
import {
  canvas,
  example,
  makeViews,
  routeJson,
  screenOf,
  stubHealth,
  stubWorkspace,
  viewScale,
  waitForImage,
  type Stub,
} from "./helpers";

// view-set.json is "cabinet": three 1080×1920 PNGs and clicks of four points,
// corner_left marked in one image only. workspace.json has one camera of that size.
const SET = example<ViewSet>("view-set.json");
const CLICKS = SET.clicks as Required<ClicksFile>;
const FILES = SET.images.map((image) => image.file);
const CAMERA = "iphone11-1x-1080p-portrait";
const SAVED = /^Saved \d\d:\d\d:\d\d$/;

interface Service {
  /** GET /view-sets/cabinet */
  viewSet: Stub;
  /** PUT /view-sets/cabinet/clicks */
  clicks: Stub;
  /** The images the page asked for. */
  images: string[];
  /** Answer for this image only once the returned function is called. */
  holdImage(file: string): () => void;
}

/**
 * The perception service with the cabinet set, its images drawn in the page.
 * Nothing reaches a real one. The page's clock is a fake that runs as usual,
 * so a test can move it past the save debounce to see that nothing was sent.
 */
async function serve(page: Page, options: { viewSet?: ViewSet | null; workspace?: Workspace } = {}): Promise<Service> {
  await page.clock.install();
  // Registered first, so it only gets what no stub below answers.
  await page.route("**/view-sets/**", (route) => route.abort("connectionrefused"));
  await stubHealth(page);
  await stubWorkspace(page, options.workspace ?? example<Workspace>("workspace.json"));
  const viewSet = await routeJson(page, "GET", "**/view-sets/cabinet", options.viewSet ?? SET);
  const clicks = await routeJson(page, "PUT", "**/view-sets/cabinet/clicks", example("clicks-summary.json"));

  const views = await makeViews(page, FILES.map((name) => ({ name, dots: {} })));
  const images: string[] = [];
  const held = new Map<string, Promise<void>>();
  await page.route("**/view-sets/cabinet/images/*", async (route) => {
    const file = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    images.push(file);
    await held.get(file);
    const view = views.find((candidate) => candidate.name === file);
    if (view) await route.fulfill({ contentType: "image/png", body: view.buffer });
    else await route.fulfill({ status: 404, json: { detail: `no image '${file}' in view set 'cabinet'` } });
  });

  return {
    viewSet,
    clicks,
    images,
    holdImage(file) {
      const { promise, resolve } = Promise.withResolvers<void>();
      held.set(file, promise);
      return resolve;
    },
  };
}

async function openCabinet(page: Page) {
  await page.goto("/annotate/?set=cabinet");
  await waitForImage(page, FILES[0]);
}

/**
 * Whether the page sends its clicks once a change waiting to be saved is due:
 * the clock moves past the debounce, and a request it starts shows within moments.
 */
async function sendsClicks(page: Page): Promise<boolean> {
  const put = page.waitForRequest((request) => request.method() === "PUT", { timeout: 500 }).then(
    () => true,
    () => false,
  );
  await page.clock.runFor(2000);
  return put;
}

/** The point's button; its name also says whether the point is marked in the image on screen. */
function pointButton(page: Page, name: string) {
  return page.getByRole("button", { name: new RegExp(`^${name}, (not )?marked in this image, `) });
}

function imageButton(page: Page, file: string) {
  return page.getByRole("button", { name: new RegExp(`^${file.replaceAll(".", "\\.")}`) });
}

async function clickPixel(page: Page, pixel: [number, number]) {
  const [x, y] = await screenOf(page, pixel);
  await page.mouse.click(x, y);
}

/** Download clicks.json and read it: the state the page has. */
async function downloadClicks(page: Page): Promise<ClicksFile> {
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download clicks.json" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("clicks.json");
  return JSON.parse(await readFile((await file.path()) as string, "utf8"));
}

/** The alert next to the save status. */
function saveProblem(page: Page) {
  return page.getByRole("alert").filter({ hasText: /not saved/i });
}

test("a view set opens with its images, its points in order and its clicks", async ({ page }) => {
  const service = await serve(page);
  const release = service.holdImage(FILES[2]);
  await page.goto("/annotate/?set=cabinet");
  await expect(page.getByText("Loading 2 / 3")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Images loaded" })).toHaveAttribute("aria-valuetext", "2 of 3");
  release();
  await waitForImage(page, FILES[0]);
  expect([...service.images].sort()).toEqual(FILES);

  await expect(page.getByRole("definition")).toHaveText("cabinet");
  await expect(page.getByLabel("Camera id")).toHaveValue(CAMERA);
  await expect(page.getByRole("status").filter({ hasText: "3 image(s) opened." })).toBeVisible();

  // The points in the order of the file, with the images each is marked in.
  const rows = page.locator("[data-point]");
  await expect.poll(() => rows.evaluateAll((all) => all.map((row) => row.getAttribute("data-point")))).toEqual(
    CLICKS.points,
  );
  await expect(pointButton(page, "hinge_top")).toHaveAccessibleName("hinge_top, marked in this image, 3 views");
  await expect(pointButton(page, "handle")).toHaveAccessibleName("handle, marked in this image, 2 views");
  await expect(pointButton(page, "corner_left")).toHaveAccessibleName(
    "corner_left, not marked in this image, 1 view, needs 2",
  );
  await expect(pointButton(page, "drone")).toHaveAccessibleName("drone, marked in this image, 2 views");
  await expect(imageButton(page, FILES[0])).toContainText("3/4");
  await expect(imageButton(page, FILES[1])).toContainText("4/4");
  await expect(imageButton(page, FILES[2])).toContainText("1/4");

  // Opening changes nothing, so nothing is sent; the page holds the set's clicks as they are.
  expect(await sendsClicks(page)).toBe(false);
  expect(await downloadClicks(page)).toEqual(CLICKS);
  await expect(page.getByRole("status").filter({ hasText: "Downloaded clicks.json." })).toBeVisible();
});

test("without clicks, the camera is the only one of the set's size, and opening saves nothing", async ({ page }) => {
  const service = await serve(page, { viewSet: { ...SET, clicks: null } });
  await openCabinet(page);
  await expect(page.getByLabel("Camera id")).toHaveValue(CAMERA);
  await expect(page.locator("[data-point]")).toHaveCount(0);
  expect(await sendsClicks(page)).toBe(false);

  await page.getByLabel("New point id").fill("hinge_top");
  await page.getByLabel("New point id").press("Enter");
  await expect(page.getByText(SAVED)).toBeVisible();
  expect(service.clicks.bodies).toEqual([{ camera_id: CAMERA, points: ["hinge_top"], views: {} }]);
});

test("marks are saved to the set, several quick ones in one request", async ({ page }) => {
  const service = await serve(page);
  await openCabinet(page);
  await imageButton(page, FILES[2]).click();
  await waitForImage(page, FILES[2]);
  await pointButton(page, "handle").click();
  const bound = (0.5 * Math.SQRT2) / (await viewScale(page));

  // handle, then corner_left and drone, each picked by auto-advance.
  service.clicks.hold();
  const marks: [number, number][] = [
    [688, 1003],
    [120, 1500],
    [530, 1190],
  ];
  for (const pixel of marks) await clickPixel(page, pixel);
  await expect(page.getByText("Saving…")).toBeVisible();
  await expect.poll(() => service.clicks.bodies.length).toBe(1);
  service.clicks.release();
  await expect(page.getByText(SAVED)).toBeVisible();
  expect(service.clicks.bodies).toHaveLength(1);

  // What was sent is the page's state, which is also what it downloads.
  const sent = service.clicks.bodies[0] as Required<ClicksFile>;
  expect(sent).toEqual(await downloadClicks(page));
  expect(sent.camera_id).toBe(CAMERA);
  expect(sent.points).toEqual(CLICKS.points);
  expect(Object.keys(sent.views[FILES[2]])).toEqual(CLICKS.points);
  for (const [index, name] of ["handle", "corner_left", "drone"].entries()) {
    const [x, y] = sent.views[FILES[2]][name];
    expect(Math.hypot(x - marks[index][0], y - marks[index][1])).toBeLessThanOrEqual(bound);
  }
  expect(sent.views[FILES[0]]).toEqual(CLICKS.views[FILES[0]]);
  expect(sent.views[FILES[1]]).toEqual(CLICKS.views[FILES[1]]);
});

test("a failed save says why, and Retry sends it again", async ({ page }) => {
  const service = await serve(page);
  await openCabinet(page);
  service.clicks.reply({ detail: "cannot write data/views/cabinet/clicks.json" }, 500);
  await pointButton(page, "corner_left").click();
  await clickPixel(page, [120, 1500]);
  await expect(saveProblem(page)).toHaveText("Not saved: cannot write data/views/cabinet/clicks.json");

  service.clicks.reply(example("clicks-summary.json"));
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText(SAVED)).toBeVisible();
  await expect(saveProblem(page)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0);
  expect(service.clicks.bodies).toHaveLength(2);
  expect(service.clicks.bodies[1]).toEqual(service.clicks.bodies[0]);

  // A service that cannot be reached is said as such; the next change tries again.
  service.clicks.goOffline();
  await clickPixel(page, [130, 1510]);
  await expect(saveProblem(page)).toHaveText(/^Not saved: Cannot reach the perception service at /);
  service.clicks.reply(example("clicks-summary.json"));
  await clickPixel(page, [140, 1520]);
  await expect(page.getByText(SAVED)).toBeVisible();
  expect(service.clicks.bodies).toHaveLength(4);
});

test("a read-only service keeps the marks on the page and says they are not saved", async ({ page }) => {
  const service = await serve(page);
  await openCabinet(page);
  service.clicks.reply({ detail: "the service is read-only" }, 403);
  await pointButton(page, "corner_left").click();
  await clickPixel(page, [120, 1500]);
  await expect(saveProblem(page)).toHaveText("Read-only service: not saved");
  await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0);

  // The service refuses every change, so later ones are not sent.
  await clickPixel(page, [130, 1510]);
  expect(await sendsClicks(page)).toBe(false);
  expect(service.clicks.bodies).toHaveLength(1);
  await expect(pointButton(page, "corner_left")).toHaveAccessibleName(/^corner_left, marked in this image, 2 views$/);
});

test("a workspace that says it is read-only is sent no changes", async ({ page }) => {
  const workspace = example<Workspace>("workspace.json");
  const service = await serve(page, { workspace: { ...workspace, read_only: true } });
  await openCabinet(page);
  await expect(page.getByText("Read-only service", { exact: true })).toBeVisible();

  await pointButton(page, "corner_left").click();
  await clickPixel(page, [120, 1500]);
  await expect(saveProblem(page)).toHaveText("Read-only service: not saved");
  expect(await sendsClicks(page)).toBe(false);
  expect(service.clicks.bodies).toEqual([]);
});

test("an unknown view set says so, with Retry and a way to files from disk", async ({ page }) => {
  await stubHealth(page);
  await stubWorkspace(page, example("workspace.json"));
  const nope = await routeJson(page, "GET", "**/view-sets/nope", { detail: "no view set named 'nope'" }, 404);
  await page.goto("/annotate/?set=nope");
  const failure = page.getByRole("alert").filter({ hasText: "Cannot open nope" });
  await expect(failure).toHaveText(/^Cannot open nope.*no view set named 'nope'$/);

  await page.getByRole("link", { name: "Local files" }).click();
  await expect(page).toHaveURL(/\/annotate\/$/);
  await expect(page.getByLabel("New point id")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open images…" }).first()).toBeVisible();

  // Asked again once the set exists, here still without images.
  await page.goBack();
  await expect(failure).toContainText("no view set named 'nope'");
  nope.reply({ name: "nope", images: [], clicks: null, clicks_error: null });
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("No images in nope")).toBeVisible();
  await expect(page.getByRole("definition")).toHaveText("nope");
});

test("a name that cannot be a view set is not asked for", async ({ page }) => {
  await stubHealth(page);
  await stubWorkspace(page, example("workspace.json"));
  const asked: string[] = [];
  await page.route("**/view-sets/**", async (route) => {
    asked.push(route.request().url());
    await route.abort("connectionrefused");
  });
  await page.goto(`/annotate/?set=${encodeURIComponent("../calib")}`);
  await expect(page.getByRole("alert").filter({ hasText: "Invalid view set name" })).toHaveText(
    "Invalid view set name../calib",
  );
  await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Local files" })).toBeVisible();
  expect(asked).toEqual([]);
});

test("a view set leaves the local session alone, and the local session still comes back", async ({ page }) => {
  await serve(page);
  await page.goto("/annotate/");
  await page.getByLabel("Camera id").fill("phone-0.5x");
  await page.getByLabel("New point id").fill("local_point");
  await page.getByLabel("New point id").press("Enter");
  await expect(pointButton(page, "local_point")).toBeVisible();
  const session = () => page.evaluate(() => localStorage.getItem("smc-annotate:v1"));
  const before = await session();
  expect(before).toContain("local_point");

  await openCabinet(page);
  await expect(page.getByLabel("Camera id")).toHaveValue(CAMERA);
  await expect(pointButton(page, "local_point")).toHaveCount(0);
  await pointButton(page, "corner_left").click();
  await clickPixel(page, [120, 1500]);
  await page.getByLabel("Camera id").fill("phone-1x");
  await expect(page.getByText(SAVED)).toBeVisible();
  expect(await session()).toBe(before);

  await page.goto("/annotate/");
  await expect(page.getByText(/Restored 1 point\(s\) from your last session/)).toBeVisible();
  await expect(page.getByLabel("Camera id")).toHaveValue("phone-0.5x");
  await expect(pointButton(page, "local_point")).toBeVisible();
  await expect(pointButton(page, "hinge_top")).toHaveCount(0);
});

test("files from disk can be neither opened nor dropped on a view set", async ({ page }) => {
  await serve(page);
  await openCabinet(page);
  await expect(page.getByRole("button", { name: "Open images…" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open clicks.json…" })).toHaveCount(0);
  await expect(page.getByLabel("Open images")).toHaveCount(0);
  await expect(page.getByLabel("Open clicks.json")).toHaveCount(0);

  const [view] = await makeViews(page, [{ name: "other.png", dots: {} }]);
  const drops = await page.evaluate((data) => {
    const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
    return ['aside[aria-label="Points"]', "canvas[data-image]"].map((selector) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([bytes], "other.png", { type: "image/png" }));
      transfer.dropEffect = "copy";
      const target = document.querySelector(selector);
      if (!target) throw new Error(`nothing at ${selector}`);
      target.dispatchEvent(new DragEvent("dragover", { dataTransfer: transfer, bubbles: true, cancelable: true }));
      const effect = transfer.dropEffect;
      const drop = new DragEvent("drop", { dataTransfer: transfer, bubbles: true, cancelable: true });
      // dispatchEvent is false when the drop was cancelled: the browser would not leave the page for the file.
      return { effect, cancelled: !target.dispatchEvent(drop) };
    });
  }, view.buffer.toString("base64"));
  expect(drops).toEqual([
    { effect: "none", cancelled: true },
    { effect: "none", cancelled: true },
  ]);
  await expect(page).toHaveURL(/\/annotate\/\?set=cabinet$/);
  await expect(canvas(page)).toHaveAttribute("data-image", FILES[0]);
  await expect(page.getByRole("button", { name: /^(frame_|other)/ })).toHaveCount(3);
});

test("a change not yet sent goes out at once when the tab is hidden, the page goes or a link leaves", async ({
  page,
}) => {
  const service = await serve(page);
  await openCabinet(page);
  // Time stands still from here: the debounce never fires, so a request can only come from leaving.
  await page.clock.pauseAt(Date.now() + 5000);
  await pointButton(page, "corner_left").click();
  const sentMark = async (pixel: [number, number], count: number) => {
    await clickPixel(page, pixel);
    await expect(page.getByText("Saving…")).toBeVisible();
    expect(service.clicks.bodies).toHaveLength(count - 1);
    return async () => {
      await expect.poll(() => service.clicks.bodies.length).toBe(count);
      const [x, y] = (service.clicks.bodies[count - 1] as ClicksFile).views[FILES[0]].corner_left;
      expect(Math.hypot(x - pixel[0], y - pixel[1])).toBeLessThan(5);
    };
  };

  // Another tab is brought to the front. (Playwright cannot watch a real unload: its routing
  // drops a keepalive request that needs a CORS preflight, which Chrome itself sends.)
  let sent = await sentMark([120, 1500], 1);
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await sent();
  await expect(page.getByText(SAVED)).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
    document.dispatchEvent(new Event("visibilitychange"));
  });

  // The page is closed or replaced.
  sent = await sentMark([130, 1510], 2);
  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent("pagehide", { persisted: false })));
  await sent();

  // A link inside the app removes the annotator without unloading the page.
  sent = await sentMark([140, 1520], 3);
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Annotate" }).click();
  await expect(page).toHaveURL(/\/annotate\/$/);
  await sent();
  // The annotator for files from disk waits for timers to load.
  await page.clock.resume();
  await expect(page.getByLabel("New point id")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open images…" }).first()).toBeVisible();
});

test("leaving the page asks first only while a change is not saved", async ({ page }) => {
  const service = await serve(page);
  const dialogs: string[] = [];
  // The visitor stays: nothing unloads, so nothing can be lost or escape the stubs.
  page.on("dialog", (dialog) => {
    dialogs.push(dialog.type());
    void dialog.dismiss();
  });
  await openCabinet(page);
  await pointButton(page, "corner_left").click();
  service.clicks.hold();
  await clickPixel(page, [120, 1500]);
  await expect.poll(() => service.clicks.bodies.length).toBe(1);

  // A full page load of the home page, which the visitor then cancels.
  await page.evaluate(() => window.location.assign(window.location.origin));
  await expect.poll(() => dialogs).toEqual(["beforeunload"]);
  await expect(page).toHaveURL(/\/annotate\/\?set=cabinet$/);

  service.clicks.release();
  await expect(page.getByText(SAVED)).toBeVisible();
  await page.goto("/");
  await expect(page).toHaveURL(/:\d+\/$/);
  expect(dialogs).toEqual(["beforeunload"]);
});
