import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "@playwright/test";

import {
  canvas,
  makeViews,
  savedState,
  screenOf,
  stubHealth,
  viewOf,
  viewScale,
  waitForImage,
  type View,
} from "./helpers";

// Three views of the same three points. In view_2 the corner is outside the frame.
const VIEWS: View[] = [
  { name: "view_0.png", dots: { corner_top_left: [166, 321], handle_screw: [537, 828], drone: [614, 749] } },
  { name: "view_1.png", dots: { corner_top_left: [302, 650], handle_screw: [550, 1018], drone: [635, 1203] } },
  { name: "view_2.png", dots: { handle_screw: [393, 863], drone: [270, 842] } },
];
const POINTS = ["corner_top_left", "handle_screw", "drone"];

async function addPoint(page: Page, name: string) {
  await page.getByLabel("New point id").fill(name);
  await page.getByLabel("New point id").press("Enter");
}

async function openViews(page: Page, views: View[] = VIEWS) {
  await page.getByLabel("Open images").setInputFiles(await makeViews(page, views));
  await waitForImage(page, views[0].name);
}

/** The point's button; its name also says whether the point is marked in the image on screen. */
function pointButton(page: Page, name: string) {
  return page.getByRole("button", { name: new RegExp(`^${name}, (not )?marked in this image, `) });
}

async function selectPoint(page: Page, name: string) {
  await pointButton(page, name).click();
}

async function clickPixel(page: Page, pixel: [number, number]) {
  const [x, y] = await screenOf(page, pixel);
  await page.mouse.click(x, y);
}

/** Move to another image with the keyboard, from the canvas. */
async function nextImage(page: Page, name: string) {
  await canvas(page).focus();
  await page.keyboard.press("]");
  await waitForImage(page, name);
}

test.beforeEach(async ({ page }) => {
  await stubHealth(page);
  await page.goto("/annotate/");
  // The annotator is loaded in the browser after the page; wait until it is there.
  await expect(page.getByLabel("New point id")).toBeVisible();
});

test("marks points with the mouse, zoomed and not, to half a screen pixel", async ({ page }) => {
  await page.getByLabel("Camera id").fill("phone-1x-portrait");
  for (const name of POINTS) await addPoint(page, name);
  await openViews(page);

  const worst = { zoomed: 0, fit: 0 };
  for (const [index, view] of VIEWS.entries()) {
    if (index > 0) await nextImage(page, view.name);
    for (const [name, pixel] of Object.entries(view.dots)) {
      await selectPoint(page, name);
      const zoomed = index === 0;
      if (zoomed) {
        const [x, y] = await screenOf(page, pixel);
        await page.mouse.move(x, y);
        for (let step = 0; step < 3; step++) await page.mouse.wheel(0, -600);
        await expect.poll(() => viewScale(page)).toBeGreaterThan(2);
      }
      const scale = await viewScale(page);
      await clickPixel(page, pixel);
      await expect(pointButton(page, name)).toHaveAccessibleName(new RegExp(`^${name}, marked in this image`));
      if (zoomed) await page.keyboard.press("0");

      // A mouse position is a whole screen pixel: a click is exact to half a screen pixel per axis.
      const [x, y] = (await savedState(page)).clicks[view.name][name];
      const error = Math.hypot(x - pixel[0], y - pixel[1]) / ((0.5 * Math.SQRT2) / scale);
      worst[zoomed ? "zoomed" : "fit"] = Math.max(worst[zoomed ? "zoomed" : "fit"], error);
    }
  }
  expect(worst.zoomed).toBeLessThanOrEqual(1);
  expect(worst.fit).toBeLessThanOrEqual(1);

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save clicks.json" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("clicks.json");
  const saved = JSON.parse(await readFile((await file.path()) as string, "utf8"));
  expect(saved.camera_id).toBe("phone-1x-portrait");
  expect(Object.keys(saved.views)).toEqual(["view_0.png", "view_1.png", "view_2.png"]);
  expect(Object.keys(saved.views["view_2.png"])).toEqual(["handle_screw", "drone"]);
});

