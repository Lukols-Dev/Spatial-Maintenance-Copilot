"use client";

import { cn } from "@/lib/utils";

export function ImagesPanel({
  images,
  points,
  current,
  onSelect,
}: {
  images: { name: string; marked: number }[];
  /** How many points there are, to show "marked / all" per image. */
  points: number;
  current: number;
  onSelect: (index: number) => void;
}) {
  return (
    <aside className="flex min-h-0 flex-col border-b bg-card lg:border-r lg:border-b-0" aria-label="Images">
      <h2 className="px-4 pt-4 pb-2 text-sm font-semibold">
        Images {images.length > 0 && <span className="font-normal text-muted-foreground">({images.length})</span>}
      </h2>
      <ul className="max-h-40 min-h-0 flex-1 overflow-y-auto px-2 pb-2 lg:max-h-none">
        {images.map((image, index) => {
          const isCurrent = index === current;
          return (
            <li key={image.name}>
              <button
                type="button"
                onClick={() => onSelect(index)}
                aria-current={isCurrent ? "true" : undefined}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm outline-hidden hover:bg-muted focus-visible:outline-2 focus-visible:outline-solid focus-visible:-outline-offset-2 focus-visible:outline-foreground/70",
                  isCurrent && "bg-muted font-medium",
                )}
              >
                <span className="truncate">{image.name}</span>
                <span
                  className={cn("shrink-0 text-xs tabular-nums", isCurrent ? "text-foreground" : "text-muted-foreground")}
                  aria-label={`${image.marked} of ${points} points marked`}
                >
                  {image.marked}/{points}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
