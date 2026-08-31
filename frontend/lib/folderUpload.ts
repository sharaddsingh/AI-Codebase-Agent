// Browser folder ingestion: turn whatever the browser gives us into a flat list
// of repo-root-relative paths, ready for `uploadRepository`.
//
// Three ingestion paths exist and they do NOT agree on what a path looks like:
//
//   * `showDirectoryPicker()` yields handles whose names are relative to the
//     picked folder — the folder's own name is not in the path.
//   * A drag-and-drop `webkitGetAsEntry()` gives the dropped folder itself, so a
//     naive walk prefixes every path with that folder's name.
//   * `<input webkitdirectory>` sets `webkitRelativePath`, which always starts
//     with the picked folder's name.
//
// Everything here normalizes to the first form — paths relative to the repo
// root — and returns the stripped folder name separately, so the same tree
// arrives at the backend regardless of how the user chose it.

export interface FlatFile {
  /** Repo-root-relative path, forward slashes, no leading folder name. */
  relativePath: string;
  file: File;
}

// ---- Frontend ignore filters ----------------------------------------------
//
// The backend (code_intelligence/ignore.py:DEFAULT_IGNORE_DIRS) silently drops
// noisy directories and lockfiles/minified bundles during ingestion. If we
// don't apply the same filter on the frontend, the per-folder file-count cap
// trips on real-world folders whose `node_modules` / `.git` / `dist` / etc.
// dwarf the actual source tree. Mirror that list here so the count the user
// sees matches what will actually be registered. Keep in sync with the backend.

export const FRONTEND_IGNORE_DIRS: ReadonlySet<string> = new Set([
  ".git", ".hg", ".svn",
  "node_modules", "bower_components",
  ".venv", "venv", "env", ".env.d", "virtualenv",
  "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
  "dist", "build", "out", "target", ".next", ".nuxt", ".svelte-kit",
  ".gradle", ".idea", ".vscode", ".cache", ".turbo", ".parcel-cache",
  "coverage", "htmlcov", ".terraform", "vendor", "Pods",
  ".DS_Store",
]);

// Mirrors `DEFAULT_IGNORE_FILE_GLOBS` — regex-based, matched against basename.
export const FRONTEND_IGNORE_FILE_PATTERNS: readonly RegExp[] = [
  /^.*.min.js$/i,
  /^.*.min.css$/i,
  /^.*.map$/i,
  /^package-lock.json$/i,
  /^yarn.lock$/i,
  /^pnpm-lock.yaml$/i,
  /^poetry.lock$/i,
  /^Cargo.lock$/i,
  /^.*.pyc$/i,
  /^.*.pyo$/i,
  /^.*.class$/i,
  /^.*.o$/i,
  /^.*.a$/i,
];

function isIgnoredDirName(name: string): boolean {
  return FRONTEND_IGNORE_DIRS.has(name);
}

function isIgnoredFileName(name: string): boolean {
  for (const re of FRONTEND_IGNORE_FILE_PATTERNS) {
    if (re.test(name)) return true;
  }
  return false;
}

export interface WalkSkipStats {
  /** Absolute count of directories that were skipped (whole subtrees). */
  dirs: number;
  /** Absolute count of individual files that were skipped. */
  files: number;
  /** A handful of ignored directory names for display. */
  sampleDirs: string[];
}

/**
 * Optional stats collector passed into the walkers. When supplied, the
 * walker increments `dirs` / `files` for every entry it skips and records up
 * to five example directory names so the UI can tell the user what got
 * filtered ("Skipped 12 451 entries across 4 directories: node_modules, .git, …").
 */
export function createSkipStats(): WalkSkipStats {
  return { dirs: 0, files: 0, sampleDirs: [] };
}

function recordSkippedDir(stats: WalkSkipStats | undefined, name: string): void {
  if (!stats) return;
  stats.dirs += 1;
  if (stats.sampleDirs.length < 5 && !stats.sampleDirs.includes(name)) {
    stats.sampleDirs.push(name);
  }
}

