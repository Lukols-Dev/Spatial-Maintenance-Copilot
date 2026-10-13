"use client";

import { Boxes, CircleAlert, ServerOff } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { agent, useAgentView } from "@/components/agent/hooks";
import { AgentPanel } from "@/components/agent/agent-panel";
import { AgentTrace } from "@/components/agent/agent-trace";
import { DecisionPanel } from "@/components/locate/decision-panel";
import { useLoaded } from "@/components/locate/hooks";
import { LayerToggles } from "@/components/locate/layer-toggles";
import { LAYERS, LocalisationImage, type Layers } from "@/components/locate/localisation-image";
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
import { ViewpointStrip } from "@/components/locate/viewpoint-strip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { agentViewpoints, sessionKey, viewpointAction } from "@/lib/agent/session";
import { imageUrl } from "@/lib/api";
import { count, unavailableTitle } from "@/lib/locate/format";
import type { Shown } from "@/lib/locate/session";
import { latestByView, shownTruth } from "@/lib/locate/trace";
import {
  atlasOptions,
  buildSetOf,
  pickAtlas,
  pickViewSet,
  viewpointSets,
  viewpointsOf,
  type Viewpoint,
} from "@/lib/locate/viewpoints";
import { cn } from "@/lib/utils";
import { getAtlas, getViewSet, refreshWorkspace, useWorkspace, type Workspace } from "@/lib/workspace";

// A session of the agent on recorded viewpoints: the operator gives a view,
// the geometry localises the hidden target, the policy decides, and the agent
// asks for the move the policy chose, or for approval of the next step.

const loadAtlas = (id: string, signal: AbortSignal) => getAtlas(id, { signal });
const loadViewSet = (name: string, signal: AbortSignal) => getViewSet(name, { signal });

const ALL_LAYERS = Object.fromEntries(LAYERS.map((layer) => [layer, true])) as Layers;

/** The perception service answered with a workspace at least once, or not at all. */
export function AgentPage() {
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
  return <Agent workspace={data} problem={problem} />;
}

