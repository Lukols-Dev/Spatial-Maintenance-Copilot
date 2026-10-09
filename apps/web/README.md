# Web app

Next.js 16 with shadcn/ui, exported as static files for S3 + CloudFront. The geometry runs in Python
(`packages/smc_core`, `services/perception`); this app reads and changes the perception service's workspace
through its HTTP API, from the browser.

## Pages

| Path | What it is |
|---|---|
| `/` | Locate: pick an atlas and a recorded viewpoint; `POST /localise` draws the landmarks, the target region and its 95 % region on the image, with the decision (accept, or the move that should give a better view) and a trace of the viewpoints tried |
| `/annotate/` | Point annotator on PNG files opened from disk: mark landmarks and the target, download `clicks.json` |
| `/annotate/?set=<name>` | The same on a view set of the workspace: images from the service, every change saved to its `clicks.json` |
| `/atlas/` | Atlas: import a video or photos as a view set, measure the rig board, build an atlas from a set's clicks and inspect it (points, σ, plan of the board frame) |

The sidebar lists the pages of `NAV` in `lib/site.ts`. A page is listed only once it works; the site has no
placeholder pages.

## The perception service

`NEXT_PUBLIC_API_URL` is the service's address, `http://localhost:8000` when unset (see `.env.example`). It is
baked in at build time. The service owns a workspace on its disk (`calib/` and `data/` under `SMC_WORKSPACE`);
the web app keeps no data of its own beyond the local annotator session in `localStorage`.

- `lib/api.ts` is the only place that talks HTTP. A failed call rejects with an `ApiError`: `status` is the HTTP
  status, or `null` when no answer came, and the message is FastAPI's `detail` (a validation list becomes
  `field: problem; …`), `HTTP <status>`, `Cannot reach the perception service at <url>` or
  `No answer within <n> s`. `errorMessage(error)` gives that text for anything caught.
- `lib/workspace.ts` has the types of the service's models, with the JSON field names as they are. Each has an
  example in `lib/api-examples/`; `tests/test_api_examples.py` validates them against the pydantic models, and the
  web tests answer with them.
- `useWorkspace()` is one store of `GET /workspace` for the whole page. It reads again when a component starts
  showing it and when the tab becomes visible, at most every 2 s, and keeps the last good data when a read fails.
- The calls, each `GET` unless noted:

  | Function | Endpoint |
  |---|---|
  | `measureBoard(id, measurement)` | `PUT /boards/{id}/measurement` |
  | `importViews({name, window, files}, onProgress)` | `POST /view-sets`, multipart, with upload progress |
  | `getViewSet(name)` | `/view-sets/{name}` |
  | `imageUrl(name, file)` in `lib/api.ts` | `/view-sets/{name}/images/{file}` |
  | `saveClicks(name, clicks)` | `PUT /view-sets/{name}/clicks` |
  | `getAtlas(id)` | `/atlases/{id}` |
  | `buildAtlas(request)` | `POST /atlases`, up to 10 minutes |

  A change re-reads the workspace once it succeeds, except `saveClicks`, which runs on every edit and updates
  only its view set in the store from the answer.
- A read-only service (`SMC_READ_ONLY`) answers every change with 403; `read_only` in the workspace says so in
  advance.
- `lib/health.ts` asks `GET /health` for the API status in the sidebar.

## Run and check

```bash
npm ci
npm run dev          # http://localhost:3000; the service: `make api` from the repository root
npm run lint
npm run typecheck    # next typegen, then tsc
npm test             # Vitest, lib/**/*.test.ts
npm run test:e2e     # next build, then Playwright on out/ with the installed Google Chrome
```

From the repository root, `make web-check` runs lint, typecheck and unit tests, and `make e2e` the browser tests.

The end-to-end tests serve `out/` with `e2e/static-server.mjs`, which answers like an S3 website endpoint
(folder index, redirect to the trailing slash, `404.html`). That checks the layout of the export, not the
CloudFront setup below, which has its own rules. The perception service does not run in them: `e2e/helpers.ts`
answers its endpoints (`stubHealth`, `stubWorkspace`, `routeJson`) with the examples (`example(name)`) and
records what the page sent.

## Deploying

- `npm run build` writes the site to `out/`. With `trailingSlash: true` every page is `<path>/index.html`.
- `NEXT_PUBLIC_API_URL` is baked in at build time. Set it in the environment of the deploy build;
  `.env.local` (localhost) would otherwise end up in the bundle.
- The API must allow the site's origin in CORS (`CORS_ALLOWED_ORIGINS` in the perception service), for `GET`,
  `POST` and `PUT`.
- CloudFront with a private S3 origin does not serve `index.html` for sub-paths: add a viewer-request function
  that appends `index.html` to URIs ending in `/` and redirects extensionless paths to `<path>/`.
- A private S3 origin answers a missing key with 403, not 404. Map both 403 and 404 to `/404.html` with status
  404 in CloudFront's custom error responses.
- The site is served over https, so the API must be https too, for example the API Gateway endpoint or an ALB
  with an ACM certificate. The browser blocks an http API as mixed content.
- Files under `_next/static/` are content-hashed and can be cached for a year; HTML and the `*.txt` payloads
  change on every deploy and should not be cached for long.
