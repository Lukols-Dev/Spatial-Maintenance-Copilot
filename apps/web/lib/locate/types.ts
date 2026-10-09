// The models of POST /localise, with the service's JSON field names, so each
// type matches its example in lib/api-examples/ one to one. Pixels are OpenCV
// pixels: (0, 0) is the centre of the first pixel.

import type { Vec3 } from "@/lib/workspace";

export type Vec2 = [number, number];

export interface LocaliseRequest {
  asset_id: string;
  view_set: string;
  /** An image of the set whose clicks are the observations. */
  view: string;
  /**
   * An image of the same set in which the target is clicked: its click is the
   * truth. null: the view's own target click, when it has one.
   */
  truth_view?: string | null;
  /** Monte Carlo samples of the region, 50 to 5000; 500. */
  samples?: number;
  seed?: number;
  /** 1-sigma error of a click; null: the atlas build's, else 2.0. */
  sigma_px?: number | null;
}

/** Why a localisation could not be computed at all; no threshold is involved. */
export type Failure =
  | "too_few_correspondences"
  | "degenerate_geometry"
  | "pnp_failed"
  | "target_behind_camera"
  | "unstable_pose";

/** How well the pose explains the observations. */
export interface Quality {
  /** Landmarks seen that the atlas knows. */
  observed: number;
  inliers: number;
  inlier_ratio: number;
  outlier_ids: string[];
  /** Over the inliers. */
  rms_reprojection_px: number;
  max_reprojection_px: number;
  /** Error of every observed landmark. */
  reprojection_px: Record<string, number>;
  /** Area of the inliers' convex hull / frame area. */
  image_coverage: number;
  /** Smallest / largest spread of the inliers in 3D; 0 when they are coplanar. */
  non_planarity: number;
}

/** Asset frame to camera frame. */
export interface Pose {
  rvec: Vec3;
  tvec_mm: Vec3;
}

export interface ProjectedTarget {
  centre_px: Vec2;
  /** Distance of the centre along the optical axis. */
  depth_mm: number;
  in_frame: boolean;
  /** Convex hull of the projected extent box. */
  outline_px: Vec2[];
  /** Radius of a circle with the outline's area. */
  radius_px: number;
}

export interface Ellipse {
  semi_major_px: number;
  semi_minor_px: number;
  /** Major axis, from the image x axis towards y, 0 to 180. */
  angle_deg: number;
}

/** Where the target centre lands when every input varies within its sigma. */
export interface UncertaintyRegion {
  confidence: number;
  covariance_px: [Vec2, Vec2];
  ellipse: Ellipse;
  /** The target held at its atlas position: the part a new viewpoint can shrink. */
  pose_only: Ellipse;
  samples: number;
  failed_samples: number;
  seed: number;
}

/** Everything the geometry says about one view; after a failure, what could not be computed is null. */
export interface Localisation {
  view_id: string;
  failure: Failure | null;
  quality: Quality | null;
  pose: Pose | null;
  target: ProjectedTarget | null;
  uncertainty: UncertaintyRegion | null;
}

export type Action = "ACCEPT" | "MOVE_LEFT" | "MOVE_RIGHT" | "MOVE_CLOSER" | "MOVE_BACK" | "MOVE_UP" | "MOVE_DOWN";

/** One measurement against its threshold. */
export interface Check {
  name: string;
  /** The measurement; null when it cannot be computed (after a failure). */
  value: number | null;
  limit: number;
  op: ">=" | "<=";
  passed: boolean;
}

/** The calibrated opinions the decision applies. */
export interface Policy {
  min_landmarks: number;
  min_inliers: number;
  min_inlier_ratio: number;
  max_rms_reprojection_px: number;
  min_image_coverage: number;
  max_failed_sample_ratio: number;
  max_region_ratio: number;
}

export interface Decision {
  reliable: boolean;
  action: Action;
  /** One short fact per failed check. */
  reasons: string[];
  /** The fact the move comes from; "" for ACCEPT. */
  move_reason: string;
  checks: Check[];
  policy: Policy;
}

/** A clicked landmark of the view. inlier is null without a pose. */
export interface Observation {
  landmark_id: string;
  pixel: Vec2;
  inlier: boolean | null;
}

/** An atlas landmark through the estimated pose; pixel is null behind the camera. */
export interface Projection {
  landmark_id: string;
  pixel: Vec2 | null;
  in_frame: boolean;
  observed: boolean;
}

/** The target clicked by hand, in this view or in a paired shot from the same position. */
export interface Truth {
  /** The image the click comes from. */
  source_view: string;
  target_px: Vec2;
  /** Distance to the projected target; null without one. */
  error_px: number | null;
  /** Within the 95 % region; null without a region. */
  inside_95: boolean | null;
}

export interface LocaliseResult {
  /** The request as the service ran it: sigma_px resolved. */
  request: Required<LocaliseRequest> & { sigma_px: number };
  camera_id: string;
  image: { width: number; height: number };
  localisation: Localisation;
  observations: Observation[];
  /** Every atlas landmark through the estimated pose; empty without a pose. */
  projections: Projection[];
  /** Clicked in the view but not atlas landmarks (the target excluded). */
  ignored_points: string[];
  truth: Truth | null;
  decision: Decision;
}
