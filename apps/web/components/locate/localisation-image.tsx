"use client";

import { ImageOff, LoaderCircle } from "lucide-react";
import { useId, useMemo, useState, type ComponentProps, type ReactNode } from "react";

import { useElementSize } from "@/components/locate/hooks";
import { ellipseTransform, imagePixelsPerScreenPixel, svgNumber, type EllipseShape } from "@/lib/locate/geometry";
import {
  overlayOf,
  placeLabels,
  type ObservedMark,
  type Overlay,
  type ProjectedMark,
  type RegionStyle,
} from "@/lib/locate/overlay";
import type { LocaliseResult, Truth, Vec2 } from "@/lib/locate/types";
import { cn } from "@/lib/utils";

// The camera image with what the localisation says about it, drawn in the
// image's own coordinates: the <svg> has the image as its viewBox, so every
// position is an image pixel, whatever size the image is shown at. Marks and
// lines are sized in screen pixels (times the image pixels per screen pixel),
// so they read the same on a phone and on a large screen.

export const LAYERS = ["landmarks", "residuals", "projections", "labels", "target", "region", "poseOnly", "truth"] as const;
export type Layer = (typeof LAYERS)[number];
export type Layers = Record<Layer, boolean>;

/** How far inside the border a landmark outside the frame is marked, in screen pixels. */
const EDGE_INSET = 14;

function at([x, y]: Vec2): string {
  return `translate(${svgNumber(x)} ${svgNumber(y)})`;
}

/** Strokes are drawn twice: a dark band under the colour keeps them visible on a white door and a dark room alike. */
function Halo({ children, width, k }: { children: ReactNode; width: number; k: number }) {
  return (
    <g className="fill-none stroke-black" strokeOpacity={0.6} strokeWidth={width * k} strokeLinecap="round" aria-hidden>
      {children}
    </g>
  );
}

const REGION_STROKE: Record<RegionStyle, string> = {
  reliable: "stroke-emerald-400",
  unreliable: "stroke-amber-400",
};

/** The dash of the warning style, in screen pixels. */
function dash(style: RegionStyle, k: number): string | undefined {
  return style === "unreliable" ? `${svgNumber(9 * k)} ${svgNumber(6 * k)}` : undefined;
}

function Ellipse({ shape, ...props }: { shape: EllipseShape } & ComponentProps<"ellipse">) {
  return (
    <ellipse
      cx={svgNumber(shape.cx)}
      cy={svgNumber(shape.cy)}
      rx={svgNumber(shape.rx)}
      ry={svgNumber(shape.ry)}
      transform={ellipseTransform(shape)}
      {...props}
    />
  );
}

function TargetLayer({ overlay, k, hatch }: { overlay: Overlay; k: number; hatch: string }) {
  if (!overlay.target) return null;
  const { style } = overlay;
  return (
    <g data-layer="target" data-style={style}>
      <Halo width={4.5} k={k}>
        <path d={overlay.target.outline} />
      </Halo>
      <path
        data-part="target-outline"
        data-style={style}
        d={overlay.target.outline}
        className={cn(REGION_STROKE[style], style === "reliable" && "fill-emerald-400/10")}
        fill={style === "unreliable" ? `url(#${hatch})` : undefined}
        strokeWidth={2 * k}
        strokeDasharray={dash(style, k)}
        strokeLinejoin="round"
      />
    </g>
  );
}

function RegionLayer({ shape, style, k, hatch }: { shape: EllipseShape; style: RegionStyle; k: number; hatch: string }) {
  return (
    <g data-layer="region" data-style={style}>
      <Halo width={5} k={k}>
        <Ellipse shape={shape} />
      </Halo>
      <Ellipse
        shape={shape}
        data-part="region"
        data-style={style}
        className={cn(REGION_STROKE[style], style === "reliable" && "fill-emerald-400/20")}
        fill={style === "unreliable" ? `url(#${hatch})` : undefined}
        strokeWidth={2.5 * k}
        strokeDasharray={dash(style, k)}
      />
    </g>
  );
}

function PoseOnlyLayer({ shape, k }: { shape: EllipseShape; k: number }) {
  return (
    <g data-layer="pose-only">
      <Halo width={4} k={k}>
        <Ellipse shape={shape} />
      </Halo>
      <Ellipse
        shape={shape}
        data-part="pose-only"
        className="fill-none stroke-sky-300"
        strokeWidth={2 * k}
        strokeDasharray={`${svgNumber(2 * k)} ${svgNumber(4 * k)}`}
        strokeLinecap="round"
      />
    </g>
  );
}

const OBSERVED_COLOUR: Record<ObservedMark["kind"], string> = {
  inlier: "stroke-sky-300",
  outlier: "stroke-rose-400",
  unposed: "stroke-white",
};

