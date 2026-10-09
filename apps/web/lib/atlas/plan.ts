import type { AtlasDetail, Board, Vec3 } from "@/lib/workspace";

// The plan view of an atlas: its frame seen face-on, the way the board was
// printed. The board defines the frame (OpenCV's ChArUco convention): origin
// at the board's top-left corner, x along its first square count to the
// right, y along the second one down, z into the board. SVG's y grows
// downward too, so millimetres become pixels by one scale and one offset,
// with no flip. z is not drawn; the points table has it.

export interface PlanPoint {
  id: string;
  position_mm: Vec3;
  /** 1-sigma error of each coordinate. */
  sigma_mm: number;
}

export interface PlanTarget extends PlanPoint {
  /** Full size of the box around the target along x, y and z. */
  extent_mm: Vec3;
}

export interface PlanBoard {
  id: string;
  squares_x: number;
  squares_y: number;
  square_mm: number;
}

export interface PlanInput {
  landmarks: readonly PlanPoint[];
  target: PlanTarget;
  /** Null when the board's size is not known: no outline is drawn. */
  board: PlanBoard | null;
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Segment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface Label {
  x: number;
  y: number;
  anchor: "start" | "middle" | "end";
  text: string;
}

/** A point in pixels: its centre, its 1-sigma circle, and its label when one fits. */
export interface PlacedPoint {
  id: string;
  x: number;
  y: number;
  r: number;
  label: Label | null;
}

export interface Plan {
  width: number;
  height: number;
  /** Pixels per millimetre, the same along x and y. */
  scale: number;
  /** Where the frame's origin is; the axes start there. */
  origin: { x: number; y: number };
  axes: { x: Segment & { label: Label }; y: Segment & { label: Label } };
  board: (Box & { grid: Segment[] }) | null;
  landmarks: PlacedPoint[];
  target: PlacedPoint & { box: Box };
  scaleBar: Segment & { mm: number; label: Label };
}

/** Room around the drawing for labels, in pixels. */
const PAD = 24;
/** Room below it for the scale bar. */
const BAND = 24;
/** Length of each axis arrow. */
const AXIS = 32;
/** Radius of a point's dot; labels start this far beyond it. */
export const DOT = 4;
const GAP = 4;
const FONT = 11;
/** Width of a character of the label font, rounded up: labels are placed by this estimate. */
const CHAR = 6.6;
const LINE = 14;
/** The scale bar is at most this share of the drawing's width, and may always be this long in pixels. */
const BAR_SHARE = 0.4;
const BAR_MIN = 48;

/** The board's outline from the rig, at its measured square size: the size posing uses. */
export function planBoard(board: Board | undefined): PlanBoard | null {
  if (!board || board.square_measured_mm === null) return null;
  return {
    id: board.id,
    squares_x: board.squares_x,
    squares_y: board.squares_y,
    square_mm: board.square_measured_mm,
  };
}

/** The board an atlas frame is defined by: "board:rig_board_a" is rig_board_a; null for any other frame. */
export function frameBoard(frame: string): string | null {
  return /^board:(.+)$/.exec(frame)?.[1] ?? null;
}

/** What the plan of an atlas draws: its points, and the outline of the board its build named. */
export function planInput(detail: AtlasDetail, boards: readonly Board[]): PlanInput {
  const { atlas, report } = detail;
  const boardId = report?.request.board ?? frameBoard(atlas.frame);
  const { id, position_mm, sigma_mm, extent_mm } = atlas.target;
  return {
    landmarks: atlas.landmarks.map((landmark) => ({
      id: landmark.id,
      position_mm: landmark.position_mm,
      sigma_mm: landmark.sigma_mm,
    })),
    target: { id, position_mm, sigma_mm, extent_mm },
    board: planBoard(boards.find((board) => board.id === boardId)),
  };
}

/** The largest 1, 2 or 5 times a power of ten that is at most `limit`. */
export function niceLength(limit: number): number {
  const power = 10 ** Math.floor(Math.log10(limit));
  return [5, 2, 1].map((step) => step * power).find((length) => length <= limit) ?? power;
}

interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

function grow(bounds: Bounds, x: number, y: number, halfX = 0, halfY = halfX) {
  bounds.minX = Math.min(bounds.minX, x - halfX);
  bounds.maxX = Math.max(bounds.maxX, x + halfX);
  bounds.minY = Math.min(bounds.minY, y - halfY);
  bounds.maxY = Math.max(bounds.maxY, y + halfY);
}

function overlaps(a: Box, b: Box): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

function inside(box: Box, area: Box): boolean {
  return (
    box.x >= area.x &&
    box.y >= area.y &&
    box.x + box.width <= area.x + area.width &&
    box.y + box.height <= area.y + area.height
  );
}

/** The box a label covers, by the estimated width of its text. */
export function labelBox(label: Label): Box {
  const width = label.text.length * CHAR;
  const x = label.anchor === "start" ? label.x : label.anchor === "end" ? label.x - width : label.x - width / 2;
  // The baseline sits about a third of the font size below the middle of the line.
  return { x, y: label.y - FONT * 0.35 - LINE / 2, width, height: LINE };
}

/** Where a label can go around a dot at (x, y): right, left, below, above. */
function spots(x: number, y: number, text: string): Label[] {
  const off = DOT + GAP;
  return [
    { x: x + off, y: y + FONT * 0.35, anchor: "start", text },
    { x: x - off, y: y + FONT * 0.35, anchor: "end", text },
    { x, y: y + off + LINE / 2 + FONT * 0.35, anchor: "middle", text },
    { x, y: y - off - LINE / 2 + FONT * 0.35, anchor: "middle", text },
  ];
}

/**
 * Labels for the points in order, each at the first spot that stays in `area`
 * and clear of the dots and of the labels placed before it; null where none
 * is clear. The points table carries every id, so a crowded label gives way.
 */
export function placeLabels(
  points: readonly { x: number; y: number; text: string }[],
  area: Box,
  taken: readonly Box[] = [],
): (Label | null)[] {
  const dots = points.map(({ x, y }) => ({ x: x - DOT - 1, y: y - DOT - 1, width: 2 * DOT + 2, height: 2 * DOT + 2 }));
  const placed: Box[] = [...taken];
  return points.map(({ x, y, text }) => {
    const spot = spots(x, y, text)
      .map((label) => ({ label, box: labelBox(label) }))
      .find(
        ({ box }) =>
          inside(box, area) && !dots.some((dot) => overlaps(box, dot)) && !placed.some((other) => overlaps(box, other)),
      );
    if (!spot) return null;
    placed.push(spot.box);
    return spot.label;
  });
}

/**
 * The plan of an atlas drawn `width` pixels wide and at most `maxHeight`
 * high: the board, every landmark with its sigma circle, the target's extent
 * box and sigma circle, and the frame's axes, all at one scale, centred
 * across the width, with a scale bar under its left edge.
 */
export function layoutPlan(input: PlanInput, width: number, maxHeight = 560): Plan {
  const { landmarks, target, board } = input;
  // The origin is always in view: the axes start there.
  const bounds: Bounds = { minX: 0, maxX: 0, minY: 0, maxY: 0 };
  if (board) grow(bounds, board.squares_x * board.square_mm, board.squares_y * board.square_mm);
  for (const { position_mm: [x, y], sigma_mm } of landmarks) grow(bounds, x, y, sigma_mm);
  const [tx, ty] = target.position_mm;
  grow(bounds, tx, ty, Math.max(target.extent_mm[0] / 2, target.sigma_mm), Math.max(target.extent_mm[1] / 2, target.sigma_mm));

  const innerWidth = Math.max(width - 2 * PAD, 1);
  const innerHeight = Math.max(maxHeight - 2 * PAD - BAND, 1);
  const fit = () =>
    Math.min(innerWidth / Math.max(bounds.maxX - bounds.minX, 1), innerHeight / Math.max(bounds.maxY - bounds.minY, 1));
  // The axes are drawn in pixels: make room for their arrows at the scale they will have.
  grow(bounds, AXIS / fit(), AXIS / fit(), 0);
  const scale = fit();

  const spanX = Math.max(bounds.maxX - bounds.minX, 1);
  const spanY = Math.max(bounds.maxY - bounds.minY, 1);
  const height = Math.round(spanY * scale + 2 * PAD + BAND);
  const left = (width - spanX * scale) / 2;
  const px = (x: number) => left + (x - bounds.minX) * scale;
  const py = (y: number) => PAD + (y - bounds.minY) * scale;

  const origin = { x: px(0), y: py(0) };
  // The arrows run along the board's top and left edges; their names sit outside it.
  const axisLabels: [Label, Label] = [
    { x: origin.x + AXIS, y: origin.y - 6, anchor: "middle", text: "x" },
    { x: origin.x - 6, y: origin.y + AXIS + FONT * 0.35, anchor: "end", text: "y" },
  ];

  let outline: Plan["board"] = null;
  if (board) {
    const grid: Segment[] = [];
    const right = board.squares_x * board.square_mm;
    const bottom = board.squares_y * board.square_mm;
    for (let column = 1; column < board.squares_x; column++) {
      const x = px(column * board.square_mm);
      grid.push({ x1: x, y1: py(0), x2: x, y2: py(bottom) });
    }
    for (let row = 1; row < board.squares_y; row++) {
      const y = py(row * board.square_mm);
      grid.push({ x1: px(0), y1: y, x2: px(right), y2: y });
    }
    outline = { x: px(0), y: py(0), width: right * scale, height: bottom * scale, grid };
  }

  const points = [
    { id: target.id, position_mm: target.position_mm, sigma_mm: target.sigma_mm },
    ...landmarks,
  ].map(({ id, position_mm: [x, y], sigma_mm }) => ({ id, x: px(x), y: py(y), r: sigma_mm * scale, text: id }));
  const area = { x: 0, y: 0, width, height: height - BAND };
  const labels = placeLabels(points, area, axisLabels.map(labelBox));
  const placed = points.map(({ id, x, y, r }, index) => ({ id, x, y, r, label: labels[index] }));

  const barMm = niceLength(Math.max(spanX * scale * BAR_SHARE, BAR_MIN) / scale);
  const barX = Math.max(PAD, left);
  const barY = height - BAND / 2;
  const barEnd = barX + barMm * scale;

  return {
    width,
    height,
    scale,
    origin,
    axes: {
      x: { x1: origin.x, y1: origin.y, x2: origin.x + AXIS, y2: origin.y, label: axisLabels[0] },
      y: { x1: origin.x, y1: origin.y, x2: origin.x, y2: origin.y + AXIS, label: axisLabels[1] },
    },
    board: outline,
    target: {
      ...placed[0],
      box: {
        x: px(tx - target.extent_mm[0] / 2),
        y: py(ty - target.extent_mm[1] / 2),
        width: target.extent_mm[0] * scale,
        height: target.extent_mm[1] * scale,
      },
    },
    landmarks: placed.slice(1),
    scaleBar: {
      x1: barX,
      y1: barY,
      x2: barEnd,
      y2: barY,
      mm: barMm,
      label: { x: barEnd + 6, y: barY + FONT * 0.35, anchor: "start", text: `${barMm} mm` },
    },
  };
}
