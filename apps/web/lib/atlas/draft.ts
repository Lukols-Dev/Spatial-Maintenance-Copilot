import type { FormDraft } from "./form";

// The Atlas page outlives a visit to another page of the app: the Annotate
// link unmounts it, and what was typed in the Build form and the atlas the
// Result card showed are still there on the way back. A reload starts afresh
// from the workspace.

let kept: FormDraft = {};
let keptAtlasId: string | null = null;

export function keptDraft(): FormDraft {
  return kept;
}

export function keepDraft(draft: FormDraft): void {
  kept = draft;
}

/** The atlas the reader chose in the Result card; null: the newest one. */
export function keptAtlas(): string | null {
  return keptAtlasId;
}

export function keepAtlas(id: string | null): void {
  keptAtlasId = id;
}
