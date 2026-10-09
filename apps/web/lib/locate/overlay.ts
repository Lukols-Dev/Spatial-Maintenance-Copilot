import { edgeMarker, ellipseShape, outlinePath, toSvg, type EllipseShape } from "@/lib/locate/geometry";
import type { LocaliseResult, Truth, Vec2 } from "@/lib/locate/types";

// What the overlay draws for one answer of POST /localise, in the user units
// of the image's viewBox (OpenCV pixels moved by half a pixel). The page only
// sizes and colours it; every position comes from here.

/**
 * How the target region is drawn. Anything the decision does not accept is
 * drawn in the warning style: a plausible-looking region in the wrong place
 * is a failure, so it must never look like a reliable one.
 */
export type RegionStyle = "reliable" | "unreliable";

/** A landmark clicked in the view. */
export interface ObservedMark {
  id: string;
  at: Vec2;
  /** Whether the pose explains it; "unposed" when there is no pose to ask. */
  kind: "inlier" | "outlier" | "unposed";
  /** Where the pose puts the landmark; null without a pose, or behind the camera. */
  reprojection: Vec2 | null;
  /** Distance between the click and its reprojection, px; null without a pose. */
  errorPx: number | null;
}

/** An atlas landmark not clicked in the view, through the pose. */
export interface ProjectedMark {
  id: string;
  /** Inside the frame: where it lands. Outside: null, and `edge` points at it. */
  at: Vec2 | null;
  /** Outside the frame: a point `inset` inside the border towards it, and the direction (degrees from x towards y). */
  edge: { at: Vec2; angle: number } | null;
}

export interface Overlay {
  width: number;
  height: number;
  style: RegionStyle;
  observed: ObservedMark[];
  unobserved: ProjectedMark[];
  /** The projected extent box of the target and its centre; null after a failure. */
  target: { outline: string; centre: Vec2 } | null;
  /** The 95 % region of the target centre. */
  region: EllipseShape | null;
  /** The same with the target held at its atlas position: the part another viewpoint can shrink. */
  poseOnly: EllipseShape | null;
  /** The target clicked by hand. */
  truth: Vec2 | null;
}

/** A label of the overlay, placed: (x, y) is where its text starts, ends or is centred, at its middle height. */
export interface PlacedLabel {
  id: string;
  text: string;
  x: number;
  y: number;
  anchor: "start" | "middle" | "end";
  /** The label of a projection: a prediction, drawn fainter. */
  faint: boolean;
}

/** Roughly how wide a character of the overlay's sans font is, in font sizes: enough to keep labels apart. */
const CHAR_WIDTH = 0.58;

export interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** The box a label covers, about: its text is set at `fontSize` in the overlay's sans font. */
export function labelBox(label: Pick<PlacedLabel, "text" | "x" | "y" | "anchor">, fontSize: number): Box {
  const width = label.text.length * CHAR_WIDTH * fontSize;
  const left = label.anchor === "start" ? label.x : label.anchor === "end" ? label.x - width : label.x - width / 2;
  return { left, top: label.y - fontSize / 2, right: left + width, bottom: label.y + fontSize / 2 };
}

function overlap(a: Box, b: Box): number {
  const width = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const height = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return width > 0 && height > 0 ? width * height : 0;
}

/**
 * Every landmark's label beside its mark, all in user units: on the first side
 * where it stays inside the image and clear of the marks and of the labels
 * placed before it; failing that, where it covers the least. A landmark
 * outside the frame is labelled beside its arrow at the border.
 */
export function placeLabels(overlay: Overlay, fontSize: number, gap: number, markRadius: number): PlacedLabel[] {
  const marks: { id: string; at: Vec2; faint: boolean }[] = [
    ...overlay.observed.map((mark) => ({ id: mark.id, at: mark.at, faint: false })),
    ...overlay.unobserved.flatMap((mark) => {
      const at = mark.at ?? mark.edge?.at;
      return at ? [{ id: mark.id, at, faint: true }] : [];
    }),
  ];
  const image: Box = { left: 0, top: 0, right: overlay.width, bottom: overlay.height };
  const taken: Box[] = marks.map(({ at: [x, y] }) => ({
    left: x - markRadius,
    top: y - markRadius,
    right: x + markRadius,
    bottom: y + markRadius,
  }));

  return marks.map(({ id, at: [x, y], faint }) => {
    // Right of the mark, then left, above or below it; the first that fits wins.
    const sides: Pick<PlacedLabel, "x" | "y" | "anchor">[] = [
      { x: x + gap, y: y - gap, anchor: "start" },
      { x: x + gap, y: y + gap, anchor: "start" },
      { x: x - gap, y: y - gap, anchor: "end" },
      { x: x - gap, y: y + gap, anchor: "end" },
      { x, y: y - gap - fontSize, anchor: "middle" },
      { x, y: y + gap + fontSize, anchor: "middle" },
    ];
    const cost = (side: Pick<PlacedLabel, "x" | "y" | "anchor">) => {
      const box = labelBox({ text: id, ...side }, fontSize);
      const outside = (box.right - box.left) * (box.bottom - box.top) - overlap(box, image);
      return outside * 4 + taken.reduce((sum, other) => sum + overlap(box, other), 0);
    };
    const best = sides.reduce((chosen, side) => (cost(side) < cost(chosen) ? side : chosen));
    taken.push(labelBox({ text: id, ...best }, fontSize));
    return { id, text: id, ...best, faint };
  });
}

/**
 * The overlay of a result. `truth` is the truth the page shows, which can be
 * none although the service gave one (see shownTruth); `inset` is how far
 * inside the border a marker for a landmark outside the frame goes, in user units.
 */
export function overlayOf(result: LocaliseResult, truth: Truth | null, inset: number): Overlay {
  const { width, height } = result.image;
  const { quality, target, uncertainty } = result.localisation;
  const projected = new Map(result.projections.map((projection) => [projection.landmark_id, projection]));

  const observed = result.observations.map((observation): ObservedMark => {
    const pixel = projected.get(observation.landmark_id)?.pixel ?? null;
    const kind = observation.inlier === null ? "unposed" : observation.inlier ? "inlier" : "outlier";
    const error = quality && Object.hasOwn(quality.reprojection_px, observation.landmark_id)
      ? quality.reprojection_px[observation.landmark_id]
      : null;
    return {
      id: observation.landmark_id,
      at: toSvg(observation.pixel),
      kind,
      reprojection: kind === "unposed" || pixel === null ? null : toSvg(pixel),
      errorPx: kind === "unposed" ? null : error,
    };
  });

  const clicked = new Set(result.observations.map((observation) => observation.landmark_id));
  const unobserved = result.projections.flatMap((projection): ProjectedMark[] => {
    // Behind the camera a landmark lands nowhere in the image.
    if (projection.pixel === null || projection.observed || clicked.has(projection.landmark_id)) return [];
    return [
      projection.in_frame
        ? { id: projection.landmark_id, at: toSvg(projection.pixel), edge: null }
        : { id: projection.landmark_id, at: null, edge: edgeMarker(projection.pixel, width, height, inset) },
    ];
  });

  return {
    width,
    height,
    style: result.decision.reliable ? "reliable" : "unreliable",
    observed,
    unobserved,
    target: target && { outline: outlinePath(target.outline_px), centre: toSvg(target.centre_px) },
    region: target && uncertainty ? ellipseShape(target.centre_px, uncertainty.ellipse) : null,
    poseOnly: target && uncertainty ? ellipseShape(target.centre_px, uncertainty.pose_only) : null,
    truth: truth && toSvg(truth.target_px),
  };
}