function Agent({ workspace, problem }: { workspace: Workspace; problem: string | null }) {
  const [wanted, setWanted] = useState<{ asset: string | null; set: string | null }>({ asset: null, set: null });
  const [layers, setLayers] = useState<Layers>(ALL_LAYERS);

  const atlases = useMemo(() => atlasOptions(workspace), [workspace]);
  const assetId = pickAtlas(atlases, wanted.asset);
  const summary = atlases.find((atlas) => atlas.asset_id === assetId) ?? null;
  const atlasRead = useLoaded(assetId, summary?.built_at ?? "", loadAtlas);
  const detail = atlasRead.state.status === "ready" ? atlasRead.state.data : null;

  const sets = useMemo(() => (detail ? viewpointSets(workspace, detail.atlas) : []), [workspace, detail]);
  const buildSet = detail ? buildSetOf(detail) : null;
  const setName = detail ? pickViewSet(sets, buildSet, wanted.asset === assetId ? wanted.set : null) : null;
  const setSummary = sets.find((set) => set.name === setName) ?? null;
  const setRead = useLoaded(setName, setSummary?.updated_at ?? "", loadViewSet);
  const viewSet = setRead.state.status === "ready" ? setRead.state.data : null;

  const viewpoints = useMemo(
    () => (viewSet && detail ? agentViewpoints(viewpointsOf(viewSet, detail.atlas)) : null),
    [viewSet, detail],
  );

  const toolbar = (
    <Toolbar problem={problem}>
      <Field label="Asset" htmlFor="agent-asset" facts={summary && atlasFacts(summary)}>
        <Select
          value={assetId ?? ""}
          onValueChange={(asset) => setWanted({ asset, set: null })}
          disabled={atlases.length === 0}
        >
          <SelectTrigger id="agent-asset" className="w-52">
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
        htmlFor="agent-set"
        facts={viewpoints && `${count(viewpoints.length, "viewpoint")} with the target hidden`}
      >
        <Select
          value={setName ?? ""}
          onValueChange={(set) => assetId && setWanted({ asset: assetId, set })}
          disabled={sets.length === 0}
        >
          <SelectTrigger id="agent-set" className="w-52">
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

  const frame = (body: ReactNode) => <Page toolbar={toolbar}>{body}</Page>;
  if (atlases.length === 0) return frame(<State icon={<Boxes />} title="No atlas" action={<AtlasLink />} />);
  if (assetId === null || summary === null) {
    return frame(<State icon={<Boxes />} title="No readable atlas" detail={atlases[0].error} action={<AtlasLink />} />);
  }
  if (atlasRead.state.status === "error") {
    return frame(
      <State
        icon={<CircleAlert />}
        title={`${assetId} not read`}
        detail={atlasRead.state.message}
        alert
        action={<RetryButton onRetry={atlasRead.retry} />}
      />,
    );
  }
  if (!detail) return frame(<BodySkeleton />);
  if (setName === null || (viewpoints !== null && viewpoints.length === 0)) {
    return frame(
      <State
        icon={<Boxes />}
        title="No viewpoints with the target hidden"
        detail={viewSet?.clicks_error}
        action={<AtlasLink />}
      />,
    );
  }
  if (setRead.state.status === "error") {
    return frame(
      <State
        icon={<CircleAlert />}
        title={`${setName} not read`}
        detail={setRead.state.message}
        alert
        action={<RetryButton onRetry={setRead.retry} />}
      />,
    );
  }
  if (!viewpoints) return frame(<BodySkeleton />);

  const key = sessionKey(assetId, summary.built_at, setName);
  return (
    <Session
      key={key}
      storageKey={key}
      asset={assetId}
      set={setName}
      viewpoints={viewpoints}
      layers={layers}
      onLayers={setLayers}
      toolbar={toolbar}
    />
  );
}

function Session({
  storageKey,
  asset,
  set,
  viewpoints,
  layers,
  onLayers,
  toolbar,
}: {
  storageKey: string;
  asset: string;
  set: string;
  viewpoints: Viewpoint[];
  layers: Layers;
  onLayers: (layers: Layers) => void;
  toolbar: ReactNode;
}) {
  const { session: state, pending, failure } = useAgentView(storageKey);
  // A session of this atlas and set left in this tab is read back; leaving drops the call on its way.
  useEffect(() => {
    agent.resume(storageKey);
    return () => agent.cancel();
  }, [storageKey]);

  const turn = state.turn;
  const step = state.steps.at(-1) ?? null;
  const pendingView = pending && (pending.kind === "start" || pending.kind === "choose") ? pending.view : null;
  const firstView = viewpoints[0].file;
  const currentView = pendingView ?? step?.view ?? firstView;
  const result = !pendingView && step?.view === currentView ? step.result : null;
  const viewpoint = viewpoints.find((candidate) => candidate.file === currentView) ?? null;
  const size =
    result?.image ?? (viewpoint?.width && viewpoint.height ? { width: viewpoint.width, height: viewpoint.height } : null);

  const shown: Shown = pendingView
    ? { status: "running", request: { asset_id: asset, view_set: set, view: pendingView, truth_view: null } }
    : step
      ? { status: "shown", step }
      : { status: "idle" };
  const action = viewpointAction(turn);
  const awaiting = turn?.awaiting ?? null;
  const latest = useMemo(() => latestByView(state.steps), [state.steps]);

  function select(view: string) {
    if (pending) return;
    if (action === "start") agent.run(storageKey, { kind: "start", asset, set, view });
    else if (action === "choose") agent.run(storageKey, { kind: "choose", view });
  }

  return (
    <Page toolbar={toolbar} below={<AgentTrace events={state.events} className="m-3 @5xl:m-4" />}>
      <div className={GRID}>
        <ViewpointStrip
          set={set}
          viewpoints={viewpoints}
          current={currentView}
          busy={pendingView}
          latest={latest}
          suggested={awaiting?.kind === "view" ? awaiting.suggested_views : []}
          disabled={pending !== null || action === null}
          onSelect={select}
          className={AREA.strip}
        />

        <section aria-labelledby="view-heading" className={cn("flex min-h-0 min-w-0 flex-col", AREA.image)}>
          <div className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-2 border-b bg-card px-3 py-2">
            <h2 id="view-heading" className="min-w-0 truncate text-sm font-semibold">
              {currentView}
            </h2>
            {size && (
              <span className="text-xs text-muted-foreground tabular-nums">
                {size.width} × {size.height} px
              </span>
            )}
            {step?.truthView && result && (
              <span className="ml-auto text-xs text-muted-foreground">Truth from {step.truthView}</span>
            )}
          </div>
          <div className={IMAGE_BOX}>
            {size ? (
              <LocalisationImage
                src={imageUrl(set, currentView)}
                width={size.width}
                height={size.height}
                result={result}
                truth={result && step ? shownTruth(step) : null}
                layers={layers}
                label={pictureLabel(currentView, result)}
                busy={pendingView !== null}
              />
            ) : (
              <p className="absolute inset-0 flex items-center justify-center text-sm text-neutral-300">
                Image size unknown
              </p>
            )}
            <div className="pointer-events-none absolute top-3 left-3 flex">
              <ImageChip shown={shown} />
            </div>
          </div>
        </section>

        <div className={cn("flex min-h-0 flex-col divide-y", AREA.panel)}>
          <AgentPanel
            turn={turn}
            model={state.model}
            pending={pending}
            error={failure?.message ?? null}
            firstView={firstView}
            onStart={(view) => agent.run(storageKey, { kind: "start", asset, set, view })}
            onChoose={(view) => agent.run(storageKey, { kind: "choose", view })}
            onApprove={(approved) => agent.run(storageKey, { kind: "approve", approved })}
            onNewSession={() => agent.reset(storageKey)}
            onRetry={() => failure && agent.run(storageKey, failure.action)}
          />
          {(step || pendingView) && <DecisionPanel shown={shown} steps={state.steps} onRetry={() => undefined} />}
        </div>

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
