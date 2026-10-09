import { count, megabytes } from "./format";

// The Import views dialog: what the chosen files are in the service's terms,
// before anything is sent. The service decides; this spares an upload of a
// long video it would refuse anyway.

const VIDEO = [".mov", ".mp4", ".m4v", ".avi", ".mkv"];
const IMAGES = [".png", ".jpg", ".jpeg"];

/** For the file input: what POST /view-sets reads. */
export const ACCEPT = [...VIDEO, ...IMAGES].join(",");
/** POST /view-sets keeps the sharpest frame of every this many of a video. */
export const DEFAULT_WINDOW = 15;

export interface Selection {
  kind: "none" | "video" | "images" | "refused";
  /** What was chosen: "IMG_0412.MOV · 245.3 MB", "12 images · 30.1 MB". */
  summary: string;
  /** Why the service would refuse it; null when it would not. */
  problem: string | null;
}

interface Picked {
  name: string;
  size: number;
}

function suffix(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
}

/** One video, or images: what the service accepts, and how much is to be sent. */
export function describeFiles(files: readonly Picked[]): Selection {
  if (files.length === 0) return { kind: "none", summary: "No file chosen", problem: null };
  const bytes = megabytes(files.reduce((total, file) => total + file.size, 0));
  const unsupported = files.filter((file) => ![...VIDEO, ...IMAGES].includes(suffix(file.name)));
  const videos = files.filter((file) => VIDEO.includes(suffix(file.name)));
  const images = files.length - unsupported.length - videos.length;
  const what = images === files.length ? "image" : "file";
  const summary = files.length === 1 ? `${files[0].name} · ${bytes}` : `${count(files.length, what)} · ${bytes}`;
  if (unsupported.length > 0) {
    const names = unsupported.map((file) => file.name).join(", ");
    return { kind: "refused", summary, problem: `Not a video or an image: ${names}` };
  }
  if (videos.length > 0 && files.length > 1) return { kind: "refused", summary, problem: "One video, or images without a video" };
  return { kind: videos.length === 1 ? "video" : "images", summary, problem: null };
}

/** Where an upload is: its share sent, then the service's turn to decode what it got. */
export type UploadPhase = { kind: "uploading"; percent: number } | { kind: "processing" };

/**
 * The phase at this uploaded fraction. A percentage rounds down, so 100 %
 * never shows while a byte is still to go: once all is sent it is "Processing".
 */
export function uploadPhase(fraction: number): UploadPhase {
  if (fraction >= 1) return { kind: "processing" };
  return { kind: "uploading", percent: Math.max(0, Math.floor(fraction * 100)) };
}

/** A view set name from a file name: its stem, with what a name cannot hold replaced. "" when nothing is left. */
export function nameFromFile(fileName: string): string {
  const dot = fileName.lastIndexOf(".");
  const stem = dot > 0 ? fileName.slice(0, dot) : fileName;
  return stem
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^[^A-Za-z0-9]+/, "")
    .slice(0, 64)
    .replace(/[-.]+$/, "");
}
