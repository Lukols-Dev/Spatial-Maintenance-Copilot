"use client";

import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
  type Ref,
} from "react";

import * as core from "@/lib/annotate/core";
import { cn } from "@/lib/utils";

export interface Marker {
  name: string;
  /** OpenCV pixels. */
  pixel: core.Pixel;
  selected: boolean;
}

export interface CanvasHandle {
  zoomBy(factor: number): void;
  fit(): void;
  focus(): void;
}

const MAX_SCALE = 40;
const DRAG_THRESHOLD_PX = 4;
/** How close to the edge the keyboard cursor may come before the view follows it. */
const EDGE_PX = 24;

/** A position snapped to the centre of the pixel it is in, kept inside the image. */
function pixelCentre(value: number, size: number) {
  return Math.min(size - 0.5, Math.max(0.5, Math.floor(value) + 0.5));
}

function drawMarker(ctx: CanvasRenderingContext2D, sx: number, sy: number, name: string, selected: boolean) {
  const arm = 11;
  const gap = 3;
  const colour = selected ? "#ffd24c" : "#4cc2ff";
  const segments = [
    [sx - arm, sy, sx - gap, sy],
    [sx + gap, sy, sx + arm, sy],
    [sx, sy - arm, sx, sy - gap],
    [sx, sy + gap, sx, sy + arm],
  ];
  ctx.lineCap = "butt";
  for (const [width, style] of [
    [3.5, "#000"],
    [1.5, colour],
  ] as const) {
    ctx.lineWidth = width;
    ctx.strokeStyle = style;
    ctx.beginPath();
    for (const [x0, y0, x1, y1] of segments) {
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
    }
    ctx.stroke();
  }
  ctx.font = "12px ui-sans-serif, system-ui, sans-serif";
  ctx.textBaseline = "middle";
  ctx.lineWidth = 3;
  ctx.strokeStyle = "#000";
  ctx.strokeText(name, sx + arm + 4, sy - 2);
  ctx.fillStyle = colour;
  ctx.fillText(name, sx + arm + 4, sy - 2);
}

/** The keyboard cursor: a white and black frame around one image pixel, with ticks pointing at it. */
function drawKeyCursor(ctx: CanvasRenderingContext2D, sx: number, sy: number, scale: number) {
  const half = Math.max(scale / 2, 3);
  const tick = 10;
  for (const [width, style] of [
    [3, "#000"],
    [1, "#fff"],
  ] as const) {
    ctx.lineWidth = width;
    ctx.strokeStyle = style;
    ctx.strokeRect(sx - half, sy - half, half * 2, half * 2);
    ctx.beginPath();
    ctx.moveTo(sx - half - tick, sy);
    ctx.lineTo(sx - half, sy);
    ctx.moveTo(sx + half, sy);
    ctx.lineTo(sx + half + tick, sy);
    ctx.moveTo(sx, sy - half - tick);
    ctx.lineTo(sx, sy - half);
    ctx.moveTo(sx, sy + half);
    ctx.lineTo(sx, sy + half + tick);
    ctx.stroke();
  }
}

/**
 * The image with its markers on a canvas. With the mouse: click to place, drag
 * to pan, wheel to zoom at the cursor. With the keyboard: the arrow keys move a
 * cursor one image pixel at a time and Enter or Space places the point there.
 * The view lives in refs and is drawn imperatively, so panning does not
 * re-render React.
 */
