# smc-perception

FastAPI service that owns a workspace on disk: the cameras, the boards, the
view sets with their clicks, and the atlases. The web app is its client. The
geometry is in `smc_core`; this service reads and writes files and calls it.

## Running

```bash
make api                     # :8000, the repository is the workspace
SMC_WORKSPACE=/path/to/ws uv run uvicorn smc_perception.main:app --port 8000
```

| Variable               | Default                 | Meaning                                                        |
| ---------------------- | ----------------------- | -------------------------------------------------------------- |
| `SMC_WORKSPACE`        | the working directory   | Folder that holds `calib/` and `data/`. Read on every request. |
| `SMC_READ_ONLY`        | unset                   | `1`, `true` or `yes`: every write is refused with 403.         |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated web origins allowed to call the API.           |

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