function recordSkippedFile(stats: WalkSkipStats | undefined): void {
  if (!stats) return;
  stats.files += 1;
}

// ---- File System Access API (showDirectoryPicker) --------------------------

export interface FileSystemDirectoryHandleLike {
  values: () => AsyncIterable<FileSystemHandleLike>;
  name: string;
}
export interface FileSystemFileHandleLike {
  getFile: () => Promise<File>;
  name: string;
}
export type FileSystemHandleLike =
  | (FileSystemDirectoryHandleLike & { kind: "directory" })
  | (FileSystemFileHandleLike & { kind: "file" });

/** Walk a picked directory handle. Call with `prefix: ""` on the picked root. */
export async function walkHandle(
  dir: FileSystemDirectoryHandleLike,
  prefix: string,
  out: FlatFile[],
  skipped?: WalkSkipStats,
): Promise<void> {
  for await (const entry of dir.values()) {
    if (entry.kind === "file") {
      if (isIgnoredFileName(entry.name)) {
        recordSkippedFile(skipped);
        continue;
      }
      const file = await entry.getFile();
      out.push({
        relativePath: prefix ? `${prefix}/${entry.name}` : entry.name,
        file,
      });
    } else {
      if (isIgnoredDirName(entry.name)) {
        recordSkippedDir(skipped, entry.name);
        continue;
      }
      await walkHandle(
        entry,
        prefix ? `${prefix}/${entry.name}` : entry.name,
        out,
        skipped,
      );
    }
  }
}

// ---- Drag-and-drop entries (webkitGetAsEntry) ------------------------------

export interface FileSystemEntryLike {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  fullPath: string;
}
export interface FileSystemFileEntryLike extends FileSystemEntryLike {
  file: (cb: (file: File) => void, err: (e: unknown) => void) => void;
}
export interface FileSystemDirectoryEntryLike extends FileSystemEntryLike {
  createReader: () => {
    readEntries: (
      cb: (entries: FileSystemEntryLike[]) => void,
      err: (e: unknown) => void,
    ) => void;
  };
}

/**
 * Read a directory entry to exhaustion.
 *
 * `readEntries` is *paginated*: Chrome hands back at most 100 entries per call
 * and signals the end with an empty array. Calling it once — the
 * obvious-looking implementation — silently drops every file past the first 100
 * in any directory, so a big folder uploads partially with no error anywhere.
 * The same reader must be re-read until it comes back empty.
 */
export async function readAllEntries(
  dir: FileSystemDirectoryEntryLike,
): Promise<FileSystemEntryLike[]> {
  const reader = dir.createReader();
  const all: FileSystemEntryLike[] = [];
  for (;;) {
    const batch: FileSystemEntryLike[] = await new Promise((resolve, reject) =>
      reader.readEntries(resolve, reject),
    );
    if (batch.length === 0) return all;
    all.push(...batch);
  }
}

/** Walk a dropped entry, putting its own name into the path. */
export async function walkEntry(
  entry: FileSystemEntryLike,
  prefix: string,
  out: FlatFile[],
  skipped?: WalkSkipStats,
): Promise<void> {
  if (entry.isFile) {
    if (isIgnoredFileName(entry.name)) {
      recordSkippedFile(skipped);
      return;
    }
    const f = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntryLike).file(resolve, reject),
    );
    out.push({
      relativePath: prefix ? `${prefix}/${entry.name}` : entry.name,
      file: f,
    });
    return;
  }
  if (entry.isDirectory) {
    if (isIgnoredDirName(entry.name)) {
      recordSkippedDir(skipped, entry.name);
      return;
    }
    await walkEntryChildren(
      entry as FileSystemDirectoryEntryLike,
      prefix ? `${prefix}/${entry.name}` : entry.name,
      out,
      skipped,
    );
  }
}

/**
 * Walk a directory's *contents* into `out`, without putting the directory's own
 * name into the paths. Dropping "my-project" should upload its contents as the
 * repo root — matching what `showDirectoryPicker` produces — with the folder
 * name carried separately as the display name.
 */
