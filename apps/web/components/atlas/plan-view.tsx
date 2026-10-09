"use client";

import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";

import { caliper } from "@/lib/atlas/format";
import { DOT, layoutPlan, type Label, type PlanInput } from "@/lib/atlas/plan";

/** The plan is at most this high: a tall atlas is drawn smaller rather than pushing the table away. */
const MAX_HEIGHT = 480;
/** Half the length of each stroke of the cross on the target's centre. */
const CROSS = 7;

/** The width of an element on screen, null until it is first measured. */
function useWidth(ref: RefObject<HTMLElement | null>): number | null {
  const [width, setWidth] = useState<number | null>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

/** Text with a halo of the card's colour, so it reads over grid lines and circles. */
function Text({ label, muted }: { label: Label; muted?: boolean }) {
  return (
    <text
      x={label.x}
      y={label.y}
      textAnchor={label.anchor}
      className={`${muted ? "fill-muted-foreground" : "fill-foreground"} stroke-card text-[11px] [paint-order:stroke] [stroke-linejoin:round] [stroke-width:3px]`}
    >
      {label.text}
    </text>
  );
}

function Swatch({ children }: { children: ReactNode }) {
  return (
    <svg aria-hidden width={16} height={16} viewBox="0 0 16 16" className="shrink-0">
      {children}
    </svg>
  );
}

/**
 * The atlas seen face-on in the board's frame, x to the right and y down as
 * the board was printed: the board, every landmark with its 1σ circle, the
 * target's extent box and 1σ circle, all at one scale. The points table
 * carries the numbers; this shows where they are.
 */
export function PlanView({ input, label }: { input: PlanInput; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const width = useWidth(ref);
  const arrow = useId();
  const plan = width ? layoutPlan(input, width, MAX_HEIGHT) : null;

  return (
    <figure className="min-w-0 space-y-2">
      <div ref={ref} className="w-full min-w-0">
        {plan ? (
          <svg
            role="img"
            aria-label={label}
            data-scale={plan.scale}
            width={plan.width}
            height={plan.height}
            viewBox={`0 0 ${plan.width} ${plan.height}`}
            className="block"
          >
            <defs>
              <marker id={arrow} viewBox="0 0 8 8" refX={7} refY={4} markerWidth={8} markerHeight={8} orient="auto">
                <path d="M0,0 L8,4 L0,8 z" className="fill-muted-foreground" />
              </marker>
            </defs>

            {plan.board && (
              <g data-board={input.board?.id}>
                <rect
                  x={plan.board.x}
                  y={plan.board.y}
                  width={plan.board.width}
                  height={plan.board.height}
                  className="fill-muted stroke-muted-foreground"
                />
                {plan.board.grid.map((line, index) => (
                  <line key={index} {...line} className="stroke-muted-foreground/40" />
                ))}
              </g>
            )}

            {(["x", "y"] as const).map((axis) => {
              const { label: name, ...line } = plan.axes[axis];
              return (
                <g key={axis}>
                  <line {...line} className="stroke-muted-foreground" strokeWidth={1.5} markerEnd={`url(#${arrow})`} />
                  <Text label={name} muted />
                </g>
              );
            })}

            <g data-target={plan.target.id}>
              <rect
                {...plan.target.box}
                className="fill-foreground/5 stroke-foreground"
                strokeDasharray="5 4"
              />
              <circle cx={plan.target.x} cy={plan.target.y} r={plan.target.r} className="fill-foreground/10 stroke-foreground" />
              <path
                d={`M${plan.target.x - CROSS},${plan.target.y}h${2 * CROSS}M${plan.target.x},${plan.target.y - CROSS}v${2 * CROSS}`}
                className="stroke-foreground"
                strokeWidth={1.5}
              />
            </g>

            {plan.landmarks.map((point) => (
              <g key={point.id} data-landmark={point.id}>
                <circle cx={point.x} cy={point.y} r={point.r} className="fill-foreground/10 stroke-foreground/60" />
                <circle cx={point.x} cy={point.y} r={DOT} className="fill-foreground" />
              </g>
            ))}

            {[plan.target, ...plan.landmarks].map((point) =>
              point.label ? <Text key={point.id} label={point.label} /> : null,
            )}

            <g>
              <path
                d={`M${plan.scaleBar.x1},${plan.scaleBar.y1 - 4}v8M${plan.scaleBar.x1},${plan.scaleBar.y1}H${plan.scaleBar.x2}M${plan.scaleBar.x2},${plan.scaleBar.y2 - 4}v8`}
                className="fill-none stroke-muted-foreground"
                strokeWidth={1.5}
              />
              <Text label={plan.scaleBar.label} muted />
            </g>
          </svg>
        ) : (
          <div className="h-64" />
        )}
      </div>
      <figcaption>
        <ul className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <li className="flex items-center gap-1.5">
            <Swatch>
              <circle cx={8} cy={8} r={DOT} className="fill-foreground" />
            </Swatch>
            Landmark
          </li>
          <li className="flex items-center gap-1.5">
            <Swatch>
              <circle cx={8} cy={8} r={6.5} className="fill-foreground/10 stroke-foreground/60" />
            </Swatch>
            1σ
          </li>
          <li className="flex items-center gap-1.5">
            <Swatch>
              <rect x={1.5} y={1.5} width={13} height={13} className="fill-foreground/5 stroke-foreground" strokeDasharray="3 2" />
              <path d="M4,8h8M8,4v8" className="stroke-foreground" />
            </Swatch>
            Target extent
          </li>
          {input.board && (
            <li className="flex items-center gap-1.5">
              <Swatch>
                <rect x={1.5} y={1.5} width={13} height={13} className="fill-muted stroke-muted-foreground" />
                <path d="M8,1.5v13M1.5,8h13" className="stroke-muted-foreground/40" />
              </Swatch>
              {input.board.id} · {input.board.squares_x}×{input.board.squares_y} × {caliper(input.board.square_mm)} mm
            </li>
          )}
        </ul>
      </figcaption>
    </figure>
  );
}
