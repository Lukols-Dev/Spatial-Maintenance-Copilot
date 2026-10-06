// Logic of the point annotator, kept apart from the page so it can be tested.
//
// Two coordinate systems meet here. On screen and in the browser an image has
// its top-left corner at (0, 0). OpenCV puts (0, 0) at the centre of the first
// pixel, and every pixel the pipeline reads (corners, camera matrix) uses that
// convention. Clicks are stored the OpenCV way, so they sit half a pixel from
// what the canvas reports.
//
// Every function that changes the state returns a new state and leaves the
// one it was given untouched, which is what React state updates need.

/** An (x, y) position in pixels. */
export type Pixel = [number, number];

/** How the image sits on screen: screen = image * scale + (x, y). */
export interface View {
  scale: number;
  x: number;
  y: number;
}

/** One click per (image, point), stored in OpenCV pixels. */
export type Clicks = Record<string, Record<string, Pixel>>;

export interface AnnotationState {
  cameraId: string;
  points: string[];
  clicks: Clicks;
}

/** The file the atlas builder reads (smc_core.contracts.Clicks). */
export interface ClicksFile {
  camera_id: string;
  /**
   * Every point of the session in its order, clicked or not, so a point not yet
   * marked anywhere survives a save. Files written before it was added have none.
   */
  points?: string[];
  views: Clicks;
}

export type Outcome =
  | { ok: true; state: AnnotationState; name: string }
  | { ok: false; error: string };

const POINT_NAME = /^[A-Za-z0-9][A-Za-z0-9_.-]*$/;

/** The atlas builder triangulates a point only from at least this many views. */
export const MIN_VIEWS = 2;

// ---- view ---------------------------------------------------------------------

export function fitView(imageW: number, imageH: number, canvasW: number, canvasH: number): View {
  const scale = Math.min(canvasW / imageW, canvasH / imageH);
  return { scale, x: (canvasW - imageW * scale) / 2, y: (canvasH - imageH * scale) / 2 };
}

export function screenToImage(view: View, sx: number, sy: number): Pixel {
  return [(sx - view.x) / view.scale, (sy - view.y) / view.scale];
}

export function imageToScreen(view: View, ix: number, iy: number): Pixel {
  return [ix * view.scale + view.x, iy * view.scale + view.y];
}

/** Zoom by `factor` and keep the image point under (sx, sy) where it is. */
export function zoomAt(
  view: View,
  factor: number,
  sx: number,
  sy: number,
  minScale: number,
  maxScale: number,
): View {
  const scale = Math.min(maxScale, Math.max(minScale, view.scale * factor));
  const k = scale / view.scale;
  return { scale, x: sx - (sx - view.x) * k, y: sy - (sy - view.y) * k };
}

export function panBy(view: View, dx: number, dy: number): View {
  return { scale: view.scale, x: view.x + dx, y: view.y + dy };
}

export function toOpenCv(ix: number, iy: number): Pixel {
  return [ix - 0.5, iy - 0.5];
}

export function fromOpenCv(x: number, y: number): Pixel {
  return [x + 0.5, y + 0.5];
}

/**
 * A mouse reports whole screen pixels, so the position it gives is the
 * pixel's top-left corner. The cursor pointed somewhere inside the pixel, best
 * taken as its centre; without this every click is biased up and left.
 */
export function centreOfPixel(value: number): number {
  return Number.isInteger(value) ? value + 0.5 : value;
}

// ---- state --------------------------------------------------------------------

export function createState(): AnnotationState {
  return { cameraId: "", points: [], clicks: {} };
}

