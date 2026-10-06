// Serves out/ the way an S3 website endpoint does, so the end-to-end tests see
// the routing the deployed site will have:
// - a key is served as it is;
// - a path ending in "/" gets that folder's index.html;
// - a folder requested without the slash is redirected to it;
// - anything else is 404 with 404.html.
// Usage: node e2e/static-server.mjs <root> <port>

import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

const root = resolve(process.argv[2] ?? "out");
const port = Number(process.argv[3] ?? 3100);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};

async function fileAt(path) {
  try {
    return (await stat(path)).isFile() ? path : null;
  } catch {
    return null;
  }
}

async function folderAt(path) {
  try {
    return (await stat(path)).isDirectory();
  } catch {
    return false;
  }
}

function send(response, status, path) {
  response.writeHead(status, { "content-type": TYPES[extname(path)] ?? "application/octet-stream" });
  createReadStream(path)
    .on("error", () => response.destroy())
    .pipe(response);
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");
  let key;
  try {
    key = normalize(decodeURIComponent(url.pathname));
  } catch {
    response.writeHead(400).end();
    return;
  }
  const path = join(root, key);
  if (path !== root && !path.startsWith(root + sep)) {
    response.writeHead(400).end();
    return;
  }

  const target = key.endsWith("/") ? await fileAt(join(path, "index.html")) : await fileAt(path);
  if (target) {
    send(response, 200, target);
    return;
  }
  if (!key.endsWith("/") && (await folderAt(path)) && (await fileAt(join(path, "index.html")))) {
    response.writeHead(302, { location: `${url.pathname}/${url.search}` }).end();
    return;
  }
  const notFound = await fileAt(join(root, "404.html"));
  if (notFound) send(response, 404, notFound);
  else response.writeHead(404).end();
}).listen(port, "127.0.0.1", () => {
  console.log(`serving ${root} on http://127.0.0.1:${port}`);
});
