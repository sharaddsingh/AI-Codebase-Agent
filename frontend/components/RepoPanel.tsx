"use client";

/**
 * RepoPanel — the redesigned left-column panel.
 *
 * Replaces the old RepoSelector. Two big "+" tiles are the only call to
 * action: clicking Upload opens a full-height modal with drag-and-drop /
 * folder picker; clicking Add GitHub opens an inline URL form with live
 * validation. Registered repos are listed below as cards with a tiny
 * rotating-cube SVG (cyan for uploads, violet for GitHub repos) and a
 * 3D-tilt hover effect.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  CircleAlert,
  FolderUp,
  Github,
  Info,
  Loader2,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import type { HealthResponse, RepositoryInfo, RepositoryKind } from "@/lib/types";
import {
  ApiError,
  type UploadFileLike,
  type UploadProgress,
} from "@/lib/api";
import {
  collectDropEntries,
  createSkipStats,
  flattenFileList,
  walkDropEntries,
  walkHandle,
  type FileSystemDirectoryHandleLike,
  type FlatFile,
  type WalkSkipStats,
} from "@/lib/folderUpload";
import { Spinner } from "./ui";

type Mode = "closed" | "upload" | "github";

interface RepoPanelProps {
  repos: RepositoryInfo[];
  activeRepoId: string | null;
  health: HealthResponse | null;
  healthError: string | null;
  onSelectRepo: (id: string) => void;
  onUpload: (files: UploadFileLike[], name?: string) => Promise<void>;
  onRegisterGitHub: (url: string, name?: string) => Promise<void>;
  onRemove: (repo: RepositoryInfo) => void;
}

// ---- helpers ---------------------------------------------------------------

function RotatingCube({ kind }: { kind: RepositoryKind }) {
  const tint = kind === "github" ? "#7c5cff" : "#22d3ee";
  const tintSoft = kind === "github" ? "#9b87ff" : "#67e8f9";
  return (
    <svg
      viewBox="0 0 32 32"
      className="h-7 w-7 flex-shrink-0 animate-cube-spin"
      style={{ transformStyle: "preserve-3d" }}
      aria-hidden
    >
      <defs>
        <linearGradient id={`grad-${kind}-top`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={tintSoft} />
          <stop offset="100%" stopColor={tint} />
        </linearGradient>
        <linearGradient id={`grad-${kind}-left`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={tint} stopOpacity="0.7" />
          <stop offset="100%" stopColor={tint} stopOpacity="0.35" />
        </linearGradient>
        <linearGradient id={`grad-${kind}-right`} x1="1" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={tint} stopOpacity="0.9" />
          <stop offset="100%" stopColor={tint} stopOpacity="0.5" />
        </linearGradient>
      </defs>
      {/* Top face */}
      <polygon
        points="16,4 28,9 16,14 4,9"
        fill={`url(#grad-${kind}-top)`}
        stroke={tintSoft}
        strokeWidth="0.6"
      />
      {/* Left face */}
      <polygon
        points="4,9 16,14 16,28 4,23"
        fill={`url(#grad-${kind}-left)`}
        stroke={tint}
        strokeWidth="0.6"
      />
      {/* Right face */}
      <polygon
        points="28,9 16,14 16,28 28,23"
        fill={`url(#grad-${kind}-right)`}
        stroke={tint}
        strokeWidth="0.6"
      />
    </svg>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

// ---- GitHub URL live-validation -------------------------------------------

