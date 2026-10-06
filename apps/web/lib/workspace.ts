import { useSyncExternalStore } from "react";

import { MIN_VIEWS, type ClicksFile } from "@/lib/annotate/core";
import { apiJson, apiUpload, errorMessage } from "@/lib/api";

// The workspace of the perception service: the cameras, boards, view sets and
// atlases on its disk. One store keeps the last answer of GET /workspace for
// every component that shows it, and the calls that change the workspace
// refresh it. Field names are the service's JSON names, so each type matches
// its example in lib/api-examples/ one to one.

export type Vec3 = [number, number, number];

// ---- models -------------------------------------------------------------------

/** A file in calib/intrinsics/. One that cannot be read is listed with error set and the rest null. */
export interface Camera {
  file: string;
  camera_id: string | null;
  image_width: number | null;
  image_height: number | null;
  frames: number | null;
  rms_px: number | null;
  fx: number | null;
  fy: number | null;
  cx: number | null;
  cy: number | null;
  /** k1 k2 p1 p2 k3; empty when the file cannot be read. */
  dist_coeffs: number[];
  /** Standard deviation of each intrinsic; empty when the file cannot be read. */
  std: Partial<Record<"fx" | "fy" | "cx" | "cy" | "k1" | "k2" | "p1" | "p2" | "k3", number>>;
  /** As written in the file. */
  calibrated_at: string | null;
  opencv_version: string | null;
  error: string | null;
}

/** calib/rig.yaml. A missing or broken file gives no boards and error set. */
export interface Rig {
  dictionary: string | null;
  boards: Board[];
  error: string | null;
}

export interface Board {
  id: string;
  squares_x: number;
  squares_y: number;
  /** First and last marker id, inclusive. */
  marker_ids: [number, number];
  square_nominal_mm: number;
  marker_nominal_mm: number;
  square_measured_mm: number | null;
  marker_measured_mm: number | null;
  measurement_uncertainty_mm: number | null;
  substrate: string | null;
  /** YYYY-MM-DD */
  measured_on: string | null;
  measured: boolean;
}

/**
 * A caliper reading of one board. The service refuses a square outside 0.8 to
 * 1.25 times the nominal size: that is a span typed as one square.
 */
export interface BoardMeasurement {
  square_measured_mm: number;
  measurement_uncertainty_mm: number;
  /** Smaller than the square. */
  marker_measured_mm?: number | null;
  substrate?: string | null;
  /** YYYY-MM-DD; the service's today when left out. */
  measured_on?: string | null;
}

/** A folder of data/views/. */
export interface ViewSetSummary {
  name: string;
  image_count: number;
  jpeg_count: number;
  /** [width, height]; null when the set is empty or its images differ in size. */
  image_size: [number, number] | null;
  mixed_sizes: boolean;
  /** Cameras whose image size is image_size. */
  camera_ids: string[];
  /** Null when the set has no clicks.json. */
  clicks: ClicksSummary | null;
  /** ISO 8601 with offset: the newest file of the set. */
  updated_at: string;
  error: string | null;
}

/** The clicks.json of a set, counted. An invalid file gives zero counts and error set. */
export interface ClicksSummary {
  camera_id: string;
  /** Defined points and clicked ids together. */
  point_count: number;
  marked_images: number;
  /** Points clicked in at least two images, the minimum to triangulate one. */
  ready_points: number;
  /** Images each point is clicked in: the defined points in their order first, zeros included. */
  point_views: Record<string, number>;
  /** ISO 8601 with offset. */
  saved_at: string;
  error: string | null;
}

export interface ViewSetImage {
  file: string;
  width: number | null;
  height: number | null;
  format: "png" | "jpeg";
  error: string | null;
}

export interface ViewSet {
  name: string;
  /** Sorted by file name. */
  images: ViewSetImage[];
  clicks: ClicksFile | null;
  clicks_error: string | null;
}

/** A file of data/atlas/. */
export interface AtlasSummary {
  asset_id: string;
  file: string;
  version: string | null;
  frame: string | null;
  landmarks: number | null;
  target_id: string | null;
  target_sigma_mm: number | null;
  /** ISO 8601 with offset. */
  built_at: string;
  has_report: boolean;
  error: string | null;
}

/** Positions are millimetres in the asset frame; sigma is the 1-sigma error of each coordinate. */
export interface Landmark {
  id: string;
  position_mm: Vec3;
  sigma_mm: number;
  description: string;
}

export interface Target {
  id: string;
  position_mm: Vec3;
  sigma_mm: number;
  /** Full size of a box around the target, along x, y and z. */
  extent_mm: Vec3;
  description: string;
}

