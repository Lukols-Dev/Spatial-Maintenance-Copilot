import type { Decision, Localisation, Observation, Vec2 } from "@/lib/locate/types";

// The frames of a camera or a video as the perception service answers them:
// smc_perception.models.FrameAnswer and InspectAnswer, field for field. Each
// type matches its example in lib/api-examples/ one to one.

/** How far the camera is from the atlas's guide view, and how the asset looks from there. */
export interface Guidance {
  /** The panels as the guide view sees them. */
  outlines_px: Vec2[][];
  /** Mean distance between the asset's points as this pose and the guide view put them; null without a pose. */
  alignment_px: number | null;
  /** 0 far from the guide view, 1 on it; null without a pose. */
  progress: number | null;
}

/** The target's tag in sight: the panel is open, and the prediction is held against it. */
export interface TargetSighting {
  tag_px: Vec2[];
  centre_px: Vec2;
  /** From the projected target point; null without one. */
  error_px: number | null;
  inside_95: boolean | null;
}

/** One frame localised from its printed markers; the service keeps it a while under frame_id. */
export interface FrameAnswer {
  frame_id: string;
  asset_id: string;
  camera_id: string;
  image: { width: number; height: number };
  /** The atlas's landmarks found in the frame. */
  observations: Observation[];
  localisation: Localisation;
  decision: Decision;
  guidance: Guidance | null;
  sighting: TargetSighting | null;
  elapsed_ms: number;
}

/** A vision-language model's look at the target's region of a frame: words, never geometry. */
export interface InspectAnswer {
  frame_id: string;
  /** Left, top, right, bottom. */
  region_px: [number, number, number, number];
  question: string;
  verdict: "yes" | "no" | "unclear";
  answer: string;
  model: string;
}

/** Which atlas the frames are localised against, and which camera took them. */
export interface FrameQuery {
  asset_id: string;
  camera_id: string;
}
