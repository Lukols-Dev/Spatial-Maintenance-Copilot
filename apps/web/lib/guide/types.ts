import type { Decision, Localisation, Observation, Vec2 } from "@/lib/locate/types";

// The frames of a camera or a video as the perception service answers them:
// smc_perception.models.FrameAnswer and InspectAnswer, field for field. Each
// type matches its example in lib/api-examples/ one to one.

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
  sighting: TargetSighting | null;
  /** The frame's blur, measured on its markers. */
  frame_quality: FrameQuality;
  elapsed_ms: number;
}

/** How wide the markers' edges are: a still camera draws them about three pixels wide, a moving one smears them. */
export interface FrameQuality {
  /** Markers of the rig found and measured. */
  markers: number;
  /** Median over the markers; null without a marker. */
  edge_width_px: number | null;
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
