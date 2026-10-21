"use client";

import { Boxes, Camera as CameraIcon, CircleAlert, FileVideo, LoaderCircle, ServerOff, Square, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ChangeEvent } from "react";

import { SessionSummaryCard } from "@/components/agent/session-summary";
import { CueCard, GuideHud, SIDEWAYS_WORDS, SidewaysHud } from "@/components/guide/guide-hud";
import { GuideOverlay } from "@/components/guide/guide-overlay";
import { GuideSettings } from "@/components/guide/guide-settings";
import {
  AtlasLink,
  Field,
  Page,
  PageSkeleton,
  RetryButton,
  State,
  Toolbar,
  atlasFacts,
} from "@/components/locate/page-parts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useIsMobile } from "@/hooks/use-mobile";
import { answerApproval, chooseView, startSession } from "@/lib/agent/api";
import { errorMessage } from "@/lib/api";
import { inspectFrame, postFrame } from "@/lib/guide/api";
import { wordsOf } from "@/lib/guide/moves";
import { useGuideSettings } from "@/lib/guide/settings";
import { summariseLog } from "@/lib/guide/summary";
import { cameraSource, fileSource } from "@/lib/guide/sources";
import { IDLE, createGuideStore, type GuideState, type GuideStore } from "@/lib/guide/store";
import type { FrameAnswer } from "@/lib/guide/types";
import { unavailableTitle } from "@/lib/locate/format";
import { atlasOptions, pickAtlas } from "@/lib/locate/viewpoints";
import { cn } from "@/lib/utils";
import { refreshWorkspace, useWorkspace, type Camera, type Workspace } from "@/lib/workspace";

// The operator's view of the loop: frames of the camera, or of a video,
// localised as they come. The move is shown and spoken, the agent asks for it
// in its words and then for approval of the next step, and once the panel is
// open the target's tag takes the move's place and confirms the prediction.
//
// On a phone a running camera takes the whole screen, as an app would: the
// picture fills it, Exit and the settings sit over its top, and the
// instruction, the agent's words and its buttons over its bottom, so nothing
// is scrolled to. A wider screen keeps the picture beside the measurements.

function newStore(): GuideStore {
  return createGuideStore({
    calls: {
      postFrame: (image, query, options) => postFrame(image, query, options),
      inspect: (frameId, options) => inspectFrame(frameId, options),
      start: (body, options) => startSession(body, options),
      choose: (id, view, options) => chooseView(id, view, options),
      approve: (id, approved, options) => answerApproval(id, approved, options),
    },
    now: () => Date.now(),
  });
}

function calibrated(cameras: Camera[]): (Camera & { camera_id: string; image_width: number; image_height: number })[] {
  return cameras.filter(
    (camera): camera is Camera & { camera_id: string; image_width: number; image_height: number } =>
      camera.camera_id !== null && camera.image_width !== null && camera.image_height !== null && camera.error === null,
  );
}

export function GuidePage() {
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
  return <Guide workspace={data} problem={problem} />;
}

