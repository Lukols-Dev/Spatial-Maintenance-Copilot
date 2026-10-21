import { grey, sampleSize } from "@/lib/guide/motion";
import type { FrameSource } from "@/lib/guide/store";

// The frames of the Guide page, from a <video> element: the camera as it
// streams, or a video file stepped through. A frame is the video's own pixels,
// drawn at its size into a canvas and encoded as JPEG: the size the camera was
// calibrated at, or the service refuses it.

/** How far a video file is stepped between frames, in seconds. */
export const FILE_STEP_S = 0.2;
const JPEG_QUALITY = 0.92;

function capture(video: HTMLVideoElement, canvas: HTMLCanvasElement): Promise<Blob | null> {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (width === 0 || height === 0) return Promise.resolve(null);
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return Promise.resolve(null);
  context.drawImage(video, 0, 0, width, height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
}

function aborted(signal: AbortSignal): Promise<never> {
  return new Promise((_, reject) => {
    if (signal.aborted) reject(signal.reason);
    signal.addEventListener("abort", () => reject(signal.reason), { once: true });
  });
}

/** The next frame the video shows: requestVideoFrameCallback where there is one, else the next paint. */
function nextVideoFrame(video: HTMLVideoElement): Promise<void> {
  return new Promise((resolve) => {
    if ("requestVideoFrameCallback" in video) video.requestVideoFrameCallback(() => resolve());
    else requestAnimationFrame(() => resolve());
  });
}

/** Draws a video's current picture small and grey, as lib/guide/motion measures motion on. */
function sampler(): (video: HTMLVideoElement) => Uint8ClampedArray | null {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { willReadFrequently: true });
  return (video) => {
    if (!context || video.videoWidth === 0 || video.videoHeight === 0) return null;
    const size = sampleSize(video.videoWidth, video.videoHeight);
    if (canvas.width !== size.width) canvas.width = size.width;
    if (canvas.height !== size.height) canvas.height = size.height;
    // Averaged down rather than picked, as the thresholds were measured.
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    context.drawImage(video, 0, 0, size.width, size.height);
    return grey(context.getImageData(0, 0, size.width, size.height).data);
  };
}

/**
 * A camera's width and height as getUserMedia takes them: the longer side as the width. Browsers apply
 * the two in landscape and turn the frames of a phone held upright, so a phone asked for 1920 × 1080 gives
 * 1080 × 1920 upright; asked for 1080 × 1920 it gives the frames of the other orientation.
 */
export function landscape(size: { width: number; height: number }): { width: number; height: number } {
  return { width: Math.max(size.width, size.height), height: Math.min(size.width, size.height) };
}

/** The camera facing away from the operator, asked for at the size its calibration has. */
export async function cameraSource(
  video: HTMLVideoElement,
  want: { width: number; height: number },
): Promise<FrameSource> {
  const asked = landscape(want);
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: { ideal: "environment" }, width: { ideal: asked.width }, height: { ideal: asked.height } },
  });
  video.srcObject = stream;
  video.muted = true;
  await video.play();
  const canvas = document.createElement("canvas");
  const sample = sampler();
  return {
    live: true,
    size: () => (video.videoWidth > 0 ? { width: video.videoWidth, height: video.videoHeight } : null),
    async look(signal) {
      for (;;) {
        await Promise.race([nextVideoFrame(video), aborted(signal)]);
        const pixels = sample(video);
        if (pixels) return { pixels, at: performance.now() };
      }
    },
    async next(signal) {
      // Until the stream has a frame to draw, wait for the next one.
      for (;;) {
        await Promise.race([nextVideoFrame(video), aborted(signal)]);
        const blob = await capture(video, canvas);
        if (blob) return blob;
      }
    },
    stop() {
      stream.getTracks().forEach((track) => track.stop());
      video.srcObject = null;
    },
  };
}

/** A video file, stepped through FILE_STEP_S at a time, each step shown while it is localised. */
export async function fileSource(video: HTMLVideoElement, file: File): Promise<FrameSource> {
  const url = URL.createObjectURL(file);
  video.srcObject = null;
  video.src = url;
  video.muted = true;
  video.pause();
  await new Promise<void>((resolve, reject) => {
    video.onloadedmetadata = () => resolve();
    video.onerror = () => reject(new Error(`${file.name} cannot be played here`));
  });
  const canvas = document.createElement("canvas");
  let time = 0;
  return {
    live: false,
    size: () => (video.videoWidth > 0 ? { width: video.videoWidth, height: video.videoHeight } : null),
    async next(signal) {
      if (time > video.duration) return null;
      const seeked = new Promise<void>((resolve) => {
        video.onseeked = () => resolve();
      });
      video.currentTime = time;
      await Promise.race([seeked, aborted(signal)]);
      time += FILE_STEP_S;
      return capture(video, canvas);
    },
    stop() {
      video.removeAttribute("src");
      video.load();
      URL.revokeObjectURL(url);
    },
  };
}
