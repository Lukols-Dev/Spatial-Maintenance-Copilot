import { expect, test, type Locator, type Page } from "@playwright/test";

import type { Board, ViewSetSummary, Workspace } from "../lib/workspace";
import { example, routeJson, stubHealth, stubWorkspace, type Stub } from "./helpers";

// workspace.json: the set cabinet (3 images; hinge_top, handle and the drone
// marked in two or more, corner_left in one), rig_board_a measured, and the
// atlas home-cabinet v1 built from the set (atlas.json). workspace-empty.json:
// the repository today, with no set and rig_board_a not measured.

const CAMERA = "iphone11-1x-1080p-portrait";
const SCALE_REFUSAL =
  "square_measured_mm 100.16 mm is far from the nominal square of 25 mm (expected 20 to 31.25 mm for one square)";

// The examples were written in Warsaw; times on the page are in the reader's zone.
test.use({ timezoneId: "Europe/Warsaw" });

interface Service {
  /** GET /workspace */
  workspace: Stub;
  /** GET /atlases/home-cabinet */
  atlas: Stub;
  /** POST /atlases */
  build: Stub;
  /** PUT /boards/rig_board_a/measurement */
  measure: Stub;
  /** POST /view-sets */
  upload: Stub;
}

/** The perception service, answering with the examples. Nothing reaches a real one. */
async function serve(page: Page, workspace: Workspace | "offline" = example("workspace.json")): Promise<Service> {
  // Registered first, so it only gets what no stub below answers.
  await page.route(/^https?:\/\/localhost:8000\//, (route) => route.abort("connectionrefused"));
  await stubHealth(page);
  return {
    workspace: await stubWorkspace(page, workspace),
    atlas: await routeJson(page, "GET", "**/atlases/home-cabinet", example("atlas.json")),
    build: await routeJson(page, "POST", "**/atlases", example("atlas.json"), 201),
    measure: await routeJson(page, "PUT", "**/boards/rig_board_a/measurement", measuredBoard()),
    upload: await routeJson(page, "POST", "**/view-sets", example("view-set-summary.json"), 201),
  };
}

/** rig_board_a as the service answers once it is measured. */
function measuredBoard(): Board {
  const board = example<Workspace>("workspace-empty.json").rig.boards[1];
  return { ...board, square_measured_mm: 25.04, measurement_uncertainty_mm: 0.01, measured_on: "2026-10-09", measured: true };
}

function buildForm(page: Page): Locator {
  return page.getByRole("form", { name: "Build atlas" });
}

function resultCard(page: Page): Locator {
  return page.locator("[data-slot=card]", { has: page.getByRole("heading", { name: "Result", level: 2 }) });
}

function missing(form: Locator): Locator {
  return form.getByRole("list", { name: "Missing" }).getByRole("listitem");
}

/** The value a <dl> of the card gives for this term. */
function fact(card: Locator, term: string): Locator {
  return card.locator(`dl > div:has(> dt:text-is("${term}")) > dd`);
}

test("shows the sets, the boards and the atlases of the workspace", async ({ page }) => {
  await serve(page);
  await page.goto("/atlas/");
  await expect(page).toHaveTitle(/^Atlas · /);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Atlas");

  const form = buildForm(page);
  await expect(form.getByRole("combobox", { name: "View set" })).toHaveText("cabinet · 3 images");
  await expect(form.getByText("3 images · 1080×1920 · 4 points, 3 in ≥ 2 images")).toBeVisible();
  await expect(form.getByRole("combobox", { name: "Camera" })).toHaveText(`${CAMERA} · 1080×1920`);
  await expect(form.getByText("RMS 0.90 px · 58 frames · calibrated 2026-10-05")).toBeVisible();
  await expect(form.getByRole("combobox", { name: "Board" })).toHaveText("rig_board_a");
  await expect(form.getByText("4×6 squares of 25.04 ± 0.01 mm · measured 2026-10-06")).toBeVisible();
  await expect(form.getByRole("combobox", { name: "Target" })).toHaveText("drone · 2 views");
  // The last atlas built from the set: built again under its id, with its extent, as the next version.
  await expect(form.getByLabel("Asset id")).toHaveValue("home-cabinet");
  await expect(form.getByLabel("Version")).toHaveValue("2");
  for (const [axis, value] of [
    ["x", "300"],
    ["y", "300"],
    ["z", "100"],
  ]) {
    await expect(form.getByLabel(`Target extent ${axis} (mm)`)).toHaveValue(value);
  }
  await expect(form.getByText("Replaces home-cabinet v1 · built 2026-10-06 14:25")).toBeVisible();
  await expect(form.getByText("click σ 2 px · centre σ 5 mm · 200 samples · seed 0")).toBeVisible();
  await expect(form.getByRole("button", { name: "Build atlas" })).toBeEnabled();
  await expect(missing(form)).toHaveCount(0);

  // A point marked in one image cannot be the target; another board can be chosen and is measured or not.
  await form.getByRole("combobox", { name: "Target" }).click();
  await expect(page.getByRole("option", { name: "corner_left · 1 view" })).toBeDisabled();
  await expect(page.getByRole("option", { name: "hinge_top · 3 views" })).toBeEnabled();
  await page.keyboard.press("Escape");
  await form.getByRole("combobox", { name: "Board" }).click();
  await expect(page.getByRole("option")).toHaveText(["calibration_board · 30.00 mm", "rig_board_a · 25.04 mm", "rig_board_b · not measured"]);
  await page.getByRole("option", { name: "rig_board_b · not measured" }).click();
  await expect(form.getByRole("combobox", { name: "Board" })).toHaveText("rig_board_b");
  await expect(form.getByText("Not measured", { exact: true })).toBeVisible();
  await expect(missing(form)).toHaveText(["Board not measured"]);
  await expect(form.getByRole("button", { name: "Build atlas" })).toBeDisabled();

  const result = resultCard(page);
  await expect(result.getByRole("combobox", { name: "Atlas" })).toHaveText("home-cabinet v1");
  await expect(fact(result, "Set")).toHaveText("cabinet");
  await expect(fact(result, "Camera")).toHaveText(CAMERA);
  await expect(fact(result, "Board")).toHaveText("rig_board_a");
  await expect(fact(result, "Built")).toHaveText("2026-10-06 14:25");
  await expect(fact(result, "Landmarks")).toHaveText("2");
  await expect(fact(result, "Target σ")).toHaveText("5.21 mm");
  await expect(fact(result, "Posed / clicked")).toHaveText("2 / 3 views");
  await expect(fact(result, "Skipped points")).toHaveText("1");
  await expectAtlasShown(result);
});

/** The Result card shows home-cabinet v1 of atlas.json: its plan, its points, what was left out. */
async function expectAtlasShown(result: Locator) {
  const plan = result.getByRole("img", {
    name: "Plan of home-cabinet v1: 2 landmarks and the target drone on rig_board_a",
  });
  await expect(plan).toBeVisible();
  // The board drawn at its measured size, and y growing downward as in the board's frame.
  const scale = Number(await plan.getAttribute("data-scale"));
  const board = plan.locator("[data-board=rig_board_a] > rect");
  expect(Number(await board.getAttribute("width"))).toBeCloseTo(4 * 25.04 * scale, 3);
  expect(Number(await board.getAttribute("height"))).toBeCloseTo(6 * 25.04 * scale, 3);
  const centreY = async (id: string) => Number(await plan.locator(`[data-landmark=${id}] > circle`).last().getAttribute("cy"));
  expect((await centreY("handle")) - (await centreY("hinge_top"))).toBeCloseTo((95.3 + 310.2) * scale, 3);
  await expect(plan.locator("[data-landmark]")).toHaveCount(2);
  await expect(plan.locator("[data-target=drone]")).toHaveCount(1);

  const rows = result.getByRole("table", { name: "Points" }).getByRole("row");
  await expect(rows.first().getByRole("columnheader")).toHaveText([
    "Point",
    "x mm",
    "y mm",
    "z mm",
    "σ mm",
    "Views",
    "Worst px",
    "Ray angle °",
  ]);
  await expect(rows).toHaveCount(4);
  await expect(rows.nth(1).getByRole("cell")).toHaveText([/^drone\s*Target$/, "95.0", "160.4", "−210.8", "5.21", "2", "1.32", "18.2"]);
  await expect(rows.nth(2).getByRole("cell")).toHaveText(["handle", "182.6", "95.3", "21.7", "2.31", "2", "0.87", "17.9"]);
  await expect(rows.nth(3).getByRole("cell")).toHaveText(["hinge_top", "−12.4", "−310.2", "4.1", "1.84", "2", "0.64", "18.6"]);

  await expect(result.locator("[data-skipped=corner_left]")).toHaveText("corner_left · Seen in 1 posed view, needs 2");
  await expect(result.getByRole("heading", { name: "Unposed views" })).toBeVisible();
  await expect(result.getByText("frame_000030.png", { exact: true })).toBeVisible();
}

test("the repository today: no set to build from, and the rig board to measure", async ({ page }) => {
  await serve(page, example("workspace-empty.json"));
  await page.goto("/atlas/");
  const form = buildForm(page);
  await expect(form.getByRole("combobox", { name: "View set" })).toHaveText("No view set");
  await expect(form.getByRole("combobox", { name: "View set" })).toBeDisabled();
  await expect(form.getByRole("button", { name: "Import views…" })).toBeEnabled();
  await expect(form.getByRole("link", { name: "Annotate" })).toHaveCount(0);
  await expect(form.getByRole("combobox", { name: "Board" })).toHaveText("rig_board_a");
  await expect(form.getByText("Not measured", { exact: true })).toBeVisible();
  await expect(form.getByRole("button", { name: "Measure…" })).toBeEnabled();
  await expect(form.getByRole("combobox", { name: "Target" })).toBeDisabled();

  await expect(form.getByRole("button", { name: "Build atlas" })).toBeDisabled();
  await expect(missing(form)).toHaveText(["No view set", "Board not measured", "Target extent missing", "Asset id missing"]);
  await expect(resultCard(page).getByText("No atlas yet")).toBeVisible();
});

test("a caliper span over four squares measures the board, and the board shows as measured", async ({ page }) => {
  const service = await serve(page, example("workspace-empty.json"));
  await page.goto("/atlas/");
  const form = buildForm(page);
  await form.getByRole("button", { name: "Measure…" }).click();

  const dialog = page.getByRole("dialog", { name: "Measure rig_board_a" });
  await expect(dialog.getByText("4×6 squares · nominal 25.00 mm")).toBeVisible();
  await expect(dialog.getByLabel("N squares")).toHaveValue("4");
  await dialog.getByLabel("Length (mm)", { exact: true }).fill("100.16");
  await expect(dialog.getByRole("status")).toHaveText("Square side 25.04 mm · +0.16 % vs nominal");
  await expect(dialog.getByRole("button", { name: "Save" })).toBeDisabled();
  await expect(dialog.getByRole("list", { name: "Missing" })).toHaveText("Length uncertainty missing");
  await dialog.getByLabel("Length uncertainty (mm)").fill("0.04");
  await expect(dialog.getByRole("status")).toHaveText("Square side 25.04 ± 0.01 mm · +0.16 % vs nominal");

  // The service answers with the board measured, and the workspace then has it so.
  const measured = example<Workspace>("workspace-empty.json");
  measured.rig.boards[1] = measuredBoard();
  service.workspace.reply(measured);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  expect(service.measure.bodies).toEqual([
    { square_measured_mm: 25.04, measurement_uncertainty_mm: 0.01, marker_measured_mm: null, substrate: null },
  ]);

  await expect(form.getByText("4×6 squares of 25.04 ± 0.01 mm · measured 2026-10-09")).toBeVisible();
  await expect(form.getByText("Not measured", { exact: true })).toHaveCount(0);
  await expect(missing(form)).toHaveText(["No view set", "Target extent missing", "Asset id missing"]);
});

test("a measurement the service refuses shows its words in the dialog", async ({ page }) => {
  const service = await serve(page, example("workspace-empty.json"));
  service.measure.reply({ detail: SCALE_REFUSAL }, 422);
  await page.goto("/atlas/");
  await buildForm(page).getByRole("button", { name: "Measure…" }).click();

  const dialog = page.getByRole("dialog", { name: "Measure rig_board_a" });
  await dialog.getByLabel("Length (mm)", { exact: true }).fill("100.16");
  await dialog.getByLabel("N squares").fill("1");
  await dialog.getByLabel("Length uncertainty (mm)").fill("0.04");
  await expect(dialog.getByRole("status")).toHaveText("Square side 100.16 ± 0.04 mm · +300.64 % vs nominal");
  await dialog.getByLabel("Substrate").fill("A4 print glued to the cabinet side");
  await dialog.getByRole("button", { name: "Save" }).click();

  await expect(dialog.getByRole("alert")).toHaveText(SCALE_REFUSAL);
  await expect(dialog).toBeVisible();
  expect(service.measure.bodies).toEqual([
    {
      square_measured_mm: 100.16,
      measurement_uncertainty_mm: 0.04,
      marker_measured_mm: null,
      substrate: "A4 print glued to the cabinet side",
    },
  ]);
  // A corrected reading clears the old answer.
  await dialog.getByLabel("N squares").fill("4");
  await expect(dialog.getByText(SCALE_REFUSAL)).toHaveCount(0);
});

test("Import views sends a video as a form, shows its progress, then opens the new set", async ({ page }) => {
  const service = await serve(page, example("workspace-empty.json"));
  await page.goto("/atlas/");
  const form = buildForm(page);
  await form.getByRole("button", { name: "Import views…" }).click();

  const dialog = page.getByRole("dialog", { name: "Import views" });
  await expect(dialog.getByRole("button", { name: "Import" })).toBeDisabled();
  await dialog.getByLabel("Video or photos").setInputFiles({
    name: "cabinet-2.mov",
    mimeType: "video/quicktime",
    buffer: Buffer.from("not really a video"),
  });
  await expect(dialog.getByText("cabinet-2.mov · 0.0 MB")).toBeVisible();
  await expect(dialog.getByLabel("Name")).toHaveValue("cabinet-2");
  const window = dialog.getByLabel("Keep the sharpest of every N frames");
  await expect(window).toHaveValue("15");
  await window.fill("10");

  // The answer waits until the test lets it go; the workspace then lists the new set.
  const imported = example<Workspace>("workspace-empty.json");
  imported.view_sets = [example<ViewSetSummary>("view-set-summary.json")];
  service.workspace.reply(imported);
  service.upload.hold();
  await dialog.getByRole("button", { name: "Import" }).click();
  // A stubbed answer holds the body back, so the browser reports no bytes sent until it comes.
  await expect(dialog.getByRole("progressbar", { name: "Upload" })).toHaveAttribute("aria-valuetext", "0 %");
  await expect(dialog.getByRole("status")).toHaveText("Uploading 0 %");
  await expect(dialog.getByLabel("Name")).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Import" })).toBeDisabled();
  // Closed, the dialog's button shows the upload going on.
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(form.getByRole("button", { name: "Uploading 0 %" })).toBeVisible();
  service.upload.release();
  await expect(form.getByRole("button", { name: "Import views…" })).toBeVisible();

  const sent = String(service.upload.bodies[0]);
  expect(sent).toMatch(/name="name"\r\n\r\ncabinet-2\r\n/);
  expect(sent).toMatch(/name="window"\r\n\r\n10\r\n/);
  expect(sent).toMatch(/name="files"; filename="cabinet-2\.mov"\r\nContent-Type: video\/quicktime\r\n\r\nnot really a video\r\n/);
  await expect(form.getByRole("combobox", { name: "View set" })).toHaveText("cabinet-2 · 24 images");
  await expect(form.getByRole("link", { name: "Annotate" })).toHaveAttribute("href", "/annotate/?set=cabinet-2");
  await expect(missing(form)).toContainText(["No points marked"]);
});

test("an import the service refuses shows its words, and the dialog keeps the files", async ({ page }) => {
  const service = await serve(page, example("workspace-empty.json"));
  service.upload.reply({ detail: "no frames could be read from cabinet-2.mov" }, 422);
  await page.goto("/atlas/");
  await buildForm(page).getByRole("button", { name: "Import views…" }).click();
  const dialog = page.getByRole("dialog", { name: "Import views" });
  await dialog.getByLabel("Video or photos").setInputFiles({ name: "cabinet-2.mov", mimeType: "video/quicktime", buffer: Buffer.from("x") });
  await dialog.getByRole("button", { name: "Import" }).click();
  await expect(dialog.getByRole("alert")).toHaveText("no frames could be read from cabinet-2.mov");
  await expect(dialog.getByRole("button", { name: "Import" })).toBeEnabled();
});

test("another view set brings its own target, also after a set without points", async ({ page }) => {
  // cabinet-2 is newer and has no points, so the form opens on it without a target.
  const workspace = example<Workspace>("workspace.json");
  workspace.view_sets.push(example<ViewSetSummary>("view-set-summary.json"));
  await serve(page, workspace);
  await page.goto("/atlas/");
  const form = buildForm(page);
  await expect(form.getByRole("combobox", { name: "View set" })).toHaveText("cabinet-2 · 24 images");
  await expect(form.getByRole("combobox", { name: "Target" })).toBeDisabled();

  // The target select gets new options and a value at once: the value must survive that.
  await form.getByRole("combobox", { name: "View set" }).click();
  await page.getByRole("option", { name: "cabinet · 3 images" }).click();
  await expect(form.getByRole("combobox", { name: "Target" })).toHaveText("drone · 2 views");
  await expect(missing(form)).toHaveCount(0);
  await expect(form.getByRole("button", { name: "Build atlas" })).toBeEnabled();
});

test("Build atlas sends the request of the example and shows the atlas it built", async ({ page }) => {
  const before = example<Workspace>("workspace.json");
  before.atlases = [];
  const service = await serve(page, before);
  await page.goto("/atlas/");
  const form = buildForm(page);
  await expect(resultCard(page).getByText("No atlas yet")).toBeVisible();
  await expect(form.getByLabel("Asset id")).toHaveValue("cabinet");
  await expect(missing(form)).toHaveText(["Target extent missing"]);

  await form.getByLabel("Target extent x (mm)").fill("300");
  await form.getByLabel("Target extent y (mm)").fill("300");
  await form.getByLabel("Target extent z (mm)").fill("100");
  await form.getByLabel("Asset id").fill("home-cabinet");
  await expect(form.getByLabel("Version")).toHaveValue("1");
  await expect(missing(form)).toHaveCount(0);

  service.workspace.reply(example("workspace.json"));
  service.build.hold();
  await form.getByRole("button", { name: "Build atlas" }).click();
  // The form is locked while the service builds, and the seconds count.
  await expect(form.getByRole("button", { name: /^Building… \d+ s$/ })).toBeDisabled();
  await expect(form.getByRole("status")).toHaveText("Building home-cabinet v1 from cabinet");
  await expect(form.getByLabel("Asset id")).toBeDisabled();
  await expect(form.getByRole("combobox", { name: "View set" })).toBeDisabled();
  expect(service.build.bodies).toEqual([example("atlas-build-request.json")]);
  service.build.release();

  await expect(form.getByRole("status")).toHaveText(/^Built home-cabinet v1 in \d+ s$/);
  const result = resultCard(page);
  await expect(result.getByRole("combobox", { name: "Atlas" })).toHaveText("home-cabinet v1");
  await expectAtlasShown(result);
  // The atlas came with the build's answer: it is not read again.
  expect(service.atlas.bodies).toHaveLength(0);
  // The next build starts from this one.
  await expect(form.getByLabel("Asset id")).toBeEnabled();
  await expect(form.getByLabel("Version")).toHaveValue("2");
});

test("a build the service refuses shows its words until the request changes", async ({ page }) => {
  const refusal = "target 'drone' is not located: seen in 1 posed view, needs 2";
  const service = await serve(page);
  service.build.reply({ detail: refusal }, 409);
  await page.goto("/atlas/");
  const form = buildForm(page);
  await expect(form.getByLabel("Version")).toHaveValue("2");
  await form.getByRole("button", { name: "Build atlas" }).click();
  await expect(form.getByRole("alert")).toHaveText(refusal);
  await expect(form.getByRole("button", { name: "Build atlas" })).toBeEnabled();
  await expect(form.getByRole("status")).toHaveCount(0);

  await form.getByLabel("Version").fill("3");
  await expect(form.getByText(refusal)).toHaveCount(0);
});

test("the Annotate link opens the set in the annotator", async ({ page }) => {
  await serve(page);
  await page.goto("/atlas/");
  const link = buildForm(page).getByRole("link", { name: "Annotate" });
  await expect(link).toHaveAttribute("href", "/annotate/?set=cabinet");
  await link.click();
  await expect(page).toHaveURL(/\/annotate\/\?set=cabinet$/);
});

test("the form is used from the keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/atlas/");
  const form = buildForm(page);
  const viewSet = form.getByRole("combobox", { name: "View set" });
  await expect(viewSet).toHaveText("cabinet · 3 images");

  await viewSet.focus();
  const order = [
    form.getByRole("link", { name: "Annotate" }),
    form.getByRole("button", { name: "Import views…" }),
    form.getByRole("combobox", { name: "Camera" }),
    form.getByRole("combobox", { name: "Board" }),
    form.getByRole("button", { name: "Measure…" }),
    form.getByRole("combobox", { name: "Target" }),
  ];
  for (const next of order) {
    await page.keyboard.press("Tab");
    await expect(next).toBeFocused();
  }

  // A dialog opens on its first field and gives the focus back when it closes.
  const measure = form.getByRole("button", { name: "Measure…" });
  await measure.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Measure rig_board_a" });
  await page.keyboard.type("100.16");
  await expect(dialog.getByLabel("Length (mm)", { exact: true })).toHaveValue("100.16");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(measure).toBeFocused();

  // The arrows pass over a point marked in one image.
  const target = form.getByRole("combobox", { name: "Target" });
  await target.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("option", { name: "drone · 2 views" })).toBeFocused();
  await page.keyboard.press("ArrowUp");
  await expect(page.getByRole("option", { name: "handle · 2 views" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(target).toHaveText("handle · 2 views");
});

test("a read-only service shows the atlases and nothing that would change them", async ({ page }) => {
  await serve(page, { ...example<Workspace>("workspace.json"), read_only: true });
  await page.goto("/atlas/");
  const result = resultCard(page);
  await expectAtlasShown(result);
  await expect(buildForm(page)).toHaveCount(0);
  const main = page.getByRole("main");
  for (const name of [/^Import views/, /^Measure/, /^Build/, /^Save/]) await expect(main.getByRole("button", { name })).toHaveCount(0);
  await expect(main.getByRole("textbox")).toHaveCount(0);
  await expect(main.getByRole("spinbutton")).toHaveCount(0);
});

test("an unreachable service is said so, and Retry reads the workspace again", async ({ page }) => {
  const service = await serve(page, "offline");
  await page.goto("/atlas/");
  const failure = page.getByRole("alert").filter({ hasText: "Cannot reach the perception service at" });
  await expect(failure).toBeVisible();
  await expect(buildForm(page)).toHaveCount(0);

  service.workspace.reply(example("workspace.json"));
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(buildForm(page).getByRole("combobox", { name: "View set" })).toHaveText("cabinet · 3 images");
  await expect(failure).toHaveCount(0);
});

test("a failed read of an atlas says why, and Retry reads it again", async ({ page }) => {
  const service = await serve(page);
  service.atlas.reply({ detail: "data/atlas/home-cabinet.json is not an atlas: target: Field required" }, 409);
  await page.goto("/atlas/");
  const result = resultCard(page);
  await expect(result.getByRole("alert")).toHaveText("data/atlas/home-cabinet.json is not an atlas: target: Field required");
  service.atlas.reply(example("atlas.json"));
  await result.getByRole("button", { name: "Retry" }).click();
  await expectAtlasShown(result);
});

test("the page logs no error, and says no more than facts", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  // Words that instruct rather than state: no step lists, no commands, no "click here".
  // ("Click σ" is the uncertainty of a click, a field like any other.)
  const INSTRUCTION = /\b(click (here|to|on|the)|tap|press|step \d|first|then|please|you|your|how to|uv run|python|npm|make)\b/i;
  const main = page.getByRole("main");

  for (const data of ["workspace.json", "workspace-empty.json"]) {
    await serve(page, example(data));
    await page.goto("/atlas/");
    await expect(buildForm(page).getByRole("button", { name: "Build atlas" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await buildForm(page).getByRole("button", { name: "Advanced" }).click();
    await expect(buildForm(page).getByLabel("Samples")).toBeVisible();
    expect(await main.innerText()).not.toMatch(INSTRUCTION);

    for (const [button, title] of [
      ["Measure…", "Measure rig_board_a"],
      ["Import views…", "Import views"],
    ]) {
      await buildForm(page).getByRole("button", { name: button }).click();
      const dialog = page.getByRole("dialog", { name: title });
      await expect(dialog).toBeVisible();
      expect(await dialog.innerText()).not.toMatch(INSTRUCTION);
      await dialog.getByRole("button", { name: "Close" }).first().click();
      await expect(dialog).toBeHidden();
    }
    await page.unrouteAll({ behavior: "ignoreErrors" });
  }
  expect(errors).toEqual([]);
});

test("a phone shows the page without scrolling sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await serve(page);
  await page.goto("/atlas/");
  await expectAtlasShown(resultCard(page));
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