/** smc_core.contracts.Atlas */
export interface Atlas {
  asset_id: string;
  version: string;
  /** How the asset frame is defined, e.g. "board:rig_board_a". */
  frame: string;
  landmarks: Landmark[];
  target: Target;
}

/** POST /atlases. The service fills in the optional fields with the defaults noted. */
export interface AtlasBuildRequest {
  asset_id: string;
  view_set: string;
  camera_id: string;
  board: string;
  target_id: string;
  target_extent_mm: Vec3;
  /** The target centre measured with a ruler, to compare the triangulated one with. */
  target_measured_mm?: Vec3 | null;
  /** 2.0 */
  click_sigma_px?: number;
  /** 5.0: how far the clicked centre of the target may be from its real centre. */
  target_centre_sigma_mm?: number;
  /** 200, from 10 to 2000. */
  samples?: number;
  /** 0 */
  seed?: number;
  /** "1" */
  version?: string;
}

/** A view in which the board was found. */
export interface PosedView {
  file: string;
  corners: number;
  rms_px: number;
}

export interface LocatedPoint {
  id: string;
  position_mm: Vec3;
  /** As stored in the atlas: for the target, the triangulation combined with target_centre_sigma_mm. */
  sigma_mm: number;
  triangulation_sigma_mm: number;
  views: number;
  worst_px: number;
  ray_angle_deg: number;
  is_target: boolean;
}

export interface AtlasBuildReport {
  /** ISO 8601 with offset. */
  built_at: string;
  /** The request as the service ran it, defaults filled in. */
  request: Required<AtlasBuildRequest>;
  posed_views: PosedView[];
  /** Images in which the board was not found: their clicks are not used. */
  unposed_views: string[];
  /** Sorted by id. */
  points: LocatedPoint[];
  /** Point id -> why it is not in the atlas. */
  skipped: Record<string, string>;
  /** Distance between the triangulated and the measured target, when one was measured. */
  target_gap_mm: number | null;
}

export interface AtlasDetail {
  atlas: Atlas;
  report: AtlasBuildReport | null;
}

export interface Workspace {
  /** Every change is refused (403): the public deployment. */
  read_only: boolean;
  cameras: Camera[];
  rig: Rig;
  view_sets: ViewSetSummary[];
  atlases: AtlasSummary[];
}

// ---- store --------------------------------------------------------------------

export type WorkspaceState =
  | { status: "loading" }
  | { status: "ready"; data: Workspace; refreshing: boolean }
  // A failed refresh keeps the last data it had, so the page does not go blank.
  | { status: "error"; message: string; data?: Workspace };

const LOADING: WorkspaceState = { status: "loading" };
/** Refreshes nobody asked for (first use, the tab shown again) are at least this far apart. */
const AUTO_REFRESH_MS = 2000;

let current: WorkspaceState = LOADING;
let latest = 0;
let lastRefreshAt = Number.NEGATIVE_INFINITY;
const listeners = new Set<() => void>();

function publish(next: WorkspaceState) {
  if (next === current) return;
  current = next;
  listeners.forEach((listener) => listener());
}

function lastData(): Workspace | undefined {
  return current.status === "loading" ? undefined : current.data;
}

/** Ask the service again. Never rejects: a failure becomes the error state. */
export async function refreshWorkspace(): Promise<void> {
  // Only the newest request may publish, so a slow old answer cannot overwrite a newer one.
  const request = ++latest;
  lastRefreshAt = Date.now();
  const data = lastData();
  publish(data ? { status: "ready", data, refreshing: true } : LOADING);
  try {
    const next = await apiJson<Workspace>("/workspace", { cache: "no-store" });
    if (request === latest) publish({ status: "ready", data: next, refreshing: false });
  } catch (error) {
    if (request !== latest) return;
    const message = errorMessage(error);
    const last = lastData();
    publish(last ? { status: "error", message, data: last } : { status: "error", message });
  }
}

function autoRefresh() {
  if (Date.now() - lastRefreshAt >= AUTO_REFRESH_MS) void refreshWorkspace();
}

function onVisibilityChange() {
  if (document.visibilityState === "visible") autoRefresh();
}

// The first component to show the workspace asks for it, so a page opened
// after another one changed the workspace does not show stale data.
function subscribe(listener: () => void) {
  if (listeners.size === 0) {
    document.addEventListener("visibilitychange", onVisibilityChange);
    autoRefresh();
  }
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) document.removeEventListener("visibilitychange", onVisibilityChange);
  };
}

/** The workspace as last read. The prerendered HTML always says "loading". */
export function useWorkspace(): WorkspaceState {
  return useSyncExternalStore(subscribe, () => current, () => LOADING);
}

/** The same state, for code outside React. */
export function workspaceState(): WorkspaceState {
  return current;
}

