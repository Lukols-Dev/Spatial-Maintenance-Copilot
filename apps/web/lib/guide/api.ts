import { apiJson } from "@/lib/api";
import type { FrameAnswer, FrameQuery, InspectAnswer } from "@/lib/guide/types";

// The calls of the Guide page: a frame localised, and a second look at it.

/** A frame is localised in well under a second; the margin covers a busy machine. */
export const FRAME_TIMEOUT_MS = 20_000;
/** The vision model answers in seconds. */
export const INSPECT_TIMEOUT_MS = 60_000;
/** Monte Carlo samples per frame: enough for the region, quick enough for a camera. */
export const FRAME_SAMPLES = 200;

type Options = { signal?: AbortSignal };

/** One frame, the image itself as the body: localised from its printed markers and kept a while. */
export function postFrame(image: Blob, query: FrameQuery, options: Options = {}): Promise<FrameAnswer> {
  const params = new URLSearchParams({
    asset_id: query.asset_id,
    camera_id: query.camera_id,
    samples: String(FRAME_SAMPLES),
  });
  return apiJson<FrameAnswer>(`/frames?${params}`, {
    method: "POST",
    headers: { "Content-Type": image.type || "image/jpeg" },
    body: image,
    timeoutMs: FRAME_TIMEOUT_MS,
    signal: options.signal,
  });
}

/** The vision model's look at the target's region of a kept frame. */
export function inspectFrame(frameId: string, options: Options = {}): Promise<InspectAnswer> {
  return apiJson<InspectAnswer>(`/frames/${encodeURIComponent(frameId)}/inspect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
    timeoutMs: INSPECT_TIMEOUT_MS,
    signal: options.signal,
  });
}
