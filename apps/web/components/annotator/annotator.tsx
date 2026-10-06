"use client";

import { Download, FolderOpen, ImagePlus, Upload } from "lucide-react";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { AnnotationCanvas, type CanvasHandle, type Marker } from "@/components/annotator/annotation-canvas";
import { ImagesPanel } from "@/components/annotator/images-panel";
import { ConfirmDialog } from "@/components/annotator/point-dialogs";
import { PointsPanel } from "@/components/annotator/points-panel";
import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import * as core from "@/lib/annotate/core";

export const STORAGE_KEY = "smc-annotate:v1";
const SHORTCUTS_KEY = "smc-annotate:shortcuts";

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

/** id changes with every message, so the same words said twice are announced twice. */
type Message = { kind: "ok" | "error"; text: string; id?: number } | null;

interface ImageEntry {
  name: string;
  url: string;
}

/** A view set of the workspace open in the annotator, instead of files from disk. */
export interface WorkspaceSource {
  set: string;
  /** The state the set's clicks.json gives. */
  initial: core.AnnotationState;
  /** The set's images, read from the service. */
  files: File[];
  /** Facts about the set to say once its images are open. */
  notices: string[];
  /** Every new state, for the service to save. */
  onChange: (state: core.AnnotationState) => void;
  /** Whether the latest change is saved, at the end of the toolbar. */
  status: ReactNode;
}

/** The state left by the last session. This component never renders on the server. */
function loadSaved(): { state: core.AnnotationState; message: Message } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const restored = raw ? core.restore(JSON.parse(raw)) : null;
    if (restored && (restored.points.length > 0 || restored.cameraId)) {
      return {
        state: restored,
        message: {
          kind: "ok",
          text: `Restored ${restored.points.length} point(s) from your last session. Open the same images to continue.`,
        },
      };
    }
  } catch {
    // Storage blocked or unreadable: start empty.
  }
  return { state: core.createState(), message: null };
}

/**
 * What a picked or dropped entry is, from its first bytes rather than its name:
 * a JPEG renamed to .png would still be turned by its EXIF tag. A dropped folder
 * arrives as an entry that cannot be read.
 */
async function kindOf(file: File): Promise<"png" | "json" | "other" | "unreadable"> {
  if (/\.json$/i.test(file.name) || file.type === "application/json") return "json";
  try {
    const head = new Uint8Array(await file.slice(0, PNG_SIGNATURE.length).arrayBuffer());
    return PNG_SIGNATURE.every((byte, index) => head[index] === byte) ? "png" : "other";
  } catch {
    return "unreadable";
  }
}

/** Whether single-key shortcuts are on; they can be turned off (WCAG 2.1.4). */
function loadShortcuts(): boolean {
  try {
    return localStorage.getItem(SHORTCUTS_KEY) !== "off";
  } catch {
    return true;
  }
}

/** Keys typed into a field or a dialog are not shortcuts. */
function isTyping(target: EventTarget | null) {
  return (
    target instanceof Element &&
    target.closest(
      "input, textarea, select, [contenteditable='true'], [role='dialog'], [role='alertdialog'], [role='menu'], [role='listbox'], [role='radiogroup'], [role='slider']",
    ) !== null
  );
}

/**
 * The point annotator. Without `workspace` it works on files opened from disk
 * and keeps the session in localStorage; with it, on a view set of the
 * perception service, which saves every change.
 */