const GH_REGEX = /^(?:https?:\/\/)?(?:www\.)?github\.com\/([\w.-]+)\/([\w.-]+?)(?:\.git)?\/?(?:#.*)?$/i;
const SHORT_REGEX = /^([\w.-]+)\/([\w.-]+?)$/;

function parseGitHub(s: string): { owner: string; repo: string } | null {
  const m1 = GH_REGEX.exec(s.trim());
  if (m1) return { owner: m1[1], repo: m1[2] };
  const m2 = SHORT_REGEX.exec(s.trim());
  if (m2 && !m2[1].includes(".") && !m2[1].includes("/")) {
    return { owner: m2[1], repo: m2[2] };
  }
  return null;
}

// ---- Upload modal ---------------------------------------------------------

const MAX_FILES_HARD_CAP = 20000;

/**
 * Render the "Filtered out N entries" message shown under the drop zone after
 * the user picks a folder.  Kept inline so the skip stats and the strings
 * stay close together; the format is reused by every ingestion path.
 */
function formatSkipSummary(stats: WalkSkipStats): string | null {
  const total = stats.dirs + stats.files;
  if (total === 0) return null;
  const bits: string[] = [];
  if (stats.dirs > 0) {
    const list = stats.sampleDirs.join(", ");
    const more = stats.dirs > stats.sampleDirs.length ? ", …" : "";
    bits.push(`${stats.dirs} ignored ${stats.dirs === 1 ? "directory" : "directories"} (${list}${more})`);
  }
  if (stats.files > 0) {
    bits.push(`${stats.files} locked/minified ${stats.files === 1 ? "file" : "files"}`);
  }
  return `Filtered out ${total} ${total === 1 ? "entry" : "entries"}: ${bits.join(" · ")}.`;
}


function UploadModal({
  open,
  onClose,
  onUpload,
}: {
  open: boolean;
  onClose: () => void;
  onUpload: (files: UploadFileLike[], name?: string) => Promise<void>;
}) {
  const [pickerSupported] = useState(
    typeof window !== "undefined" && "showDirectoryPicker" in window,
  );
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dragCounter = useRef(0);

  const close = useCallback(() => {
    if (busy) return;
    onClose();
  }, [busy, onClose]);

  const handleError = useCallback((err: unknown) => {
    if (err instanceof ApiError) setError(err.message);
    else if (err instanceof Error) setError(err.message);
    else setError("Upload failed.");
  }, []);

  const upload = useCallback(
    async (files: FlatFile[], name?: string, skipSummary?: string | null) => {
      if (busy) return;
      if (!files.length) {
        setError("No files found in the selected folder.");
        return;
      }
      if (files.length > MAX_FILES_HARD_CAP) {
        setError(
          `Folder has too many files (${files.length}); limit is ${MAX_FILES_HARD_CAP}.`,
        );
        return;
      }
      setError(null);
      setInfo(skipSummary ?? null);
      setBusy(true);
      setProgress({
        totalBytes: files.reduce((s, f) => s + f.file.size, 0),
        sentBytes: 0,
        filesAdded: 0,
        filesTotal: files.length,
      });
      try {
        await onUpload(
          files.map((f) => ({ relativePath: f.relativePath, file: f.file })),
          name,
        );
        onClose();
      } catch (err) {
        handleError(err);
      } finally {
        setBusy(false);
        setProgress(null);
      }
    },
    [busy, onUpload, handleError, onClose],
  );

  const handlePick = useCallback(async () => {
    setError(null);
    setProgress(null);
    try {
      const w = window as unknown as {
        showDirectoryPicker: (
          opts?: { mode?: "read" | "readwrite" },
        ) => Promise<FileSystemDirectoryHandleLike>;
      };
      const handle = await w.showDirectoryPicker({ mode: "read" });
      const files: FlatFile[] = [];
      const skipped = createSkipStats();
      await walkHandle(handle, "", files, skipped);
      await upload(files, handle.name, formatSkipSummary(skipped));
    } catch (err) {
      if ((err as { name?: string })?.name === "AbortError") return;
      handleError(err);
    }
  }, [upload, handleError]);

  const handleFileInput = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files;
      if (!fileList || fileList.length === 0) return;
      const skipped = createSkipStats();
      const { files, name } = flattenFileList(fileList, skipped);
      await upload(files, name, formatSkipSummary(skipped));
    },
    [upload],
  );

  const handleDrop = useCallback(
    async (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      dragCounter.current = 0;
      if (busy) return;

      // Pull everything out of the DataTransfer synchronously — it is neutered
      // as soon as this handler yields.
      const entries = collectDropEntries(e.dataTransfer.items);
      const droppedFiles = e.dataTransfer.files;
      const skipped = createSkipStats();

      if (entries.length > 0) {
        const { files, name } = await walkDropEntries(entries, skipped);
        if (files.length > 0) {
          await upload(files, name, formatSkipSummary(skipped));
          return;
        }
      }

      if (droppedFiles && droppedFiles.length > 0) {
        const { files, name } = flattenFileList(droppedFiles, skipped);
        await upload(files, name, formatSkipSummary(skipped));
      }
    },
    [busy, upload],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="presentation"
    >
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-md"
        onClick={close}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-modal-title"
        className="relative z-10 flex h-full max-h-[640px] w-full max-w-xl flex-col overflow-hidden rounded-card border border-slate-line bg-slate-raised shadow-elevated"
      >
        <div className="flex items-center justify-between border-b border-slate-line px-5 py-3">
          <div className="flex items-center gap-2">
            <FolderUp className="h-4 w-4 text-violet-brand-soft" aria-hidden />
            <h2
              id="upload-modal-title"
              className="text-sm font-semibold text-zinc-100"
            >
              Upload a folder
            </h2>
          </div>
          <button
            type="button"
            onClick={close}
            disabled={busy}
            aria-label="Close upload dialog"
            className="rounded-btn p-1.5 text-zinc-400 transition-colors hover:bg-slate-line hover:text-zinc-100 disabled:opacity-50"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-3 p-5">
          <div
            onDragEnter={(e) => {
              e.preventDefault();
              dragCounter.current += 1;
              setDragging(true);
            }}
            onDragOver={(e) => e.preventDefault()}
            onDragLeave={() => {
              dragCounter.current -= 1;
              if (dragCounter.current <= 0) {
                dragCounter.current = 0;
                setDragging(false);
              }
            }}
            onDrop={handleDrop}
            className={
              "drop-3d relative flex flex-1 flex-col items-center justify-center gap-3 overflow-hidden rounded-card border-2 border-dashed px-6 py-8 text-center transition-all duration-200 " +
              (dragging
                ? "border-violet-brand bg-violet-brand/10"
                : "border-slate-line bg-slate-panel/40 hover:border-violet-brand/40")
            }
          >
            {busy ? (
              <div className="flex flex-col items-center gap-3 text-xs text-zinc-300">
                <Loader2 className="h-6 w-6 animate-spin text-violet-brand-soft" />
                <p className="font-mono">
                  Uploading {progress?.filesAdded ?? 0}/{progress?.filesTotal ?? 0}
                  {" "}
                  ({formatBytes(progress?.sentBytes ?? 0)} of {formatBytes(progress?.totalBytes ?? 0)})
                </p>
                {progress && progress.totalBytes > 0 ? (
                  <div className="h-1 w-3/4 overflow-hidden rounded-full bg-slate-line">
                    <div
                      className="h-full bg-gradient-to-r from-violet-brand to-cyan-brand transition-all duration-200"
                      style={{
                        width: `${Math.round(
                          (progress.sentBytes / progress.totalBytes) * 100,
                        )}%`,
                      }}
                    />
                  </div>
                ) : null}
              </div>
            ) : (
              <>
                <FolderUp
                  className="h-8 w-8 text-violet-brand-soft animate-pulse-soft"
                  aria-hidden
                />
                <p className="text-sm font-medium text-zinc-100">
                  Drop a folder here
                </p>
                <p className="text-xs text-zinc-500">
                  or use the picker below
                </p>
                {pickerSupported ? (
                  <button
                    type="button"
                    onClick={handlePick}
                    className="mt-1 rounded-btn bg-gradient-to-r from-violet-brand to-cyan-brand px-4 py-2 text-xs font-semibold text-white shadow-glow transition-all duration-200 hover:shadow-elevated hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-brand focus-visible:ring-offset-2 focus-visible:ring-offset-slate-raised"
                  >
                    Choose folder
                  </button>
                ) : null}
                {!pickerSupported ? (
                  <p className="text-[10px] text-zinc-500">
                    Fallback input below — pick the folder&apos;s contents.
                  </p>
                ) : null}
                {!pickerSupported ? (
                  <input
                    ref={inputRef}
                    type="file"
                    multiple
                    // @ts-expect-error non-standard but supported by Chromium/Firefox
                    webkitdirectory=""
                    directory=""
                    onChange={handleFileInput}
                    className="mt-1 block w-full max-w-xs text-[11px] text-zinc-400 file:mr-2 file:rounded-btn file:border-0 file:bg-slate-line file:px-2 file:py-1 file:text-xs file:text-zinc-100 hover:file:bg-violet-brand/40"
                  />
                ) : null}
              </>
            )}
          </div>

          {error ? (
            <div className="flex items-start gap-2 rounded-btn border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              <CircleAlert className="h-3.5 w-3.5 flex-shrink-0 text-red-400" aria-hidden />
              <span className="min-w-0 flex-1 break-words">{error}</span>
              <button
                type="button"
                onClick={() => setError(null)}
                aria-label="Dismiss error"
                className="flex-shrink-0 rounded p-0.5 text-red-400 hover:text-red-200"
              >
                <X className="h-3 w-3" aria-hidden />
              </button>
            </div>
          ) : null}
          {info && !error ? (
            <div className="flex items-start gap-2 rounded-btn border border-cyan-brand/40 bg-cyan-brand/10 px-3 py-2 text-xs text-cyan-brand-soft">
              <Info className="h-3.5 w-3.5 flex-shrink-0 text-cyan-brand" aria-hidden />
              <span className="min-w-0 flex-1 break-words">{info}</span>
              <button
                type="button"
                onClick={() => setInfo(null)}
                aria-label="Dismiss info"
                className="flex-shrink-0 rounded p-0.5 text-cyan-brand hover:text-cyan-brand-soft"
              >
                <X className="h-3 w-3" aria-hidden />
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ---- GitHub inline form ---------------------------------------------------

function GitHubForm({
  onSubmit,
  busy,
}: {
  onSubmit: (url: string) => Promise<void>;
  busy: boolean;
}) {
  const [value, setValue] = useState("");
  const parsed = useMemo(() => parseGitHub(value), [value]);
  const valid = parsed !== null;
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      if (!valid || busy) return;
      setError(null);
      try {
        const { owner, repo } = parsed!;
        const url = `https://github.com/${owner}/${repo}`;
        await onSubmit(url);
        setValue("");
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to register repository.");
      }
    },
    [valid, busy, parsed, onSubmit],
  );

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-2 rounded-card border border-slate-line bg-slate-panel/60 p-3 animate-fade-in"
    >
      <label className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
        GitHub URL or owner/repo
      </label>
      <div className="relative">
        <input
          autoFocus
          type="text"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError(null);
          }}
          placeholder="facebook/react"
          spellCheck={false}
          disabled={busy}
          className="w-full rounded-btn border border-slate-line bg-slate-base px-3 py-2 pr-9 font-mono text-xs text-zinc-100 placeholder:text-zinc-600 focus:border-violet-brand focus:outline-none focus:ring-1 focus:ring-violet-brand/40 disabled:opacity-60"
        />
        {value.length > 0 ? (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
            {valid ? (
              <CheckCircle2
                className="h-4 w-4 text-cyan-brand"
                aria-label="Valid GitHub identifier"
              />
            ) : (
              <CircleAlert
                className="h-4 w-4 text-amber-400"
                aria-label="Unrecognized format"
              />
            )}
          </span>
        ) : null}
      </div>
      {valid ? (
        <p className="font-mono text-[11px] text-cyan-brand-soft">
          github.com/{parsed!.owner}/{parsed!.repo}
        </p>
      ) : (
        <p className="text-[11px] text-zinc-500">
          Examples: <span className="font-mono">facebook/react</span> or{" "}
          <span className="font-mono">https://github.com/vercel/next.js</span>
        </p>
      )}
      {error ? (
        <p className="text-[11px] text-red-400">{error}</p>
      ) : null}
      <button
        type="submit"
        disabled={!valid || busy}
        className="mt-1 inline-flex items-center justify-center gap-1.5 rounded-btn bg-gradient-to-r from-violet-brand to-cyan-brand px-3 py-2 text-xs font-semibold text-white shadow-glow transition-all duration-200 hover:brightness-110 hover:shadow-elevated focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-brand focus-visible:ring-offset-2 focus-visible:ring-offset-slate-panel disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : (
          <Plus className="h-3.5 w-3.5" aria-hidden />
        )}
        Register
      </button>
    </form>
  );
}

