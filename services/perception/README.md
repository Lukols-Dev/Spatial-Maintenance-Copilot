# smc-perception

FastAPI service that owns a workspace on disk: the cameras, the boards, the
view sets with their clicks, and the atlases. The web app is its client. The
geometry is in `smc_core`; this service reads and writes files and calls it.

## Running

```bash
cp services/perception/.env.example services/perception/.env   # once; git ignores .env
make api                     # :8000, the repository is the workspace, settings from .env
SMC_WORKSPACE=/path/to/ws uv run uvicorn smc_perception.main:app --port 8000
```


Two kinds of setting:

- **The agent's model and its keys**, in `services/perception/.env` (git ignores
  it). `.env.example` lists exactly these, and every one is required: the
  service does not start without them, and names the ones missing.

  | Variable                | Meaning                                                                                                                           |
  | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
  | `SMC_BEDROCK_REGION`    | AWS region with access to the model, e.g. `eu-north-1`.                                                                           |
  | `SMC_AGENT_MODEL`       | Bedrock model id: `eu.amazon.nova-2-lite-v1:0` (Amazon Nova, through Converse) or `anthropic.claude-opus-5-5` (Claude, Messages API). |
  | `SMC_AGENT_EFFORT`      | How long the model may think per call: `low` to `max` (Nova has three levels: `xhigh` and `max` are its `high`).                  |
  | `AWS_ACCESS_KEY_ID`     | Key of an IAM user allowed to invoke the model (`AKIA…`).                                                                         |
  | `AWS_SECRET_ACCESS_KEY` | Its secret.                                                                                                                       |

- **How the service runs**, from the environment, with local defaults; `make api`
  sets the workspace and the deployment the rest. No secrets, so no file.

  | Variable               | Default                 | Meaning                                                        |
  | ---------------------- | ----------------------- | -------------------------------------------------------------- |
  | `SMC_WORKSPACE`        | the working directory   | Folder that holds `calib/` and `data/`. Read on every request. |
  | `SMC_READ_ONLY`        | unset                   | `1`, `true` or `yes`: every write is refused with 403.         |
  | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated web origins allowed to call the API.           |

`src/smc_perception/config.py` reads both, a variable set in the shell winning
over the file. At startup the service logs what is configured (the key id
masked) and stops on anything missing or invalid, every variable named. The
keys reach the Bedrock client from the settings; on ECS they come into the
task's environment from Secrets Manager. The container has no copy of the
file: `make api-run` passes it to Docker. The tests read no `.env`
(`SMC_ENV_FILE` is empty in them) and never call Bedrock. When the model gives
no answer, the reason is logged (`the model gave no answer: ...`), not shown in
the trace.

## Workspace

```
calib/intrinsics/*.yml            cameras, as save_calibration writes them (.yaml .json .xml too)
calib/rig.yaml                    the printed boards and their caliper measurements
data/views/<set>/*.png|jpg|jpeg   view sets
data/views/<set>/clicks.json      the points marked on that set (smc_core.contracts.Clicks)
data/atlas/<asset_id>.json        atlases (smc_core.contracts.Atlas)
data/atlas/<asset_id>.report.json what went into an atlas the service built
```

Set names and asset ids match `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`; image files
are named `^[A-Za-z0-9][A-Za-z0-9._ -]*\.(png|jpe?g)$`. Anything else in these
folders is not listed. A path from a request must stay inside its folder and
inside the workspace, symlinks resolved. `data/views` and `data/atlas` are
created by the first write. Every file is written to a temporary file next to
it and renamed into place.

## Endpoints