/** A line from each click to where the pose puts it, and a ring there. Sub-pixel for a good pose. */
function ResidualLayer({ marks, k }: { marks: ObservedMark[]; k: number }) {
  const posed = marks.filter((mark): mark is ObservedMark & { reprojection: Vec2 } => mark.reprojection !== null);
  return (
    <g data-layer="residuals" className="fill-none">
      {posed.map((mark) => {
        const [x1, y1] = mark.at;
        const [x2, y2] = mark.reprojection;
        return (
          <g key={mark.id} data-landmark={mark.id}>
            <Halo width={3.5} k={k}>
              <line x1={svgNumber(x1)} y1={svgNumber(y1)} x2={svgNumber(x2)} y2={svgNumber(y2)} />
              <circle cx={svgNumber(x2)} cy={svgNumber(y2)} r={svgNumber(7 * k)} />
            </Halo>
            <line
              data-part="residual"
              x1={svgNumber(x1)}
              y1={svgNumber(y1)}
              x2={svgNumber(x2)}
              y2={svgNumber(y2)}
              className={OBSERVED_COLOUR[mark.kind]}
              strokeWidth={1.5 * k}
            />
            <circle
              data-part="reprojection"
              cx={svgNumber(x2)}
              cy={svgNumber(y2)}
              r={svgNumber(7 * k)}
              className={OBSERVED_COLOUR[mark.kind]}
              strokeWidth={1.5 * k}
            />
          </g>
        );
      })}
    </g>
  );
}

/** Inliers are filled dots, outliers crosses, and clicks without a pose open rings: shape and colour both differ. */
function LandmarkMark({ mark, k }: { mark: ObservedMark; k: number }) {
  const common = { "data-part": "landmark", "data-landmark": mark.id, "data-kind": mark.kind, transform: at(mark.at) };
  if (mark.kind === "outlier") {
    const arm = svgNumber(5.5 * k);
    const cross = `M-${arm} -${arm} L${arm} ${arm} M${arm} -${arm} L-${arm} ${arm}`;
    return (
      <g {...common}>
        <path d={cross} className="fill-none stroke-black" strokeOpacity={0.7} strokeWidth={4.5 * k} strokeLinecap="round" />
        <path d={cross} className="fill-none stroke-rose-400" strokeWidth={2.5 * k} strokeLinecap="round" />
      </g>
    );
  }
  if (mark.kind === "unposed") {
    return (
      <g {...common}>
        <circle r={svgNumber(5.5 * k)} className="fill-none stroke-black" strokeOpacity={0.7} strokeWidth={4.5 * k} />
        <circle r={svgNumber(5.5 * k)} className="fill-none stroke-white" strokeWidth={2 * k} />
      </g>
    );
  }
  return (
    <g {...common}>
      <circle r={svgNumber(5 * k)} className="fill-sky-400 stroke-black" strokeOpacity={0.8} strokeWidth={1.5 * k} />
    </g>
  );
}

/** Atlas landmarks not clicked here, where the pose puts them: faint, as they are a prediction. */
function ProjectionMark({ mark, k }: { mark: ProjectedMark; k: number }) {
  if (mark.at) {
    const size = svgNumber(4.5 * k);
    return (
      <g data-part="projection" data-landmark={mark.id} transform={at(mark.at)} opacity={0.75}>
        <path
          d={`M0 -${size} L${size} 0 L0 ${size} L-${size} 0 Z`}
          className="fill-black/30 stroke-white"
          strokeWidth={1.5 * k}
          strokeLinejoin="round"
        />
      </g>
    );
  }
  if (!mark.edge) return null;
  const tip = svgNumber(7 * k);
  const back = svgNumber(5 * k);
  return (
    <g
      data-part="projection-edge"
      data-landmark={mark.id}
      transform={`${at(mark.edge.at)} rotate(${svgNumber(mark.edge.angle)})`}
      opacity={0.85}
    >
      <path
        d={`M${tip} 0 L-${back} -${back} L-${back} ${back} Z`}
        className="fill-white stroke-black"
        strokeOpacity={0.7}
        strokeWidth={1.5 * k}
        strokeLinejoin="round"
      />
    </g>
  );
}

/** A dot, small enough to leave the region around it in view. */
function TargetCentre({ centre, style, k }: { centre: Vec2; style: RegionStyle; k: number }) {
  return (
    <g data-part="target-centre" data-style={style} transform={at(centre)}>
      <circle
        r={svgNumber(2.5 * k)}
        className={cn("stroke-black", style === "reliable" ? "fill-emerald-400" : "fill-amber-400")}
        strokeOpacity={0.8}
        strokeWidth={1.5 * k}
      />
    </g>
  );
}

/** Four ticks around an open centre: the truth often lands on the target centre and its region. */
function TruthMark({ point, k }: { point: Vec2; k: number }) {
  const ticks = [
    [1, 0],
    [-1, 0],
    [0, 1],
    [0, -1],
  ]
    .map(([dx, dy]) => `M${svgNumber(dx * 7 * k)} ${svgNumber(dy * 7 * k)} L${svgNumber(dx * 14 * k)} ${svgNumber(dy * 14 * k)}`)
    .join(" ");
  return (
    <g data-part="truth" transform={at(point)}>
      <path d={ticks} className="fill-none stroke-black" strokeOpacity={0.7} strokeWidth={4.5 * k} strokeLinecap="round" />
      <path d={ticks} className="fill-none stroke-fuchsia-400" strokeWidth={2.5 * k} strokeLinecap="round" />
    </g>
  );
}

