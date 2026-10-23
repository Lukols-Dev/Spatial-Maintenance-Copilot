import { describe, expect, it } from "vitest";

import { parseRecordings, recordingUrl } from "@/lib/guide/recordings";

describe("the recordings' index", () => {
  it("lists the recordings with a file, a title and a length, in its order", () => {
    const index = {
      recordings: [
        { file: "demo_2.mp4", title: "Too close", seconds: 23.7 },
        { file: "demo_1.mp4", title: "From the left side", seconds: 28.3 },
      ],
    };

    expect(parseRecordings(index).map((recording) => recording.file)).toEqual(["demo_2.mp4", "demo_1.mp4"]);
    expect(recordingUrl(parseRecordings(index)[0])).toBe("/recordings/demo_2.mp4");
  });

  it("leaves out what is not a served clip, and reads a missing index as none", () => {
    const index = {
      recordings: [
        { file: "../secret.mp4", title: "Elsewhere", seconds: 1 },
        { file: "demo_3.mov", title: "Not converted", seconds: 1 },
        { file: "demo_4.mp4", title: "", seconds: 1 },
        { file: "demo_5.mp4", title: "No length" },
        { file: "demo_6.mp4", title: "Kept", seconds: 22.1 },
      ],
    };

    expect(parseRecordings(index).map((recording) => recording.file)).toEqual(["demo_6.mp4"]);
    expect(parseRecordings(null)).toEqual([]);
    expect(parseRecordings({ recordings: "none" })).toEqual([]);
  });
});