function checkPointName(state: AnnotationState, name: string): string | null {
  if (!POINT_NAME.test(name)) {
    return 'Use letters, digits, "_", "-" or "." and start with a letter or digit.';
  }
  if (state.points.includes(name)) {
    return `"${name}" already exists.`;
  }
  return null;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function withoutEmptyImages(clicks: Clicks): Clicks {
  return Object.fromEntries(
    Object.entries(clicks).filter(([, marked]) => Object.keys(marked).length > 0),
  );
}

export function addPoint(state: AnnotationState, name: string): Outcome {
  const trimmed = name.trim();
  const error = checkPointName(state, trimmed);
  if (error) return { ok: false, error };
  return { ok: true, name: trimmed, state: { ...state, points: [...state.points, trimmed] } };
}

export function renamePoint(state: AnnotationState, oldName: string, newName: string): Outcome {
  if (!state.points.includes(oldName)) return { ok: false, error: `"${oldName}" does not exist.` };
  const trimmed = newName.trim();
  if (trimmed === oldName) return { ok: true, name: oldName, state };
  const error = checkPointName(state, trimmed);
  if (error) return { ok: false, error };

  const clicks: Clicks = {};
  for (const [image, marked] of Object.entries(state.clicks)) {
    clicks[image] = Object.fromEntries(
      Object.entries(marked).map(([point, pixel]) => [point === oldName ? trimmed : point, pixel]),
    );
  }
  const points = state.points.map((point) => (point === oldName ? trimmed : point));
  return { ok: true, name: trimmed, state: { ...state, points, clicks } };
}

export function removePoint(state: AnnotationState, name: string): AnnotationState {
  const clicks: Clicks = {};
  for (const [image, marked] of Object.entries(state.clicks)) {
    clicks[image] = Object.fromEntries(Object.entries(marked).filter(([point]) => point !== name));
  }
  return {
    ...state,
    points: state.points.filter((point) => point !== name),
    clicks: withoutEmptyImages(clicks),
  };
}

/** Mark `point` in `image` at (ix, iy), a position with the image's top-left corner at (0, 0). */
export function place(
  state: AnnotationState,
  image: string,
  point: string,
  ix: number,
  iy: number,
): AnnotationState {
  if (!state.points.includes(point)) return state;
  const [x, y] = toOpenCv(ix, iy);
  return {
    ...state,
    clicks: { ...state.clicks, [image]: { ...state.clicks[image], [point]: [round2(x), round2(y)] } },
  };
}

export function unplace(state: AnnotationState, image: string, point: string): AnnotationState {
  const marked = state.clicks[image];
  if (!marked || !(point in marked)) return state;
  const rest = Object.fromEntries(Object.entries(marked).filter(([p]) => p !== point));
  return { ...state, clicks: withoutEmptyImages({ ...state.clicks, [image]: rest }) };
}

/** The click in OpenCV pixels, or null. */
export function clickAt(state: AnnotationState, image: string, point: string): Pixel | null {
  const marked = state.clicks[image];
  return marked && Object.prototype.hasOwnProperty.call(marked, point) ? marked[point] : null;
}

export function countsPerPoint(state: AnnotationState): Record<string, number> {
  const counts: Record<string, number> = Object.fromEntries(state.points.map((p) => [p, 0]));
  for (const marked of Object.values(state.clicks)) {
    for (const point of Object.keys(marked)) {
      if (point in counts) counts[point] += 1;
    }
  }
  return counts;
}

export function markedInImage(state: AnnotationState, image: string): string[] {
  return state.points.filter((point) => clickAt(state, image, point) !== null);
}

/**
 * The point `step` places after `current`, wrapping round. Without a current
 * point, stepping forward gives the first point and stepping back the last.
 */
export function stepPoint(state: AnnotationState, current: string | null, step: number): string | null {
  const n = state.points.length;
  if (n === 0) return null;
  const at = current === null ? -1 : state.points.indexOf(current);
  if (at === -1) return step >= 0 ? state.points[0] : state.points[n - 1];
  return state.points[(((at + step) % n) + n) % n];
}

/** The first point after `current` that has no click in `image`, or null. */
export function nextUnplaced(state: AnnotationState, image: string, current: string | null): string | null {
  const n = state.points.length;
  const at = current === null ? -1 : state.points.indexOf(current);
  for (let i = 1; i <= n; i++) {
    const candidate = state.points[(at + i + n) % n];
    if (clickAt(state, image, candidate) === null) return candidate;
  }
  return null;
}

// ---- files --------------------------------------------------------------------

export function toJson(state: AnnotationState): ClicksFile {
  const views: Clicks = {};
  for (const image of Object.keys(state.clicks).sort()) {
    const marked: Record<string, Pixel> = {};
    for (const point of state.points) {
      const pixel = clickAt(state, image, point);
      if (pixel) marked[point] = pixel;
    }
    if (Object.keys(marked).length > 0) views[image] = marked;
  }
  return { camera_id: state.cameraId, points: [...state.points], views };
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isPixel(value: unknown): value is Pixel {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    Number.isFinite(value[0]) &&
    Number.isFinite(value[1])
  );
}

/** The "points" list of a clicks file: empty when the file has none. Throws when it is malformed. */
function listedPoints(data: Record<string, unknown>): string[] {
  const points = data.points;
  if (points === undefined) return [];
  if (!Array.isArray(points) || !points.every((point): point is string => typeof point === "string" && point !== "")) {
    throw new Error('"points": expected a list of point names.');
  }
  const twice = points.find((point, index) => points.indexOf(point) !== index);
  if (twice !== undefined) throw new Error(`"points": "${twice}" is listed twice.`);
  return points;
}

/**
 * Merge a clicks file into the state. Throws an Error that says what is wrong.
 *
 * Pixels only mean something for the camera they were clicked on, so a file for
 * another camera than the session's is refused rather than merged.
 *
 * New points are added in the file's order: its "points" list first, then any
 * clicked point the list does not name (older files have no list).
 */
export function fromJson(
  state: AnnotationState,
  data: unknown,
): { state: AnnotationState; images: number; pointsAdded: number } {
  if (!isObject(data) || !isObject(data.views)) {
    throw new Error('Not a clicks file: "views" is missing.');
  }
  const incoming = typeof data.camera_id === "string" ? data.camera_id.trim() : "";
  const current = state.cameraId.trim();
  if (incoming && current && incoming !== current) {
    throw new Error(
      `this file is for camera "${incoming}", but this session is for "${current}". Change the camera id first.`,
    );
  }
  const views = data.views;
  for (const [image, marked] of Object.entries(views)) {
    if (!isObject(marked)) throw new Error(`"${image}": expected {point: [x, y]}.`);
    for (const [point, pixel] of Object.entries(marked)) {
      if (point === "" || !isPixel(pixel)) throw new Error(`"${image}" / "${point}": expected [x, y].`);
    }
  }
  const listed = listedPoints(data);

  const points = [...state.points];
  let added = 0;
  const include = (point: string) => {
    if (points.includes(point)) return;
    points.push(point);
    added += 1;
  };
  listed.forEach(include);
  const clicks: Clicks = { ...state.clicks };
  for (const [image, marked] of Object.entries(views)) {
    const merged = { ...clicks[image] };
    for (const [point, pixel] of Object.entries(marked as Record<string, Pixel>)) {
      include(point);
      merged[point] = [round2(pixel[0]), round2(pixel[1])];
    }
    clicks[image] = merged;
  }
  const cameraId = current ? state.cameraId : incoming;
  return {
    state: { cameraId, points, clicks: withoutEmptyImages(clicks) },
    images: Object.keys(views).length,
    pointsAdded: added,
  };
}

/** A state saved by an earlier session, or null when it is malformed. */
export function restore(saved: unknown): AnnotationState | null {
  if (!isObject(saved) || typeof saved.cameraId !== "string" || !Array.isArray(saved.points)) return null;
  const points = saved.points;
  if (!points.every((p): p is string => typeof p === "string" && p !== "")) return null;
  if (new Set(points).size !== points.length) return null;
  try {
    const fresh: AnnotationState = { cameraId: saved.cameraId, points: [...points], clicks: {} };
    return fromJson(fresh, { views: saved.clicks ?? {} }).state;
  } catch {
    return null;
  }
}
