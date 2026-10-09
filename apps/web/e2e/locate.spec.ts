import { expect, test, type Page } from "@playwright/test";

import type { LocaliseRequest, LocaliseResult, Truth } from "../lib/locate/types";
import type { Workspace } from "../lib/workspace";
import { example, makeViews, routeJson, stubHealth, stubWorkspace, type Stub } from "./helpers";

// workspace-locate.json has one atlas, home-cabinet, and two sets that mark its
// landmarks; cabinet-test is the newer one and the page's default. Its three
// views give the three example answers of POST /localise.
const SET = "cabinet-test";
const VIEWS = ["frame_000010.png", "frame_000040.png", "frame_000070.png"] as const;
const ANSWERS: Record<string, string> = {
  // 5 inliers, needs 6; landmarks beyond the left edge: MOVE_LEFT.
  "frame_000010.png": "localise-result.json",
  // ACCEPT, the drone clicked in the view itself, inside the 95 % region.
  "frame_000040.png": "localise-result-reliable.json",
  // 3 landmarks: too_few_correspondences, MOVE_BACK.
  "frame_000070.png": "localise-result-failure.json",
};

type Answer = LocaliseResult | { status: number; detail: string } | "offline";

interface Service {
  workspace: Stub;
  /** What the page asked POST /localise, in order. */
  requests: LocaliseRequest[];
  /** How many localisations have been answered or dropped. */
  settled(): number;
  /** Keep the answer for this view back until the returned function is called. */
  hold(view: string): () => void;
  /** Answer this view with this instead of its example; null: the example again. */
  answer(view: string, answer: Answer | null): void;
}

/** The example answer for a request, with the truth view it asked for. */
function exampleFor(request: LocaliseRequest): LocaliseResult {
  const result = example<LocaliseResult>(ANSWERS[request.view]);
  result.request = { ...result.request, truth_view: request.truth_view ?? null };
  return result;
}

/** The perception service with the cabinet atlas and its test views. Nothing reaches a real one. */
async function serve(page: Page, options: { workspace?: Workspace | "offline" } = {}): Promise<Service> {
  // Registered first, so it only gets what no stub below answers.
  await page.route(/\/(view-sets|atlases|localise)(\/|\?|$)/, (route) => route.abort("connectionrefused"));
  await stubHealth(page);
  const workspace = await stubWorkspace(page, options.workspace ?? example<Workspace>("workspace-locate.json"));
  await routeJson(page, "GET", "**/atlases/home-cabinet", example("atlas-cabinet.json"));
  await routeJson(page, "GET", `**/view-sets/${SET}`, example("view-set-viewpoints.json"));

  // The images and their thumbnails (?width=240): any PNG of the right size will do.
  const views = await makeViews(page, VIEWS.map((name) => ({ name, dots: {} })));
  await page.route(`**/view-sets/${SET}/images/**`, async (route) => {
    const file = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    const view = views.find((candidate) => candidate.name === file);
    if (view) await route.fulfill({ contentType: "image/png", body: view.buffer });
    else await route.fulfill({ status: 404, json: { detail: `no image '${file}' in view set '${SET}'` } });
  });

  const requests: LocaliseRequest[] = [];
  const held = new Map<string, Promise<void>>();
  const answers = new Map<string, Answer>();
  let settled = 0;
  await page.route("**/localise", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    const request = route.request().postDataJSON() as LocaliseRequest;
    requests.push(request);
    await held.get(request.view);
    const answer = answers.get(request.view) ?? exampleFor(request);
    try {
      if (answer === "offline") await route.abort("connectionrefused");
      else if ("detail" in answer) await route.fulfill({ status: answer.status, json: { detail: answer.detail } });
      else await route.fulfill({ json: answer });
    } catch {
      // The page dropped the request while it was held.
    } finally {
      settled += 1;
    }
  });

  return {
    workspace,
    requests,
    settled: () => settled,
    hold(view) {
      const { promise, resolve } = Promise.withResolvers<void>();
      held.set(view, promise);
      return () => {
        held.delete(view);
        resolve();
      };
    },
    answer(view, answer) {
      if (answer === null) answers.delete(view);
      else answers.set(view, answer);
    },
  };
}

function request(view: string, truth_view: string | null = null): LocaliseRequest {
  return { asset_id: "home-cabinet", view_set: SET, view, truth_view };
}