export function AnnotationCanvas({
  ref,
  image,
  markers,
  onPlace,
  onFiles,
  onError,
  target,
  empty,
}: {
  ref?: Ref<CanvasHandle>;
  image: { name: string; url: string } | null;
  markers: Marker[];
  /** The point the next mark places. */
  target: string | null;
  /** (ix, iy): position in the image with its top-left corner at (0, 0). */
  onPlace: (ix: number, iy: number) => void;
  /** Files dropped on the image; without it the image is no drop target. */
  onFiles?: (files: File[]) => void;
  /** The browser could not decode the image. */
  onError: (name: string) => void;
  empty: ReactNode;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const readoutRef = useRef<HTMLSpanElement>(null);
  const elementRef = useRef<HTMLImageElement | null>(null);
  const viewRef = useRef<core.View>({ scale: 1, x: 0, y: 0 });
  const fittedRef = useRef(true);
  // The device pixel ratio the backing store was sized with; draw() must use the same one.
  const sizeRef = useRef({ width: 0, height: 0, dpr: 1 });
  const markersRef = useRef<Marker[]>([]);
  // Image coordinates of the keyboard cursor, always at a pixel centre; null until first used.
  const keyCursorRef = useRef<core.Pixel | null>(null);
  const focusedRef = useRef(false);
  // The mouse position over the canvas, for the readout; null when it is elsewhere.
  const pointerRef = useRef<core.Pixel | null>(null);
  const onPlaceRef = useRef(onPlace);
  const onErrorRef = useRef(onError);
  const [loaded, setLoaded] = useState<{ url: string; width: number; height: number } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // The latest callbacks, without re-subscribing the pointer listeners (which would drop a drag).
  useLayoutEffect(() => {
    onPlaceRef.current = onPlace;
    onErrorRef.current = onError;
  });

  /** An image position (top-left corner at 0, 0) as OpenCV pixels in the status bar. */
  const showReadout = useCallback((ix: number, iy: number) => {
    const out = readoutRef.current;
    const element = elementRef.current;
    if (!out || !element) return;
    const inside = ix >= 0 && iy >= 0 && ix <= element.naturalWidth && iy <= element.naturalHeight;
    // Rounding can leave -0.0 at the first pixel; it is 0.
    const show = (value: number) => (Math.abs(value) < 0.05 ? 0 : value).toFixed(1);
    const [x, y] = core.toOpenCv(ix, iy);
    out.textContent = `${inside ? `x ${show(x)}  y ${show(y)}   ` : ""}×${viewRef.current.scale.toFixed(2)}`;
  }, []);

  /** The readout follows the mouse over the canvas, else the keyboard cursor, else shows the zoom. */
  const refreshReadout = useCallback(() => {
    const out = readoutRef.current;
    if (!out) return;
    if (!elementRef.current) {
      out.textContent = "";
      return;
    }
    const pointer = pointerRef.current;
    const cursor = keyCursorRef.current;
    if (pointer) showReadout(...core.screenToImage(viewRef.current, pointer[0], pointer[1]));
    else if (focusedRef.current && cursor) showReadout(cursor[0], cursor[1]);
    else out.textContent = `×${viewRef.current.scale.toFixed(2)}`;
  }, [showReadout]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const { width, height, dpr } = sizeRef.current;
    const view = viewRef.current;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    // Read by the end-to-end tests to turn image pixels into screen positions.
    canvas.dataset.viewScale = String(view.scale);
    canvas.dataset.viewX = String(view.x);
    canvas.dataset.viewY = String(view.y);

    const element = elementRef.current;
    refreshReadout();
    if (!element) return;
    ctx.imageSmoothingEnabled = view.scale < 2;
    ctx.drawImage(element, view.x, view.y, element.naturalWidth * view.scale, element.naturalHeight * view.scale);
    for (const marker of markersRef.current) {
      const [ix, iy] = core.fromOpenCv(marker.pixel[0], marker.pixel[1]);
      const [sx, sy] = core.imageToScreen(view, ix, iy);
      drawMarker(ctx, sx, sy, marker.name, marker.selected);
    }
    const cursor = keyCursorRef.current;
    if (focusedRef.current && cursor) {
      const [sx, sy] = core.imageToScreen(view, cursor[0], cursor[1]);
      drawKeyCursor(ctx, sx, sy, view.scale);
    }
  }, [refreshReadout]);

  const fit = useCallback(() => {
    const element = elementRef.current;
    const { width, height } = sizeRef.current;
    fittedRef.current = true;
    if (element && width > 0 && height > 0) {
      viewRef.current = core.fitView(element.naturalWidth, element.naturalHeight, width, height);
    }
    draw();
  }, [draw]);

  const zoom = useCallback(
    (factor: number, sx: number, sy: number) => {
      const element = elementRef.current;
      const { width, height } = sizeRef.current;
      if (!element || width === 0 || height === 0) return;
      const minScale = core.fitView(element.naturalWidth, element.naturalHeight, width, height).scale * 0.5;
      viewRef.current = core.zoomAt(viewRef.current, factor, sx, sy, minScale, MAX_SCALE);
      fittedRef.current = false;
      draw();
    },
    [draw],
  );

  /** Put the keyboard cursor at the centre of the view, unless it is already there. */
  const ensureCursor = useCallback(() => {
    const element = elementRef.current;
    if (!element || keyCursorRef.current) return;
    const { width, height } = sizeRef.current;
    const [ix, iy] = core.screenToImage(viewRef.current, width / 2, height / 2);
    keyCursorRef.current = [pixelCentre(ix, element.naturalWidth), pixelCentre(iy, element.naturalHeight)];
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      // Zoom at the keyboard cursor while it is shown, else at the centre.
      zoomBy: (factor: number) => {
        const { width, height } = sizeRef.current;
        const cursor = keyCursorRef.current;
        if (focusedRef.current && cursor) {
          const [sx, sy] = core.imageToScreen(viewRef.current, cursor[0], cursor[1]);
          if (sx >= 0 && sx <= width && sy >= 0 && sy <= height) {
            zoom(factor, sx, sy);
            return;
          }
        }
        zoom(factor, width / 2, height / 2);
      },
      fit,
      focus: () => canvasRef.current?.focus(),
    }),
    [zoom, fit],
  );

  // Markers drawn on the next draw.
  useEffect(() => {
    markersRef.current = markers;
    draw();
  }, [markers, draw]);

  // Load and fit the current image. Until it has loaded nothing is drawn, so the
  // next image's markers never appear on the previous picture. data-loaded tells
  // the tests the picture on screen is this one.
  useEffect(() => {
    elementRef.current = null;
    keyCursorRef.current = null;
    if (canvasRef.current) delete canvasRef.current.dataset.loaded;
    draw();
    if (!image) return;
    let cancelled = false;
    const element = new Image();
    element.onload = () => {
      if (cancelled) return;
      elementRef.current = element;
      setLoaded({ url: image.url, width: element.naturalWidth, height: element.naturalHeight });
      fit();
      // With keyboard focus on the canvas, the cursor is there at once, at the centre of the new view.
      if (canvasRef.current?.matches(":focus-visible")) {
        ensureCursor();
        draw();
      }
      if (canvasRef.current) canvasRef.current.dataset.loaded = image.name;
    };
    element.onerror = () => {
      if (cancelled) return;
      setFailed(image.url);
      onErrorRef.current(image.name);
    };
    element.src = image.url;
    return () => {
      cancelled = true;
    };
  }, [image, draw, fit, ensureCursor]);

  // Keep the backing store the size of the box in device pixels, also when the
  // window moves to a screen with another pixel ratio (the box does not change size then).
  useEffect(() => {
    const viewport = viewportRef.current;
    const canvas = canvasRef.current;
    if (!viewport || !canvas) return;

    const resize = () => {
      const rect = viewport.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      sizeRef.current = { width: rect.width, height: rect.height, dpr };
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      if (fittedRef.current) fit();
      else draw();
    };

    const observer = new ResizeObserver(resize);
    observer.observe(viewport);

    // A resolution query matches one ratio only, so it is armed again after every change.
    let media: MediaQueryList | null = null;
    const onRatio = () => {
      resize();
      arm();
    };
    const arm = () => {
      media?.removeEventListener("change", onRatio);
      media = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`);
      media.addEventListener("change", onRatio);
    };
    arm();

    return () => {
      observer.disconnect();
      media?.removeEventListener("change", onRatio);
    };
  }, [draw, fit]);

  // Click, drag and wheel. Set up once; the latest onPlace is read from a ref.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let drag: { startX: number; startY: number; lastX: number; lastY: number; moved: boolean } | null = null;

    // A mouse reports whole screen pixels; take the centre of the pixel it is on.
    const local = (event: MouseEvent): core.Pixel => {
      const rect = canvas.getBoundingClientRect();
      return [core.centreOfPixel(event.clientX) - rect.left, core.centreOfPixel(event.clientY) - rect.top];
    };

    const down = (event: MouseEvent) => {
      if (event.button !== 0) return;
      const [x, y] = local(event);
      drag = { startX: x, startY: y, lastX: x, lastY: y, moved: false };
    };
    const move = (event: MouseEvent) => {
      const [x, y] = local(event);
      const { width, height } = sizeRef.current;
      const over = x >= 0 && y >= 0 && x <= width && y <= height;
      pointerRef.current = over || drag ? [x, y] : null;
      if (!drag?.moved) refreshReadout();
      if (!drag) return;
      if (!drag.moved && Math.hypot(x - drag.startX, y - drag.startY) > DRAG_THRESHOLD_PX) drag.moved = true;
      if (drag.moved) {
        viewRef.current = core.panBy(viewRef.current, x - drag.lastX, y - drag.lastY);
        fittedRef.current = false;
        draw();
      }
      drag.lastX = x;
      drag.lastY = y;
    };
    const up = (event: MouseEvent) => {
      if (!drag) return;
      const wasClick = !drag.moved && event.button === 0;
      const { startX, startY } = drag;
      drag = null;
      const element = elementRef.current;
      if (!wasClick || !element) return;
      const [ix, iy] = core.screenToImage(viewRef.current, startX, startY);
      if (ix < 0 || iy < 0 || ix > element.naturalWidth || iy > element.naturalHeight) return;
      onPlaceRef.current(ix, iy);
    };
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const [x, y] = local(event);
      zoom(Math.exp(-event.deltaY * 0.0015), x, y);
    };

    const leave = () => {
      if (drag) return;
      pointerRef.current = null;
      refreshReadout();
    };

    canvas.addEventListener("mousedown", down);
    canvas.addEventListener("mouseleave", leave);
    canvas.addEventListener("wheel", wheel, { passive: false });
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      canvas.removeEventListener("mousedown", down);
      canvas.removeEventListener("mouseleave", leave);
      canvas.removeEventListener("wheel", wheel);
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [draw, zoom, refreshReadout]);

  /** Arrow keys move the keyboard cursor; Enter or Space places the selected point under it. */
  function onKeyDown(event: KeyboardEvent<HTMLCanvasElement>) {
    const element = elementRef.current;
    if (!element || event.altKey || event.metaKey || event.ctrlKey) return;
    const step = event.shiftKey ? 10 : 1;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const isMove = event.key in moves;
    const isPlace = event.key === "Enter" || event.key === " ";
    if (!isMove && !isPlace) return;
    event.preventDefault();
    // A held Enter would mark every remaining point at the same pixel.
    if (isPlace && event.repeat) return;

    const { width, height } = sizeRef.current;
    let cursor = keyCursorRef.current;
    if (!cursor) {
      // Focus came from the mouse, so there is no cursor yet: show it first, at the centre.
      ensureCursor();
      cursor = keyCursorRef.current ?? [0.5, 0.5];
    } else if (isMove) {
      const [dx, dy] = moves[event.key];
      cursor = [pixelCentre(cursor[0] + dx, element.naturalWidth), pixelCentre(cursor[1] + dy, element.naturalHeight)];
    } else {
      onPlaceRef.current(cursor[0], cursor[1]);
    }
    keyCursorRef.current = cursor;

    // Pan so the cursor stays in view.
    const [sx, sy] = core.imageToScreen(viewRef.current, cursor[0], cursor[1]);
    const dx = sx < EDGE_PX ? EDGE_PX - sx : sx > width - EDGE_PX ? width - EDGE_PX - sx : 0;
    const dy = sy < EDGE_PX ? EDGE_PX - sy : sy > height - EDGE_PX ? height - EDGE_PX - sy : 0;
    if (dx !== 0 || dy !== 0) {
      viewRef.current = core.panBy(viewRef.current, dx, dy);
      fittedRef.current = false;
    }
    draw();
  }

  const size = image && loaded && loaded.url === image.url ? loaded : null;
  const broken = image !== null && failed === image.url;

  return (
    <div className="flex min-h-[50svh] min-w-0 flex-1 flex-col lg:min-h-0">
      <div
        ref={viewportRef}
        className={cn(
          "relative min-h-0 flex-1 bg-neutral-950",
          dragOver && "outline-2 -outline-offset-8 outline-primary outline-dashed",
        )}
        onDragOver={
          onFiles &&
          ((event) => {
            event.preventDefault();
            setDragOver(true);
          })
        }
        onDragLeave={onFiles && (() => setDragOver(false))}
        onDrop={
          onFiles &&
          ((event) => {
            event.preventDefault();
            setDragOver(false);
            onFiles(Array.from(event.dataTransfer.files));
          })
        }
      >
        <canvas
          ref={canvasRef}
          tabIndex={0}
          data-image={image?.name ?? ""}
          // An application role lets screen readers pass the arrows, Enter and Space to the canvas.
          // The name stays the same; what changes (image, point) is in the description, read on
          // focus, while each change is announced once, by the status message.
          role={image ? "application" : undefined}
          aria-label={image ? "Image annotator" : "No image open"}
          aria-describedby={image ? "annotator-help" : undefined}
          // The focus frame is the overlay below: anything painted on the canvas itself sits under the image.
          className="peer absolute inset-0 size-full cursor-crosshair outline-hidden"
          onKeyDown={onKeyDown}
          onFocus={(event) => {
            focusedRef.current = true;
            if (event.currentTarget.matches(":focus-visible")) ensureCursor();
            draw();
          }}
          onBlur={() => {
            focusedRef.current = false;
            draw();
          }}
          onContextMenu={(event) => event.preventDefault()}
        />
        {/* Black and white bands above the image, so the focus shows on a white board and on a dark photo alike. */}
        <div
          aria-hidden
          data-slot="canvas-focus"
          className="pointer-events-none absolute inset-0 hidden shadow-[inset_0_0_0_2px_#000,inset_0_0_0_4px_#fff] peer-focus-visible:block"
        />
        <p id="annotator-help" className="sr-only">
          {image ? `${image.name}, marking ${target ?? "no point"}. ` : ""}
          Arrow keys move a cursor by one pixel, with Shift by ten. Enter or Space marks the selected point at the
          cursor. With a mouse: click to mark, drag to pan, scroll to zoom.
        </p>
        {!image && <div className="absolute inset-0 flex items-center justify-center p-6">{empty}</div>}
        {broken && (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-neutral-200">
            Cannot decode {image.name}.
          </div>
        )}
      </div>
      <div className="flex justify-between gap-3 border-t bg-card px-3 py-1.5 text-xs text-muted-foreground tabular-nums">
        <span className="truncate">
          {image ? `${image.name}${size ? `  ·  ${size.width}×${size.height} px` : ""}` : "No image"}
          {image && target && (
            <>
              {"  ·  "}marking <span className="font-medium text-foreground">{target}</span>
            </>
          )}
        </span>
        <span ref={readoutRef} className="shrink-0" />
      </div>
    </div>
  );
}
