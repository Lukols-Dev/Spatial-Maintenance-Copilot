import { MIN_VIEWS } from "@/lib/annotate/core";
import {
  atlasReadiness,
  type AtlasBuildReport,
  type AtlasBuildRequest,
  type AtlasDetail,
  type AtlasSummary,
  type Board,
  type Camera,
  type Vec3,
  type ViewSetSummary,
  type Workspace,
} from "@/lib/workspace";

import { caliper, count, size } from "./format";
import { nameProblem, readNumber, type NumberRule } from "./rules";

// The Build form of the Atlas page: what it opens with, what its selects
// offer, and the request it sends. Every field holds the text of its control,
// so a value typed half-way stays as typed; a request is made only from a form
// with nothing missing, and what is missing is said in a few words.

export type Triple = [string, string, string];

export interface AtlasForm {
  view_set: string;
  camera_id: string;
  board: string;
  target_id: string;
  target_extent_mm: Triple;
  asset_id: string;
  version: string;
  click_sigma_px: string;
  target_centre_sigma_mm: string;
  samples: string;
  seed: string;
  /** All three empty: not measured. */
  target_measured_mm: Triple;
}

/** The fields the reader set; the others follow the workspace. */
export type FormDraft = Partial<AtlasForm>;

/** Something that stops a build, and the field it is about. */
export interface Missing {
  field: keyof AtlasForm;
  text: string;
}

export interface Option {
  value: string;
  label: string;
  disabled: boolean;
}

/** What POST /atlases uses for a field it is not sent. */
export const BUILD_DEFAULTS = {
  click_sigma_px: 2,
  target_centre_sigma_mm: 5,
  samples: 200,
  seed: 0,
  version: "1",
} as const;
export const SAMPLES_RANGE = { min: 10, max: 2000 } as const;

/** <id>.report.json is the build report of atlas <id>, so no atlas may be called that. */
const REPORT_SUFFIX = ".report";
/** The calibration board stays on the desk; an asset frame comes from a board fixed to the asset. */
const CALIBRATION_BOARD = "calibration_board";
/** The hidden component of this project's test object: the target when a set has it marked. */
const USUAL_TARGET = "drone";
/** The fields a view set decides: another set brings its own. */
const SET_FIELDS = ["camera_id", "target_id", "asset_id", "version"] as const;

const EMPTY: Triple = ["", "", ""];

// ---- choosing --------------------------------------------------------------------

function newestFirst<T>(items: readonly T[], time: (item: T) => string): T[] {
  return [...items].sort((a, b) => Date.parse(time(b)) - Date.parse(time(a)));
}

export function viewSetsNewestFirst(workspace: Workspace): ViewSetSummary[] {
  return newestFirst(workspace.view_sets, (set) => set.updated_at);
}

export function atlasesNewestFirst(workspace: Workspace): AtlasSummary[] {
  return newestFirst(workspace.atlases, (atlas) => atlas.built_at);
}

type Reported = AtlasDetail & { report: AtlasBuildReport };

function reported(detail: AtlasDetail): detail is Reported {
  return detail.report !== null;
}

/** The newest atlas the service built from this view set, as its build report says. */
export function previousBuild(details: readonly AtlasDetail[], viewSet: string): Reported | undefined {
  const fromSet = details.filter(reported).filter((detail) => detail.report.request.view_set === viewSet);
  return newestFirst(fromSet, (detail) => detail.report.built_at)[0];
}

/** The version after this one: a whole number counts up; anything else is the reader's to change. */
export function nextVersion(version: string): string {
  return /^\d{1,15}$/.test(version) ? String(Number(version) + 1) : version;
}

function calibrated(camera: Camera): boolean {
  return (
    camera.error === null && camera.camera_id !== null && camera.image_width !== null && camera.image_height !== null
  );
}

/** A calibrated camera whose intrinsics describe the set's pixels; any calibrated one without a set size. */
function fits(camera: Camera, set: ViewSetSummary | undefined): boolean {
  if (!calibrated(camera)) return false;
  const imageSize = set?.image_size;
  return !imageSize || (camera.image_width === imageSize[0] && camera.image_height === imageSize[1]);
}

/** The camera the set's points were marked on, else the first that fits its images. */
function defaultCamera(workspace: Workspace, set: ViewSetSummary | undefined): string {
  const clickedOn = set?.clicks?.camera_id;
  const usable = workspace.cameras.filter((camera) => fits(camera, set));
  const camera = usable.find((candidate) => candidate.camera_id === clickedOn) ?? usable[0];
  return camera?.camera_id ?? "";
}