/** A viewpoint of the strip: its name starts with the file name. */
function viewpoint(page: Page, view: string) {
  return page.getByRole("button", { name: new RegExp(`^${view.replaceAll(".", "\\.")}`) });
}

function decision(page: Page) {
  return page.getByRole("complementary", { name: "Decision" });
}

/** The live part of the decision: the verdict, the move and the reasons. */
function verdict(page: Page) {
  return decision(page).getByRole("status");
}

function picture(page: Page) {
  return page.locator("svg[data-image]");
}

function trace(page: Page) {
  return page.locator("[data-slot=card]").filter({ has: page.getByRole("heading", { name: /^Trace/ }) });
}

function traceRows(page: Page) {
  return trace(page).locator("tbody tr");
}

/** The answer for this view is on screen: the decision, and the image it is drawn on. */
async function expectShown(page: Page, view: string, step?: number) {
  await expect(decision(page)).toHaveAttribute("data-status", "shown");
  await expect(decision(page)).toHaveAttribute("data-view", view);
  if (step !== undefined) await expect(decision(page)).toHaveAttribute("data-step", String(step));
  await expect(picture(page)).toHaveAttribute("data-image", new RegExp(`/${view.replaceAll(".", "\\.")}$`));
}

async function openAndWalk(page: Page) {
  await page.goto("/");
  await expectShown(page, VIEWS[0], 1);
  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1], 2);
  await viewpoint(page, VIEWS[2]).click();
  await expectShown(page, VIEWS[2], 3);
}

test("each viewpoint is located and decided: move left, accept, move back, with the reasons", async ({ page }) => {
  const service = await serve(page);
  await page.goto("/");
  await expect(page).toHaveTitle("Locate · Spatial Maintenance Copilot");
  await expect(page.getByRole("combobox", { name: "Asset" })).toHaveText("home-cabinet");
  await expect(page.getByRole("combobox", { name: "Viewpoints" })).toHaveText("cabinet-test");

  // The first viewpoint is located as the page opens.
  await expectShown(page, VIEWS[0], 1);
  await expect(verdict(page)).toContainText("Not reliable");
  await expect(verdict(page)).toContainText("Move left");
  await expect(verdict(page)).toContainText("Landmarks extend beyond the left edge of the frame");
  await expect(verdict(page).getByRole("listitem")).toHaveText(["5 inliers, needs ≥ 6"]);
  await expect(decision(page).locator("[data-check=inliers] td")).toHaveText(["Inliers", "5", "≥ 6", "Fail"]);
  await expect(decision(page).locator("[data-check=landmarks] td")).toHaveText(["Landmarks matched", "5", "≥ 4", "Pass"]);
  await expect(page.locator("[data-action]")).toHaveAttribute("data-action", "MOVE_LEFT");

  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1], 2);
  await expect(verdict(page)).toContainText("Reliable");
  await expect(verdict(page)).not.toContainText("Not reliable");
  await expect(verdict(page)).toContainText("Accept");
  await expect(verdict(page)).toContainText("8 of 8 checks passed");
  await expect(verdict(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.locator("[data-action]")).toHaveAttribute("data-action", "ACCEPT");

  await viewpoint(page, VIEWS[2]).click();
  await expectShown(page, VIEWS[2], 3);
  await expect(verdict(page)).toContainText("Not reliable");
  await expect(verdict(page)).toContainText("Too few correspondences");
  await expect(verdict(page)).toContainText("Move back");
  await expect(verdict(page)).toContainText("Too few landmarks in view to fit a pose");
  await expect(verdict(page).getByRole("listitem")).toHaveText([
    "Localisation failed: too few correspondences",
    "3 landmarks matched, needs ≥ 4",
  ]);
  // What a failure leaves uncomputed is not measured, rather than failed.
  await expect(decision(page).locator("[data-check=inliers] td")).toHaveText(["Inliers", "—", "≥ 6", "Not measured"]);
  await expect(page.locator("[data-action]")).toHaveAttribute("data-action", "MOVE_BACK");

  expect(service.requests).toEqual([request(VIEWS[0]), request(VIEWS[1], VIEWS[1]), request(VIEWS[2])]);
  // Each viewpoint says its result in this session.
  await expect(viewpoint(page, VIEWS[0])).toContainText("Move left");
  await expect(viewpoint(page, VIEWS[1])).toContainText("Reliable");
  await expect(viewpoint(page, VIEWS[2])).toContainText("Failed");
  await expect(viewpoint(page, VIEWS[2])).toHaveAttribute("aria-current", "true");
});