test("the keyboard alone marks points, and the view follows the cursor", async ({ page }) => {
  for (const name of ["corner", "drone", "spare"]) await addPoint(page, name);
  await openViews(page);
  await selectPoint(page, "corner");

  // Tab from the image list onto the canvas: the cursor is there at once, at the
  // centre of the view on a whole pixel, and the status bar reads out where.
  await page.getByRole("button", { name: /^view_2\.png/ }).focus();
  await page.keyboard.press("Tab");
  await expect(canvas(page)).toBeFocused();
  // The focus frame is a layer above the image (black and white bands), shown while the canvas has keyboard focus.
  const frame = page.locator('[data-slot="canvas-focus"]');
  const look = await frame.evaluate((element) => {
    const style = getComputedStyle(element);
    return { display: style.display, shadow: style.boxShadow };
  });
  expect(look.display).toBe("block");
  expect(look.shadow).toContain("inset");
  await page.getByRole("button", { name: /^view_2\.png/ }).focus();
  await expect(frame).toBeHidden();
  await page.keyboard.press("Tab");
  const readout = page.getByText(/^x \d+\.0\s+y \d+\.0/);
  const position = async (): Promise<[number, number]> => {
    const [, x, y] = ((await readout.textContent()) ?? "").match(/^x (\d+)\.0\s+y (\d+)\.0/) ?? [];
    return [Number(x), Number(y)];
  };
  const centre = await position();
  await page.keyboard.press("Enter");
  expect((await savedState(page)).clicks["view_0.png"].corner).toEqual(centre);
  await expect(page.getByRole("status").filter({ hasText: /^Marked corner at x \d+, y \d+\. Next: drone\.$/ })).toBeVisible();

  // The arrows move it by one pixel, with Shift by ten.
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Shift+ArrowDown");
  const moved = await position();
  expect(moved).toEqual([centre[0] + 2, centre[1] + 10]);

  // A held Enter marks the selected point once. Its repeats would mark the next
  // point, already selected by auto-advance, at the same pixel.
  await page.keyboard.down("Enter");
  await page.keyboard.down("Enter");
  await page.keyboard.up("Enter");
  const clicks = (await savedState(page)).clicks["view_0.png"];
  expect(clicks.drone).toEqual(moved);
  expect(clicks.spare).toBeUndefined();

  // Zoomed in, a long move pans the view so the cursor stays on screen.
  for (let step = 0; step < 8; step++) await page.keyboard.press("+");
  const before = await viewOf(page);
  for (let step = 0; step < 30; step++) await page.keyboard.press("Shift+ArrowRight");
  const after = await viewOf(page);
  expect(after.x).toBeLessThan(before.x);
  const box = await canvas(page).boundingBox();
  const [sx] = await screenOf(page, [moved[0] + 300, moved[1]]);
  expect(sx).toBeGreaterThan(box!.x);
  expect(sx).toBeLessThan(box!.x + box!.width);
});

