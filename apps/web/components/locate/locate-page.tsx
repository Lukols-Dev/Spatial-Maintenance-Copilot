"use client";

import { Boxes, CircleAlert, ServerOff } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { DecisionPanel } from "@/components/locate/decision-panel";
import {
  AREA,
  AtlasLink,
  BodySkeleton,
  Field,
  GRID,
  IMAGE_BOX,
  ImageChip,
  Page,
  PageSkeleton,
  RetryButton,
  State,
  Toolbar,
  atlasFacts,
  pictureLabel,
} from "@/components/locate/page-parts";
import { session, sessionStore, traces, useLoaded, useShown, useTraceSteps } from "@/components/locate/hooks";
import { LayerToggles } from "@/components/locate/layer-toggles";
import { LAYERS, LocalisationImage, type Layers } from "@/components/locate/localisation-image";
import { TraceCard } from "@/components/locate/trace-card";
import { ViewpointStrip } from "@/components/locate/viewpoint-strip";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { imageUrl } from "@/lib/api";
import { count, unavailableTitle } from "@/lib/locate/format";
import type { Shown } from "@/lib/locate/session";
import { latestByView, readSelection, shownTruth, traceKey, writeSelection, type Selection } from "@/lib/locate/trace";
import {
  atlasOptions,
  buildSetOf,
  defaultTruthView,
  pickAtlas,
  pickViewSet,
  truthViews,
  viewpointSets,
  viewpointsOf,
  type Viewpoint,
} from "@/lib/locate/viewpoints";
import { cn } from "@/lib/utils";
import { getAtlas, getViewSet, refreshWorkspace, useWorkspace, type Workspace } from "@/lib/workspace";

// The home page: an atlas, one of its recorded viewpoints, and what the
// geometry and the decision make of that view. Choosing another viewpoint
// runs the localisation again, and the trace shows whether it improved.

const loadAtlas = (id: string, signal: AbortSignal) => getAtlas(id, { signal });
const loadViewSet = (name: string, signal: AbortSignal) => getViewSet(name, { signal });

const ALL_LAYERS = Object.fromEntries(LAYERS.map((layer) => [layer, true])) as Layers;

/** The value of "None" in the truth select: no file name starts with "-". */
const NO_TRUTH = "-";

/** The perception service answered with a workspace at least once, or not at all. */
export function LocatePage() {
  const workspace = useWorkspace();
  if (workspace.status === "loading") return <PageSkeleton />;
  const data = workspace.data;
  const problem = workspace.status === "error" ? workspace.message : null;
  if (!data) {
    return (
      <State
        icon={<ServerOff />}
        title={unavailableTitle(problem ?? "")}
        detail={problem}
        alert
        action={<RetryButton onRetry={() => void refreshWorkspace()} />}
      />
    );
  }
  return <Locate workspace={data} problem={problem} />;
}