test("the measurements and the truth are shown with their units", async ({ page }) => {
  await serve(page);
  await page.goto("/");
  await expectShown(page, VIEWS[0], 1);
  const panel = decision(page);
  await expect(panel.getByRole("definition")).toContainText([
    "23.1 px",
    "First step",
    "5 / 5",
    "1.00",
    "0.47 px",
    "0.77 px",
    "20.0 %",
    "0.013",
    "23.1 × 18.6 px",
    "17.9 px",
    "212.0 px",
    "1408 mm",
  ]);
  await expect(panel.getByRole("region", { name: "Truth" })).toHaveText(/^Truth\s*None$/);

  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1], 2);
  const truth = panel.getByRole("region", { name: "Truth" });
  await expect(truth.getByRole("definition")).toHaveText(["1.3 px", "Inside", "frame_000040.png"]);
  await expect(panel).toContainText("Change vs #1");
  await expect(panel).toContainText("−39.5 % improved");
});

test("the overlay draws the landmarks, the target and its regions at the example's pixels, half a pixel on", async ({
  page,
}) => {
  await serve(page);
  await page.goto("/");
  await expectShown(page, VIEWS[0]);
  const svg = picture(page);
  await expect(svg).toHaveAttribute("viewBox", "0 0 1080 1920");
  // Two landmarks project beyond the left edge: arrows on the left border point at them.
  await expect(svg.locator("[data-part=projection-edge]")).toHaveCount(2);
  await expect(svg.locator("[data-part=projection-edge][data-landmark=corner_top_left]")).toBeAttached();
  await expect(svg.locator("[data-part=landmark][data-kind=inlier]")).toHaveCount(5);

  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1]);
  await expect(svg.locator("image")).toHaveAttribute("width", "1080");
  await expect(svg.locator("image")).toHaveAttribute("height", "1920");
  await expect(svg.locator("[data-part=target-outline]")).toHaveAttribute(
    "d",
    "M688.234 1241.302 L377.288 1241.428 L380.194 931.235 L685.789 931.136 Z",
  );
  const region = svg.locator("[data-part=region]");
  await expect(region).toHaveAttribute("cx", "533.321");
  await expect(region).toHaveAttribute("cy", "1084.505");
  await expect(region).toHaveAttribute("rx", "13.963");
  await expect(region).toHaveAttribute("ry", "13.763");
  // The angle runs from the image x axis towards y, as SVG's rotate does in a y-down viewBox.
  await expect(region).toHaveAttribute("transform", "rotate(146.616 533.321 1084.505)");
  const poseOnly = svg.locator("[data-part=pose-only]");
  await expect(poseOnly).toHaveAttribute("rx", "7.231");
  await expect(poseOnly).toHaveAttribute("ry", "5.471");
  await expect(poseOnly).toHaveAttribute("transform", "rotate(171.236 533.321 1084.505)");
  await expect(poseOnly).toHaveAttribute("stroke-dasharray", /\d/);
  await expect(svg.locator("[data-part=target-centre]")).toHaveAttribute("transform", "translate(533.321 1084.505)");
  await expect(svg.locator("[data-part=truth]")).toHaveAttribute("transform", "translate(532.03 1084.81)");
  await expect(svg.locator("[data-part=landmark][data-kind=inlier]")).toHaveCount(7);
  await expect(svg.locator("[data-part=landmark][data-landmark=handle]")).toHaveAttribute(
    "transform",
    "translate(330.66 1109.27)",
  );
  await expect(svg.locator("[data-part=projection], [data-part=projection-edge]")).toHaveCount(0);
});

