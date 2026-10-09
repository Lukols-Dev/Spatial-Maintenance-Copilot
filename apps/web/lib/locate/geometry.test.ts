import { describe, expect, it } from "vitest";

import reliableExample from "../api-examples/localise-result-reliable.json";
import moveExample from "../api-examples/localise-result.json";
import {
  edgeMarker,
  ellipsePoint,
  ellipseShape,
  ellipseTransform,
  imagePixelsPerScreenPixel,
  outlinePath,
  svgNumber,
  toSvg,
} from "./geometry";
import type { LocaliseResult, Vec2 } from "./types";

const RELIABLE = reliableExample as unknown as LocaliseResult;
const MOVE = moveExample as unknown as LocaliseResult;

/** The squared Mahalanobis radius holding 95 % of a 2D Gaussian (smc_core.uncertainty.CHI2_95_2DOF). */
const CHI2_95_2DOF = 5.991464547107979;

describe("OpenCV pixels on the image's viewBox", () => {
  it("moves a position by half a pixel: OpenCV's (0, 0) is the centre of the first pixel", () => {
    expect(toSvg([0, 0])).toEqual([0.5, 0.5]);
    expect(toSvg([1079, 1919])).toEqual([1079.5, 1919.5]);
    expect(toSvg([-92.98, 390.61])).toEqual([-92.48, 391.11]);
  });

  it("writes attributes to a thousandth of a pixel, without -0", () => {
    expect(svgNumber(532.8206781773437)).toBe("532.821");
    expect(svgNumber(13.9632604)).toBe("13.963");
    expect(svgNumber(-0.0001)).toBe("0");
    expect(svgNumber(1084)).toBe("1084");
  });

  it("draws the target outline through the example's pixels, half a pixel on", () => {
    const outline = RELIABLE.localisation.target?.outline_px ?? [];
    expect(outlinePath(outline)).toBe("M688.234 1241.302 L377.288 1241.428 L380.194 931.235 L685.789 931.136 Z");
    expect(outlinePath([])).toBe("");
  });
});

describe("the region ellipse", () => {
  it("is centred on the target, half a pixel on, with the semi-axes as radii", () => {
    const { target, uncertainty } = RELIABLE.localisation;
    if (!target || !uncertainty) throw new Error("the example has a region");
    const shape = ellipseShape(target.centre_px, uncertainty.ellipse);
    expect(shape.cx).toBeCloseTo(533.3206781773437, 9);
    expect(shape.cy).toBeCloseTo(1084.5045963785394, 9);
    expect(shape.rx).toBe(uncertainty.ellipse.semi_major_px);
    expect(shape.ry).toBe(uncertainty.ellipse.semi_minor_px);
    expect(ellipseTransform(shape)).toBe("rotate(146.616 533.321 1084.505)");
  });

  it("turns the major axis onto the covariance's principal direction, and the axes are its 95 % radii", () => {
    for (const result of [RELIABLE, MOVE]) {
      const { target, uncertainty } = result.localisation;
      if (!target || !uncertainty) throw new Error("the example has a region");
      const [[a, b], [, d]] = uncertainty.covariance_px;
      // Eigenvalues of the symmetric 2 × 2 covariance.
      const mean = (a + d) / 2;
      const spread = Math.hypot((a - d) / 2, b);
      const [large, small] = [mean + spread, mean - spread];
      const shape = ellipseShape(target.centre_px, uncertainty.ellipse);
      expect(shape.rx).toBeCloseTo(Math.sqrt(CHI2_95_2DOF * large), 3);
      expect(shape.ry).toBeCloseTo(Math.sqrt(CHI2_95_2DOF * small), 3);

      // The end of the drawn major axis, as a direction: C v = λ v for the larger eigenvalue.
      const [x, y] = ellipsePoint(shape, 0);
      const v: Vec2 = [(x - shape.cx) / shape.rx, (y - shape.cy) / shape.rx];
      expect(a * v[0] + b * v[1]).toBeCloseTo(large * v[0], 6);
      expect(b * v[0] + d * v[1]).toBeCloseTo(large * v[1], 6);
    }
  });

  it("rotates from the image x axis towards y, as y grows down the image", () => {
    const shape = ellipseShape([99.5, 199.5], { semi_major_px: 10, semi_minor_px: 4, angle_deg: 90 });
    const [x0, y0] = ellipsePoint(shape, 0);
    expect(x0).toBeCloseTo(100, 9);
    expect(y0).toBeCloseTo(210, 9);
    const [x1, y1] = ellipsePoint(shape, Math.PI / 2);
    expect(x1).toBeCloseTo(96, 9);
    expect(y1).toBeCloseTo(200, 9);
  });
});

describe("imagePixelsPerScreenPixel", () => {
  it("follows the side that limits a contained image", () => {
    // A portrait image in a wide box is as tall as the box.
    expect(imagePixelsPerScreenPixel(1080, 1920, 900, 480)).toBe(4);
    // In a narrow box it is as wide as the box.
    expect(imagePixelsPerScreenPixel(1080, 1920, 270, 1000)).toBe(4);
    expect(imagePixelsPerScreenPixel(1080, 1920, 0, 0)).toBe(1);
  });
});

describe("edgeMarker", () => {
  it("puts a projection beyond the left edge on the left border, pointing left", () => {
    const marker = edgeMarker([-92.98, 959.5], 1080, 1920, 20);
    expect(marker.at[0]).toBeCloseTo(20, 9);
    expect(marker.at[1]).toBeCloseTo(960, 9);
    expect(marker.angle).toBeCloseTo(180, 9);
  });

  it("follows the line from the frame centre and stays inside the border", () => {
    const marker = edgeMarker([1539.5, 2879.5], 1080, 1920, 0);
    // From (540, 960) towards (1540, 2880): the bottom border comes first.
    expect(marker.at[1]).toBeCloseTo(1920, 9);
    expect(marker.at[0]).toBeCloseTo(540 + (1000 * 960) / 1920, 9);
    expect(marker.angle).toBeGreaterThan(0);
    expect(marker.angle).toBeLessThan(90);
  });

  it("leaves a position inside the border where it is", () => {
    expect(edgeMarker([99.5, 499.5], 1080, 1920, 20).at).toEqual([100, 500]);
  });
});
