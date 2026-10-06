"use client";

import { ChevronDown, Keyboard, Pencil, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ConfirmDialog, RenamePointDialog } from "@/components/annotator/point-dialogs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Label } from "@/components/ui/label";
import { MIN_VIEWS } from "@/lib/annotate/core";
import { cn } from "@/lib/utils";

export interface PointRow {
  name: string;
  /** Images the point is marked in. */
  views: number;
  /** Marked in the image on screen. */
  here: boolean;
}

/** Where focus goes once the list has re-rendered: a point's row, or the new-point field. */
type FocusTarget = { point: string } | { field: true };

export function PointsPanel({
  points,
  selected,
  onSelect,
  onAdd,
  onRename,
  onDelete,
  autoAdvance,
  onAutoAdvance,
  shortcuts,
  onShortcuts,
  message,
}: {
  points: PointRow[];
  selected: string | null;
  onSelect: (name: string) => void;
  /** Returns an error message, or null when the point was added. */
  onAdd: (name: string) => string | null;
  onRename: (name: string, newName: string) => string | null;
  onDelete: (name: string) => void;
  autoAdvance: boolean;
  onAutoAdvance: (value: boolean) => void;
  /** Single-key shortcuts on or off. */
  shortcuts: boolean;
  onShortcuts: (value: boolean) => void;
  message: { kind: "ok" | "error"; text: string; id?: number } | null;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  // A rename or delete unmounts the row that held the dialog, and focus would
  // fall back to the top of the page; this keeps the place in the list.
  const pendingFocus = useRef<FocusTarget | null>(null);

  const names = points.map((point) => point.name).join("\n");
  useEffect(() => {
    const target = pendingFocus.current;
    if (!target) return;
    pendingFocus.current = null;
    const row =
      "point" in target
        ? listRef.current?.querySelector<HTMLElement>(`[data-point="${CSS.escape(target.point)}"]`)
        : null;
    (row ?? document.getElementById("new-point"))?.focus();
  }, [names]);

  function add(event: FormEvent) {
    event.preventDefault();
    const problem = onAdd(draft);
    setError(problem);
    if (!problem) setDraft("");
  }

  function rename(name: string, newName: string) {
    const problem = onRename(name, newName);
    if (!problem && newName.trim() !== name) pendingFocus.current = { point: newName.trim() };
    return problem;
  }

  function remove(index: number) {
    const neighbour = points[index + 1] ?? points[index - 1];
    pendingFocus.current = neighbour ? { point: neighbour.name } : { field: true };
    onDelete(points[index].name);
  }

  return (
    <aside className="flex min-h-0 flex-col gap-4 overflow-y-auto border-t bg-card p-4 lg:border-t-0 lg:border-l" aria-label="Points">
      <h2 className="text-sm font-semibold">Points</h2>

      <form onSubmit={add} className="space-y-1.5" noValidate>
        <Label htmlFor="new-point" className="sr-only">
          New point id
        </Label>
        <div className="flex gap-2">
          <Input
            id="new-point"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="e.g. corner_top_left"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "new-point-error" : undefined}
          />
          <Button type="submit">Add</Button>
        </div>
        {/* Always rendered, so screen readers announce the text when it appears. */}
        <p id="new-point-error" role="alert" className="text-xs text-destructive empty:hidden">
          {error ?? ""}
        </p>
      </form>

      {points.length > 0 && (
        <ul ref={listRef} className="space-y-1" aria-label="Point list">
          {points.map((point, index) => {
            const isSelected = point.name === selected;
            const short = point.views < MIN_VIEWS;
            return (
              <li
                key={point.name}
                className={cn(
                  "flex items-center gap-1 rounded-lg border border-transparent pr-1",
                  isSelected && "border-amber-600 bg-amber-400/10 dark:border-amber-400/70",
                )}
              >
                <button
                  type="button"
                  data-point={point.name}
                  onClick={() => onSelect(point.name)}
                  aria-pressed={isSelected}
                  aria-label={`${point.name}, ${point.here ? "marked" : "not marked"} in this image, ${point.views} ${point.views === 1 ? "view" : "views"}${short ? `, needs ${MIN_VIEWS}` : ""}`}
                  className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:-outline-offset-2 focus-visible:outline-foreground/70"
                >
                  {/* The digit is the keyboard shortcut, a visual hint only; the keys list names it. */}
                  <span
                    className={cn(
                      "w-3 text-right text-xs tabular-nums",
                      isSelected ? "text-foreground" : "text-muted-foreground",
                    )}
                    aria-hidden
                  >
                    {index < 9 ? index + 1 : ""}
                  </span>
                  <span
                    className={cn(
                      "size-2 shrink-0 rounded-full",
                      point.here ? "bg-emerald-600 dark:bg-emerald-400" : "bg-transparent",
                    )}
                    aria-hidden
                  />
                  {/* Name and count on two lines, so the badge never squeezes the name. */}
                  <span className="flex min-w-0 flex-col items-start gap-0.5">
                    <span className="max-w-full truncate">{point.name}</span>
                    <Badge
                      variant={short ? "destructive" : "secondary"}
                      className={cn("tabular-nums", short && "text-red-700 dark:text-red-300")}
                    >
                      {point.views} {point.views === 1 ? "view" : "views"}
                      {short && ` · needs ${MIN_VIEWS}`}
                    </Badge>
                  </span>
                </button>
                <RenamePointDialog
                  name={point.name}
                  onRename={(newName) => rename(point.name, newName)}
                  trigger={
                    <Button variant="ghost" size="icon-xs" aria-label={`Rename ${point.name}`}>
                      <Pencil />
                    </Button>
                  }
                />
                <ConfirmDialog
                  title={`Delete “${point.name}”?`}
                  description={`Its ${point.views} click(s) in all images are deleted too.`}
                  action="Delete"
                  onConfirm={() => remove(index)}
                  trigger={
                    <Button variant="ghost" size="icon-xs" aria-label={`Delete ${point.name}`}>
                      <Trash2 />
                    </Button>
                  }
                />
              </li>
            );
          })}
        </ul>
      )}

      <div className="space-y-2">
        <div className="flex items-start gap-2">
          <Checkbox
            id="auto-advance"
            checked={autoAdvance}
            onCheckedChange={(value) => onAutoAdvance(value === true)}
          />
          <Label htmlFor="auto-advance" className="text-xs leading-snug font-normal text-muted-foreground">
            After a mark, select the next point not yet marked in this image
          </Label>
        </div>
        <div className="flex items-start gap-2">
          <Checkbox id="shortcuts" checked={shortcuts} onCheckedChange={(value) => onShortcuts(value === true)} />
          <Label htmlFor="shortcuts" className="text-xs leading-snug font-normal text-muted-foreground">
            Single-key shortcuts (1–9, S, [ ], + − 0)
          </Label>
        </div>
      </div>

      <p
        role="status"
        className={cn(
          "min-h-10 text-sm",
          message?.kind === "error" && "text-destructive",
          message?.kind === "ok" && "text-emerald-700 dark:text-emerald-400",
        )}
      >
        {/* A new element per message: a live region stays silent when its text does not change. */}
        {message && <span key={message.id}>{message.text}</span>}
      </p>

      {/* Closed until asked for: the panel shows the work, not a manual. */}
      <Collapsible className="mt-auto text-xs text-muted-foreground">
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="sm" className="-ml-2.5 text-muted-foreground">
            <Keyboard /> Keys
            <ChevronDown className="transition-transform group-data-[state=open]/button:rotate-180" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-2 pt-2">
          <p>On the image (Tab to it, or click it):</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
            <dt>
              <Kbd>←</Kbd> <Kbd>↑</Kbd> <Kbd>→</Kbd> <Kbd>↓</Kbd>
            </dt>
            <dd>move the cursor one pixel (with Shift: ten)</dd>
            <dt>
              <Kbd>Enter</Kbd> <Kbd>Space</Kbd>
            </dt>
            <dd>mark the selected point at the cursor</dd>
            <dt>
              <Kbd>⌫</Kbd>
            </dt>
            <dd>remove the selected point&apos;s mark in this image</dd>
            <dt>
              <Kbd>PgUp</Kbd> <Kbd>PgDn</Kbd>
            </dt>
            <dd>previous / next image (also in the image list)</dd>
          </dl>
          <p>Anywhere in the image list, the image or the points, unless single-key shortcuts are off:</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
            <dt>
              <Kbd>[</Kbd> <Kbd>]</Kbd>
            </dt>
            <dd>previous / next image</dd>
            <dt>
              <Kbd>1</Kbd>–<Kbd>9</Kbd>
            </dt>
            <dd>select a point</dd>
            <dt>
              <Kbd>S</Kbd>
            </dt>
            <dd>next point (with Shift: previous)</dd>
            <dt>
              <Kbd>+</Kbd> <Kbd>−</Kbd> <Kbd>0</Kbd>
            </dt>
            <dd>zoom in / out / fit</dd>
            <dt>wheel, drag</dt>
            <dd>zoom at the mouse, pan</dd>
          </dl>
        </CollapsibleContent>
      </Collapsible>
    </aside>
  );
}