test("a result that is not reliable is drawn in the warning style, never like a reliable one", async ({ page }) => {
  await serve(page);
  await page.goto("/");
  await expectShown(page, VIEWS[0]);
  const svg = picture(page);
  const region = svg.locator("[data-part=region]");
  const outline = svg.locator("[data-part=target-outline]");
  const strokeOf = (locator: typeof region) => locator.evaluate((element) => getComputedStyle(element).stroke);

  for (const shape of [region, outline]) {
    await expect(shape).toHaveAttribute("data-style", "unreliable");
    await expect(shape).toHaveAttribute("stroke-dasharray", /\d/);
    await expect(shape).toHaveAttribute("fill", /^url\(#.+\)$/);
  }
  const warning = await strokeOf(region);
  await expect(page.getByRole("main").getByText("Not reliable · Move left")).toBeVisible();

  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1]);
  for (const shape of [region, outline]) {
    await expect(shape).toHaveAttribute("data-style", "reliable");
    await expect(shape).not.toHaveAttribute("stroke-dasharray", /.*/);
    await expect(shape).not.toHaveAttribute("fill", /.*/);
  }
  expect(await strokeOf(region)).not.toBe(warning);
  expect(await strokeOf(outline)).toBe(await strokeOf(region));

  // Without a pose there is no region to draw at all: only the clicks, as neither inliers nor outliers.
  await viewpoint(page, VIEWS[2]).click();
  await expectShown(page, VIEWS[2]);
  await expect(svg.locator("[data-part=region], [data-part=target-outline], [data-part=target-centre]")).toHaveCount(0);
  await expect(svg.locator("[data-part=landmark][data-kind=unposed]")).toHaveCount(3);
  await expect(page.getByRole("main").getByText("Too few correspondences").first()).toBeVisible();
});

test("Truth from starts at the view's own target click, and another choice runs the localisation again", async ({
  page,
}) => {
  const service = await serve(page);
  await page.goto("/");
  await expectShown(page, VIEWS[0], 1);
  const truthFrom = page.getByRole("combobox", { name: "Truth from" });
  await expect(truthFrom).toHaveText("None");

  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1], 2);
  await expect(truthFrom).toHaveText(VIEWS[1]);
  expect(service.requests[1]).toEqual(request(VIEWS[1], VIEWS[1]));

  // A paired shot from the position of frame_000010: the drone clicked in frame_000040.
  const paired = exampleFor(request(VIEWS[0], VIEWS[1]));
  const truth: Truth = { source_view: VIEWS[1], target_px: [531.53, 1084.31], error_px: 140.21, inside_95: false };
  service.answer(VIEWS[0], { ...paired, truth });
  await viewpoint(page, VIEWS[0]).click();
  await expectShown(page, VIEWS[0], 3);
  await expect(truthFrom).toHaveText("None");
  await expect(picture(page).locator("[data-part=truth]")).toHaveCount(0);

  await truthFrom.click();
  await expect(page.getByRole("option")).toHaveText(["None", VIEWS[1]]);
  await page.getByRole("option", { name: VIEWS[1] }).click();
  await expectShown(page, VIEWS[0], 4);
  expect(service.requests[3]).toEqual(request(VIEWS[0], VIEWS[1]));
  await expect(truthFrom).toHaveText(VIEWS[1]);
  const facts = decision(page).getByRole("region", { name: "Truth" }).getByRole("definition");
  await expect(facts).toHaveText(["140.2 px", "Outside", VIEWS[1]]);
  await expect(picture(page).locator("[data-part=truth]")).toHaveAttribute("transform", "translate(532.03 1084.81)");

  // "None" on a view with its own click: the service still sends that click, and the page shows no truth.
  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1], 5);
  await truthFrom.click();
  await page.getByRole("option", { name: "None" }).click();
  await expectShown(page, VIEWS[1], 6);
  expect(service.requests[5]).toEqual(request(VIEWS[1]));
  await expect(decision(page).getByRole("region", { name: "Truth" })).toHaveText(/^Truth\s*None$/);
  await expect(picture(page).locator("[data-part=truth]")).toHaveCount(0);
});