// ---- Repo card with hover tilt --------------------------------------------

function RepoCard({
  repo,
  active,
  onSelect,
  onRemove,
}: {
  repo: RepositoryInfo;
  active: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const cardRef = useRef<HTMLDivElement | null>(null);

  // For a GitHub repo `root` is the URL, which is worth showing. For an upload
  // it is a server-side filesystem path — meaningless to the user and not ours
  // to display — so summarise the upload instead.
  const subtitle = useMemo(() => {
    if (repo.kind === "github") return repo.root;
    const n = repo.file_count_hint;
    return n == null
      ? "Uploaded folder"
      : `Uploaded folder · ${n} file${n === 1 ? "" : "s"}`;
  }, [repo.kind, repo.root, repo.file_count_hint]);

  const onMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const el = cardRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * 100;
    const py = ((e.clientY - rect.top) / rect.height) * 100;
    // Map to a -4deg..+4deg tilt; the highlight follows the cursor.
    const ry = ((px - 50) / 50) * 4;
    const rx = -((py - 50) / 50) * 4;
    el.style.setProperty("--tilt-x", `${ry}deg`);
    el.style.setProperty("--tilt-y", `${rx}deg`);
    el.style.setProperty("--shine-x", `${px}%`);
    el.style.setProperty("--shine-y", `${py}%`);
  }, []);

  const onMouseLeave = useCallback(() => {
    const el = cardRef.current;
    if (!el) return;
    el.style.setProperty("--tilt-x", `0deg`);
    el.style.setProperty("--tilt-y", `0deg`);
    el.style.setProperty("--shine-x", `50%`);
    el.style.setProperty("--shine-y", `50%`);
  }, []);

  return (
    // The card itself is a plain element, not a button. It holds two
    // independent controls — select and remove — and a <button> may not nest
    // inside a <button>: it is invalid HTML and React warns that it breaks
    // hydration. So the select target is the full-width button below, and
    // Remove is its sibling, overlaid on the right.
    <div
      ref={cardRef}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      className={
        "tilt-card group relative overflow-hidden rounded-card border bg-slate-panel/60 transition-colors duration-200 " +
        (active
          ? "border-violet-brand/60 shadow-glow"
          : "border-slate-line hover:border-violet-brand/40")
      }
      style={{ transformStyle: "preserve-3d" }}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        // pr-9 keeps a long name or subtitle from running under the Remove
        // button, which no longer takes up flex space of its own.
        className="flex w-full items-center gap-3 rounded-card px-3 py-2.5 pr-9 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet-brand/60"
      >
        <RotatingCube kind={repo.kind} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="truncate font-mono text-xs font-semibold text-zinc-100"
              title={repo.name}
            >
              {repo.name}
            </span>
            <span
              className={
                "rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide " +
                (repo.kind === "github"
                  ? "bg-violet-brand/20 text-violet-brand-soft"
                  : "bg-cyan-brand/20 text-cyan-brand-soft")
              }
            >
              {repo.kind}
            </span>
          </div>
          <p
            className="mt-0.5 truncate font-mono text-[10px] text-zinc-500"
            title={subtitle}
          >
            {subtitle}
          </p>
        </div>
      </button>
      <button
        type="button"
        onClick={onRemove}
        title="Remove repository"
        aria-label={`Remove ${repo.name}`}
        className="absolute right-2 top-1/2 z-10 -translate-y-1/2 rounded p-1 text-zinc-500 opacity-0 transition-opacity hover:bg-red-500/20 hover:text-red-300 focus-visible:opacity-100 focus-visible:outline-none group-hover:opacity-100"
      >
        <Trash2 className="h-3.5 w-3.5" aria-hidden />
      </button>
    </div>
  );
}

