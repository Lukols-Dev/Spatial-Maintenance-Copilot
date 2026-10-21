import { expect, test, type Page } from "@playwright/test";

import type { SessionTurn } from "../lib/agent/types";
import type { AtlasDetail, Workspace } from "../lib/workspace";
import { example, makeViews, routeJson, stubHealth, stubWorkspace, type Stub } from "./helpers";

// workspace-agent.json has the synthetic cabinet's atlas, home-cabinet, and one
// set, cabinet-agent: A_close sees every landmark, B_close four, C_close three,
// and A_open is A's shot with the drone in sight. The session examples are the
// service's answers to: start at B_close, then A_close, then approval.
const SET = "cabinet-agent";
const FILES = ["A_close.png", "A_open.png", "B_close.png", "C_close.png"] as const;
const ID = "5d7c0a3e9b6f4c21a8e04f6b2d913c57";

interface Service {
  start: Stub;
  view: Stub;
  approval: Stub;
  session: Stub;
}

function turn(name: string): SessionTurn {
  return example<SessionTurn>(name);
}

/** The perception service with the cabinet and its agent. Nothing reaches a real one. */
async function serve(page: Page, options: { move?: SessionTurn } = {}): Promise<Service> {
  await page.route(/\/(view-sets|atlases|sessions|localise)(\/|\?|$)/, (route) => route.abort("connectionrefused"));
  await stubHealth(page);
  await stubWorkspace(page, example("workspace-agent.json"));
  await routeJson(page, "GET", "**/atlases/home-cabinet", example("atlas-agent.json"));
  await routeJson(page, "GET", `**/view-sets/${SET}`, example("view-set-agent.json"));
  const views = await makeViews(page, FILES.map((name) => ({ name, dots: {} })));
  await page.route(`**/view-sets/${SET}/images/**`, async (route) => {
    const file = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    const view = views.find((candidate) => candidate.name === file);
    await route.fulfill(view ? { contentType: "image/png", body: view.buffer } : { status: 404, json: { detail: "no image" } });
  });
  return {
    start: await routeJson(page, "POST", "**/sessions", options.move ?? turn("session-turn-move.json"), 201),
    view: await routeJson(page, "POST", "**/sessions/*/view", turn("session-turn-approval.json")),
    approval: await routeJson(page, "POST", "**/sessions/*/approval", turn("session-turn-accepted.json")),
    session: await routeJson(page, "GET", "**/sessions/*", turn("session-turn-move.json")),
  };
}

function agent(page: Page) {
  return page.getByRole("region", { name: "Agent" });
}

/** A viewpoint of the strip, not the agent's suggestion of it. */
function viewpoint(page: Page, view: string) {
  return page.locator(`button[data-view="${view}"]`);
}

function traceRows(page: Page) {
  return page
    .locator("[data-slot=card]")
    .filter({ has: page.getByRole("heading", { name: /^Agent trace/ }) })
    .locator("tbody tr");
}

async function kinds(page: Page): Promise<string[]> {
  return traceRows(page).evaluateAll((rows) => rows.map((row) => row.getAttribute("data-kind") ?? ""));
}

async function startAtB(page: Page) {
  await page.goto("/");
  await expect(agent(page)).toHaveAttribute("data-status", "none");
  await viewpoint(page, "B_close.png").click();
  await expect(agent(page)).toHaveAttribute("data-status", "view");
}

test("a session runs from the policy's move to the operator's approval, every step in the trace", async ({ page }) => {
  const service = await serve(page);
  await startAtB(page);

  expect(service.start.bodies).toEqual([{ asset_id: "home-cabinet", view_set: SET, view: "B_close.png" }]);
  await expect(agent(page).getByRole("heading", { name: "Move closer" })).toBeVisible();
  await expect(agent(page).locator("[data-guidance]")).toHaveText(
    "Only four marks are in view. Move so the marks on the other side of the door come in too.",
  );
  await expect(agent(page)).toContainText("anthropic.claude-opus-5-5 (eu-central-1)");
  expect(await kinds(page)).toEqual(["perception", "decision", "tool", "agent"]);
  await expect(page.getByRole("complementary", { name: "Decision" })).toHaveAttribute("data-view", "B_close.png");

  await viewpoint(page, "A_close.png").click();
  await expect(agent(page)).toHaveAttribute("data-status", "approval");
  expect(service.view.bodies).toEqual([{ view: "A_close.png" }]);
  await expect(agent(page).locator("[data-explanation]")).toHaveText(
    "The drone sits behind the middle of the door, inside the highlighted region.",
  );
  await expect(agent(page).locator("[data-next-step]")).toHaveText(
    "Open the door and lift the drone out from behind the hinges.",
  );
  expect(await kinds(page)).toEqual(["perception", "decision", "tool", "agent", "human", "perception", "decision", "agent"]);
  await expect(viewpoint(page, "C_close.png")).toBeDisabled();

  await agent(page).getByRole("button", { name: "Approve" }).click();
  await expect(agent(page)).toHaveAttribute("data-status", "accepted");
  expect(service.approval.bodies).toEqual([{ approved: true }]);
  await expect(agent(page).getByRole("status")).toHaveText("Accepted");
  await expect(traceRows(page)).toHaveCount(9);

  // The session view by view: each measurement next to the decision and the action it led to.
  const summary = page.getByRole("region", { name: "Session" });
  const rows = summary.locator("tbody tr");
  await expect(rows).toHaveCount(2);
  await expect(summary.locator("[data-part=session-headline]")).toContainText("2 views · accepted at view 2");
  await expect(summary.locator("[data-part=session-headline]")).toContainText("next step approved");
  await expect(rows.nth(0)).toContainText("B_close.png");
  await expect(rows.nth(0)).toContainText("Move closer");
  await expect(rows.nth(0)).toContainText("Asked: move closer");
  await expect(rows.nth(0)).toContainText("Chose A_close.png");
  await expect(rows.nth(1)).toContainText("Reliable");
  await expect(rows.nth(1)).toContainText("Approved");

  await agent(page).getByRole("button", { name: "New session" }).click();
  await expect(agent(page)).toHaveAttribute("data-status", "none");
  await expect(traceRows(page)).toHaveCount(0);
});