test("the trace records every step and how the region changed, survives a reload, and shows a step again", async ({
  page,
}) => {
  const service = await serve(page);
  await openAndWalk(page);
  const rows = traceRows(page);
  const expected = [
    ["1", "frame_000010.png", "Move left", "No", "23.1 px", "—", "—"],
    ["2", "frame_000040.png", "Accept", "Yes", "14.0 px", "−39.5 % improved", "1.3 px inside"],
    ["3", "frame_000070.png", "Move back", "No", "Too few correspondences", "worse", "—"],
  ];
  await expect(rows).toHaveCount(3);
  for (const [index, cells] of expected.entries()) await expect(rows.nth(index).locator("td")).toHaveText(cells);
  await expect(rows.nth(2)).toHaveAttribute("aria-current", "true");

  // The trace is kept for the tab: a reload shows it, and the latest step, without asking the service.
  await page.reload();
  await expectShown(page, VIEWS[2], 3);
  await expect(rows).toHaveCount(3);
  for (const [index, cells] of expected.entries()) await expect(rows.nth(index).locator("td")).toHaveText(cells);
  expect(service.requests).toHaveLength(3);

  // A row shows its step again, as it was.
  await trace(page).getByRole("button", { name: "Show step 2" }).click();
  await expectShown(page, VIEWS[1], 2);
  await expect(verdict(page)).toContainText("Accept");
  await expect(page.getByRole("combobox", { name: "Truth from" })).toHaveText(VIEWS[1]);
  await expect(rows.nth(1)).toHaveAttribute("aria-current", "true");
  await rows.nth(0).click();
  await expectShown(page, VIEWS[0], 1);
  expect(service.requests).toHaveLength(3);

  // Clearing it keeps what is on screen; the next step starts a new trace.
  await trace(page).getByRole("button", { name: "Clear trace" }).click();
  await expect(rows).toHaveCount(0);
  await expect(trace(page)).toContainText("No steps");
  await expectShown(page, VIEWS[0], 1);
  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1], 1);
  await expect(rows).toHaveCount(1);
  await page.reload();
  await expect(rows).toHaveCount(1);
  expect(service.requests).toHaveLength(4);
});

test("a slow answer never replaces a later choice", async ({ page }) => {
  const service = await serve(page);
  const release = service.hold(VIEWS[0]);
  await page.goto("/");
  await expect(viewpoint(page, VIEWS[0])).toHaveAttribute("aria-busy", "true");
  await expect(verdict(page)).toHaveText(`Locating ${VIEWS[0]}…`);

  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1], 1);
  release();
  await expect.poll(() => service.settled()).toBe(2);
  // Whatever became of the first answer, the second stays on screen and alone in the trace.
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 100))));
  await expectShown(page, VIEWS[1], 1);
  await expect(traceRows(page)).toHaveCount(1);
  await expect(viewpoint(page, VIEWS[0])).not.toHaveAttribute("aria-busy", "true");
  await expect(viewpoint(page, VIEWS[0])).not.toContainText("Move left");
  expect(service.requests.map((sent) => sent.view)).toEqual([VIEWS[0], VIEWS[1]]);
});

test("a viewpoint is chosen with the keyboard as well", async ({ page }) => {
  await serve(page);
  await page.goto("/");
  await expectShown(page, VIEWS[0], 1);
  await viewpoint(page, VIEWS[1]).focus();
  await page.keyboard.press("Enter");
  await expectShown(page, VIEWS[1], 2);
  await page.keyboard.press("Tab");
  await expect(viewpoint(page, VIEWS[2])).toBeFocused();
  await page.keyboard.press("Space");
  await expectShown(page, VIEWS[2], 3);
});

test("each layer of the overlay is switched off and on by its checkbox", async ({ page }) => {
  await serve(page);
  await page.goto("/");
  await expectShown(page, VIEWS[0]);
  const svg = picture(page);
  await page.getByRole("checkbox", { name: "Projections", exact: true }).click();
  await expect(svg.locator("[data-part=projection-edge]")).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Projections", exact: true }).click();
  await expect(svg.locator("[data-part=projection-edge]")).toHaveCount(2);

  await viewpoint(page, VIEWS[1]).click();
  await expectShown(page, VIEWS[1]);
  const layers: [string, string][] = [
    ["Landmarks", "[data-part=landmark]"],
    ["Residuals", "[data-part=residual]"],
    ["Labels", "[data-label]"],
    ["Target", "[data-part=target-outline]"],
    ["95 % region", "[data-part=region]"],
    ["Pose-only region", "[data-part=pose-only]"],
    ["Truth", "[data-part=truth]"],
  ];
  for (const [name, part] of layers) {
    const box = page.getByRole("checkbox", { name, exact: true });
    await expect(box).toBeChecked();
    await expect(svg.locator(part).first()).toBeAttached();
    await box.click();
    await expect(box).not.toBeChecked();
    await expect(svg.locator(part)).toHaveCount(0);
    await box.click();
    await expect(svg.locator(part).first()).toBeAttached();
  }
});