/** The board of the last build, else a board on the asset, measured if one is. */
function defaultBoard(boards: readonly Board[], last: string | undefined): string {
  if (last && boards.some((board) => board.id === last)) return last;
  const onAsset = boards.filter((board) => board.id !== CALIBRATION_BOARD);
  return (onAsset.find((board) => board.measured) ?? onAsset[0] ?? boards[0])?.id ?? "";
}

/** The first candidate that is a point of the set. */
function defaultTarget(set: ViewSetSummary | undefined, candidates: readonly (string | null | undefined)[]): string {
  const points = set?.clicks?.point_views ?? {};
  return candidates.find((id): id is string => typeof id === "string" && Object.hasOwn(points, id)) ?? "";
}

function triple(values: Vec3 | null | undefined): Triple {
  return values ? [String(values[0]), String(values[1]), String(values[2])] : EMPTY;
}

/**
 * The form as it opens. The newest view set, the camera its points were marked
 * on, a board on the asset, and as the target the one this asset had, else
 * the drone, else the target of the newest atlas. The asset id is the one the
 * last atlas of that set was built under, else the set's name; when an atlas
 * of that id exists, its extent and build settings are repeated and its
 * version counts up, so building again replaces it with a newer version. The
 * draft's fields win over all of it. `details` are the atlases read so far.
 */
export function initialForm(workspace: Workspace, details: readonly AtlasDetail[], draft: FormDraft = {}): AtlasForm {
  const view_set = draft.view_set ?? viewSetsNewestFirst(workspace)[0]?.name ?? "";
  const set = workspace.view_sets.find((candidate) => candidate.name === view_set);
  const asset_id = draft.asset_id ?? previousBuild(details, view_set)?.atlas.asset_id ?? view_set;
  const existing = workspace.atlases.find((atlas) => atlas.asset_id === asset_id);
  const detail = details.find((candidate) => candidate.atlas.asset_id === asset_id);
  const last = detail?.report?.request;
  const newestTarget = atlasesNewestFirst(workspace).find((atlas) => atlas.target_id)?.target_id;

  return {
    view_set,
    camera_id: draft.camera_id ?? defaultCamera(workspace, set),
    board: draft.board ?? defaultBoard(workspace.rig.boards, last?.board),
    target_id: draft.target_id ?? defaultTarget(set, [last?.target_id, USUAL_TARGET, newestTarget]),
    target_extent_mm: draft.target_extent_mm ?? triple(detail?.atlas.target.extent_mm),
    asset_id,
    version: draft.version ?? (existing ? nextVersion(existing.version ?? BUILD_DEFAULTS.version) : BUILD_DEFAULTS.version),
    click_sigma_px: draft.click_sigma_px ?? String(last?.click_sigma_px ?? BUILD_DEFAULTS.click_sigma_px),
    target_centre_sigma_mm:
      draft.target_centre_sigma_mm ?? String(last?.target_centre_sigma_mm ?? BUILD_DEFAULTS.target_centre_sigma_mm),
    samples: draft.samples ?? String(last?.samples ?? BUILD_DEFAULTS.samples),
    seed: draft.seed ?? String(last?.seed ?? BUILD_DEFAULTS.seed),
    target_measured_mm: draft.target_measured_mm ?? triple(last?.target_measured_mm),
  };
}

/** The draft with another view set: the fields the set decides follow it again. */
export function withViewSet(draft: FormDraft, viewSet: string): FormDraft {
  const next: FormDraft = { ...draft, view_set: viewSet };
  for (const field of SET_FIELDS) delete next[field];
  return next;
}

// ---- what the selects offer ------------------------------------------------------

/** The view sets, newest first, with their image counts. */
export function setOptions(workspace: Workspace): Option[] {
  return viewSetsNewestFirst(workspace).map((set) => ({
    value: set.name,
    label: `${set.name} · ${count(set.image_count, "image")}`,
    disabled: false,
  }));
}

/** The boards of the rig, as the file lists them, each with its measured square. */
export function boardOptions(workspace: Workspace): Option[] {
  return workspace.rig.boards.map((board) => ({
    value: board.id,
    label: `${board.id} · ${board.square_measured_mm === null ? "not measured" : `${caliper(board.square_measured_mm)} mm`}`,
    disabled: false,
  }));
}

/** The cameras, those whose image size is the set's first; the others cannot be chosen. */
export function cameraOptions(workspace: Workspace, viewSet: string): Option[] {
  const set = workspace.view_sets.find((candidate) => candidate.name === viewSet);
  const options = workspace.cameras.map((camera) => {
    const name = camera.camera_id ?? camera.file;
    return {
      value: name,
      label: camera.error ? `${name} · unreadable` : `${name} · ${size(camera.image_width, camera.image_height)}`,
      disabled: !fits(camera, set),
    };
  });
  return [...options.filter((option) => !option.disabled), ...options.filter((option) => option.disabled)];
}

