import { boxEdgesPath, ellipseShape, outlinePath, toSvg, type EllipseShape } from "@/lib/locate/geometry";
import type { RegionStyle } from "@/lib/locate/overlay";
import { verdictOf } from "@/lib/guide/moves";
import type { FrameAnswer } from "@/lib/guide/types";
import type { Vec2 } from "@/lib/locate/types";

// What the Guide page draws over a frame, in the user units of the frame's
// viewBox (OpenCV pixels moved by half a pixel), as lib/locate/overlay does
// for a clicked view. Every position comes from the service's answer.

export interface GuideOverlay {
  width: number;
  height: number;
  /** Reliable when the policy accepts the frame or, with the target's tag in sight, when the tag confirms the prediction. */
  style: RegionStyle;
  /** The panel the target is behind, and where its name goes. */
  occluder: { id: string; outline: string; label: Vec2 } | null;
  /** The target's box: its 12 edges, dashed while hidden, and its point. */
  target: { edges: string; centre: Vec2; hidden: boolean } | null;
  region: EllipseShape | null;
  /** The landmarks found, inliers and the rest. */
  marks: { at: Vec2; inlier: boolean }[];
  /** The target's tag, when the panel is open. */
  tag: { outline: string; centre: Vec2; inside: boolean | null } | null;
}

export function guideOverlayOf(answer: FrameAnswer): GuideOverlay {
  const { target, uncertainty, occluder } = answer.localisation;
  const top = occluder ? Math.min(...occluder.outline_px.map(([, y]) => y)) : 0;
  const xs = occluder ? occluder.outline_px.map(([x]) => x) : [0];
  // The tag in the frame is the target itself: where it falls says more than the policy's checks.
  const verdict = verdictOf(answer);
  const reliable = verdict === null ? answer.decision.reliable : verdict === "confirmed";
  return {
    width: answer.image.width,
    height: answer.image.height,
    style: reliable ? "reliable" : "unreliable",
    occluder: occluder && {
      id: occluder.panel_id,
      outline: outlinePath(occluder.outline_px),
      label: toSvg([(Math.min(...xs) + Math.max(...xs)) / 2, top]),
    },
    target: target && {
      edges: boxEdgesPath(target.corners_px),
      centre: toSvg(target.centre_px),
      hidden: occluder !== null && answer.sighting === null,
    },
    region: target && uncertainty ? ellipseShape(target.centre_px, uncertainty.ellipse) : null,
    marks: answer.observations.map((observation) => ({
      at: toSvg(observation.pixel),
      inlier: observation.inlier === true,
    })),
    tag: answer.sighting && {
      outline: outlinePath(answer.sighting.tag_px),
      centre: toSvg(answer.sighting.centre_px),
      inside: answer.sighting.inside_95,
    },
  };
}
