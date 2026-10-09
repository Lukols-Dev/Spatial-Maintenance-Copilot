import type { Ellipse, Vec2 } from "@/lib/locate/types";

// Geometry of the overlay. It is an <svg> whose viewBox is the image,
// "0 0 W H", so a user unit is an image pixel and (0, 0) is the top-left
// corner of the first pixel. OpenCV puts (0, 0) at the centre of that pixel:
// every position the service gives moves by half a pixel on its way in, while
// lengths (radii, semi-axes) stay as they are.

export const OPENCV_TO_SVG = 0.5;

export function toSvg([x, y]: Vec2): Vec2 {
  return [x + OPENCV_TO_SVG, y + OPENCV_TO_SVG];
}

/** A number for an SVG attribute: a thousandth of a pixel is far below what a screen shows. */
export function svgNumber(value: number): string {
  const rounded = Math.round(value * 1000) / 1000;
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

function svgPoint(point: Vec2): [string, string] {
  const [x, y] = toSvg(point);
  return [svgNumber(x), svgNumber(y)];
}

/** A closed <path d> through OpenCV pixels; empty without points. */
export function outlinePath(points: readonly Vec2[]): string {
  if (points.length === 0) return "";
  const steps = points.map((point, index) => `${index === 0 ? "M" : "L"}${svgPoint(point).join(" ")}`);
  return `${steps.join(" ")} Z`;
}

/** An <ellipse> in user units, with the rotation it is drawn with. */
export interface EllipseShape {
  cx: number;
  cy: number;
  rx: number;
  ry: number;
  /** Degrees, from the x axis towards y. */
  angle: number;
}

/**
 * The region around an OpenCV centre. The service measures the angle of the
 * major axis from the image x axis towards y, which is the direction SVG's
 * rotate() turns in a y-down viewBox, so the angle is used as it is.
 */
export function ellipseShape(centre: Vec2, ellipse: Ellipse): EllipseShape {
  const [cx, cy] = toSvg(centre);
  return { cx, cy, rx: ellipse.semi_major_px, ry: ellipse.semi_minor_px, angle: ellipse.angle_deg };
}

/** The transform attribute that turns an ellipse drawn along x into the region. */
export function ellipseTransform(shape: EllipseShape): string {
  return `rotate(${svgNumber(shape.angle)} ${svgNumber(shape.cx)} ${svgNumber(shape.cy)})`;
}

/** Where the drawn ellipse passes at parameter t: (rx cos t, ry sin t), rotated about its centre. */
export function ellipsePoint(shape: EllipseShape, t: number): Vec2 {
  const angle = (shape.angle * Math.PI) / 180;
  const x = shape.rx * Math.cos(t);
  const y = shape.ry * Math.sin(t);
  return [shape.cx + x * Math.cos(angle) - y * Math.sin(angle), shape.cy + x * Math.sin(angle) + y * Math.cos(angle)];
}

/**
 * Image pixels per screen pixel for an image of width × height drawn into a
 * box of boxWidth × boxHeight with preserveAspectRatio "meet". Markers and
 * labels are sized with it, so they keep their size on screen at any scale.
 */
export function imagePixelsPerScreenPixel(width: number, height: number, boxWidth: number, boxHeight: number): number {
  if (boxWidth <= 0 || boxHeight <= 0) return 1;
  return Math.max(width / boxWidth, height / boxHeight);
}

/**
 * A marker for a projection outside the frame: on the line from the frame's
 * centre to the projection, where it crosses a border `inset` user units inside
 * the frame, turned to point at it (degrees from x towards y).
 */
export function edgeMarker(pixel: Vec2, width: number, height: number, inset: number): { at: Vec2; angle: number } {
  const [x, y] = toSvg(pixel);
  const cx = width / 2;
  const cy = height / 2;
  const dx = x - cx;
  const dy = y - cy;
  const halfWidth = Math.max(width / 2 - inset, Number.EPSILON);
  const halfHeight = Math.max(height / 2 - inset, Number.EPSILON);
  // A projection inside that border stays where it is.
  const scale = Math.max(Math.abs(dx) / halfWidth, Math.abs(dy) / halfHeight, 1);
  return { at: [cx + dx / scale, cy + dy / scale], angle: (Math.atan2(dy, dx) * 180) / Math.PI };
}
