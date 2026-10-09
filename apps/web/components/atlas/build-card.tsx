"use client";

import { ChevronRight, Crosshair, Hammer, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { Fragment, useEffect, useState, useSyncExternalStore, type FormEvent } from "react";

import { ImportViewsDialog } from "@/components/atlas/import-views-dialog";
import { MeasureBoardDialog } from "@/components/atlas/measure-board-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { startBuild, useBuildJob, type BuildJob } from "@/lib/atlas/build-job";
import { readAtlas, readAtlases, useAtlasReads } from "@/lib/atlas/details";
import { keepDraft, keptDraft } from "@/lib/atlas/draft";
import { caliper, count, fixed, localTime, size } from "@/lib/atlas/format";
import {
  boardOptions,
  cameraOptions,
  checkForm,
  initialForm,
  setOptions,
  targetOptions,
  withViewSet,
  type AtlasForm,
  type FormDraft,
  type Option,
  type Triple,
} from "@/lib/atlas/form";
import { cn } from "@/lib/utils";
import type { AtlasBuildRequest, Board, Camera, ViewSetSummary, Workspace } from "@/lib/workspace";

const AXES = ["x", "y", "z"] as const;

function annotateHref(set: string): string {
  return `/annotate/?set=${encodeURIComponent(set)}`;
}

// Each helper gives the facts of one control: a list read as "a · b · c", or one
// sentence of the service's (an error), which may wrap anywhere.

function setFacts(set: ViewSetSummary): string[] | string {
  if (set.error) return set.error;
  const facts = [count(set.image_count, "image")];
  if (set.image_size) facts.push(size(set.image_size[0], set.image_size[1]));
  else if (set.mixed_sizes) facts.push("sizes differ");
  if (!set.clicks) facts.push("no points marked");
  else if (set.clicks.error) return set.clicks.error;
  else facts.push(`${count(set.clicks.point_count, "point")}, ${set.clicks.ready_points} in ≥ 2 images`);
  return facts;
}

function cameraFacts(camera: Camera): string[] | string {
  if (camera.error) return camera.error;
  const facts: string[] = [];
  if (camera.rms_px !== null) facts.push(`RMS ${fixed(camera.rms_px, 2)} px`);
  if (camera.frames !== null) facts.push(count(camera.frames, "frame"));
  if (camera.calibrated_at) facts.push(`calibrated ${camera.calibrated_at.slice(0, 10)}`);
  return facts;
}

function boardFacts(board: Board): string[] {
  if (board.square_measured_mm === null) return ["Not measured"];
  const spread = board.measurement_uncertainty_mm === null ? "" : ` ± ${caliper(board.measurement_uncertainty_mm)}`;
  const facts = [`${board.squares_x}×${board.squares_y} squares of ${caliper(board.square_measured_mm)}${spread} mm`];
  if (board.measured_on) facts.push(`measured ${board.measured_on}`);
  return facts;
}

function advancedFacts(form: AtlasForm): string[] {
  const facts = [
    `click σ ${form.click_sigma_px} px`,
    `centre σ ${form.target_centre_sigma_mm} mm`,
    `${form.samples} samples`,
    `seed ${form.seed}`,
  ];
  if (form.target_measured_mm.every((value) => value.trim() !== "")) {
    facts.push(`measured target ${form.target_measured_mm.join(", ")} mm`);
  }
  return facts;
}

/** Facts joined by " · ", each kept whole on its line: "2026-10-06" never breaks at a hyphen. */
function FactList({ facts }: { facts: string[] | string }) {
  if (typeof facts === "string") return facts;
  return facts.map((fact, index) => (
    <Fragment key={index}>
      {index > 0 && " · "}
      <span className="whitespace-nowrap">{fact}</span>
    </Fragment>
  ));
}

function replaced(triple: Triple, index: number, value: string): Triple {
  const next: Triple = [...triple];
  next[index] = value;
  return next;
}

function sameRequest(a: AtlasBuildRequest, b: AtlasBuildRequest | null): boolean {
  return b !== null && JSON.stringify(a) === JSON.stringify(b);
}

// ---- time ------------------------------------------------------------------------

function everySecond(onTick: () => void) {
  const timer = setInterval(onTick, 250);
  return () => clearInterval(timer);
}

function currentSecond() {
  return Math.floor(Date.now() / 1000);
}

/** Whole seconds since `since` (ms), counting while shown. */
function Elapsed({ since }: { since: number }) {
  const start = Math.floor(since / 1000);
  const now = useSyncExternalStore(everySecond, currentSecond, () => start);
  return <span className="tabular-nums">{Math.max(0, now - start)} s</span>;
}

// ---- fields ----------------------------------------------------------------------

function Facts({ id, facts }: { id?: string; facts: string[] | string | null }) {
  return (
    <p id={id} className="text-sm text-muted-foreground wrap-anywhere empty:hidden">
      {facts && <FactList facts={facts} />}
    </p>
  );
}

/** A select of options; a value no option has, from an older draft, is listed so it stays visible. */
function Choice({
  id,
  value,
  options,
  placeholder,
  shown,
  disabled,
  describedBy,
  onChange,
  className,
}: {
  id: string;
  value: string;
  options: Option[];
  /** Shown while nothing is chosen. */
  placeholder: string;
  /** Shown for the chosen value instead of its whole label, where the facts below say the rest. */
  shown?: string;
  disabled: boolean;
  describedBy?: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  const listed =
    value && !options.some((option) => option.value === value)
      ? [...options, { value, label: `${value} · not found`, disabled: true }]
      : options;
  // In a form, Radix keeps a hidden native <select> in step with the value. When the value
  // and the options change together (another view set brings its own points), it sets the
  // new value before the new options are in it and reports "". No option is "", so that is
  // never the reader's choice, and taking it would clear the field.
  function choose(next: string) {
    if (next !== "") onChange(next);
  }
  return (
    <Select value={value} onValueChange={choose} disabled={disabled || listed.length === 0}>
      <SelectTrigger id={id} aria-describedby={describedBy} className={cn("w-full min-w-0", className)}>
        <SelectValue placeholder={placeholder}>{shown}</SelectValue>
      </SelectTrigger>
      <SelectContent position="popper">
        {listed.map((option, index) => (
          <SelectItem key={`${index}:${option.value}`} value={option.value} disabled={option.disabled}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function TripleInputs({
  name,
  values,
  onChange,
}: {
  /** "Target extent": each input is named "<name> x (mm)". */
  name: string;
  values: Triple;
  onChange: (values: Triple) => void;
}) {
  const id = name.toLowerCase().replaceAll(" ", "-");
  return (
    <fieldset className="min-w-0 space-y-1.5">
      <legend className="text-sm font-medium">{name} (mm)</legend>
      <div className="grid grid-cols-3 gap-2">
        {AXES.map((axis, index) => (
          <div key={axis} className="flex min-w-0 items-center gap-1.5">
            <Label htmlFor={`atlas-${id}-${axis}`} className="text-muted-foreground">
              {axis}
            </Label>
            <Input
              id={`atlas-${id}-${axis}`}
              aria-label={`${name} ${axis} (mm)`}
              type="number"
              inputMode="decimal"
              step="any"
              value={values[index]}
              onChange={(event) => onChange(replaced(values, index, event.target.value))}
              className="tabular-nums"
            />
          </div>
        ))}
      </div>
    </fieldset>
  );
}

function NumberField({
  id,
  label,
  value,
  onChange,
  integer,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  integer?: boolean;
}) {
  return (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        inputMode={integer ? "numeric" : "decimal"}
        step={integer ? 1 : "any"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="tabular-nums"
      />
    </div>
  );
}

// ---- the card --------------------------------------------------------------------

function jobStatus(job: BuildJob): string {
  if (job.status === "building") {
    return `Building ${job.request.asset_id} v${job.request.version} from ${job.request.view_set}`;
  }
  if (job.status === "built") {
    return `Built ${job.detail.atlas.asset_id} v${job.detail.atlas.version} in ${job.seconds} s`;
  }
  return "";
}

/**
 * The form that builds an atlas from a view set. It opens on the workspace's
 * newest set and the last build's settings; the Build button stays off while
 * anything is missing, and what is missing is listed beside it.
 */
export function BuildCard({ workspace, onBuilt }: { workspace: Workspace; onBuilt: (assetId: string) => void }) {
  useAtlasReads();
  const job = useBuildJob();
  const [draft, setDraft] = useState<FormDraft>(keptDraft);
  const [advanced, setAdvanced] = useState(false);

  // The form repeats the last build of a set, which only the atlases' build reports name.
  useEffect(() => {
    for (const atlas of workspace.atlases) readAtlas(atlas);
  }, [workspace.atlases]);

  const form = initialForm(workspace, readAtlases(), draft);
  const { request, missing } = checkForm(workspace, form);
  const building = job.status === "building";
  const set = workspace.view_sets.find((candidate) => candidate.name === form.view_set);
  const camera = workspace.cameras.find((candidate) => candidate.camera_id === form.camera_id);
  const board = workspace.rig.boards.find((candidate) => candidate.id === form.board);
  const existing = workspace.atlases.find((atlas) => atlas.asset_id === form.asset_id.trim());
  const failure = job.status === "failed" && sameRequest(job.request, request) ? job.message : "";
  const targets = targetOptions(workspace, form.view_set);

  /** Every change goes through the kept draft, so a dialog finishing later never works on an old one. */
  function change(next: FormDraft) {
    keepDraft(next);
    setDraft(next);
  }
  function edit(fields: FormDraft) {
    change({ ...keptDraft(), ...fields });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!request || building) return;
    const detail = await startBuild(request);
    if (!detail) return;
    // The next build starts from this one: its set, its settings, the next version.
    change({ view_set: request.view_set });
    onBuilt(detail.atlas.asset_id);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Build</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} noValidate aria-label="Build atlas" className="space-y-4">
          <fieldset disabled={building} className="min-w-0 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="atlas-view-set">View set</Label>
              <div className="flex flex-wrap items-center gap-2">
                <Choice
                  id="atlas-view-set"
                  value={form.view_set}
                  options={setOptions(workspace)}
                  placeholder="No view set"
                  disabled={building}
                  describedBy="atlas-view-set-facts"
                  onChange={(value) => change(withViewSet(keptDraft(), value))}
                  className="flex-1 basis-48"
                />
                {set && (
                  <Button asChild variant="outline">
                    <Link href={annotateHref(set.name)}>
                      <Crosshair /> Annotate
                    </Link>
                  </Button>
                )}
                <ImportViewsDialog
                  workspace={workspace}
                  onImported={(imported) => change(withViewSet(keptDraft(), imported.name))}
                />
              </div>
              <Facts id="atlas-view-set-facts" facts={set ? setFacts(set) : null} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="atlas-camera">Camera</Label>
              <Choice
                id="atlas-camera"
                value={form.camera_id}
                options={cameraOptions(workspace, form.view_set)}
                placeholder="No camera"
                disabled={building}
                describedBy="atlas-camera-facts"
                onChange={(value) => edit({ camera_id: value })}
              />
              <Facts id="atlas-camera-facts" facts={camera ? cameraFacts(camera) : null} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="atlas-board">Board</Label>
              <div className="flex flex-wrap items-center gap-2">
                <Choice
                  id="atlas-board"
                  value={form.board}
                  options={boardOptions(workspace)}
                  placeholder={workspace.rig.error ? "No rig" : "No board"}
                  shown={board?.id}
                  disabled={building}
                  describedBy="atlas-board-facts"
                  onChange={(value) => edit({ board: value })}
                  className="flex-1 basis-48"
                />
                {board && <MeasureBoardDialog key={board.id} board={board} />}
              </div>
              <Facts id="atlas-board-facts" facts={board ? boardFacts(board) : workspace.rig.error} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="atlas-target">Target</Label>
              <Choice
                id="atlas-target"
                value={form.target_id}
                options={targets}
                placeholder={targets.length === 0 ? "No points" : "None"}
                disabled={building}
                onChange={(value) => edit({ target_id: value })}
              />
            </div>

            <TripleInputs
              name="Target extent"
              values={form.target_extent_mm}
              onChange={(values) => edit({ target_extent_mm: values })}
            />

            <div className="space-y-1.5">
              <div className="grid grid-cols-[minmax(0,1fr)_6rem] gap-2">
                <div className="min-w-0 space-y-1.5">
                  <Label htmlFor="atlas-asset-id">Asset id</Label>
                  <Input
                    id="atlas-asset-id"
                    value={form.asset_id}
                    onChange={(event) => edit({ asset_id: event.target.value })}
                    aria-describedby="atlas-asset-facts"
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
                <div className="min-w-0 space-y-1.5">
                  <Label htmlFor="atlas-version">Version</Label>
                  <Input
                    id="atlas-version"
                    value={form.version}
                    onChange={(event) => edit({ version: event.target.value })}
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
              </div>
              <Facts
                id="atlas-asset-facts"
                facts={
                  existing
                    ? [
                        `Replaces ${existing.asset_id}${existing.version ? ` v${existing.version}` : ""}`,
                        `built ${localTime(existing.built_at)}`,
                      ]
                    : null
                }
              />
            </div>

            <Collapsible open={advanced} onOpenChange={setAdvanced}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <CollapsibleTrigger asChild>
                  <Button type="button" variant="ghost" size="sm" className="-ml-2.5">
                    <ChevronRight className={cn("transition-transform", advanced && "rotate-90")} />
                    Advanced
                  </Button>
                </CollapsibleTrigger>
                <span className="text-xs text-muted-foreground tabular-nums">
                  <FactList facts={advancedFacts(form)} />
                </span>
              </div>
              <CollapsibleContent className="space-y-4 pt-3">
                <div className="grid grid-cols-2 gap-3">
                  <NumberField
                    id="atlas-click-sigma"
                    label="Click σ (px)"
                    value={form.click_sigma_px}
                    onChange={(value) => edit({ click_sigma_px: value })}
                  />
                  <NumberField
                    id="atlas-centre-sigma"
                    label="Target centre σ (mm)"
                    value={form.target_centre_sigma_mm}
                    onChange={(value) => edit({ target_centre_sigma_mm: value })}
                  />
                  <NumberField
                    id="atlas-samples"
                    label="Samples"
                    value={form.samples}
                    onChange={(value) => edit({ samples: value })}
                    integer
                  />
                  <NumberField
                    id="atlas-seed"
                    label="Seed"
                    value={form.seed}
                    onChange={(value) => edit({ seed: value })}
                    integer
                  />
                </div>
                <TripleInputs
                  name="Measured target"
                  values={form.target_measured_mm}
                  onChange={(values) => edit({ target_measured_mm: values })}
                />
              </CollapsibleContent>
            </Collapsible>
          </fieldset>

          <div className="space-y-2">
            <Button type="submit" disabled={!request || building} aria-describedby="atlas-missing">
              {job.status === "building" ? (
                <>
                  <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                  Building… <Elapsed since={job.startedAt} />
                </>
              ) : (
                <>
                  <Hammer /> Build atlas
                </>
              )}
            </Button>
            <ul id="atlas-missing" aria-label="Missing" className="space-y-0.5 text-sm text-muted-foreground empty:hidden">
              {!building && missing.map((item) => <li key={`${item.field}:${item.text}`}>{item.text}</li>)}
            </ul>
            <p role="status" className="text-sm empty:hidden">
              {jobStatus(job)}
            </p>
            <p role="alert" className="text-sm text-destructive wrap-anywhere empty:hidden">
              {failure}
            </p>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