test("shortcuts only act in the workspace, never while typing or in a dialog", async ({ page }) => {
  for (const name of POINTS) await addPoint(page, name);
  await openViews(page);
  await selectPoint(page, "corner_top_left");

  // Typed into the name field: a character, not a shortcut.
  await page.getByLabel("New point id").fill("");
  await page.getByLabel("New point id").press("2");
  await expect(pointButton(page, "handle_screw")).toHaveAttribute("aria-pressed", "false");
  await page.getByLabel("New point id").fill("");

  // Focus in the sidebar: outside the workspace.
  await page.getByRole("link", { name: "Source on GitHub" }).focus();
  await page.keyboard.press("2");
  await page.keyboard.press("]");
  await expect(pointButton(page, "handle_screw")).toHaveAttribute("aria-pressed", "false");
  await expect(canvas(page)).toHaveAttribute("data-image", "view_0.png");

  // Inside a dialog. While it is open the page behind it is hidden, so check after closing it.
  await page.getByRole("button", { name: "Rename drone" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).focus();
  await page.keyboard.press("3");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(pointButton(page, "drone")).toHaveAttribute("aria-pressed", "false");
  await expect(pointButton(page, "corner_top_left")).toHaveAttribute("aria-pressed", "true");

  // In the workspace they work: digits, S, and the image keys.
  await canvas(page).focus();
  await page.keyboard.press("2");
  await expect(pointButton(page, "handle_screw")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("status").filter({ hasText: "Marking handle_screw." })).toBeVisible();
  // The same words again are a new announcement: a new element in the live region.
  const said = await page.getByRole("status").locator("span").elementHandle();
  await page.keyboard.press("1");
  await page.keyboard.press("2");
  expect(await said?.evaluate((element) => element.isConnected)).toBe(false);
  await page.keyboard.press("s");
  await expect(pointButton(page, "drone")).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Shift+S");
  await expect(pointButton(page, "handle_screw")).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("PageDown");
  await waitForImage(page, "view_1.png");
  await expect(page.getByRole("status").filter({ hasText: "Image 2 of 3: view_1.png." })).toBeVisible();
  await page.keyboard.press("[");
  await waitForImage(page, "view_0.png");

  // Switched off, single keys do nothing; PageDown is not a character key and still works.
  await page.getByLabel("Single-key shortcuts").uncheck();
  await canvas(page).focus();
  await page.keyboard.press("3");
  await page.keyboard.press("]");
  await expect(pointButton(page, "drone")).toHaveAttribute("aria-pressed", "false");
  await expect(canvas(page)).toHaveAttribute("data-image", "view_0.png");
  await page.keyboard.press("PageDown");
  await waitForImage(page, "view_1.png");
});

test("keyboard focus on the lists is visible", async ({ page }) => {
  await addPoint(page, "drone");
  await openViews(page);
  await page.getByLabel("New point id").focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  const row = pointButton(page, "drone");
  await expect(row).toBeFocused();
  const outline = await row.evaluate((element) => {
    const style = getComputedStyle(element);
    return { style: style.outlineStyle, width: style.outlineWidth };
  });
  expect(outline).toEqual({ style: "solid", width: "2px" });
});

test("Backspace removes a mark only from the image, and says so", async ({ page }) => {
  await addPoint(page, "drone");
  await openViews(page);
  await clickPixel(page, VIEWS[0].dots.drone);
  await expect(pointButton(page, "drone")).toHaveAccessibleName(/^drone, marked in this image/);
  await expect(page.getByRole("status").filter({ hasText: /^Marked drone at x/ })).toBeVisible();

  await pointButton(page, "drone").focus();
  await page.keyboard.press("Backspace");
  await expect(pointButton(page, "drone")).toHaveAccessibleName(/^drone, marked in this image/);

  await canvas(page).focus();
  await page.keyboard.press("Backspace");
  await expect(pointButton(page, "drone")).toHaveAccessibleName(/^drone, not marked in this image/);
  await expect(page.getByRole("status").filter({ hasText: "Removed the mark of drone in view_0.png" })).toBeVisible();
});

test("the zoom keys zoom and fit", async ({ page }) => {
  await addPoint(page, "drone");
  await openViews(page);
  const fit = await viewScale(page);
  await canvas(page).focus();

  await page.keyboard.press("+");
  await expect.poll(() => viewScale(page)).toBeCloseTo(fit * 1.4, 6);
  await page.keyboard.press("-");
  await expect.poll(() => viewScale(page)).toBeCloseTo(fit, 6);
  await page.keyboard.press("+");
  await page.keyboard.press("+");
  await page.keyboard.press("0");
  await expect.poll(() => viewScale(page)).toBeCloseTo(fit, 6);
});

test("a point in fewer than two views is flagged until it has two", async ({ page }) => {
  await addPoint(page, "drone");
  await openViews(page);
  const badge = page.locator('[data-slot="badge"]', { hasText: /view/ });

  await expect(badge).toHaveText("0 views · needs 2");
  await expect(badge).toHaveAttribute("data-variant", "destructive");
  await clickPixel(page, VIEWS[0].dots.drone);
  await expect(badge).toHaveText("1 view · needs 2");
  await expect(badge).toHaveAttribute("data-variant", "destructive");
  // Screen readers hear the warning too.
  await expect(pointButton(page, "drone")).toHaveAccessibleName(/, 1 view, needs 2$/);
  await nextImage(page, "view_1.png");
  await clickPixel(page, VIEWS[1].dots.drone);
  await expect(badge).toHaveText("2 views");
  await expect(badge).toHaveAttribute("data-variant", "secondary");
  await expect(pointButton(page, "drone")).toHaveAccessibleName(/, 2 views$/);
});

test("names are checked, and rename and delete keep the focus in the list", async ({ page }) => {
  await addPoint(page, "two words");
  await expect(page.getByRole("alert").filter({ hasText: /Use letters, digits/ })).toBeVisible();

  await addPoint(page, "corner");
  await addPoint(page, "badge");
  await page.getByRole("button", { name: "Rename corner" }).click();
  const rename = page.getByRole("dialog");
  await rename.getByLabel("New name").fill("badge");
  await rename.getByRole("button", { name: "Rename" }).click();
  await expect(rename.getByRole("alert")).toHaveText('"badge" already exists.');
  await rename.getByLabel("New name").fill("corner_top_left");
  await rename.getByRole("button", { name: "Rename" }).click();
  await expect(pointButton(page, "corner_top_left")).toBeFocused();

  await page.getByRole("button", { name: "Delete corner_top_left" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();
  await expect(pointButton(page, "corner_top_left")).toHaveCount(0);
  await expect(pointButton(page, "badge")).toBeFocused();

  await page.getByRole("button", { name: "Delete badge" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();
  await expect(page.getByLabel("New point id")).toBeFocused();
});

test("only real PNG files open, each under its own name", async ({ page }) => {
  const status = page.getByRole("status");

  const jpeg = await makeViews(page, [{ name: "IMG_0001.jpg", dots: {} }], "image/jpeg");
  await page.getByLabel("Open images").setInputFiles(jpeg);
  await expect(status.filter({ hasText: "not PNG" })).toBeVisible();

  // A JPEG renamed to .png is still a JPEG: the browser would turn it by its EXIF tag.
  await page.getByLabel("Open images").setInputFiles([{ ...jpeg[0], name: "renamed.png", mimeType: "image/png" }]);
  await expect(status.filter({ hasText: "1 file(s) skipped because they are not PNG" })).toBeVisible();
  await expect(canvas(page)).toHaveAttribute("data-image", "");

  const [view] = await makeViews(page, [VIEWS[0]]);
  await page.getByLabel("Open images").setInputFiles([view, { ...view, name: view.name }]);
  await expect(status.filter({ hasText: "more than one image is called view_0.png" })).toBeVisible();

  const broken = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.from("no image")]);
  await page.getByLabel("Open images").setInputFiles([{ name: "broken.png", mimeType: "image/png", buffer: broken }]);
  await expect(status.filter({ hasText: "Cannot decode broken.png" })).toBeVisible();
});

test("images dropped beside the canvas open instead of leaving the page", async ({ page }) => {
  const [view] = await makeViews(page, [VIEWS[0]]);
  await page.evaluate(
    ({ data, name }) => {
      const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
      const transfer = new DataTransfer();
      transfer.items.add(new File([bytes], name, { type: "image/png" }));
      const target = document.querySelector('aside[aria-label="Points"]');
      if (!target) throw new Error("no points panel");
      for (const type of ["dragover", "drop"]) {
        target.dispatchEvent(new DragEvent(type, { dataTransfer: transfer, bubbles: true, cancelable: true }));
      }
    },
    { data: view.buffer.toString("base64"), name: view.name },
  );
  await waitForImage(page, "view_0.png");
  await expect(page).toHaveURL(/\/annotate\/$/);

  const drop = (selector: string, name: string, type: string, data: string) =>
    page.evaluate(
      ({ selector, name, type, data }) => {
        const transfer = new DataTransfer();
        transfer.items.add(new File([data], name, { type }));
        const target = document.querySelector(selector);
        if (!target) throw new Error(`nothing at ${selector}`);
        for (const event of ["dragover", "drop"]) {
          target.dispatchEvent(new DragEvent(event, { dataTransfer: transfer, bubbles: true, cancelable: true }));
        }
      },
      { selector, name, type, data },
    );

  const clicks = JSON.stringify({ camera_id: "phone-1x-portrait", views: { "view_0.png": { drone: [614, 749] } } });
  await drop('aside[aria-label="Points"]', "clicks.json", "application/json", clicks);
  await expect(page.getByRole("status").filter({ hasText: "Read 1 image(s) and 1 new point(s) from clicks.json." })).toBeVisible();

  // Dropped together, a clicks file and two images of the same name: the refusal comes first and stays.
  await page.evaluate(
    ({ data, json }) => {
      const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
      const transfer = new DataTransfer();
      transfer.items.add(new File([json], "more.json", { type: "application/json" }));
      transfer.items.add(new File([bytes], "view_0.png", { type: "image/png" }));
      transfer.items.add(new File([bytes], "view_0.png", { type: "image/png" }));
      const target = document.querySelector('aside[aria-label="Points"]');
      for (const type of ["dragover", "drop"]) {
        target?.dispatchEvent(new DragEvent(type, { dataTransfer: transfer, bubbles: true, cancelable: true }));
      }
    },
    { data: view.buffer.toString("base64"), json: JSON.stringify({ camera_id: "phone-1x-portrait", views: {} }) },
  );
  await expect(page.getByRole("status")).toHaveText(
    /^No image opened: more than one image is called view_0\.png\..* Read 0 image\(s\) and 0 new point\(s\) from more\.json\.$/,
  );

  await page.getByRole("button", { name: "Rename drone" }).click();
  await drop("[role=dialog]", "other.png", "image/png", "ignored");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(canvas(page)).toHaveAttribute("data-image", "view_0.png");
});

test("the work survives a reload", async ({ page }) => {
  await page.getByLabel("Camera id").fill("phone-1x-portrait");
  await addPoint(page, "drone");
  await openViews(page);
  await clickPixel(page, VIEWS[0].dots.drone);

  await page.reload();
  await expect(page.getByText(/Restored 1 point\(s\) from your last session/)).toBeVisible();
  await expect(page.getByLabel("Camera id")).toHaveValue("phone-1x-portrait");
  await openViews(page);
  await expect(pointButton(page, "drone")).toHaveAccessibleName(/^drone, marked in this image/);
});

test("a saved clicks file opens again, but not for another camera", async ({ page }) => {
  const file = (camera: string) => ({
    name: "clicks.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({ camera_id: camera, views: { "view_0.png": { corner_top_left: [166, 321], drone: [614, 749] } } }),
    ),
  });
  await page.getByLabel("Open clicks.json").setInputFiles(file("phone-1x-portrait"));
  await expect(page.getByText(/Read 1 image\(s\) and 2 new point\(s\)/)).toBeVisible();
  await expect(page.getByLabel("Camera id")).toHaveValue("phone-1x-portrait");
  await expect(pointButton(page, "corner_top_left")).toBeVisible();

  await page.getByLabel("Open clicks.json").setInputFiles(file("phone-0.5x"));
  await expect(page.getByRole("status").filter({ hasText: 'this file is for camera "phone-0.5x"' })).toBeVisible();
});
