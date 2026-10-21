"use client";

import { Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { MOVING_ABOVE, STILL_BELOW } from "@/lib/guide/motion";
import { GUIDE_LAYERS, changeSettings, useGuideSettings } from "@/lib/guide/settings";
import { cn } from "@/lib/utils";

function Toggle({ id, label, checked, onChange }: { id: string; label: string; checked: boolean; onChange: (on: boolean) => void }) {
  return (
    <Label htmlFor={id} className="flex min-h-11 cursor-pointer items-center gap-3 font-normal">
      <Checkbox id={id} checked={checked} onCheckedChange={(value) => onChange(value === true)} />
      {label}
    </Label>
  );
}

/**
 * The Guide's settings behind a gear: the layers the overlay draws and the
 * voice. `overImage` styles the gear for the camera's picture, where it sits
 * on the full-screen view of a phone.
 */
export function GuideSettings({
  overImage = false,
  motion = null,
}: {
  overImage?: boolean;
  /** A live camera's change between frames, shown with the thresholds it is held against. */
  motion?: number | null;
}) {
  const settings = useGuideSettings();
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant={overImage ? "ghost" : "outline"}
          size={overImage ? "icon-lg" : "default"}
          aria-label="Settings"
          className={cn(
            overImage && "size-11 rounded-full bg-black/60 text-white hover:bg-black/75 hover:text-white [&_svg]:size-5",
          )}
        >
          <Settings aria-hidden />
          {!overImage && "Settings"}
        </Button>
      </SheetTrigger>
      <SheetContent side="bottom" className="pb-[max(env(safe-area-inset-bottom),1rem)]">
        <SheetHeader>
          <SheetTitle>Settings</SheetTitle>
          <SheetDescription>What is drawn over the camera picture</SheetDescription>
        </SheetHeader>
        <div className="grid gap-1 px-4 sm:grid-cols-2">
          {GUIDE_LAYERS.map(({ layer, name }) => (
            <Toggle
              key={layer}
              id={`guide-layer-${layer}`}
              label={name}
              checked={settings.layers[layer]}
              onChange={(on) => changeSettings({ layers: { [layer]: on } })}
            />
          ))}
          <Toggle
            id="guide-voice"
            label="Voice"
            checked={settings.voice}
            onChange={(on) => changeSettings({ voice: on })}
          />
        </div>
        {motion !== null && (
          <p data-part="camera-motion" className="px-4 text-sm text-muted-foreground tabular-nums">
            Camera motion {motion.toFixed(1)} · steady below {STILL_BELOW} · moving above {MOVING_ABOVE}
          </p>
        )}
      </SheetContent>
    </Sheet>
  );
}