/** Apply a change the service has confirmed without reading the whole workspace again. */
function patchViewSet(name: string, change: (set: ViewSetSummary) => ViewSetSummary) {
  if (current.status === "loading" || !current.data) return;
  const data = current.data;
  const viewSets = data.view_sets.map((set) => (set.name === name ? change(set) : set));
  publish({ ...current, data: { ...data, view_sets: viewSets } });
}

// ---- calls --------------------------------------------------------------------

// Building an atlas poses every image; importing a video decodes every frame.
const SLOW_CALL_MS = 10 * 60_000;
// Browsers refuse a keepalive request whose body is over 64 KiB.
const KEEPALIVE_MAX_BYTES = 60_000;
const JSON_HEADERS = { "Content-Type": "application/json" };

function segment(value: string): string {
  return encodeURIComponent(value);
}

export async function measureBoard(id: string, body: BoardMeasurement): Promise<Board> {
  const board = await apiJson<Board>(`/boards/${segment(id)}/measurement`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
  await refreshWorkspace();
  return board;
}

/**
 * Create a view set from one video (the sharpest frame of every `window`
 * frames) or from images. onProgress gets the uploaded fraction; at 1 the
 * service is still converting.
 */
export async function importViews(
  input: { name: string; window?: number; files: File[] },
  onProgress?: (fraction: number) => void,
): Promise<ViewSetSummary> {
  const form = new FormData();
  form.append("name", input.name);
  if (input.window !== undefined) form.append("window", String(input.window));
  for (const file of input.files) form.append("files", file, file.name);
  const summary = await apiUpload<ViewSetSummary>("/view-sets", form, { timeoutMs: SLOW_CALL_MS, onProgress });
  await refreshWorkspace();
  return summary;
}

export function getViewSet(name: string, options: { signal?: AbortSignal } = {}): Promise<ViewSet> {
  return apiJson<ViewSet>(`/view-sets/${segment(name)}`, { cache: "no-store", signal: options.signal });
}

/**
 * Replace the set's clicks.json. The answer updates that set in the store; the
 * rest of the workspace is not read again, as this runs on every edit.
 * keepalive lets the request outlive the page (a save flushed on page hide),
 * for a body small enough for the browser to accept it.
 */
export async function saveClicks(
  name: string,
  clicks: ClicksFile,
  options: { signal?: AbortSignal; keepalive?: boolean } = {},
): Promise<ClicksSummary> {
  const body = JSON.stringify(clicks);
  const summary = await apiJson<ClicksSummary>(`/view-sets/${segment(name)}/clicks`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body,
    signal: options.signal,
    keepalive: options.keepalive === true && new TextEncoder().encode(body).length <= KEEPALIVE_MAX_BYTES,
  });
  patchViewSet(name, (set) => ({ ...set, clicks: summary, updated_at: summary.saved_at }));
  return summary;
}

export function getAtlas(id: string, options: { signal?: AbortSignal } = {}): Promise<AtlasDetail> {
  return apiJson<AtlasDetail>(`/atlases/${segment(id)}`, { cache: "no-store", signal: options.signal });
}

/** Can take tens of seconds: the service poses every image of the set first. */
export async function buildAtlas(body: AtlasBuildRequest): Promise<AtlasDetail> {
  const detail = await apiJson<AtlasDetail>("/atlases", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
    timeoutMs: SLOW_CALL_MS,
  });
  await refreshWorkspace();
  return detail;
}

// ---- helpers for the pages ----------------------------------------------------

/**
 * One square from a caliper reading across several: the reading error is
 * divided by their number. Null for a reading or a count that cannot be right.
 */
export function squareFromSpan(lengthMm: number, squares: number): number | null {
  if (!Number.isFinite(lengthMm) || lengthMm <= 0 || !Number.isInteger(squares) || squares < 1) return null;
  // Micrometres: below any caliper's resolution, without binary noise such as 25.020000000000003.
  return Math.round((lengthMm / squares) * 1000) / 1000;
}

function calibrated(camera: Camera): boolean {
  return (
    camera.error === null && camera.camera_id !== null && camera.image_width !== null && camera.image_height !== null
  );
}

/**
 * The calibrated cameras whose image size is the set's: the only ones whose
 * intrinsics describe its pixels. Empty for an unknown set and for one whose
 * images differ in size.
 */
export function matchingCameras(workspace: Workspace, viewSet: string): Camera[] {
  const size = workspace.view_sets.find((set) => set.name === viewSet)?.image_size;
  if (!size) return [];
  return workspace.cameras.filter(
    (camera) => calibrated(camera) && camera.image_width === size[0] && camera.image_height === size[1],
  );
}

