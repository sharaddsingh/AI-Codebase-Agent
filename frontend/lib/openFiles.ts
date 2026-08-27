// Open-files ("editor tabs") state — a small, pure, framework-free reducer.
//
// This models the VS Code-like OPEN FILES strip that sits above the code viewer.
// It is deliberately kept out of React and off the network so the tab behavior
// (open, activate, close, evict) can be unit-tested as plain data transforms.
//
// IMPORTANT: an "open file" is a UI-only concept. Closing a tab removes an entry
// from this in-memory list; it never touches the repository and never issues a
// write/delete request (the API client has no such endpoint). Repository files
// and open tabs are distinct: a repo may hold hundreds of files while only a
// handful are open here.

/** A 1-based, inclusive line range to highlight/scroll to (e.g. from a citation). */
export interface HighlightRange {
  start: number;
  end: number;
}

export interface OpenFile {
  /** Repo-relative path; the unique key for a tab. */
  readonly path: string;
  /** Last line range applied to this file (from a citation), or null. */
  readonly highlight: HighlightRange | null;
}

export interface OpenFilesState {
  /** Tabs in stable left-to-right display order (new tabs append to the end). */
  readonly files: readonly OpenFile[];
  /** Path of the active tab, or null when nothing is open. */
  readonly activePath: string | null;
  /**
   * Recency list, most-recently-active first. Used to pick a neighbor when the
   * active tab is closed and to choose an eviction victim at the cap. This is
   * internal bookkeeping — the UI renders `files`, not this.
   */
  readonly mru: readonly string[];
}

/**
 * Most tabs kept open at once. Opening beyond this evicts the least-recently-used
 * *inactive* tab (never the active one) before adding the new one.
 */
export const MAX_OPEN_FILES = 8;

export const EMPTY_OPEN_FILES: OpenFilesState = {
  files: [],
  activePath: null,
  mru: [],
};

/** Move `path` to the front of the recency list (most-recently-used first). */
function touch(mru: readonly string[], path: string): string[] {
  return [path, ...mru.filter((p) => p !== path)];
}

/**
 * Open `path` and make it the active tab. Called for a file-tree click
 * (`highlight` = null, a plain open) and for a citation (`highlight` = the cited
 * line range, which the viewer scrolls to).
 *
 * - Already open: re-activate it and apply the given highlight — a citation
 *   re-navigates to its range; a plain tree open clears any prior highlight. The
 *   tab is never duplicated and its position in the strip does not move.
 * - Not open: append a new tab. If the cap is reached, first evict the
 *   least-recently-used tab that is neither active nor the file being opened.
 */
export function openFile(
  state: OpenFilesState,
  path: string,
  highlight: HighlightRange | null = null,
): OpenFilesState {
  const alreadyOpen = state.files.some((f) => f.path === path);
  if (alreadyOpen) {
    return {
      files: state.files.map((f) => (f.path === path ? { path, highlight } : f)),
      activePath: path,
      mru: touch(state.mru, path),
    };
  }

  let files = state.files;
  let mru = state.mru;
  if (files.length >= MAX_OPEN_FILES) {
    // Evict the least-recently-used tab (tail of `mru`) that is neither the
    // active tab nor the incoming one. With MAX_OPEN_FILES >= 2 a victim always
    // exists, so the active tab is never auto-closed.
    const victim = [...mru]
      .reverse()
      .find((p) => p !== state.activePath && p !== path);
    if (victim !== undefined) {
      files = files.filter((f) => f.path !== victim);
      mru = mru.filter((p) => p !== victim);
    }
  }

  return {
    files: [...files, { path, highlight }],
    activePath: path,
    mru: [path, ...mru],
  };
}

/**
 * Close (remove from the open list) a single tab.
 *
 * This is a pure UI-state transform: it does NOT delete the file from the
 * repository and issues no network request. Closing the active tab focuses the
 * most-recently-used remaining tab, or clears the selection (null) when none
 * remain. Closing a background tab leaves the active tab unchanged. Closing a
 * tab that isn't open is a no-op (returns the same state reference).
 */
export function closeFile(state: OpenFilesState, path: string): OpenFilesState {
  if (!state.files.some((f) => f.path === path)) return state;

  const files = state.files.filter((f) => f.path !== path);
  const mru = state.mru.filter((p) => p !== path);
  const activePath =
    state.activePath === path ? (mru.length > 0 ? mru[0] : null) : state.activePath;

  return { files, activePath, mru };
}

/**
 * Make an already-open tab the active one. No-op (same reference) if the path is
 * not open or is already active. The tab strip order is left unchanged.
 */
export function setActive(state: OpenFilesState, path: string): OpenFilesState {
  if (state.activePath === path) return state;
  if (!state.files.some((f) => f.path === path)) return state;
  return { ...state, activePath: path, mru: touch(state.mru, path) };
}

/** The active tab's entry, or null when nothing is open. */
export function activeFile(state: OpenFilesState): OpenFile | null {
  return state.files.find((f) => f.path === state.activePath) ?? null;
}
