"use client";

import { useMemo } from "react";

import { useElementSize } from "@/components/locate/hooks";
import { ellipseTransform, imagePixelsPerScreenPixel, svgNumber } from "@/lib/locate/geometry";
import { guideOverlayOf } from "@/lib/guide/overlay";
import type { FrameAnswer } from "@/lib/guide/types";
import { cn } from "@/lib/utils";

// The answer for a frame drawn over the video: the guide view's outline to
// line the asset up with, the panel the target is behind, the target's box
// through it, its 95 % region, the landmarks found, and the target's tag once
// the panel is open. The <svg> has the frame as its viewBox and sits on the
// <video> with the same fit, so every position is a frame pixel.

const REGION_STROKE = { reliable: "stroke-emerald-400", unreliable: "stroke-amber-400" } as const;

export function GuideOverlay({ answer, width, height }: { answer: FrameAnswer | null; width: number; height: number }) {
  const [boxRef, box] = useElementSize<SVGSVGElement>();
  const k = box ? imagePixelsPerScreenPixel(width, height, box.width, box.height) : 2;
  const overlay = useMemo(() => (answer ? guideOverlayOf(answer) : null), [answer]);
  const dash = `${svgNumber(8 * k)} ${svgNumber(6 * k)}`;

  return (
    <svg
      ref={boxRef}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className="pointer-events-none absolute inset-0 size-full"
      aria-hidden
      data-frame={answer?.frame_id ?? ""}
    >
      {overlay && (
        <>
          {overlay.guide.map((outline, index) => (
            <path
              key={index}
              data-part="guide-outline"
              d={outline}
              className="fill-none stroke-white/80"
              strokeWidth={2 * k}
              strokeDasharray={`${svgNumber(3 * k)} ${svgNumber(5 * k)}`}
              strokeLinejoin="round"
            />
          ))}
          {overlay.occluder && (
            <g data-layer="occluder">
              <path
                data-part="occluder"
                data-panel={overlay.occluder.id}
                d={overlay.occluder.outline}
                className="fill-sky-400/25 stroke-sky-300"
                strokeWidth={2.5 * k}
                strokeLinejoin="round"
              />
              <text
                data-part="occluder-label"
                x={svgNumber(overlay.occluder.label[0])}
                y={svgNumber(Math.max(overlay.occluder.label[1], 0) + 17 * k)}
                fontSize={svgNumber(13 * k)}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-white stroke-black font-sans font-semibold"
                strokeOpacity={0.6}
                strokeWidth={3 * k}
                paintOrder="stroke"
              >
                {`Target behind: ${overlay.occluder.id}`}
              </text>
            </g>
          )}
          {overlay.region && (
            <ellipse
              data-part="region"
              data-style={overlay.style}
              cx={svgNumber(overlay.region.cx)}
              cy={svgNumber(overlay.region.cy)}
              rx={svgNumber(overlay.region.rx)}
              ry={svgNumber(overlay.region.ry)}
              transform={ellipseTransform(overlay.region)}
              className={cn(REGION_STROKE[overlay.style], overlay.style === "reliable" ? "fill-emerald-400/20" : "fill-amber-400/15")}
              strokeWidth={2.5 * k}
              strokeDasharray={overlay.style === "unreliable" ? dash : undefined}
            />
          )}
          {overlay.target && (
            <path
              data-part="target-box"
              data-hidden={overlay.target.hidden ? "true" : "false"}
              d={overlay.target.edges}
              className={cn("fill-none", REGION_STROKE[overlay.style])}
              strokeWidth={2 * k}
              strokeDasharray={overlay.target.hidden ? `${svgNumber(5 * k)} ${svgNumber(4 * k)}` : undefined}
              strokeLinecap="round"
            />
          )}
          {overlay.marks.map((mark, index) => (
            <circle
              key={index}
              data-part="landmark"
              data-kind={mark.inlier ? "inlier" : "outlier"}
              cx={svgNumber(mark.at[0])}
              cy={svgNumber(mark.at[1])}
              r={svgNumber(4 * k)}
              className={cn("stroke-black", mark.inlier ? "fill-sky-400" : "fill-rose-400")}
              strokeOpacity={0.8}
              strokeWidth={1.2 * k}
            />
          ))}
          {overlay.tag && (
            <g data-part="tag" data-inside={String(overlay.tag.inside)}>
              <path d={overlay.tag.outline} className="fill-fuchsia-400/20 stroke-fuchsia-400" strokeWidth={2.5 * k} />
              <circle
                cx={svgNumber(overlay.tag.centre[0])}
                cy={svgNumber(overlay.tag.centre[1])}
                r={svgNumber(4 * k)}
                className="fill-fuchsia-400 stroke-black"
                strokeWidth={1.2 * k}
              />
            </g>
          )}
        </>
      )}
    </svg>
  );
}