// ---- Health pill (compact) -------------------------------------------------

function HealthPill({
  health,
  healthError,
}: {
  health: HealthResponse | null;
  healthError: string | null;
}) {
  if (healthError) {
    return (
      <div className="flex items-center gap-2 rounded-btn border border-red-500/30 bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-300">
        <span className="h-1.5 w-1.5 rounded-full bg-red-400 animate-pulse-soft" />
        <span className="truncate">Backend offline</span>
      </div>
    );
  }
  if (!health) {
    return (
      <div className="flex items-center gap-2 rounded-btn border border-slate-line bg-slate-panel/60 px-2.5 py-1.5 text-[11px] text-zinc-400">
        <Spinner className="h-3 w-3" />
        Connecting…
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 rounded-btn border border-cyan-brand/30 bg-cyan-brand/10 px-2.5 py-1.5 text-[11px] text-cyan-brand-soft">
      <span className="h-1.5 w-1.5 rounded-full bg-cyan-brand animate-pulse-soft" />
      <span className="truncate font-medium">Backend online</span>
    </div>
  );
}

// ---- RepoPanel -------------------------------------------------------------

export function RepoPanel({
  repos,
  activeRepoId,
  health,
  healthError,
  onSelectRepo,
  onUpload,
  onRegisterGitHub,
  onRemove,
}: RepoPanelProps) {
  const [mode, setMode] = useState<Mode>("closed");
  const [busy, setBusy] = useState(false);

  const handleUpload = useCallback(
    async (files: UploadFileLike[], name?: string) => {
      setBusy(true);
      try {
        await onUpload(files, name);
      } finally {
        setBusy(false);
      }
    },
    [onUpload],
  );

  const handleGithub = useCallback(
    async (url: string) => {
      setBusy(true);
      try {
        await onRegisterGitHub(url);
        setMode("closed");
      } finally {
        setBusy(false);
      }
    },
    [onRegisterGitHub],
  );

  return (
    <div className="flex flex-col gap-3">
      <HealthPill health={health} healthError={healthError} />

      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => setMode(mode === "upload" ? "closed" : "upload")}
          className={
            "group flex flex-col items-start gap-1 rounded-card border bg-slate-panel/50 p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card " +
            (mode === "upload"
              ? "border-violet-brand shadow-glow"
              : "border-slate-line hover:border-cyan-brand/50")
          }
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-btn bg-gradient-to-br from-violet-brand/30 to-violet-brand/10 text-violet-brand-soft transition-transform duration-200 group-hover:scale-110">
            <Plus className="h-4 w-4" aria-hidden />
          </div>
          <p className="mt-1 text-[12px] font-semibold text-zinc-100">Upload</p>
          <p className="text-[10px] leading-tight text-zinc-500">
            Drag a folder from your computer
          </p>
        </button>
        <button
          type="button"
          onClick={() => setMode(mode === "github" ? "closed" : "github")}
          className={
            "group flex flex-col items-start gap-1 rounded-card border bg-slate-panel/50 p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card " +
            (mode === "github"
              ? "border-violet-brand shadow-glow"
              : "border-slate-line hover:border-violet-brand/50")
          }
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-btn bg-gradient-to-br from-cyan-brand/30 to-cyan-brand/10 text-cyan-brand-soft transition-transform duration-200 group-hover:scale-110">
            <Github className="h-4 w-4" aria-hidden />
          </div>
          <p className="mt-1 text-[12px] font-semibold text-zinc-100">GitHub</p>
          <p className="text-[10px] leading-tight text-zinc-500">
            Paste a public repo URL
          </p>
        </button>
      </div>

      {mode === "github" ? (
        <GitHubForm onSubmit={handleGithub} busy={busy} />
      ) : null}

      <div className="flex flex-col gap-1.5">
        <p className="px-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
          Repositories
          {repos.length > 0 ? (
            <span className="ml-1 text-zinc-600">({repos.length})</span>
          ) : null}
        </p>
        {repos.length === 0 ? (
          <p className="rounded-card border border-dashed border-slate-line bg-slate-panel/30 px-3 py-4 text-center text-[11px] text-zinc-500">
            No repositories yet. Pick one above to begin.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {repos.map((repo) => (
              <RepoCard
                key={repo.id}
                repo={repo}
                active={repo.id === activeRepoId}
                onSelect={() => onSelectRepo(repo.id)}
                onRemove={() => onRemove(repo)}
              />
            ))}
          </div>
        )}
      </div>

      <UploadModal
        open={mode === "upload"}
        onClose={() => setMode("closed")}
        onUpload={handleUpload}
      />
    </div>
  );
}
