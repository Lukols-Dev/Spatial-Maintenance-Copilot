import { describe, expect, it } from "vitest";

import { ACCEPT, DEFAULT_WINDOW, describeFiles, nameFromFile, uploadPhase } from "./upload";

const MB = 1_000_000;

describe("describeFiles", () => {
  it("takes one video, whatever the case of its suffix", () => {
    expect(describeFiles([{ name: "IMG_0412.MOV", size: 245.3 * MB }])).toEqual({
      kind: "video",
      summary: "IMG_0412.MOV · 245.3 MB",
      problem: null,
    });
  });

  it("takes photos", () => {
    const photos = ["a.png", "b.JPG", "c.jpeg"].map((name) => ({ name, size: 2 * MB }));
    expect(describeFiles(photos)).toEqual({ kind: "images", summary: "3 images · 6.0 MB", problem: null });
  });

  it("refuses what the service refuses, before anything is sent", () => {
    const video = { name: "cabinet.mp4", size: 10 * MB };
    const photo = { name: "a.png", size: MB };
    expect(describeFiles([video, photo])).toEqual({
      kind: "refused",
      summary: "2 files · 11.0 MB",
      problem: "One video, or images without a video",
    });
    expect(describeFiles([video, { ...video, name: "other.mov" }]).problem).toBe("One video, or images without a video");
    expect(describeFiles([photo, { name: "notes.txt", size: 10 }])).toMatchObject({
      kind: "refused",
      summary: "2 files · 1.0 MB",
      problem: "Not a video or an image: notes.txt",
    });
    expect(describeFiles([{ name: "README", size: 10 }]).problem).toBe("Not a video or an image: README");
  });

  it("says when nothing is chosen", () => {
    expect(describeFiles([])).toEqual({ kind: "none", summary: "No file chosen", problem: null });
  });

  it("lets the file input offer what the service reads", () => {
    expect(ACCEPT.split(",")).toEqual([".mov", ".mp4", ".m4v", ".avi", ".mkv", ".png", ".jpg", ".jpeg"]);
    expect(DEFAULT_WINDOW).toBe(15);
  });
});

describe("nameFromFile", () => {
  it("makes a set name of a video's stem", () => {
    expect(nameFromFile("IMG_0412.MOV")).toBe("IMG_0412");
    expect(nameFromFile("cabinet 2026-10-09 (1).mp4")).toBe("cabinet-2026-10-09-1");
    expect(nameFromFile(".hidden.mov")).toBe("hidden");
    expect(nameFromFile("...mov")).toBe("");
    expect(nameFromFile(`${"x".repeat(70)}.mov`)).toBe("x".repeat(64));
  });
});

describe("uploadPhase", () => {
  it("counts the share sent, then hands over to the service once all of it is", () => {
    expect([0, 0.425, 0.999].map(uploadPhase)).toEqual([
      { kind: "uploading", percent: 0 },
      { kind: "uploading", percent: 42 },
      { kind: "uploading", percent: 99 },
    ]);
    expect(uploadPhase(1)).toEqual({ kind: "processing" });
  });
});