function Labels({ overlay, k }: { overlay: Overlay; k: number }) {
  const labels = useMemo(() => placeLabels(overlay, 12 * k, 9 * k, 7 * k), [overlay, k]);
  return (
    <g data-layer="labels" aria-hidden>
      {labels.map((label) => (
        <text
          key={label.id}
          data-label={label.id}
          x={svgNumber(label.x)}
          y={svgNumber(label.y)}
          fontSize={svgNumber(12 * k)}
          textAnchor={label.anchor}
          dominantBaseline="middle"
          className={cn("fill-white stroke-black font-sans font-medium", label.faint && "fill-white/80")}
          strokeOpacity={0.6}
          strokeWidth={2.75 * k}
          paintOrder="stroke"
          strokeLinejoin="round"
        >
          {label.text}
        </text>
      ))}
    </g>
  );
}

function OverlayMarks({ overlay, layers, k, hatch }: { overlay: Overlay; layers: Layers; k: number; hatch: string }) {
  const { style } = overlay;
  return (
    <>
      {layers.target && <TargetLayer overlay={overlay} k={k} hatch={hatch} />}
      {layers.region && overlay.region && <RegionLayer shape={overlay.region} style={style} k={k} hatch={hatch} />}
      {layers.poseOnly && overlay.poseOnly && <PoseOnlyLayer shape={overlay.poseOnly} k={k} />}
      {layers.projections && (
        <g data-layer="projections">
          {overlay.unobserved.map((mark) => (
            <ProjectionMark key={mark.id} mark={mark} k={k} />
          ))}
        </g>
      )}
      {layers.residuals && <ResidualLayer marks={overlay.observed} k={k} />}
      {layers.landmarks && (
        <g data-layer="landmarks">
          {overlay.observed.map((mark) => (
            <LandmarkMark key={mark.id} mark={mark} k={k} />
          ))}
        </g>
      )}
      {layers.target && overlay.target && <TargetCentre centre={overlay.target.centre} style={style} k={k} />}
      {layers.truth && overlay.truth && <TruthMark point={overlay.truth} k={k} />}
      {layers.labels && <Labels overlay={overlay} k={k} />}
    </>
  );
}

/**
 * The image at `src`, width × height pixels, fitted into its box, with the
 * overlay of `result` when there is one. `truth` is the truth the page shows.
 */
export function LocalisationImage({
  src,
  width,
  height,
  result,
  truth,
  layers,
  label,
  busy,
}: {
  src: string;
  width: number;
  height: number;
  result: LocaliseResult | null;
  truth: Truth | null;
  layers: Layers;
  /** The accessible name of the picture. */
  label: string;
  busy: boolean;
}) {
  const [boxRef, box] = useElementSize<HTMLDivElement>();
  const ids = useId();
  const clip = `${ids}-clip`;
  const hatch = `${ids}-hatch`;
  const [image, setImage] = useState<{ src: string; ok: boolean } | null>(null);
  // Image pixels per screen pixel. Until the box is measured, a 1080 × 1920 view on a laptop.
  const k = box ? imagePixelsPerScreenPixel(width, height, box.width, box.height) : 2;
  const overlay = useMemo(() => (result ? overlayOf(result, truth, EDGE_INSET * k) : null), [result, truth, k]);
  const loaded = image?.src === src && image.ok;
  const broken = image?.src === src && !image.ok;

  return (
    <div ref={boxRef} className="absolute inset-0">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="size-full"
        role="img"
        aria-label={label}
        data-image={src}
        data-loaded={loaded ? "true" : "false"}
      >
        <defs>
          <clipPath id={clip}>
            <rect width={width} height={height} />
          </clipPath>
          {/* The warning style fills a region with stripes, so it never reads as a confident solid one. */}
          <pattern
            id={hatch}
            patternUnits="userSpaceOnUse"
            width={svgNumber(7 * k)}
            height={svgNumber(7 * k)}
            patternTransform="rotate(45)"
          >
            <line x1="0" y1="0" x2="0" y2={svgNumber(7 * k)} className="stroke-amber-400/60" strokeWidth={2.5 * k} />
          </pattern>
        </defs>
        <image
          href={src}
          width={width}
          height={height}
          onLoad={() => setImage({ src, ok: true })}
          onError={() => setImage({ src, ok: false })}
        />
        {overlay && (
          <g clipPath={`url(#${clip})`}>
            <OverlayMarks overlay={overlay} layers={layers} k={k} hatch={hatch} />
          </g>
        )}
      </svg>
      {broken && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-neutral-300">
          <ImageOff aria-hidden className="size-6" />
          Image not loaded
        </div>
      )}
      {(busy || (!loaded && !broken)) && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <LoaderCircle aria-hidden className="size-8 animate-spin text-white/80 motion-reduce:animate-none" />
        </div>
      )}
    </div>
  );
}