/** The points of the set with the images each is marked in; fewer than two cannot be triangulated. */
export function targetOptions(workspace: Workspace, viewSet: string): Option[] {
  const set = workspace.view_sets.find((candidate) => candidate.name === viewSet);
  return Object.entries(set?.clicks?.point_views ?? {}).map(([id, views]) => ({
    value: id,
    label: `${id} · ${count(views, "view")}`,
    disabled: views < MIN_VIEWS,
  }));
}

// ---- the request -----------------------------------------------------------------

export interface Checked {
  /** Null while anything is missing. */
  request: AtlasBuildRequest | null;
  missing: Missing[];
}

const AXES = ["x", "y", "z"] as const;

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/** The request the form makes, or what it lacks: the workspace's blockers first, then the typed fields. */
export function checkForm(workspace: Workspace, form: AtlasForm): Checked {
  const missing: Missing[] = [];
  const add = (field: keyof AtlasForm, text: string) => missing.push({ field, text });
  const numbers: Partial<Record<keyof AtlasForm, number>> = {};
  const read = (field: keyof AtlasForm, text: string, label: string, rule: NumberRule) => {
    const result = readNumber(text, label, rule);
    if ("problem" in result) add(field, result.problem);
    else numbers[field] = result.value;
  };

  const blockers = atlasReadiness(workspace, {
    view_set: form.view_set || undefined,
    camera_id: form.camera_id || undefined,
    board: form.board || undefined,
    target_id: form.target_id || undefined,
  });
  // A field left empty is a fact only when there is something to choose for it.
  if (blockers.view_set) add("view_set", blockers.view_set);
  else if (!form.view_set) add("view_set", "No view set chosen");
  if (blockers.camera_id) add("camera_id", blockers.camera_id);
  else if (!form.camera_id && cameraOptions(workspace, form.view_set).some((option) => !option.disabled)) {
    add("camera_id", "No camera chosen");
  }
  if (blockers.board) add("board", blockers.board);
  else if (!form.board) add("board", "No board chosen");
  if (blockers.target_id) {
    add("target_id", form.target_id ? `${form.target_id} ${lowerFirst(blockers.target_id)}` : blockers.target_id);
  } else if (!form.target_id && targetOptions(workspace, form.view_set).length > 0) {
    add("target_id", "No target chosen");
  }

  const extent: number[] = [];
  if (form.target_extent_mm.some((text) => text.trim() === "")) add("target_extent_mm", "Target extent missing");
  else {
    for (const [axis, text] of form.target_extent_mm.entries()) {
      const result = readNumber(text, `Target extent ${AXES[axis]}`, { above: 0, unit: "mm" });
      if ("problem" in result) add("target_extent_mm", result.problem);
      else extent.push(result.value);
    }
  }

  const asset_id = form.asset_id.trim();
  const assetProblem = nameProblem(asset_id, "Asset id");
  if (assetProblem) add("asset_id", assetProblem);
  else if (asset_id.toLowerCase().endsWith(REPORT_SUFFIX)) add("asset_id", `Asset id ends in ${REPORT_SUFFIX}`);
  const version = form.version.trim();
  if (!version) add("version", "Version missing");

  read("click_sigma_px", form.click_sigma_px, "Click σ", { above: 0, unit: "px" });
  read("target_centre_sigma_mm", form.target_centre_sigma_mm, "Target centre σ", { min: 0, unit: "mm" });
  read("samples", form.samples, "Samples", { integer: true, ...SAMPLES_RANGE });
  read("seed", form.seed, "Seed", { integer: true, min: 0 });

  let measured: Vec3 | null = null;
  const typed = form.target_measured_mm.filter((text) => text.trim() !== "").length;
  if (typed > 0 && typed < 3) add("target_measured_mm", "Measured target incomplete");
  else if (typed === 3) {
    const values: number[] = [];
    for (const [axis, text] of form.target_measured_mm.entries()) {
      const result = readNumber(text, `Measured target ${AXES[axis]}`, { unit: "mm" });
      if ("problem" in result) add("target_measured_mm", result.problem);
      else values.push(result.value);
    }
    if (values.length === 3) measured = [values[0], values[1], values[2]];
  }

  if (missing.length > 0) return { request: null, missing };
  return {
    request: {
      asset_id,
      view_set: form.view_set,
      camera_id: form.camera_id,
      board: form.board,
      target_id: form.target_id,
      target_extent_mm: [extent[0], extent[1], extent[2]],
      target_measured_mm: measured,
      click_sigma_px: numbers.click_sigma_px,
      target_centre_sigma_mm: numbers.target_centre_sigma_mm,
      samples: numbers.samples,
      seed: numbers.seed,
      version,
    },
    missing,
  };
}
