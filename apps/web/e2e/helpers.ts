import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, type Page, type Request } from "@playwright/test";

import type { Workspace } from "../lib/workspace";

export interface View {
  name: string;
  /** Dots to draw, in OpenCV pixels: (0, 0) is the centre of the first pixel. */
  dots: Record<string, [number, number]>;
}

export type Upload = { name: string; mimeType: string; buffer: Buffer };

/**
 * Portrait 1080×1920 views with a red dot on every given position, drawn in
 * the page and returned as files for an <input type="file">, so no image file
 * is ever committed.
 */
export async function makeViews(page: Page, views: View[], mimeType = "image/png"): Promise<Upload[]> {
  const encoded = await page.evaluate(
    ({ list, type }) =>
      list.map((view) => {
        const canvas = document.createElement("canvas");
        canvas.width = 1080;
        canvas.height = 1920;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("no 2d context");
        ctx.fillStyle = "#e8e8e8";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        for (const [x, y] of Object.values(view.dots)) {
          ctx.fillStyle = "#fff";
          ctx.beginPath();
          ctx.arc(x + 0.5, y + 0.5, 8, 0, 2 * Math.PI);
          ctx.fill();
          ctx.fillStyle = "#d00";
          ctx.beginPath();
          ctx.arc(x + 0.5, y + 0.5, 5, 0, 2 * Math.PI);
          ctx.fill();
        }
        return canvas.toDataURL(type).split(",")[1];
      }),
    { list: views, type: mimeType },
  );
  return views.map((view, index) => ({ name: view.name, mimeType, buffer: Buffer.from(encoded[index], "base64") }));
}

export function canvas(page: Page) {
  return page.locator("canvas[data-image]");
}

/** The canvas shows this image: it has loaded and been fitted, not just been selected. */
export async function waitForImage(page: Page, name: string) {
  await expect(canvas(page)).toHaveAttribute("data-loaded", name);
}

/** Where an OpenCV pixel of the open image is on screen, from the view the canvas publishes. */
export async function screenOf(page: Page, [x, y]: [number, number]): Promise<[number, number]> {
  const box = await canvas(page).boundingBox();
  if (!box) throw new Error("canvas not visible");
  const view = await viewOf(page);
  return [box.x + (x + 0.5) * view.scale + view.x, box.y + (y + 0.5) * view.scale + view.y];
}

export async function viewOf(page: Page) {
  const element = canvas(page);
  return {
    scale: Number(await element.getAttribute("data-view-scale")),
    x: Number(await element.getAttribute("data-view-x")),
    y: Number(await element.getAttribute("data-view-y")),
  };
}

export async function viewScale(page: Page): Promise<number> {
  return (await viewOf(page)).scale;
}

/** The annotation state the page autosaves. */
export async function savedState(page: Page): Promise<{
  cameraId: string;
  points: string[];
  clicks: Record<string, Record<string, [number, number]>>;
}> {
  return page.evaluate(() => JSON.parse(localStorage.getItem("smc-annotate:v1") ?? "null"));
}

/** The perception service is not running in the tests; answer /health for it. */
export async function stubHealth(page: Page, online = true) {
  await page.route("**/health", (route) =>
    online
      ? route.fulfill({ json: { status: "ok", service: "perception", version: "0.1.0" } })
      : route.abort("connectionrefused"),
  );
}

/** A fresh copy of lib/api-examples/<name>: answers of the perception service as its contract shows them. */
export function example<T>(name: string): T {
  const file = name.endsWith(".json") ? name : `${name}.json`;
  return JSON.parse(readFileSync(join(__dirname, "..", "lib", "api-examples", file), "utf8")) as T;
}

/** One stubbed endpoint of the perception service. */
export interface Stub {
  /** What each request sent, in order: parsed JSON, or the raw text of any other body (multipart). */
  readonly bodies: unknown[];
  /** Answer later requests with this instead. */
  reply(json: unknown, status?: number): void;
  /** Refuse later connections, as a stopped service does. */
  goOffline(): void;
  /** Keep later answers back until release(), to see what the page shows while it waits. */
  hold(): void;
  release(): void;
}

type Answer = { json: unknown; status: number } | "offline";

function bodyOf(request: Request): unknown {
  const text = request.postData();
  if (text === null) return null;
  return (request.headers()["content-type"] ?? "").includes("application/json") ? JSON.parse(text) : text;
}

async function stub(page: Page, method: string, urlGlob: string, first: Answer): Promise<Stub> {
  let answer = first;
  let held: { promise: Promise<void>; release: () => void } | null = null;
  const bodies: unknown[] = [];
  // Other methods on the same URL fall through to their own stubs. CORS
  // preflights never get here: Playwright answers them for routed requests.
  await page.route(urlGlob, async (route) => {
    const request = route.request();
    if (request.method() !== method) {
      await route.fallback();
      return;
    }
    bodies.push(bodyOf(request));
    if (held) await held.promise;
    if (answer === "offline") await route.abort("connectionrefused");
    else await route.fulfill({ status: answer.status, json: answer.json });
  });
  return {
    bodies,
    reply(json, status = 200) {
      answer = { json, status };
    },
    goOffline() {
      answer = "offline";
    },
    hold() {
      if (held) return;
      const { promise, resolve } = Promise.withResolvers<void>();
      held = { promise, release: resolve };
    },
    release() {
      held?.release();
      held = null;
    },
  };
}

/** Answer `method urlGlob` of the perception service with this JSON, and record what the page sent. */
export function routeJson(page: Page, method: string, urlGlob: string, json: unknown, status = 200): Promise<Stub> {
  return stub(page, method.toUpperCase(), urlGlob, { json, status });
}

/** Answer GET /workspace with this workspace, or refuse the connection. */
export function stubWorkspace(page: Page, data: Workspace | "offline"): Promise<Stub> {
  return stub(page, "GET", "**/workspace", data === "offline" ? "offline" : { json: data, status: 200 });
}
