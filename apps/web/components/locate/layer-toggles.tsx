"use client";

import type { ReactNode } from "react";

import { LAYERS, type Layer, type Layers } from "@/components/locate/localisation-image";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import type { RegionStyle } from "@/lib/locate/overlay";
import { cn } from "@/lib/utils";

const NAMES: Record<Layer, string> = {
  landmarks: "Landmarks",
  residuals: "Residuals",
  projections: "Projections",
  labels: "Labels",
  target: "Target",
  region: "95 % region",
  poseOnly: "Pose-only region",
  truth: "Truth",
};

/** The mark a layer draws, at legend size, on the dark ground the image has. */
function Swatch({ layer, style }: { layer: Layer; style: RegionStyle }) {
  const region = style === "reliable" ? "stroke-emerald-400" : "stroke-amber-400";
  const dashed = style === "unreliable" ? "3 2" : undefined;
  const marks: Record<Layer, ReactNode> = {
    landmarks: (
      <>
        <circle cx="6" cy="10" r="3" className="fill-sky-400" />
        <path d="M11.5 5.5 L16.5 10.5 M16.5 5.5 L11.5 10.5" className="fill-none stroke-rose-400" strokeWidth="1.8" />
      </>
    ),
    residuals: (
      <>
        <line x1="3" y1="13" x2="13" y2="6" className="stroke-sky-300" strokeWidth="1.3" />
        <circle cx="14" cy="6" r="3" className="fill-none stroke-sky-300" strokeWidth="1.3" />
      </>
    ),
    projections: (
      <>
        <path d="M6 6 L9 9 L6 12 L3 9 Z" className="fill-none stroke-white" strokeWidth="1.2" />
        <path d="M17 9 L12 5.5 L12 12.5 Z" className="fill-white" />
      </>
    ),
    labels: (
      <text x="10" y="13" textAnchor="middle" fontSize="9" className="fill-white font-sans font-medium">
        Aa
      </text>
    ),
    target: (
      <>
        <path
          d="M3 4 L17 4 L17 15 L3 15 Z"
          className={cn("fill-none", region)}
          strokeWidth="1.4"
          strokeDasharray={dashed}
        />
        <circle cx="10" cy="9.5" r="2" className={style === "reliable" ? "fill-emerald-400" : "fill-amber-400"} />
      </>
    ),
    region: (
      <ellipse
        cx="10"
        cy="9.5"
        rx="7"
        ry="5"
        className={cn(region, style === "reliable" ? "fill-emerald-400/25" : "fill-amber-400/20")}
        strokeWidth="1.6"
        strokeDasharray={dashed}
      />
    ),
    poseOnly: (
      <ellipse
        cx="10"
        cy="9.5"
        rx="6"
        ry="4"
        className="fill-none stroke-sky-300"
        strokeWidth="1.6"
        strokeDasharray="1 2"
        strokeLinecap="round"
      />
    ),
    truth: (
      <path
        d="M12.5 9.5 L17 9.5 M7.5 9.5 L3 9.5 M10 12 L10 16.5 M10 7 L10 2.5"
        className="fill-none stroke-fuchsia-400"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    ),
  };
  return (
    <svg viewBox="0 0 20 19" className="h-[19px] w-5 shrink-0 rounded-sm bg-neutral-800" aria-hidden>
      {marks[layer]}
    </svg>
  );
}

/** One checkbox per overlay layer; the swatch beside each is what it draws, in the style of the result on screen. */
export function LayerToggles({
  layers,
  style,
  onChange,
  className,
}: {
  layers: Layers;
  style: RegionStyle;
  onChange: (layers: Layers) => void;
  className?: string;
}) {
  return (
    <section aria-labelledby="layers-heading" className={cn("bg-card p-3", className)}>
      <h2 id="layers-heading" className="mb-2 px-1 text-sm font-semibold">
        Layers
      </h2>
      <ul className="grid grid-cols-2 gap-x-3 gap-y-0.5 @5xl:grid-cols-1">
        {LAYERS.map((layer) => (
          <li key={layer}>
            <Label
              htmlFor={`layer-${layer}`}
              className="flex min-h-8 cursor-pointer items-center gap-2 rounded-md px-1 font-normal hover:bg-muted"
            >
              <Checkbox
                id={`layer-${layer}`}
                checked={layers[layer]}
                onCheckedChange={(checked) => onChange({ ...layers, [layer]: checked === true })}
                className="focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
              />
              <Swatch layer={layer} style={style} />
              <span className="truncate">{NAMES[layer]}</span>
            </Label>
          </li>
        ))}
      </ul>
    </section>
  );
}
