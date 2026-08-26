"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  File as FileIcon,
  Folder,
  FolderOpen,
  RotateCw,
} from "lucide-react";
import type { FileEntry } from "@/lib/types";
import { ApiError, getTree } from "@/lib/api";
import { EmptyState, Spinner } from "./ui";

interface DirState {
  status: "loading" | "loaded" | "error";
  entries: FileEntry[];
  truncated: boolean;
  error?: string;
}

function sortEntries(entries: FileEntry[]): FileEntry[] {
  const weight = (t: FileEntry["type"]) => (t === "dir" ? 0 : 1);
  return [...entries].sort((a, b) => {
    const w = weight(a.type) - weight(b.type);
    if (w !== 0) return w;
    return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
  });
}

const ROOT = "";

export function FileTree({
  repoId,
  activeFilePath,
  onOpenFile,
}: {
  repoId: string;
  activeFilePath: string | null;
  onOpenFile: (path: string) => void;
}) {
  const [dirs, setDirs] = useState<Record<string, DirState>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const loadDir = useCallback(
    async (dirPath: string) => {
      setDirs((prev) => ({
        ...prev,
        [dirPath]: {
          status: "loading",
          entries: prev[dirPath]?.entries ?? [],
          truncated: prev[dirPath]?.truncated ?? false,
        },
      }));
      try {
        const listing = await getTree(repoId, dirPath);
        setDirs((prev) => ({
          ...prev,
          [dirPath]: {
            status: "loaded",
            entries: sortEntries(listing.entries),
            truncated: listing.truncated,
          },
        }));
      } catch (err) {
        setDirs((prev) => ({
          ...prev,
          [dirPath]: {
            status: "error",
            entries: [],
            truncated: false,
            error: err instanceof ApiError ? err.message : "Failed to load directory.",
          },
        }));
      }
    },
    [repoId],
  );

  // Reset and (re)load the root whenever the repository changes.
  useEffect(() => {
    setDirs({});
    setExpanded(new Set());
    void loadDir(ROOT);
  }, [repoId, loadDir]);

  const toggleDir = useCallback(
    (dirPath: string) => {
      const isOpen = expanded.has(dirPath);
      const next = new Set(expanded);
      if (isOpen) next.delete(dirPath);
      else next.add(dirPath);
      setExpanded(next);
      const state = dirs[dirPath];
      if (!isOpen && (!state || state.status === "error")) {
        void loadDir(dirPath);
      }
    },
    [expanded, dirs, loadDir],
  );

  function renderEntries(dirPath: string, depth: number) {
    const state = dirs[dirPath];
    if (!state) return null;

    if (state.status === "loading" && state.entries.length === 0) {
      return (
        <div
          className="flex items-center gap-2 py-1 text-xs text-zinc-500"
          style={{ paddingLeft: depth * 14 + 8 }}
        >
          <Spinner className="h-3 w-3" /> Loading…
        </div>
      );
    }

    if (state.status === "error") {
      return (
        <div
          className="flex items-center gap-2 py-1 text-xs text-red-400"
          style={{ paddingLeft: depth * 14 + 8 }}
        >
          <span className="truncate">{state.error}</span>
          <button
            type="button"
            onClick={() => void loadDir(dirPath)}
            className="inline-flex items-center gap-1 text-zinc-400 hover:text-zinc-200"
          >
            <RotateCw className="h-3 w-3" /> Retry
          </button>
        </div>
      );
    }

    if (state.entries.length === 0) {
      return (
        <div
          className="py-1 text-xs italic text-zinc-600"
          style={{ paddingLeft: depth * 14 + 8 }}
        >
          empty
        </div>
      );
    }

    return (
      <>
        {state.entries.map((entry) => (
          <Fragment key={entry.path}>
            <TreeRow
              entry={entry}
              depth={depth}
              isExpanded={expanded.has(entry.path)}
              isActive={entry.type !== "dir" && entry.path === activeFilePath}
              onToggle={() => toggleDir(entry.path)}
              onOpen={() => onOpenFile(entry.path)}
            />
            {entry.type === "dir" && expanded.has(entry.path)
              ? renderEntries(entry.path, depth + 1)
              : null}
          </Fragment>
        ))}
        {state.truncated ? (
          <div
            className="py-1 text-[11px] italic text-zinc-600"
            style={{ paddingLeft: depth * 14 + 22 }}
          >
            …more entries (truncated)
          </div>
        ) : null}
      </>
    );
  }

  const rootState = dirs[ROOT];
  if (rootState?.status === "error") {
    return (
      <EmptyState title="Could not load file tree">
        <span className="text-red-400">{rootState.error}</span>
      </EmptyState>
    );
  }

  return (
    <div className="py-1 font-mono text-[13px] leading-tight">
      {renderEntries(ROOT, 0)}
    </div>
  );
}

function TreeRow({
  entry,
  depth,
  isExpanded,
  isActive,
  onToggle,
  onOpen,
}: {
  entry: FileEntry;
  depth: number;
  isExpanded: boolean;
  isActive: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const isDir = entry.type === "dir";
  const clickable = isDir || entry.type === "file" || entry.type === "symlink";
  const paddingLeft = depth * 14 + 8;

  return (
    <button
      type="button"
      disabled={!clickable}
      onClick={isDir ? onToggle : onOpen}
      title={entry.path}
      style={{ paddingLeft }}
      className={`flex w-full items-center gap-1.5 rounded py-1 pr-2 text-left transition-colors ${
        isActive
          ? "bg-sky-950/70 text-sky-200"
          : "text-zinc-300 hover:bg-zinc-800/60"
      } ${clickable ? "" : "opacity-60"}`}
    >
      {isDir ? (
        <>
          {isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 text-zinc-500" aria-hidden />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 flex-shrink-0 text-zinc-500" aria-hidden />
          )}
          {isExpanded ? (
            <FolderOpen className="h-3.5 w-3.5 flex-shrink-0 text-sky-500" aria-hidden />
          ) : (
            <Folder className="h-3.5 w-3.5 flex-shrink-0 text-sky-600" aria-hidden />
          )}
        </>
      ) : (
        <>
          <span className="h-3.5 w-3.5 flex-shrink-0" />
          <FileIcon className="h-3.5 w-3.5 flex-shrink-0 text-zinc-500" aria-hidden />
        </>
      )}
      <span className="truncate">{entry.name}</span>
    </button>
  );
}