test("the strip offers only viewpoints with the target hidden, and starts a session from the first", async ({ page }) => {
  const service = await serve(page);
  await page.goto("/");

  await expect(page.locator("button[data-view]")).toHaveCount(3);
  await expect(viewpoint(page, "A_open.png")).toHaveCount(0);
  await agent(page).getByRole("button", { name: "Start at A_close.png" }).click();

  await expect(agent(page)).toHaveAttribute("data-status", "view");
  expect(service.start.bodies).toEqual([{ asset_id: "home-cabinet", view_set: SET, view: "A_close.png" }]);
});

test("the page opens on the newest atlas with viewpoints, and still offers a newer one without", async ({ page }) => {
  await serve(page);
  // As a deployment serves view sets of some atlases only: no set marks a landmark of the newer one.
  const data = example<Workspace>("workspace-agent.json");
  const [cabinet] = data.atlases;
  data.atlases = [
    { ...cabinet, asset_id: "marker-cabinet", file: "marker-cabinet.json", built_at: "2026-10-15T16:00:19+02:00" },
    cabinet,
  ];
  await stubWorkspace(page, data);
  const markers = example<AtlasDetail>("atlas-agent.json");
  markers.atlas.asset_id = "marker-cabinet";
  markers.atlas.landmarks = markers.atlas.landmarks.map((landmark, index) => ({ ...landmark, id: `m${50 + index}_0` }));
  await routeJson(page, "GET", "**/atlases/marker-cabinet", markers);

  await page.goto("/");

  await expect(page.locator("#agent-asset")).toHaveText("home-cabinet");
  await expect(page.locator("button[data-view]")).toHaveCount(3);
  await page.locator("#agent-asset").click();
  await page.getByRole("option", { name: "marker-cabinet" }).click();
  await expect(page.getByText("No viewpoints with the target hidden")).toBeVisible();
});

test("the viewpoints the agent suggests are marked, and one is chosen from the agent's panel", async ({ page }) => {
  const move = turn("session-turn-move.json");
  if (move.turn.awaiting?.kind !== "view") throw new Error("the example asks for a view");
  move.turn.awaiting.suggested_views = ["A_close.png"];
  const service = await serve(page, { move });
  await startAtB(page);

  await expect(viewpoint(page, "A_close.png")).toHaveAttribute("data-suggested", "true");
  await expect(viewpoint(page, "C_close.png")).not.toHaveAttribute("data-suggested", "true");
  await agent(page).getByRole("button", { name: "A_close.png" }).click();

  await expect(agent(page)).toHaveAttribute("data-status", "approval");
  expect(service.view.bodies).toEqual([{ view: "A_close.png" }]);
});

test("a reload reads the session back from the service", async ({ page }) => {
  const service = await serve(page);
  await startAtB(page);

  await page.reload();

  await expect(agent(page)).toHaveAttribute("data-status", "view");
  expect(service.session.bodies).toHaveLength(1);
  await expect(page).toHaveURL(/:\d+\/$/);
  expect(await page.evaluate(() => Object.values(sessionStorage))).toContain(ID);
});

test("a call that fails says why, keeps the session, and Retry sends it again", async ({ page }) => {
  const service = await serve(page);
  await startAtB(page);
  service.view.reply({ detail: "session is not waiting for a view" }, 409);

  await viewpoint(page, "A_close.png").click();

  await expect(agent(page).getByRole("alert")).toContainText("session is not waiting for a view");
  await expect(agent(page).locator("[data-guidance]")).toBeVisible();
  service.view.reply(turn("session-turn-approval.json"));
  await agent(page).getByRole("button", { name: "Retry" }).click();
  await expect(agent(page)).toHaveAttribute("data-status", "approval");
  expect(service.view.bodies).toEqual([{ view: "A_close.png" }, { view: "A_close.png" }]);
});

test("the page shows facts and controls, no instructions, and logs no error", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    // The sidebar prefetches every page it lists; only this page's errors count.
    const where = new URL(message.location().url || "about:blank").pathname;
    if (message.type() === "error" && (where === "/" || where === "about:blank")) errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await serve(page);
  await startAtB(page);
  await viewpoint(page, "A_close.png").click();
  await expect(agent(page)).toHaveAttribute("data-status", "approval");

  const text = await page.getByRole("main").innerText();
  expect(text).not.toMatch(/\b(click|tap|press|choose|select an?|please|you can|how to|first,|then|uv run|npm|make)\b/i);
  expect(errors).toEqual([]);
});