/** The fields of a build request that atlasReadiness checks. */
export type AtlasChoice = Partial<Pick<AtlasBuildRequest, "view_set" | "camera_id" | "board" | "target_id">>;

/** What stops a build, per request field: a fact in a few words, to show next to that field. */
export type AtlasBlockers = Partial<Record<keyof AtlasChoice, string>>;

/** What a build takes from a view set. */
interface Buildable {
  name: string;
  size: [number, number];
  clicks: ClicksSummary;
}

/** The parts of a set a build needs, or why it cannot be built from. */
function buildable(set: ViewSetSummary): Buildable | string {
  if (set.error) return set.error;
  if (set.image_count === 0) return "No images";
  if (!set.image_size) return "Images differ in size";
  if (!set.clicks) return "No points marked";
  if (set.clicks.error) return set.clicks.error;
  return { name: set.name, size: set.image_size, clicks: set.clicks };
}

/**
 * What is missing to build an atlas. A chosen field is checked as chosen; a
 * field left out blocks only when the workspace has nothing that could fill
 * it. With every field chosen and no blockers the service will try the build,
 * which can still fail on the images (a board not found in enough of them).
 */
export function atlasReadiness(workspace: Workspace, choice: AtlasChoice = {}): AtlasBlockers {
  const blockers: AtlasBlockers = {};

  // The view set: the chosen one, else the newest one that can be built from.
  let set: Buildable | undefined;
  if (choice.view_set !== undefined) {
    const chosen = workspace.view_sets.find((candidate) => candidate.name === choice.view_set);
    const result = chosen ? buildable(chosen) : "Unknown view set";
    if (typeof result === "string") blockers.view_set = result;
    else set = result;
  } else if (workspace.view_sets.length === 0) {
    blockers.view_set = "No view set";
  } else {
    const results = [...workspace.view_sets]
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
      .map(buildable);
    set = results.find((result): result is Buildable => typeof result !== "string");
    if (!set && typeof results[0] === "string") blockers.view_set = results[0];
  }

  // The camera: its intrinsics must describe the images, and the clicks must be made on them.
  const cameras = workspace.cameras.filter(calibrated);
  let camera: Camera | undefined;
  if (choice.camera_id !== undefined) {
    camera = cameras.find((candidate) => candidate.camera_id === choice.camera_id);
    if (!camera) {
      const unreadable = workspace.cameras.find((candidate) => candidate.camera_id === choice.camera_id);
      blockers.camera_id = unreadable?.error ?? "Unknown camera";
    }
  } else if (cameras.length === 0) {
    blockers.camera_id = "No calibrated camera";
  } else if (set) {
    // The camera the clicks were made on, else the only one that fits the images.
    const { name, size, clicks } = set;
    const matching = matchingCameras(workspace, name);
    camera = cameras.find((candidate) => candidate.camera_id === clicks.camera_id);
    if (!camera && matching.length === 1) camera = matching[0];
    if (!camera && matching.length === 0) blockers.camera_id = `No camera for ${size[0]}×${size[1]}`;
  }
  if (camera && set) {
    const { size, clicks } = set;
    if (camera.image_width !== size[0] || camera.image_height !== size[1]) {
      blockers.camera_id = `Camera is ${camera.image_width}×${camera.image_height}, images ${size[0]}×${size[1]}`;
    } else if (clicks.camera_id !== camera.camera_id) {
      blockers.camera_id = clicks.camera_id ? `Clicks are for ${clicks.camera_id}` : "Clicks have no camera id";
    }
  }

  // The board defines the asset frame, so its real size must be known.
  const boards = workspace.rig.boards;
  if (choice.board !== undefined) {
    const board = boards.find((candidate) => candidate.id === choice.board);
    if (!board) blockers.board = workspace.rig.error ?? "Unknown board";
    else if (!board.measured) blockers.board = "Board not measured";
  } else if (boards.length === 0) {
    blockers.board = workspace.rig.error ?? "No board";
  } else if (!boards.some((board) => board.measured)) {
    blockers.board = "No board measured";
  }

  // The target is triangulated like any other point.
  if (set) {
    const { clicks } = set;
    if (choice.target_id !== undefined) {
      const views = Object.hasOwn(clicks.point_views, choice.target_id) ? clicks.point_views[choice.target_id] : 0;
      if (views === 0) blockers.target_id = "Not marked";
      else if (views < MIN_VIEWS) {
        blockers.target_id = `Marked in ${views} image${views === 1 ? "" : "s"}, needs ${MIN_VIEWS}`;
      }
    } else if (clicks.ready_points === 0) {
      blockers.target_id = `No point marked in ${MIN_VIEWS} images`;
    }
  }

  return blockers;
}
