"use client";

import { LoaderCircle, ScanSearch } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Elapsed } from "@/components/atlas/elapsed";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { errorMessage } from "@/lib/api";
import { count } from "@/lib/atlas/format";
import {
  answerText,
  checkMarkers,
  initialMarkers,
  landmarkMarkers,
  markerCounts,
  replacedText,
  type MarkersForm,
} from "@/lib/atlas/markers";
import { cn } from "@/lib/utils";
import { findMarkers, type AtlasDetail, type MarkersAnswer, type ViewSetSummary, type Workspace } from "@/lib/workspace";

/** The time a search starts, read in the submit handler, never while rendering. */
function now(): number {
  return Date.now();
}

function Result({ answer }: { answer: MarkersAnswer }) {
  return (
    <div className="space-y-2">
      <p role="status" className="text-sm font-medium tabular-nums">
        {answerText(answer)}
      </p>
      <ul aria-label="Images per marker" className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-sm tabular-nums sm:grid-cols-3">
        {markerCounts(answer).map(({ marker, text, missing }) => (
          <li key={marker} className={cn(missing && "text-muted-foreground")}>
            {marker}: {text}
          </li>
        ))}
      </ul>
      <p className="text-sm text-muted-foreground">
        {count(answer.clicks.point_count, "point")}, {answer.clicks.ready_points} in ≥ 2 images
      </p>
    </div>
  );
}

/**
 * The automatic way to a set's points: the rig's printed markers found in every
 * image and saved as the set's clicks. Markers on a part that opens are left out
 * of the images that show the target's tag, where that part stands open.
 */
export function FindMarkersDialog({
  workspace,
  set,
  details,
  form,
  onMarked,
}: {
  workspace: Workspace;
  set: ViewSetSummary;
  /** The atlases read so far: the one built from this set says which markers move. */
  details: readonly AtlasDetail[];
  /** The Build form's camera and target, which the dialog starts from. */
  form: { camera_id: string; target_id: string };
  onMarked: (request: { camera_id: string; target_id: string }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<MarkersForm>(() => initialMarkers(set, details, form));
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [answer, setAnswer] = useState<MarkersAnswer | null>(null);
  const [failure, setFailure] = useState("");

  const markers = landmarkMarkers(workspace.rig);
  const { request, problems } = checkMarkers(state, set, workspace.rig);
  const replaces = replacedText(set);
  const running = startedAt !== null;

  function edit(fields: Partial<MarkersForm>) {
    setState((current) => ({ ...current, ...fields }));
    setFailure("");
  }

  function toggle(marker: number, on: boolean) {
    const moving = on ? [...state.moving, marker] : state.moving.filter((id) => id !== marker);
    edit({ moving: [...new Set(moving)].sort((a, b) => a - b) });
  }

  function show(next: boolean) {
    if (running) return;
    if (next) {
      // Each opening starts from the set and the form as they are now.
      setState(initialMarkers(set, details, form));
      setAnswer(null);
      setFailure("");
    }
    setOpen(next);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // The dialog renders in a portal, but React still bubbles its submit to the Build form.
    event.stopPropagation();
    if (!request || running) return;
    setStartedAt(now());
    setFailure("");
    try {
      const found = await findMarkers(set.name, request);
      setAnswer(found);
      onMarked({ camera_id: request.camera_id, target_id: request.target_id ?? state.target_id });
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setStartedAt(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={show}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          <ScanSearch /> Find markers…
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4">
          <DialogHeader>
            <DialogTitle>Find markers in {set.name}</DialogTitle>
            <DialogDescription>
              {count(set.image_count, "image")}
              {workspace.rig.markers &&
                ` · landmarks ${workspace.rig.markers.landmark_ids.join("–")} · tag ${workspace.rig.markers.target_id}`}
            </DialogDescription>
          </DialogHeader>

          {answer ? (
            <Result answer={answer} />
          ) : (
            <fieldset disabled={running} className="grid min-w-0 gap-4">
              <div className="grid grid-cols-[minmax(0,1fr)_8rem] gap-3">
                <div className="min-w-0 space-y-1.5">
                  <Label htmlFor="markers-camera">Camera</Label>
                  <Select
                    value={state.camera_id}
                    onValueChange={(value) => value && edit({ camera_id: value })}
                    disabled={running || set.camera_ids.length === 0}
                  >
                    <SelectTrigger id="markers-camera" className="w-full min-w-0">
                      <SelectValue placeholder="No camera" />
                    </SelectTrigger>
                    <SelectContent position="popper">
                      {set.camera_ids.map((id) => (
                        <SelectItem key={id} value={id}>
                          {id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="min-w-0 space-y-1.5">
                  <Label htmlFor="markers-target">Target point</Label>
                  <Input
                    id="markers-target"
                    value={state.target_id}
                    onChange={(event) => edit({ target_id: event.target.value })}
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
              </div>

              {markers.length > 0 && (
                <fieldset className="min-w-0 space-y-2">
                  <legend className="text-sm font-medium">On a part that opens</legend>
                  <div className="grid grid-cols-4 gap-x-3 gap-y-2 sm:grid-cols-6">
                    {markers.map((marker) => (
                      <div key={marker} className="flex items-center gap-1.5">
                        <Checkbox
                          id={`markers-moving-${marker}`}
                          checked={state.moving.includes(marker)}
                          onCheckedChange={(checked) => toggle(marker, checked === true)}
                        />
                        <Label htmlFor={`markers-moving-${marker}`} className="tabular-nums">
                          {marker}
                        </Label>
                      </div>
                    ))}
                  </div>
                  <p className="text-sm text-muted-foreground">Left out of the images that show the tag</p>
                </fieldset>
              )}

              {replaces && <p className="text-sm text-destructive">{replaces}</p>}
              {problems.length > 0 && (
                <ul aria-label="Missing" className="space-y-0.5 text-sm text-muted-foreground wrap-anywhere">
                  {problems.map((problem) => (
                    <li key={problem}>{problem}</li>
                  ))}
                </ul>
              )}
            </fieldset>
          )}

          <p role="alert" className="text-sm text-destructive wrap-anywhere empty:hidden">
            {failure}
          </p>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={running}>
                Close
              </Button>
            </DialogClose>
            {!answer && (
              <Button type="submit" disabled={!request || running}>
                {running ? (
                  <>
                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    Finding… <Elapsed since={startedAt} />
                  </>
                ) : replaces ? (
                  "Replace points"
                ) : (
                  "Find markers"
                )}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
