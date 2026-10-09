import {
  ArrowBigDown,
  ArrowBigLeft,
  ArrowBigRight,
  ArrowBigUp,
  Check,
  Maximize2,
  Minimize2,
  Move,
  type LucideIcon,
  type LucideProps,
} from "lucide-react";

import type { Action } from "@/lib/locate/types";

/** The way the camera should go. Closer and back point out of and into the frame. */
const ICONS: Record<Action, LucideIcon> = {
  ACCEPT: Check,
  MOVE_LEFT: ArrowBigLeft,
  MOVE_RIGHT: ArrowBigRight,
  MOVE_UP: ArrowBigUp,
  MOVE_DOWN: ArrowBigDown,
  MOVE_CLOSER: Maximize2,
  MOVE_BACK: Minimize2,
};

/** The arrow of an action; one this page does not know yet gets a neutral four-way arrow. */
export function ActionIcon({ action, ...props }: { action: string } & LucideProps) {
  const Icon = ICONS[action as Action] ?? Move;
  return <Icon aria-hidden {...props} />;
}