function Guide({ workspace, problem }: { workspace: Workspace; problem: string | null }) {
  const [store] = useState(newStore);
  const state = useSyncExternalStore(store.subscribe, store.state, () => IDLE);
  const [wanted, setWanted] = useState<{ asset: string | null; camera: string | null }>({ asset: null, camera: null });
  const settings = useGuideSettings();
  const mobile = useIsMobile();
  const [opening, setOpening] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const atlases = useMemo(() => atlasOptions(workspace), [workspace]);
  const assetId = pickAtlas(atlases, wanted.asset);
  const summary = atlases.find((atlas) => atlas.asset_id === assetId) ?? null;
  const cameras = useMemo(() => calibrated(workspace.cameras), [workspace]);
  const camera = cameras.find((candidate) => candidate.camera_id === wanted.camera) ?? cameras[0] ?? null;
  const running = state.phase === "running";
  const fullscreen = mobile && running;
  const voice = settings.voice;

  useEffect(() => () => store.stop(), [store]);
  // Each instruction is spoken once, the same move again included.
  useEffect(() => {
    if (!voice || typeof speechSynthesis === "undefined") return;
    const words = state.sideways ? SIDEWAYS_WORDS : state.steady === null ? null : wordsOf(state.steady);
    if (words === null) return;
    speechSynthesis.cancel();
    speechSynthesis.speak(new SpeechSynthesisUtterance(words));
  }, [voice, state.steady, state.instruction, state.sideways]);
  useFullscreenPage(fullscreen);
  useScreenAwake(running);

  async function begin(open: (video: HTMLVideoElement) => Promise<Parameters<GuideStore["start"]>[0]>) {
    const video = videoRef.current;
    if (!video || !camera || !assetId) return;
    setOpening(null);
    try {
      const source = await open(video);
      store.start(
        source,
        { asset_id: assetId, camera_id: camera.camera_id },
        { width: camera.image_width, height: camera.image_height },
      );
    } catch (error) {
      setOpening(errorMessage(error));
    }
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void begin((video) => fileSource(video, file));
  }

  const toolbar = (
    <Toolbar problem={problem}>
      <Field label="Asset" htmlFor="guide-asset" facts={summary && atlasFacts(summary)}>
        <Select value={assetId ?? ""} onValueChange={(asset) => setWanted({ ...wanted, asset })} disabled={running}>
          <SelectTrigger id="guide-asset" className="w-52">
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
        label="Camera"
        htmlFor="guide-camera"
        facts={camera && `${camera.image_width} × ${camera.image_height} px`}
      >
        <Select
          value={camera?.camera_id ?? ""}
          onValueChange={(id) => setWanted({ ...wanted, camera: id })}
          disabled={running || cameras.length === 0}
        >
          <SelectTrigger id="guide-camera" className="w-60">
            <SelectValue placeholder="None" />
          </SelectTrigger>
          <SelectContent>
            {cameras.map((option) => (
              <SelectItem key={option.file} value={option.camera_id}>
                {option.camera_id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <div className="flex flex-wrap items-center gap-2">
        {running ? (
          <Button variant="outline" onClick={() => store.stop()}>
            <Square aria-hidden /> Stop
          </Button>
        ) : (
          <>
            <Button onClick={() => void begin((video) => cameraSource(video, { width: camera?.image_width ?? 0, height: camera?.image_height ?? 0 }))} disabled={!camera || !assetId}>
              <CameraIcon aria-hidden /> Camera
            </Button>
            <Button asChild variant="outline" disabled={!camera || !assetId}>
              <label>
                <FileVideo aria-hidden /> Video file
                <input type="file" accept="video/*" className="sr-only" onChange={onFile} disabled={!camera || !assetId} />
              </label>
            </Button>
          </>
        )}
        <GuideSettings motion={state.motion} />
      </div>
    </Toolbar>
  );

  if (atlases.length === 0) {
    return (
      <Page toolbar={toolbar}>
        <State icon={<Boxes />} title="No atlas" action={<AtlasLink />} />
      </Page>
    );
  }

  const width = state.frame?.image.width ?? camera?.image_width ?? 1080;
  const height = state.frame?.image.height ?? camera?.image_height ?? 1920;
  const failure = opening ?? state.failure;
  // The overlay is drawn only where the camera is: not while it moves or settles, nor while the phone
  // is sideways, when the last frame's overlay would stand still on a moving picture.
  const current = !state.sideways && (state.step === null || state.step === "analysing" || state.step === "ready");
  return (
    <Page
      toolbar={toolbar}
      below={
        !fullscreen &&
        state.log.length > 0 && (
          <div className="p-3 @5xl:p-4">
            <SessionSummaryCard
              summary={summariseLog(state.log)}
              model={state.agent.model}
              unit="instruction"
              first="At"
            />
          </div>
        )
      }
    >
      <div className="grid min-h-0 flex-1 grid-cols-1 @5xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div
          data-fullscreen={fullscreen ? "true" : undefined}
          className={cn(
            fullscreen
              ? "fixed inset-0 z-40 h-dvh bg-black"
              : "relative h-[70svh] min-h-80 bg-neutral-950 @5xl:h-auto @5xl:min-h-0",
          )}
        >
          <video
            ref={videoRef}
            playsInline
            muted
            aria-label="Frames being localised"
            className={cn("absolute inset-0 size-full", fullscreen ? "object-cover" : "object-contain")}
          />
          {current && (
            <GuideOverlay
              answer={state.frame}
              width={width}
              height={height}
              fit={fullscreen ? "cover" : "contain"}
              layers={settings.layers}
            />
          )}
          {fullscreen ? (
            <>
              <TopBar onExit={() => store.stop()} motion={state.motion} />
              <BottomPanel
                state={state}
                expected={{ width, height }}
                failure={failure}
                onAnswer={(approved) => store.answer(approved)}
                onAsk={() => store.inspect()}
              />
            </>
          ) : (
            <>
              {state.sideways ? (
                <SidewaysHud size={state.sideways} expected={{ width, height }} />
              ) : (
                (state.frame || state.step) && (
                  <GuideHud
                    frame={state.frame}
                    steady={state.steady}
                    sighted={state.sighted}
                    step={state.step}
                    settle={state.settle}
                  />
                )
              )}
              {failure && <Failure failure={failure} className="absolute inset-x-3 top-3" />}
            </>
          )}
        </div>
        <aside className={cn("space-y-3 p-3 @5xl:min-h-0 @5xl:overflow-y-auto @5xl:border-l", fullscreen && "hidden")}>
          <AgentCard state={state} onAnswer={(approved) => store.answer(approved)} />
          <TargetCard state={state} onAsk={() => store.inspect()} />
          <FrameCard state={state} />
        </aside>
      </div>
    </Page>
  );
}

/** While the camera takes the screen, the page under it does not scroll. */
function useFullscreenPage(on: boolean) {
  useEffect(() => {
    if (!on) return;
    const root = document.documentElement;
    const before = root.style.overflow;
    root.style.overflow = "hidden";
    return () => {
      root.style.overflow = before;
    };
  }, [on]);
}

/** While a camera runs, the screen stays on; asked for again when the page is shown again. */
function useScreenAwake(on: boolean) {
  useEffect(() => {
    if (!on || typeof navigator === "undefined" || !("wakeLock" in navigator)) return;
    let lock: WakeLockSentinel | null = null;
    let done = false;
    const take = () => {
      navigator.wakeLock.request("screen").then(
        (taken) => {
          if (done) void taken.release();
          else lock = taken;
        },
        () => {},
      );
    };
    const again = () => {
      if (document.visibilityState === "visible") take();
    };
    take();
    document.addEventListener("visibilitychange", again);
    return () => {
      done = true;
      document.removeEventListener("visibilitychange", again);
      void lock?.release();
    };
  }, [on]);
}

function Failure({ failure, className }: { failure: string; className?: string }) {
  return (
    <div role="alert" className={cn("flex items-start gap-2 rounded-md bg-red-950/85 p-3 text-sm text-red-50", className)}>
      <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span className="wrap-anywhere">{failure}</span>
    </div>
  );
}

const OVER_IMAGE = "rounded-full bg-black/60 text-white hover:bg-black/75 hover:text-white";

/** Over the top of a phone's full-screen picture: Exit, which stops the camera, and the settings. */
function TopBar({ onExit, motion }: { onExit: () => void; motion: number | null }) {
  return (
    <div className="absolute inset-x-0 top-0 flex items-start justify-between p-3 pt-[max(env(safe-area-inset-top),0.75rem)]">
      <Button variant="ghost" onClick={onExit} className={cn("h-11 px-4 text-base", OVER_IMAGE)}>
        <X aria-hidden className="size-5" /> Exit
      </Button>
      <GuideSettings overImage motion={motion} />
    </div>
  );
}

/** Over the bottom of a phone's full-screen picture: the instruction, the agent and, once approved, the target. */
function BottomPanel({
  state,
  expected,
  failure,
  onAnswer,
  onAsk,
}: {
  state: GuideState;
  expected: { width: number; height: number };
  failure: string | null;
  onAnswer: (approved: boolean) => void;
  onAsk: () => void;
}) {
  return (
    <div className="absolute inset-x-0 bottom-0 max-h-[60dvh] space-y-2 overflow-y-auto p-3 pb-[max(env(safe-area-inset-bottom),0.75rem)]">
      {failure && <Failure failure={failure} className="rounded-xl" />}
      {state.sideways ? (
        <SidewaysHud size={state.sideways} expected={expected} className="" />
      ) : (
        <CueCard
          frame={state.frame}
          steady={state.steady}
          sighted={state.sighted}
          step={state.step}
          settle={state.settle}
        />
      )}
      <AgentStrip state={state} onAnswer={onAnswer} />
      <TargetStrip state={state} onAsk={onAsk} />
    </div>
  );
}

const STRIP = "space-y-2 rounded-xl bg-black/70 p-3 text-sm text-white backdrop-blur-sm";

/** The agent's words over the picture, with its buttons when it asks for approval. */
function AgentStrip({ state, onAnswer }: { state: GuideState; onAnswer: (approved: boolean) => void }) {
  const { turn, busy, failure } = state.agent;
  const awaiting = turn?.awaiting ?? null;
  if (!turn && !busy && !failure) return null;
  return (
    <section aria-label="Agent" className={STRIP}>
      <p className="flex items-center gap-2 text-xs text-white/70">Agent {busy && <Busy />}</p>
      {awaiting?.kind === "view" && <p data-part="agent-guidance">{awaiting.guidance}</p>}
      {awaiting?.kind === "approval" && (
        <>
          <p data-part="agent-explanation" className="text-white/80">
            {awaiting.explanation}
          </p>
          <p data-part="agent-next-step" className="font-medium">
            {awaiting.next_step}
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Button
              className="h-11 bg-emerald-500 text-base text-white hover:bg-emerald-600"
              onClick={() => onAnswer(true)}
              disabled={busy}
            >
              Approve
            </Button>
            <Button
              variant="ghost"
              className="h-11 bg-white/15 text-base text-white hover:bg-white/25 hover:text-white"
              onClick={() => onAnswer(false)}
              disabled={busy}
            >
              Decline
            </Button>
          </div>
        </>
      )}
      {turn?.outcome && (
        <p data-part="agent-outcome">{turn.outcome === "accepted" ? "Next step approved" : "Next step declined"}</p>
      )}
      {failure && (
        <p role="alert" className="text-red-200 wrap-anywhere">
          {failure}
        </p>
      )}
    </section>
  );
}

/** Once the next step is approved: the vision model's second opinion on the target's region. */
function TargetStrip({ state, onAsk }: { state: GuideState; onAsk: () => void }) {
  const { answer, busy, failure } = state.second;
  if (state.approved !== true) return null;
  return (
    <section aria-label="Target" className={STRIP}>
      {answer && (
        <p data-part="second-opinion" data-verdict={answer.verdict}>
          <span className="text-white/70">Second opinion · </span>
          {answer.answer || answer.verdict}
        </p>
      )}
      {failure && (
        <p role="alert" className="text-red-200 wrap-anywhere">
          {failure}
        </p>
      )}
      {state.frame && (
        <Button
          variant="ghost"
          className="h-11 w-full bg-white/15 text-base text-white hover:bg-white/25 hover:text-white"
          onClick={onAsk}
          disabled={busy}
        >
          {busy && <Busy />} Second opinion
        </Button>
      )}
    </section>
  );
}

function Busy() {
  return <LoaderCircle aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />;
}

function AgentCard({ state, onAnswer }: { state: GuideState; onAnswer: (approved: boolean) => void }) {
  const { turn, model, busy, failure } = state.agent;
  const awaiting = turn?.awaiting ?? null;
  return (
    <Card aria-labelledby="guide-agent" className="gap-3 py-4">
      <CardHeader className="px-4">
        <CardTitle id="guide-agent" className="flex items-center gap-2 text-base">
          Agent {busy && <Busy />}
        </CardTitle>
        {model && <p className="text-xs text-muted-foreground">{model}</p>}
      </CardHeader>
      <CardContent className="space-y-3 px-4 text-sm">
        {awaiting?.kind === "view" && <p data-part="agent-guidance">{awaiting.guidance}</p>}
        {awaiting?.kind === "approval" && (
          <>
            <p data-part="agent-explanation">{awaiting.explanation}</p>
            <p className="font-medium" data-part="agent-next-step">
              {awaiting.next_step}
            </p>
            <div className="flex gap-2">
              <Button onClick={() => onAnswer(true)} disabled={busy}>
                Approve
              </Button>
              <Button variant="outline" onClick={() => onAnswer(false)} disabled={busy}>
                Decline
              </Button>
            </div>
          </>
        )}
        {turn?.outcome && (
          <p data-part="agent-outcome">{turn.outcome === "accepted" ? "Next step approved" : "Next step declined"}</p>
        )}
        {failure && (
          <p role="alert" className="text-destructive wrap-anywhere">
            {failure}
          </p>
        )}
        {turn && <p className="text-xs text-muted-foreground">{turn.events.length} trace events in the last call</p>}
      </CardContent>
    </Card>
  );
}

function TargetCard({ state, onAsk }: { state: GuideState; onAsk: () => void }) {
  const confirmed = state.confirmed;
  const { answer, busy, failure } = state.second;
  if (state.approved !== true) return null;
  return (
    <Card aria-labelledby="guide-target" className="gap-3 py-4">
      <CardHeader className="px-4">
        <CardTitle id="guide-target" className="text-base">
          Target
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 px-4 text-sm">
        {confirmed ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1" data-part="sighting">
            <dt className="text-muted-foreground">Tag in sight</dt>
            <dd>yes</dd>
            <dt className="text-muted-foreground">Inside the 95 % region</dt>
            <dd>{confirmed.inside_95 === null ? "-" : confirmed.inside_95 ? "yes" : "no"}</dd>
            <dt className="text-muted-foreground">Off the prediction</dt>
            <dd className="tabular-nums">{confirmed.error_px === null ? "-" : `${confirmed.error_px.toFixed(1)} px`}</dd>
          </dl>
        ) : (
          <p className="text-muted-foreground">Tag not in sight</p>
        )}
        {answer && (
          <div data-part="second-opinion" data-verdict={answer.verdict} className="space-y-1 border-t pt-2">
            <p className="text-xs text-muted-foreground">Second opinion · {answer.model}</p>
            <p>{answer.answer || answer.verdict}</p>
          </div>
        )}
        {failure && (
          <p role="alert" className="text-destructive wrap-anywhere">
            {failure}
          </p>
        )}
        {state.frame && (
          <Button size="sm" variant="outline" onClick={onAsk} disabled={busy}>
            {busy && <Busy />} Second opinion
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function facts(frame: FrameAnswer): [string, string][] {
  const quality = frame.localisation.quality;
  const region = frame.localisation.uncertainty;
  const edge = frame.frame_quality.edge_width_px;
  return [
    ["Landmarks found", String(frame.observations.length)],
    ["Inliers", quality ? String(quality.inliers) : "-"],
    ["RMS reprojection", quality ? `${quality.rms_reprojection_px.toFixed(2)} px` : "-"],
    ["Marker edge width", edge === null ? "-" : `${edge.toFixed(1)} px`],
    ["95 % region", region ? `${region.ellipse.semi_major_px.toFixed(1)} px` : "-"],
    ["Localised in", `${Math.round(frame.elapsed_ms)} ms`],
  ];
}

function FrameCard({ state }: { state: GuideState }) {
  const frame = state.frame;
  if (!frame) return null;
  return (
    <Card aria-labelledby="guide-frame" className="gap-3 py-4">
      <CardHeader className="px-4">
        <CardTitle id="guide-frame" className="text-base">
          Frame {state.frames}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 text-sm">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          {facts(frame).map(([name, value]) => (
            <div key={name} className="contents">
              <dt className="text-muted-foreground">{name}</dt>
              <dd className="tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