test("without the service the page says so, and Retry reads the workspace again", async ({ page }) => {
  const service = await serve(page, { workspace: "offline" });
  await page.goto("/");
  const main = page.getByRole("main");
  await expect(main.getByRole("alert")).toContainText("Service unreachable");
  await expect(main.getByRole("alert")).toContainText("Cannot reach the perception service");
  service.workspace.reply(example("workspace-locate.json"));
  await main.getByRole("button", { name: "Retry" }).click();
  await expectShown(page, VIEWS[0], 1);
});

test("a localisation that gets no answer says why, and Retry runs it again", async ({ page }) => {
  const service = await serve(page);
  service.answer(VIEWS[0], "offline");
  await page.goto("/");
  const alert = decision(page).getByRole("alert");
  await expect(decision(page)).toHaveAttribute("data-status", "failed");
  await expect(alert).toContainText(`${VIEWS[0]} not located`);
  await expect(alert).toContainText("Cannot reach the perception service");
  await expect(traceRows(page)).toHaveCount(0);

  service.answer(VIEWS[0], null);
  await decision(page).getByRole("button", { name: "Retry" }).click();
  await expectShown(page, VIEWS[0], 1);

  // The service's own words when it refuses.
  service.answer(VIEWS[2], { status: 409, detail: "view 'frame_000070.png' has no clicks" });
  await viewpoint(page, VIEWS[2]).click();
  await expect(alert).toContainText(`${VIEWS[2]} not located`);
  await expect(alert).toContainText("view 'frame_000070.png' has no clicks");
  expect(service.requests.map((sent) => sent.view)).toEqual([VIEWS[0], VIEWS[0], VIEWS[2]]);
});

test("without an atlas the page says so, next to a link to the Atlas page", async ({ page }) => {
  const workspace = example<Workspace>("workspace-locate.json");
  workspace.atlases = [];
  const service = await serve(page, { workspace });
  await page.goto("/");
  const main = page.getByRole("main");
  await expect(main.getByText("No atlas", { exact: true })).toBeVisible();
  await expect(main.getByRole("link", { name: "Atlas" })).toHaveAttribute("href", /^\/atlas\/?$/);
  await expect(page.getByRole("combobox", { name: "Asset" })).toBeDisabled();
  expect(service.requests).toEqual([]);
});

test("an atlas without viewpoints says so, next to a link to the Atlas page", async ({ page }) => {
  const workspace = example<Workspace>("workspace-locate.json");
  // Only the target is marked: no landmark of the atlas to localise from.
  for (const set of workspace.view_sets) if (set.clicks) set.clicks.point_views = { drone: 1 };
  const service = await serve(page, { workspace });
  await page.goto("/");
  const main = page.getByRole("main");
  await expect(main.getByText("No viewpoints with marked landmarks")).toBeVisible();
  await expect(main.getByRole("link", { name: "Atlas" })).toHaveAttribute("href", /^\/atlas\/?$/);
  await expect(page.getByRole("combobox", { name: "Viewpoints" })).toBeDisabled();
  expect(service.requests).toEqual([]);
});

test("a portrait view fits the window beside the decision on a laptop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await serve(page);
  await page.goto("/");
  await expectShown(page, VIEWS[0]);
  const image = await picture(page).locator("image").boundingBox();
  const panel = await decision(page).boundingBox();
  if (!image || !panel) throw new Error("the image and the decision are on screen");
  expect(image.y).toBeGreaterThanOrEqual(0);
  expect(image.y + image.height).toBeLessThanOrEqual(900);
  expect(image.width / image.height).toBeCloseTo(1080 / 1920, 2);
  expect(panel.x).toBeGreaterThanOrEqual(image.x + image.width);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the decision comes under the image, and the page never scrolls sideways", async ({ page }) => {
    await serve(page);
    await openAndWalk(page);
    const image = await picture(page).boundingBox();
    const panel = await decision(page).boundingBox();
    if (!image || !panel) throw new Error("the image and the decision are on the page");
    expect(panel.y).toBeGreaterThanOrEqual(image.y + image.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});

test("the page shows facts and controls, no instructions, and logs no error", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    // The sidebar prefetches every page it lists; whether the Atlas page is there is not this page's concern.
    const prefetch = new URL(message.location().url || "about:blank").pathname === "/atlas/";
    if (message.type() === "error" && !prefetch) errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await serve(page);
  await openAndWalk(page);
  const text = await page.getByRole("main").innerText();
  expect(text).not.toMatch(/\b(click|tap|press|choose|select an?|please|you can|how to|first,|then|uv run|npm|make)\b/i);
  expect(errors).toEqual([]);
});
