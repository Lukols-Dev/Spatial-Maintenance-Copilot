"use client";

import { FolderInput, LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
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
import { Progress } from "@/components/ui/progress";
import { errorMessage } from "@/lib/api";
import { nameProblem, readNumber } from "@/lib/atlas/rules";
import { ACCEPT, DEFAULT_WINDOW, describeFiles, nameFromFile, uploadPhase, type UploadPhase } from "@/lib/atlas/upload";
import { importViews, type ViewSetSummary, type Workspace } from "@/lib/workspace";

type Phase = { kind: "idle" } | UploadPhase | { kind: "failed"; message: string };

/**
 * A new view set from one video or from images. The upload goes on when the
 * dialog is closed; its button then shows how far it is.
 */
export function ImportViewsDialog({
  workspace,
  onImported,
}: {
  workspace: Workspace;
  onImported: (set: ViewSetSummary) => void;
}) {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  // Null: the name follows the video's file name until one is typed.
  const [typedName, setTypedName] = useState<string | null>(null);
  const [frames, setFrames] = useState(String(DEFAULT_WINDOW));
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  // A new key empties the file input after an import.
  const [inputKey, setInputKey] = useState(0);

  const selection = describeFiles(files);
  const video = selection.kind === "video";
  const name = (typedName ?? (video ? nameFromFile(files[0].name) : "")).trim();
  const busy = phase.kind === "uploading" || phase.kind === "processing";

  // The description says when no file is chosen; what else stops the import is listed.
  const problems: string[] = [];
  if (selection.problem) problems.push(selection.problem);
  const nameIssue = nameProblem(name, "Name");
  if (nameIssue) problems.push(nameIssue);
  else if (workspace.view_sets.some((set) => set.name === name)) problems.push(`${name} already exists`);
  let frameWindow: number | undefined;
  if (video) {
    const read = readNumber(frames, "N frames", { integer: true, min: 1 });
    if ("problem" in read) problems.push(read.problem);
    else frameWindow = read.value;
  }
  const ready = selection.kind !== "none" && problems.length === 0;

  /** The service's answer was about what was sent: a change makes it stale. */
  function edited() {
    if (phase.kind === "failed") setPhase({ kind: "idle" });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // The dialog renders in a portal, but React still bubbles its submit to the Build form.
    event.stopPropagation();
    if (!ready || busy) return;
    setPhase(uploadPhase(0));
    try {
      const set = await importViews({ name, window: frameWindow, files }, (fraction) => setPhase(uploadPhase(fraction)));
      setFiles([]);
      setTypedName(null);
      setFrames(String(DEFAULT_WINDOW));
      setInputKey((key) => key + 1);
      setPhase({ kind: "idle" });
      setOpen(false);
      onImported(set);
    } catch (error) {
      setPhase({ kind: "failed", message: errorMessage(error) });
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          {busy ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <FolderInput />}
          {phase.kind === "uploading"
            ? `Uploading ${phase.percent} %`
            : phase.kind === "processing"
              ? "Processing…"
              : "Import views…"}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4">
          <DialogHeader>
            <DialogTitle>Import views</DialogTitle>
            <DialogDescription className="wrap-anywhere">{selection.summary}</DialogDescription>
          </DialogHeader>
          <fieldset disabled={busy} className="min-w-0 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="import-files">Video or photos</Label>
              <Input
                key={inputKey}
                id="import-files"
                type="file"
                multiple
                accept={ACCEPT}
                onChange={(event) => {
                  setFiles([...(event.target.files ?? [])]);
                  edited();
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="import-name">Name</Label>
              <Input
                id="import-name"
                value={typedName ?? name}
                onChange={(event) => {
                  setTypedName(event.target.value);
                  edited();
                }}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            {video && (
              <div className="space-y-1.5">
                <Label htmlFor="import-window">Keep the sharpest of every N frames</Label>
                <Input
                  id="import-window"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  step={1}
                  value={frames}
                  onChange={(event) => {
                    setFrames(event.target.value);
                    edited();
                  }}
                  className="w-24 tabular-nums"
                />
              </div>
            )}
          </fieldset>

          {busy && (
            <Progress
              value={phase.kind === "uploading" ? phase.percent : 100}
              aria-label="Upload"
              aria-valuetext={phase.kind === "uploading" ? `${phase.percent} %` : "Processing"}
            />
          )}
          <p role="status" className="flex items-center gap-1.5 text-sm text-muted-foreground tabular-nums empty:hidden">
            {phase.kind === "uploading" && `Uploading ${phase.percent} %`}
            {phase.kind === "processing" && (
              <>
                <LoaderCircle aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
                Processing…
              </>
            )}
          </p>
          {!busy && problems.length > 0 && (
            <ul aria-label="Missing" className="space-y-0.5 text-sm text-muted-foreground wrap-anywhere">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
          {/* Always rendered, so screen readers announce the text when it appears. */}
          <p role="alert" className="text-sm text-destructive wrap-anywhere empty:hidden">
            {phase.kind === "failed" ? phase.message : ""}
          </p>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Close
              </Button>
            </DialogClose>
            <Button type="submit" disabled={!ready || busy}>
              Import
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