function Locate({ workspace, problem }: { workspace: Workspace; problem: string | null }) {
  // What this tab chose last, so a reload comes back to the same trace.
  const [wanted, setWanted] = useState<Selection | null>(() => readSelection(sessionStore()));
  const [layers, setLayers] = useState<Layers>(ALL_LAYERS);

  const atlases = useMemo(() => atlasOptions(workspace), [workspace]);
  const assetId = pickAtlas(atlases, wanted?.asset ?? null);
  const summary = atlases.find((atlas) => atlas.asset_id === assetId) ?? null;
  // Read again when the atlas is rebuilt.
  const atlasRead = useLoaded(assetId, summary?.built_at ?? "", loadAtlas);
  const detail = atlasRead.state.status === "ready" ? atlasRead.state.data : null;

  const sets = useMemo(() => (detail ? viewpointSets(workspace, detail.atlas) : []), [workspace, detail]);
  const buildSet = detail ? buildSetOf(detail) : null;
  const setName = detail ? pickViewSet(sets, buildSet, wanted?.asset === assetId ? (wanted?.set ?? null) : null) : null;
  const setSummary = sets.find((set) => set.name === setName) ?? null;
  // Read again when its clicks change.
  const setRead = useLoaded(setName, setSummary?.updated_at ?? "", loadViewSet);
  const viewSet = setRead.state.status === "ready" ? setRead.state.data : null;

  const viewpoints = useMemo(() => (viewSet && detail ? viewpointsOf(viewSet, detail.atlas) : null), [viewSet, detail]);
  const truths = useMemo(() => (viewSet && detail ? truthViews(viewSet, detail.atlas.target.id) : []), [viewSet, detail]);

  function choose(next: Selection) {
    setWanted(next);
    writeSelection(sessionStore(), next);
  }

  const toolbar = (
    <Toolbar problem={problem}>
      <Field label="Asset" htmlFor="locate-asset" facts={summary && atlasFacts(summary)}>
        <Select value={assetId ?? ""} onValueChange={(asset) => choose({ asset, set: null })} disabled={atlases.length === 0}>
          <SelectTrigger id="locate-asset" className="w-52">
            <SelectValue placeholder="None" />
          </SelectTrigger>
          <SelectContent>
            {atlases.map((atlas) => (
              <SelectItem key={atlas.file} value={atlas.asset_id} disabled={atlas.error !== null}>
                {atlas.asset_id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Field
        label="Viewpoints"
        htmlFor="locate-set"
        facts={viewpoints && `${count(viewpoints.length, "viewpoint")} · ${truths.length} with truth`}
      >
        <Select
          value={setName ?? ""}
          onValueChange={(set) => assetId && choose({ asset: assetId, set })}
          disabled={sets.length === 0}
        >
          <SelectTrigger id="locate-set" className="w-52">
            <SelectValue placeholder="None" />
          </SelectTrigger>
          <SelectContent>
            {sets.map((set) => (
              <SelectItem key={set.name} value={set.name}>
                {set.name === buildSet ? `${set.name} · build set` : set.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
    </Toolbar>
  );

  if (atlases.length === 0) {
    return (
      <Page toolbar={toolbar}>
        <State icon={<Boxes />} title="No atlas" action={<AtlasLink />} />
      </Page>
    );
  }
  if (assetId === null || summary === null) {
    return (
      <Page toolbar={toolbar}>
        <State icon={<Boxes />} title="No readable atlas" detail={atlases[0].error} action={<AtlasLink />} />
      </Page>
    );
  }
  if (atlasRead.state.status === "error") {
    return (
      <Page toolbar={toolbar}>
        <State
          icon={<CircleAlert />}
          title={`${assetId} not read`}
          detail={atlasRead.state.message}
          alert
          action={<RetryButton onRetry={atlasRead.retry} />}
        />
      </Page>
    );
  }
  if (!detail) {
    return (
      <Page toolbar={toolbar}>
        <BodySkeleton />
      </Page>
    );
  }
  if (setName === null || (viewpoints !== null && viewpoints.length === 0)) {
    return (
      <Page toolbar={toolbar}>
        <State
          icon={<Boxes />}
          title="No viewpoints with marked landmarks"
          detail={viewSet?.clicks_error}
          action={<AtlasLink />}
        />
      </Page>
    );
  }
  if (setRead.state.status === "error") {
    return (
      <Page toolbar={toolbar}>
        <State
          icon={<CircleAlert />}
          title={`${setName} not read`}
          detail={setRead.state.message}
          alert
          action={<RetryButton onRetry={setRead.retry} />}
        />
      </Page>
    );
  }
  if (!viewpoints) {
    return (
      <Page toolbar={toolbar}>
        <BodySkeleton />
      </Page>
    );
  }

  const key = traceKey(assetId, summary.built_at, setName);
  return (
    <Session
      key={key}
      traceKey={key}
      asset={assetId}
      set={setName}
      viewpoints={viewpoints}
      truths={truths}
      layers={layers}
      onLayers={setLayers}
      toolbar={toolbar}
    />
  );
}

function Session({
  traceKey: key,
  asset,
  set,
  viewpoints,
  truths,
  layers,
  onLayers,
  toolbar,
}: {
  traceKey: string;
  asset: string;
  set: string;
  viewpoints: Viewpoint[];
  /** Images of the set in which the target is clicked. */
  truths: string[];
  layers: Layers;
  onLayers: (layers: Layers) => void;
  toolbar: ReactNode;
}) {
  const steps = useTraceSteps(key);
  const shown = useShown(key);
  const latest = steps.at(-1) ?? null;
  // Nothing asked yet in this page: the latest step of the trace, as after a reload.
  const display: Shown = shown.status === "idle" && latest ? { status: "shown", step: latest } : shown;

  const first = viewpoints[0].file;
  const firstTruth = defaultTruthView(first, truths);
  const untouched = shown.status === "idle" && steps.length === 0;
  useEffect(() => {
    // A trace with nothing to show starts with the first viewpoint.
    if (untouched) session.run(key, { asset_id: asset, view_set: set, view: first, truth_view: firstTruth });
  }, [untouched, key, asset, set, first, firstTruth]);
  // Leaving this trace (another asset or set, another page) drops its request on the way.
  useEffect(() => () => session.cancel(), [key]);

  const current =
    display.status === "shown"
      ? { view: display.step.view, truthView: display.step.truthView }
      : display.status === "idle"
        ? { view: first, truthView: firstTruth }
        : { view: display.request.view, truthView: display.request.truth_view };
  const step = display.status === "shown" ? display.step : null;
  const result = step?.result ?? null;
  const viewpoint = viewpoints.find((candidate) => candidate.file === current.view) ?? null;
  const size =
    result?.image ??
    (viewpoint?.width && viewpoint.height ? { width: viewpoint.width, height: viewpoint.height } : null);
  const truthOptions = current.truthView && !truths.includes(current.truthView) ? [...truths, current.truthView] : truths;
  const latestOfViews = useMemo(() => latestByView(steps), [steps]);

  function run(view: string, truthView: string | null) {
    // The same request already on its way is left to finish.
    if (display.status === "running" && display.request.view === view && display.request.truth_view === truthView) return;
    session.run(key, { asset_id: asset, view_set: set, view, truth_view: truthView });
  }

  function clear() {
    // What is on screen stays there: only the record of the steps goes.
    if (display.status === "shown") session.show(key, display.step);
    traces.clear(key);
  }

  return (
    <Page
      toolbar={toolbar}
      below={
        <TraceCard
          steps={steps}
          shown={step}
          onShow={(chosen) => session.show(key, chosen)}
          onClear={clear}
          className="m-3 @5xl:m-4"
        />
      }
    >
      <div className={GRID}>
        <ViewpointStrip
          set={set}
          viewpoints={viewpoints}
          current={current.view}
          busy={display.status === "running" ? display.request.view : null}
          latest={latestOfViews}
          onSelect={(view) => run(view, defaultTruthView(view, truths))}
          className={AREA.strip}
        />

        <section aria-labelledby="view-heading" className={cn("flex min-h-0 min-w-0 flex-col", AREA.image)}>
          <div className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-2 border-b bg-card px-3 py-2">
            <h2 id="view-heading" className="min-w-0 truncate text-sm font-semibold">
              {current.view}
            </h2>
            {size && (
              <span className="text-xs text-muted-foreground tabular-nums">
                {size.width} × {size.height} px
              </span>
            )}
            <div className="ml-auto flex items-center gap-2">
              <Label htmlFor="locate-truth" className="text-xs text-muted-foreground">
                Truth from
              </Label>
              <Select
                value={current.truthView ?? NO_TRUTH}
                onValueChange={(value) => run(current.view, value === NO_TRUTH ? null : value)}
                disabled={truthOptions.length === 0}
              >
                <SelectTrigger id="locate-truth" size="sm" className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_TRUTH}>None</SelectItem>
                  {truthOptions.map((file) => (
                    <SelectItem key={file} value={file}>
                      {file}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className={IMAGE_BOX}>
            {size ? (
              <LocalisationImage
                src={imageUrl(set, current.view)}
                width={size.width}
                height={size.height}
                result={result}
                truth={step ? shownTruth(step) : null}
                layers={layers}
                label={pictureLabel(current.view, result)}
                busy={display.status === "running"}
              />
            ) : (
              <p className="absolute inset-0 flex items-center justify-center text-sm text-neutral-300">
                Image size unknown
              </p>
            )}
            <div className="pointer-events-none absolute top-3 left-3 flex">
              <ImageChip shown={display} />
            </div>
          </div>
        </section>

        <DecisionPanel
          shown={display}
          steps={steps}
          onRetry={() => display.status === "failed" && session.run(key, display.request)}
          className={AREA.panel}
        />

        <LayerToggles
          layers={layers}
          style={result?.decision.reliable ? "reliable" : "unreliable"}
          onChange={onLayers}
          className={AREA.layers}
        />
      </div>
    </Page>
  );
}