export function Annotator({ workspace }: { workspace?: WorkspaceSource }) {
  const local = workspace === undefined;
  const [initial] = useState(() => (workspace ? { state: workspace.initial, message: null } : loadSaved()));
  const [state, setState] = useState(initial.state);
  const [message, setMessageState] = useState<Message>(initial.message);
  const messageCount = useRef(0);
  const setMessage = useCallback(
    (next: Message) => setMessageState(next && { ...next, id: ++messageCount.current }),
    [],
  );
  const [images, setImages] = useState<ImageEntry[]>([]);
  const [current, setCurrent] = useState(-1);
  const [selected, setSelected] = useState<string | null>(initial.state.points[0] ?? null);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [shortcuts, setShortcuts] = useState(loadShortcuts);
  const canvasRef = useRef<CanvasHandle>(null);
  // The latest state, for work that finishes after an await.
  const stateRef = useRef(state);
  // Each load gets a number; a load that finishes after a newer one has started is dropped.
  const loadRef = useRef(0);
  const imagesInput = useRef<HTMLInputElement>(null);
  const jsonInput = useRef<HTMLInputElement>(null);

  const image = current >= 0 ? (images[current] ?? null) : null;
  // A selection that no longer exists (deleted, renamed, cleared) falls back to the first point.
  const active = selected !== null && state.points.includes(selected) ? selected : (state.points[0] ?? null);

  // Autosave: the work survives a closed tab. A view set's work is the service's to keep,
  // and leaves the local session alone.
  useEffect(() => {
    if (!local) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Private window or blocked storage: the page still works.
    }
  }, [local, state]);

  const onChange = workspace?.onChange;
  useEffect(() => {
    onChange?.(state);
  }, [onChange, state]);

  useLayoutEffect(() => {
    stateRef.current = state;
  });

  useEffect(() => {
    try {
      localStorage.setItem(SHORTCUTS_KEY, shortcuts ? "on" : "off");
    } catch {
      // Storage blocked: the choice lasts for this visit.
    }
  }, [shortcuts]);

  // Free the object URLs of replaced images.
  useEffect(() => () => images.forEach((entry) => URL.revokeObjectURL(entry.url)), [images]);

  /**
   * Merge one clicks file into the latest state and say how it went. The ref is
   * updated at once, so a second file read straight after builds on this one
   * (and is checked against its camera) even before React has rendered.
   */
  const mergeJson = useCallback(async (file: File): Promise<NonNullable<Message>> => {
    try {
      const data: unknown = JSON.parse(await file.text());
      const result = core.fromJson(stateRef.current, data);
      stateRef.current = result.state;
      setState(result.state);
      return { kind: "ok", text: `Read ${result.images} image(s) and ${result.pointsAdded} new point(s) from ${file.name}.` };
    } catch (error) {
      return { kind: "error", text: `Cannot read ${file.name}: ${error instanceof Error ? error.message : error}` };
    }
  }, []);

  const openJson = useCallback(async (file: File) => setMessage(await mergeJson(file)), [mergeJson, setMessage]);

  /** Open images and clicks files; `notices` go into the message this gives. */
  const loadFiles = useCallback(
    async (files: File[], notices: NonNullable<Message>[] = []) => {
      const load = ++loadRef.current;
      if (files.length === 0 && notices.length === 0) return;
      const kinds = await Promise.all(files.map(kindOf));
      if (load !== loadRef.current) return;

      // Everything this drop or pick did goes into one message, errors first.
      const outcomes: NonNullable<Message>[] = [...notices];
      // A clicks file among them is opened as clicks, one after another, not refused as an image.
      for (const file of files.filter((_, index) => kinds[index] === "json")) {
        outcomes.push(await mergeJson(file));
      }
      const pngs = files.filter((_, index) => kinds[index] === "png");
      const others = kinds.filter((kind) => kind === "other").length;
      const unreadable = kinds.filter((kind) => kind === "unreadable").length;

      const names = pngs.map((file) => file.name);
      const duplicates = [...new Set(names.filter((name, index) => names.indexOf(name) !== index))];
      if (duplicates.length > 0) {
        outcomes.push({
          kind: "error",
          text: `No image opened: more than one image is called ${duplicates.join(", ")}. clicks.json identifies a view by its file name, so every image needs its own.`,
        });
      }
      if (others > 0) {
        // A browser turns a JPEG by its EXIF tag, so its clicks would not be the calibration's pixels.
        outcomes.push({ kind: "error", text: `${others} file(s) skipped because they are not PNG.` });
      }
      if (unreadable > 0) {
        outcomes.push({
          kind: "error",
          text: `${unreadable} item(s) could not be read. A folder cannot be dropped: open it and select the PNG files inside.`,
        });
      }
      const openImages = pngs.length > 0 && duplicates.length === 0;
      if (openImages) outcomes.push({ kind: "ok", text: `${pngs.length} image(s) opened.` });

      if (load !== loadRef.current || outcomes.length === 0) return;
      const errors = outcomes.filter((outcome) => outcome.kind === "error");
      const successes = outcomes.filter((outcome) => outcome.kind === "ok");
      setMessage({
        kind: errors.length > 0 ? "error" : "ok",
        text: [...errors, ...successes].map((outcome) => outcome.text).join(" "),
      });
      if (!openImages) return;
      const sorted = [...pngs].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
      setImages(sorted.map((file) => ({ name: file.name, url: URL.createObjectURL(file) })));
      setCurrent(0);
      canvasRef.current?.focus();
    },
    [mergeJson, setMessage],
  );

  // A view set's images come from the service and go through the same checks as files from
  // disk. They open after the first render, as a drop would, and not at all if the annotator
  // is gone by then.
  const viewSetFiles = workspace?.files;
  const viewSetNotices = workspace?.notices;
  const [opening, setOpening] = useState(!local);
  useEffect(() => {
    if (!viewSetFiles) return;
    const notices = (viewSetNotices ?? []).map((text): NonNullable<Message> => ({ kind: "error", text }));
    const timer = setTimeout(() => void loadFiles(viewSetFiles, notices).then(() => setOpening(false)));
    return () => clearTimeout(timer);
  }, [viewSetFiles, viewSetNotices, loadFiles]);

  // Files dropped beside the canvas would make the browser leave the page to show them.
  useEffect(() => {
    const hasFiles = (event: DragEvent) => event.dataTransfer?.types.includes("Files") ?? false;
    const over = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      // A view set takes no files from disk: the cursor says so, and nothing is dropped.
      if (!local && event.dataTransfer) event.dataTransfer.dropEffect = "none";
    };
    const drop = (event: DragEvent) => {
      if (!hasFiles(event) || event.defaultPrevented) return;
      event.preventDefault();
      if (!local) return;
      // While a dialog is open, a drop is not meant to replace the images behind it.
      if (document.querySelector("[role='dialog'][data-state='open'], [role='alertdialog'][data-state='open']")) return;
      void loadFiles(Array.from(event.dataTransfer?.files ?? []));
    };
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [loadFiles, local]);

  const place = useCallback(
    (ix: number, iy: number) => {
      if (!image) return;
      if (!active) {
        setMessage({ kind: "error", text: "Add a point first, then mark it in the image." });
        return;
      }
      const next = core.place(state, image.name, active, ix, iy);
      setState(next);
      const [x, y] = core.clickAt(next, image.name, active) ?? [0, 0];
      const following = autoAdvance ? core.nextUnplaced(next, image.name, active) : null;
      if (autoAdvance) setSelected(following ?? active);
      // Said out loud for screen readers, which cannot see the marker or the moved selection.
      setMessage({
        kind: "ok",
        text: `Marked ${active} at x ${x}, y ${y}.${following ? ` Next: ${following}.` : autoAdvance ? " Every point is marked in this image." : ""}`,
      });
    },
    [image, active, state, autoAdvance, setMessage],
  );

  const reportUndecodable = useCallback((name: string) => {
    setMessage({ kind: "error", text: `Cannot decode ${name}.` });
  }, [setMessage]);

  function addPoint(name: string): string | null {
    const outcome = core.addPoint(state, name);
    if (!outcome.ok) return outcome.error;
    setState(outcome.state);
    setSelected(outcome.name);
    return null;
  }

  function renamePoint(name: string, newName: string): string | null {
    const outcome = core.renamePoint(state, name, newName);
    if (!outcome.ok) return outcome.error;
    setState(outcome.state);
    if (active === name) setSelected(outcome.name);
    return null;
  }

  function saveJson() {
    const cameraId = state.cameraId.trim();
    if (!cameraId) {
      setMessage({ kind: "error", text: "Enter the camera id first: it must match the calibration file." });
      return;
    }
    const data = core.toJson({ ...state, cameraId });
    if (Object.keys(data.views).length === 0) {
      setMessage({ kind: "error", text: "Nothing to save yet: no clicks." });
      return;
    }
    const url = URL.createObjectURL(new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "clicks.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage({
      kind: "ok",
      text: local ? "Saved clicks.json to your downloads folder." : "Downloaded clicks.json.",
    });
  }

  /**
   * Shortcuts act only while focus is inside the workspace (images, canvas,
   * points), never while typing or in a dialog. The canvas handles the arrow
   * keys, Enter and Space itself and marks them as handled.
   */
  function onWorkspaceKey(event: KeyboardEvent<HTMLDivElement>) {
    const key = event.key;
    const bracket = key === "[" || key === "]";
    // [ and ] need AltGr or Option on some layouts; any other modified key is not ours.
    const typedWithOption = bracket && (event.getModifierState("AltGraph") || (event.altKey && !event.ctrlKey));
    if (event.defaultPrevented || event.metaKey || ((event.ctrlKey || event.altKey) && !typedWithOption)) return;
    if (isTyping(event.target)) return;
    const onCanvas = event.target instanceof HTMLCanvasElement;
    // PageUp/PageDown scroll the points panel; they change the image only from the canvas or the image list.
    const onImages = onCanvas || (event.target instanceof Element && event.target.closest("[aria-label='Images']") !== null);
    // Single-character keys are shortcuts only while they are switched on.
    if (key.length === 1 && !shortcuts) return;

    const goTo = (index: number) => {
      if (index === current || index < 0 || index >= images.length) return;
      setCurrent(index);
      setMessage({ kind: "ok", text: `Image ${index + 1} of ${images.length}: ${images[index].name}.` });
    };
    if (((key === "PageDown" && onImages) || key === "]") && images.length > 0) goTo(current + 1);
    else if (((key === "PageUp" && onImages) || key === "[") && images.length > 0) goTo(current - 1);
    else if (key.length === 1 && key >= "1" && key <= "9") {
      const name = state.points[Number(key) - 1];
      if (!name) return;
      setSelected(name);
      setMessage({ kind: "ok", text: `Marking ${name}.` });
    } else if (key === "s" || key === "S") {
      const name = core.stepPoint(state, active, event.shiftKey ? -1 : 1);
      setSelected(name);
      if (name) setMessage({ kind: "ok", text: `Marking ${name}.` });
    } else if ((key === "Backspace" || key === "Delete") && onCanvas && image && active) {
      if (core.clickAt(state, image.name, active) === null) return;
      setState(core.unplace(state, image.name, active));
      setMessage({ kind: "ok", text: `Removed the mark of ${active} in ${image.name}.` });
    } else if (key === "+" || key === "=") canvasRef.current?.zoomBy(1.4);
    else if (key === "-" || key === "_") canvasRef.current?.zoomBy(1 / 1.4);
    else if (key === "0") canvasRef.current?.fit();
    else return;
    event.preventDefault();
  }

  const counts = useMemo(() => core.countsPerPoint(state), [state]);
  const markers = useMemo<Marker[]>(() => {
    if (!image) return [];
    return state.points.flatMap((name) => {
      const pixel = core.clickAt(state, image.name, name);
      return pixel ? [{ name, pixel, selected: name === active }] : [];
    });
  }, [state, image, active]);

  return (
    <div className="flex h-[calc(100svh-3.5rem)] min-h-144 flex-col">
      <div className="flex flex-wrap items-end gap-3 border-b p-3">
        {workspace && (
          <dl className="space-y-1">
            <dt className="text-xs text-muted-foreground">View set</dt>
            <dd className="flex h-8 items-center text-sm font-medium">{workspace.set}</dd>
          </dl>
        )}
        <div className="space-y-1">
          <Label htmlFor="camera-id" className="text-xs text-muted-foreground">
            Camera id
          </Label>
          <Input
            id="camera-id"
            className="w-72"
            value={state.cameraId}
            onChange={(event) => setState((previous) => ({ ...previous, cameraId: event.target.value }))}
            placeholder="e.g. iphone11-1x-1080p-portrait"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {local && (
            <>
              <Button variant="outline" onClick={() => imagesInput.current?.click()}>
                <ImagePlus /> Open images…
              </Button>
              <Button variant="outline" onClick={() => jsonInput.current?.click()}>
                <Upload /> Open clicks.json…
              </Button>
            </>
          )}
          <Button onClick={saveJson}>
            <Download /> {local ? "Save clicks.json" : "Download clicks.json"}
          </Button>
          <ConfirmDialog
            title="Forget every point and click?"
            description="The point names and all clicks are removed. The camera id and the open images stay."
            action="Clear all"
            onConfirm={() => {
              setState((previous) => ({ ...core.createState(), cameraId: previous.cameraId }));
              setSelected(null);
              setMessage({ kind: "ok", text: "Cleared." });
            }}
            trigger={<Button variant="ghost">Clear all</Button>}
          />
        </div>
        {workspace?.status}
        {local && (
          <>
            <input
              ref={imagesInput}
              type="file"
              accept="image/png"
              multiple
              hidden
              aria-label="Open images"
              onChange={(event) => {
                void loadFiles(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
            <input
              ref={jsonInput}
              type="file"
              accept="application/json,.json"
              hidden
              aria-label="Open clicks.json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void openJson(file);
                event.target.value = "";
              }}
            />
          </>
        )}
      </div>

      <div
        className="grid min-h-0 flex-1 grid-rows-[auto_1fr_auto] lg:grid-cols-[13rem_1fr_19rem] lg:grid-rows-1"
        onKeyDown={onWorkspaceKey}
      >
        <ImagesPanel
          images={images.map((entry) => ({ name: entry.name, marked: core.markedInImage(state, entry.name).length }))}
          points={state.points.length}
          current={current}
          onSelect={setCurrent}
        />
        <AnnotationCanvas
          ref={canvasRef}
          image={image}
          markers={markers}
          onPlace={place}
          onFiles={local ? (files) => void loadFiles(files) : undefined}
          onError={reportUndecodable}
          target={active}
          empty={
            opening ? null : (
              <Empty className="border border-dashed border-white/20 bg-neutral-900 text-neutral-200">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <FolderOpen />
                  </EmptyMedia>
                  <EmptyTitle>
                    {workspace?.files.length === 0 ? `No images in ${workspace.set}` : "No images open"}
                  </EmptyTitle>
                </EmptyHeader>
                {local && (
                  <EmptyContent>
                    <Button variant="secondary" onClick={() => imagesInput.current?.click()}>
                      <ImagePlus /> Open images…
                    </Button>
                  </EmptyContent>
                )}
              </Empty>
            )
          }
        />
        <PointsPanel
          points={state.points.map((name) => ({
            name,
            views: counts[name] ?? 0,
            here: image !== null && core.clickAt(state, image.name, name) !== null,
          }))}
          selected={active}
          onSelect={setSelected}
          onAdd={addPoint}
          onRename={renamePoint}
          onDelete={(name) => setState((previous) => core.removePoint(previous, name))}
          autoAdvance={autoAdvance}
          onAutoAdvance={setAutoAdvance}
          shortcuts={shortcuts}
          onShortcuts={setShortcuts}
          message={message}
        />
      </div>
    </div>
  );
}
