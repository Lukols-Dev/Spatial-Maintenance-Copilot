"use client";

import { LoaderCircle, Ruler } from "lucide-react";
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
import { errorMessage } from "@/lib/api";
import { caliper } from "@/lib/atlas/format";
import { checkMeasurement, initialReading, sideText, type SpanReading } from "@/lib/atlas/measure";
import { cn } from "@/lib/utils";
import { measureBoard, type Board } from "@/lib/workspace";

function NumberInput({
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
    <div className="flex flex-col justify-end gap-1.5">
      <Label htmlFor={id} className="leading-snug">
        {label}
      </Label>
      <Input
        id={id}
        type="number"
        inputMode={integer ? "numeric" : "decimal"}
        min={integer ? 1 : 0}
        step={integer ? 1 : "any"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="tabular-nums"
      />
    </div>
  );
}

/**
 * The caliper reading of a mounted board: a length across several squares,
 * shown as one square as it is typed, then written to the rig file.
 */
export function MeasureBoardDialog({ board }: { board: Board }) {
  const [open, setOpen] = useState(false);
  const [reading, setReading] = useState<SpanReading>(() => initialReading(board));
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState("");

  const { side, body, problems } = checkMeasurement(reading, board);

  function edit(fields: Partial<SpanReading>) {
    setReading((current) => ({ ...current, ...fields }));
    // The service's answer was about the reading as sent.
    setFailure("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // The dialog renders in a portal, but React still bubbles its submit to the Build form.
    event.stopPropagation();
    if (!body || saving) return;
    setSaving(true);
    setFailure("");
    try {
      const measured = await measureBoard(board.id, body);
      setReading(initialReading(measured));
      setOpen(false);
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!saving) setOpen(next);
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          <Ruler /> Measure…
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4">
          <DialogHeader>
            <DialogTitle>Measure {board.id}</DialogTitle>
            <DialogDescription>
              {board.squares_x}×{board.squares_y} squares · nominal {caliper(board.square_nominal_mm)} mm
            </DialogDescription>
          </DialogHeader>
          <fieldset disabled={saving} className="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-3">
            <NumberInput
              id="measure-length"
              label="Length (mm)"
              value={reading.length}
              onChange={(length) => edit({ length })}
            />
            <NumberInput
              id="measure-squares"
              label="N squares"
              value={reading.squares}
              onChange={(squares) => edit({ squares })}
              integer
            />
            <NumberInput
              id="measure-uncertainty"
              label="Length uncertainty (mm)"
              value={reading.uncertainty}
              onChange={(uncertainty) => edit({ uncertainty })}
            />
            <NumberInput
              id="measure-marker"
              label="Marker side (mm)"
              value={reading.marker}
              onChange={(marker) => edit({ marker })}
            />
            <div className="col-span-2 flex flex-col justify-end gap-1.5">
              <Label htmlFor="measure-substrate">Substrate</Label>
              <Input
                id="measure-substrate"
                value={reading.substrate}
                onChange={(event) => edit({ substrate: event.target.value })}
                autoComplete="off"
              />
            </div>
          </fieldset>

          <p
            role="status"
            className={cn("text-sm font-medium tabular-nums empty:hidden", side && !side.plausible && "text-destructive")}
          >
            {side ? sideText(side) : ""}
          </p>
          {problems.length > 0 && (
            <ul aria-label="Missing" className="space-y-0.5 text-sm text-muted-foreground wrap-anywhere">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
          <p role="alert" className="text-sm text-destructive wrap-anywhere empty:hidden">
            {failure}
          </p>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Close
              </Button>
            </DialogClose>
            <Button type="submit" disabled={!body || saving}>
              {saving && <LoaderCircle className="animate-spin motion-reduce:animate-none" />}
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
