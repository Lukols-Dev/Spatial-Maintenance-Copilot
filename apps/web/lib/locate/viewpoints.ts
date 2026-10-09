import type { Atlas, AtlasDetail, AtlasSummary, ViewSet, ViewSetSummary, Workspace } from "@/lib/workspace";

// What the Locate page offers to choose from, and what it takes when nothing
// is chosen. A viewpoint is an image of a view set whose clicks mark landmarks
// of the atlas: the hand-picked correspondences the localisation runs on.

function timeOf(iso: string): number {
  const time = Date.parse(iso);
  return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time;
}

/** Newest first; an unreadable time goes last, and equal times keep their order. */
function newestFirst<T>(items: readonly T[], at: (item: T) => string): T[] {
  return items
    .map((item, index) => ({ item, index, time: timeOf(at(item)) }))
    .sort((a, b) => (b.time === a.time ? a.index - b.index : b.time - a.time))
    .map(({ item }) => item);
}

/** Every atlas, newest first. One that cannot be read is listed too, to say why it cannot be used. */
export function atlasOptions(workspace: Workspace): AtlasSummary[] {
  return newestFirst(workspace.atlases, (atlas) => atlas.built_at);
}

/** The wanted atlas when it can be read, else the newest one that can. */
export function pickAtlas(atlases: readonly AtlasSummary[], wanted: string | null): string | null {
  const readable = atlases.filter((atlas) => atlas.error === null);
  return (readable.find((atlas) => atlas.asset_id === wanted) ?? newestFirst(readable, (atlas) => atlas.built_at)[0])
    ?.asset_id ?? null;
}

function landmarkIds(atlas: Atlas): Set<string> {
  return new Set(atlas.landmarks.map((landmark) => landmark.id));
}

/** The set the atlas was built from, when its build report says so. */
export function buildSetOf(detail: AtlasDetail): string | null {
  return detail.report?.request.view_set ?? null;
}

/** View sets whose clicks mark a landmark of the atlas in at least one image, newest first. */
export function viewpointSets(workspace: Workspace, atlas: Atlas): ViewSetSummary[] {
  const ids = landmarkIds(atlas);
  const marking = workspace.view_sets.filter((set) => {
    const clicks = set.clicks;
    if (set.error !== null || clicks === null || clicks.error !== null) return false;
    return Object.entries(clicks.point_views).some(([id, views]) => ids.has(id) && views > 0);
  });
  return newestFirst(marking, (set) => set.updated_at);
}

/**
 * The wanted set when it is offered, else the newest set the atlas was not
 * built from (views it has not seen are the honest test), else its build set.
 */
export function pickViewSet(sets: readonly ViewSetSummary[], buildSet: string | null, wanted: string | null): string | null {
  const offered = sets.find((set) => set.name === wanted) ?? sets.find((set) => set.name !== buildSet) ?? sets[0];
  return offered?.name ?? null;
}

export interface Viewpoint {
  file: string;
  /** Atlas landmarks clicked in it. */
  landmarks: number;
  /** The target is clicked in it: a truth for itself, or for a shot from the same position. */
  truth: boolean;
  width: number | null;
  height: number | null;
}

/** The images of the set in which atlas landmarks are clicked, in the set's order. */
export function viewpointsOf(viewSet: ViewSet, atlas: Atlas): Viewpoint[] {
  const ids = landmarkIds(atlas);
  const views = viewSet.clicks?.views ?? {};
  return viewSet.images.flatMap((image) => {
    const clicked = Object.hasOwn(views, image.file) ? Object.keys(views[image.file]) : [];
    const landmarks = clicked.filter((id) => ids.has(id)).length;
    if (landmarks === 0) return [];
    return [
      {
        file: image.file,
        landmarks,
        truth: clicked.includes(atlas.target.id),
        width: image.width,
        height: image.height,
      },
    ];
  });
}

/** The images of the set in which the target is clicked, in the set's order. */
export function truthViews(viewSet: ViewSet, targetId: string): string[] {
  const views = viewSet.clicks?.views ?? {};
  return viewSet.images
    .map((image) => image.file)
    .filter((file) => Object.hasOwn(views, file) && Object.hasOwn(views[file], targetId));
}

/** The view's own target click when it has one; otherwise no truth until one is chosen. */
export function defaultTruthView(view: string, truths: readonly string[]): string | null {
  return truths.includes(view) ? view : null;
}
