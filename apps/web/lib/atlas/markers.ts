import type { AtlasDetail, MarkersAnswer, MarkersRequest, Rig, ViewSetSummary } from "@/lib/workspace";

import { count, size } from "./format";
import { previousBuild } from "./form";

// The automatic way to a set's points: the printed markers of the rig found in
// every image of the set and saved as its clicks, instead of clicking them in
// the annotator. A marker gives its four corners as points m<id>_<corner>, the
// target's tag the target's point and its corners.

/** What the service names the target's point when it is not told: the cabinet's atlases call it that. */
export const DEFAULT_TARGET = "target";

export interface MarkersForm {
  camera_id: string;
  target_id: string;
  /** Landmark markers on a part that opens. */
  moving: number[];
}

export interface CheckedMarkers {
  /** Null while anything is missing. */
  request: MarkersRequest | null;
  problems: string[];
}

/** The landmark marker ids of the rig, in order; none without printed markers. */
export function landmarkMarkers(rig: Rig): number[] {
  if (!rig.markers) return [];
  const [first, last] = rig.markers.landmark_ids;
  return Array.from({ length: Math.max(0, last - first + 1) }, (_, index) => first + index);
}

/** The markers whose corners move with a panel in this atlas: m50_0 is a corner of marker 50. */
export function movingMarkers(detail: AtlasDetail): number[] {
  const ids = new Set<number>();
  for (const landmark of detail.atlas.landmarks) {
    const marker = /^m(\d+)_[0-3]$/.exec(landmark.id);
    if (marker && landmark.moves_with) ids.add(Number(marker[1]));
  }
  return [...ids].sort((a, b) => a - b);
}

/**
 * The dialog as it opens: the camera of the Build form when it fits the set,
 * else the first that does; the target of the form, else "target"; and as moving
 * markers those of the atlas built from this set before, if any.
 */
export function initialMarkers(
  set: ViewSetSummary,
  details: readonly AtlasDetail[],
  form: { camera_id: string; target_id: string },
): MarkersForm {
  const previous = previousBuild(details, set.name);
  return {
    camera_id: set.camera_ids.includes(form.camera_id) ? form.camera_id : (set.camera_ids[0] ?? ""),
    target_id: form.target_id || previous?.report.request.target_id || DEFAULT_TARGET,
    moving: previous ? movingMarkers(previous) : [],
  };
}

/** The request the dialog makes, or what keeps it from making one. A set with clicks has them replaced. */
export function checkMarkers(form: MarkersForm, set: ViewSetSummary, rig: Rig): CheckedMarkers {
  const problems: string[] = [];
  if (!rig.markers) problems.push(rig.error ?? "calib/rig.yaml names no printed markers");
  if (set.image_count === 0) problems.push("No images in the set");
  else if (set.camera_ids.length === 0) {
    problems.push(set.image_size ? `No camera calibrated at ${size(...set.image_size)}` : "Images of several sizes");
  } else if (!set.camera_ids.includes(form.camera_id)) problems.push("No camera chosen");
  const target_id = form.target_id.trim();
  if (!target_id) problems.push("Target point missing");
  if (problems.length > 0) return { request: null, problems };
  return {
    request: { camera_id: form.camera_id, target_id, moving: [...form.moving], replace: set.clicks !== null },
    problems,
  };
}

/** "Replaces 49 points marked in 287 images", or null when the set has no clicks to lose. */
export function replacedText(set: ViewSetSummary): string | null {
  if (!set.clicks) return null;
  return `Replaces ${count(set.clicks.point_count, "point")} marked in ${count(set.clicks.marked_images, "image")}`;
}

/** "Markers in 287 of 290 images · tag in 149" */
export function answerText(answer: MarkersAnswer): string {
  return `Markers in ${answer.marked_images} of ${count(answer.images, "image")} · tag in ${answer.tag_images}`;
}

/** Each marker with the images it is in; a marker found nowhere is said so, as it gives no landmark. */
export function markerCounts(answer: MarkersAnswer): { marker: number; text: string; missing: boolean }[] {
  return answer.markers.map(({ marker_id, images }) => ({
    marker: marker_id,
    text: images === 0 ? "not found" : count(images, "image"),
    missing: images === 0,
  }));
}