export async function walkEntryChildren(
  dir: FileSystemDirectoryEntryLike,
  prefix: string,
  out: FlatFile[],
  skipped?: WalkSkipStats,
): Promise<void> {
  for (const child of await readAllEntries(dir)) {
    await walkEntry(child, prefix, out, skipped);
  }
}

/**
 * Collect the entries from a drop synchronously.
 *
 * The `DataTransfer` is neutered as soon as the drop handler yields, so
 * `webkitGetAsEntry()` must be called for every item *before* the first
 * `await` — otherwise it returns null for all but the first item and a
 * multi-item drop silently loses most of itself.
 */
export function collectDropEntries(items: DataTransferItemList | null): FileSystemEntryLike[] {
  const entries: FileSystemEntryLike[] = [];
  for (let i = 0; i < (items?.length ?? 0); i++) {
    const entry = items![i].webkitGetAsEntry?.();
    if (entry) entries.push(entry as unknown as FileSystemEntryLike);
  }
  return entries;
}

/**
 * Walk a drop into repo-root-relative paths plus a display name.
 *
 * One dropped folder is the normal case: its *contents* become the repo root
 * and its name becomes the display name. A multi-item or mixed drop has no
 * single root, so each item keeps its own name in the path and the name is left
 * for the server to fill in from the directory it owns.
 */
export async function walkDropEntries(
  entries: FileSystemEntryLike[],
  skipped?: WalkSkipStats,
): Promise<{ files: FlatFile[]; name?: string }> {
  const files: FlatFile[] = [];
  if (entries.length === 1 && entries[0].isDirectory) {
    await walkEntryChildren(
      entries[0] as FileSystemDirectoryEntryLike,
      "",
      files,
      skipped,
    );
    return { files, name: entries[0].name };
  }
  for (const entry of entries) {
    await walkEntry(entry, "", files, skipped);
  }
  return { files, name: undefined };
}

// ---- <input webkitdirectory> / plain FileList ------------------------------

/**
 * Flatten a `FileList` (the `<input webkitdirectory>` fallback, or a drop that
 * exposed no entries) into repo-root-relative paths plus a display name.
 *
 * `webkitRelativePath` includes the picked folder's own name as its first
 * segment. Strip that shared segment so this agrees with the other two
 * ingestion paths, and hand it back as the name.
 */
export function flattenFileList(
  fileList: ArrayLike<File>,
  skipped?: WalkSkipStats,
): { files: FlatFile[]; name?: string } {
  const raw: { rel: string; file: File }[] = [];
  for (let i = 0; i < fileList.length; i++) {
    const f = fileList[i];
    const rel =
      (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
    raw.push({ rel: rel.replace(/\\/g, "/"), file: f });
  }
  const first = raw[0]?.rel ?? "";
  const root = first.includes("/") ? first.slice(0, first.indexOf("/")) : "";
  // Only strip when every path really does live under that one folder; a bare
  // multi-file selection has no root to remove.
  const strip = root !== "" && raw.every((r) => r.rel.startsWith(`${root}/`));

  const files: FlatFile[] = [];
  for (const r of raw) {
    const rel = strip ? r.rel.slice(root.length + 1) : r.rel;
    if (!rel) continue;
    // Reject anything under an ignored top-level directory component,
    // mirroring the backend's behavior so the count matches what the server
    // registers.
    const parts = rel.split("/");
    const dirPart = parts.length > 1 ? parts[0] : null;
    if (dirPart && isIgnoredDirName(dirPart)) {
      recordSkippedDir(skipped, dirPart);
      continue;
    }
    const basename = parts[parts.length - 1];
    if (isIgnoredFileName(basename)) {
      recordSkippedFile(skipped);
      continue;
    }
    files.push({ relativePath: rel, file: r.file });
  }

  return {
    files,
    name: strip ? root : undefined,
  };
}