| Method | Path                               | Body                                     | Answer                  |
| ------ | ---------------------------------- | ---------------------------------------- | ----------------------- |
| GET    | `/health`                          |                                          | `{status, service, version}` |
| GET    | `/workspace`                       |                                          | `Workspace`             |
| PUT    | `/boards/{board_id}/measurement`   | `BoardMeasurement`                       | `Board`                 |
| POST   | `/view-sets`                       | multipart: `name`, `window` (15), `files` | `ViewSetSummary`, 201  |
| GET    | `/view-sets/{name}`                |                                          | `ViewSet`               |
| GET    | `/view-sets/{name}/images/{file}`  |                                          | the image; `?width=N`: a thumbnail |
| PUT    | `/view-sets/{name}/clicks`         | `Clicks`                                 | `ClicksSummary`         |
| GET    | `/atlases/{asset_id}`              |                                          | `AtlasDetail`           |
| POST   | `/atlases`                         | `AtlasBuildRequest`                      | `AtlasDetail`, 201      |
| POST   | `/localise`                        | `LocaliseRequest`                        | `LocaliseResult`        |
| POST   | `/sessions`                        | `SessionStart`                           | `SessionTurn`, 201      |
| GET    | `/sessions/{id}`                   |                                          | `SessionTurn`, every event |
| POST   | `/sessions/{id}/view`              | `ViewChoice`                             | `SessionTurn`           |
| POST   | `/sessions/{id}/approval`          | `ApprovalAnswer`                         | `SessionTurn`           |

The models are in `src/smc_perception/models.py`; `apps/web/lib/api-examples/`
has an example of each, checked by `tests/test_api_examples.py`. Errors are
`{"detail": "..."}`, or FastAPI's list for an invalid body: 403 read-only, 404
unknown, 409 the workspace does not allow it yet (an unmeasured board, a set
without clicks), 422 invalid input, and 500 for anything else, as
`internal error: <exception>` (a full disk, say). Every answer carries the
CORS headers, a 500 too, so the web app can show why. `GET /workspace` never
fails because one file is bad; that item carries an `error`.

- **Measurement**: edits `calib/rig.yaml` in place. Only the board's
  `square_measured_mm`, `marker_measured_mm`, `measurement_uncertainty_mm`,
  `substrate` and `measured_on` change; comments and layout stay. A square
  outside 0.8 to 1.25 times the nominal side is refused.
- **Import**: one video (`.mov .mp4 .m4v .avi .mkv`), whose sharpest frame of
  every `window` frames is kept, or photos (`.png .jpg .jpeg`), read in the
  sensor grid. Both become PNG files, as `tools/export_views.py` writes them.
- **Atlas build**: poses every image of the set on the board and triangulates
  the clicks with the code `tools/build_atlas.py` runs, so both give the same
  atlas for the same files and seed. It can take tens of seconds.
- **Images**: `?width=N` (16 to 2048) scales the image down to N px wide,
  aspect kept, as a JPEG of quality 85, read in the sensor grid like the
  clicks; N at or above the image's width gets the file itself. Every answer
  has an `ETag` (modification time, size, width) and `Cache-Control: no-cache`;
  a matching `If-None-Match` gets 304.
- **Localise**: poses one image from its clicks of atlas landmarks
  (`smc_core.localise`) and judges the result (`smc_core.policy.decide`):
  reliable, or the move to a better viewpoint. A localisation that fails is
  an answer too, with the failure named. Other clicked points are listed in
  `ignored_points`. The truth is the target's click in `truth_view`, an image
  of the same set taken from the same spot, else in the image itself. The
  click sigma is the request's, else the atlas build's, else 2 px; the
  answer's `request` shows the sigma and the truth image used. 409 when the
  set or the image has no clicks, the target is not clicked in `truth_view`,
  the clicks' camera is not calibrated, or an image is not of the camera's
  size. It writes nothing, so a read-only service answers it.
- **Sessions**: the agent of `smc_agent` on one atlas and one view set. Its
  viewpoints are the images whose clicks mark atlas landmarks and not the
  target, so the target is hidden in them; the truth of one is the image of
  the same name up to the first `_` with the target clicked (`B1_close.png`
  and `B1_open.png`). `POST /sessions` localises the first viewpoint and runs
  the agent's turn; the answer asks for a viewpoint (`ViewRequest`, with the
  policy's move and recorded viewpoints that lie that way) or for approval of
  the next step (`ApprovalRequest`). A `SessionTurn` carries the turn, the
  `/localise` answer of its viewpoint to draw, and the model's name. Sessions
  live in memory: a restart ends them. 404 for an unknown session, 409 for an
  answer it does not wait for, 422 for a view that is not one of its
  viewpoints. Sessions write nothing to the workspace, so a read-only service
  runs them.
