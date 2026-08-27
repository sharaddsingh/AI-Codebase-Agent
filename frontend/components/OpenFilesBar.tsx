"use client";

import { X } from "lucide-react";
import { basename } from "@/lib/citations";
import type { OpenFile } from "@/lib/openFiles";

// The VS Code-like OPEN FILES strip. Each tab shows the file's basename
// (truncated with a full-path tooltip); the active tab is visually distinct and
// the close (×) control is subtle until you hover/focus a tab. Clicking × closes
// the tab (removes it from the open list) — it never deletes the repository file.
// The strip scrolls horizontally when there are more or longer tabs than fit.

export function OpenFilesBar({
  files,
  activePath,
  onSelect,
  onClose,
}: {
  files: readonly OpenFile[];
  activePath: string | null;
  onSelect: (path: string) => void;
  onClose: (path: string) => void;
}) {
  if (files.length === 0) return null;

  return (
    <div
      role="tablist"
      aria-label="Open files"
      className="flex flex-shrink-0 items-stretch overflow-x-auto border-b border-zinc-800 bg-zinc-900/60"
    >
      {files.map((file) => {
        const isActive = file.path === activePath;
        const name = basename(file.path);
        return (
          <div
            key={file.path}
            className={`group relative flex min-w-0 flex-shrink-0 items-center border-r border-zinc-800 ${
              isActive
                ? "bg-zinc-950 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-800/50"
            }`}
          >
            {isActive ? (
              <span
                className="absolute inset-x-0 top-0 h-0.5 bg-sky-500"
                aria-hidden
              />
            ) : null}
            <button
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => onSelect(file.path)}
              title={file.path}
              className="flex min-w-0 items-center py-1.5 pl-3 pr-1 text-xs focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-sky-600"
            >
              <span className="max-w-[11rem] truncate font-mono">{name}</span>
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onClose(file.path);
              }}
              aria-label={`Close ${name}`}
              title={`Close ${name}`}
              className={`mr-1.5 flex-shrink-0 rounded p-0.5 text-zinc-500 transition hover:bg-zinc-700 hover:text-zinc-200 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-600 ${
                isActive
                  ? "opacity-100"
                  : "opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
              }`}
            >
              <X className="h-3 w-3" aria-hidden />
            </button>
          </div>
        );
      })}
    </div>
  );
}
