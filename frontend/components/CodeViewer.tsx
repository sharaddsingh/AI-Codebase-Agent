"use client";

import { useEffect, useRef, useState } from "react";
import { FileWarning } from "lucide-react";
import type { FileContent } from "@/lib/types";
import { ApiError, getFile } from "@/lib/api";
import { basename, lineInRange } from "@/lib/citations";
import type { HighlightRange } from "@/lib/openFiles";
import { Badge, EmptyState, ErrorBanner, Spinner } from "./ui";

// Re-exported for backward compatibility; the type now lives in lib/openFiles
// (framework-free, so the tab reducer can share it and be unit-tested).
export type { HighlightRange };

const CONTEXT_LINES = 60;

export function CodeViewer({
  repoId,
  path,
  highlight,
}: {
  repoId: string | null;
  path: string | null;
  highlight: HighlightRange | null;
}) {
  const [content, setContent] = useState<FileContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const highlightRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!repoId || !path) {
      setContent(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const opts = highlight
      ? {
          startLine: Math.max(1, highlight.start - CONTEXT_LINES),
          endLine: highlight.end + CONTEXT_LINES,
          signal: controller.signal,
        }
      : { signal: controller.signal };

    getFile(repoId, path, opts)
      .then((fc) => {
        setContent(fc);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setContent(null);
        setError(err instanceof ApiError ? err.message : "Failed to load file.");
        setLoading(false);
      });

    return () => controller.abort();
  }, [repoId, path, highlight]);

  // Scroll the first highlighted line into view once content is rendered.
  useEffect(() => {
    if (content && highlight && highlightRef.current) {
      highlightRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [content, highlight]);

  if (!path) {
    return (
      <EmptyState
        title="No file open"
        icon={<FileWarning className="h-8 w-8" />}
      >
        Select a file in the tree, or click a citation from an answer to open it here.
      </EmptyState>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-zinc-800 bg-zinc-900/60 px-3 py-2">
        <span className="min-w-0 font-mono text-xs">
          <span className="text-zinc-500">{path.slice(0, path.length - basename(path).length)}</span>
          <span className="font-medium text-zinc-100">{basename(path)}</span>
        </span>
        {content ? (
          <span className="ml-auto flex items-center gap-1.5">
            <Badge tone="neutral" title="Lines shown">
              {content.start_line}–{content.end_line} of {content.total_lines}
            </Badge>
            {content.truncated ? <Badge tone="amber">truncated</Badge> : null}
            {content.encoding && content.encoding !== "utf-8" ? (
              <Badge tone="neutral">{content.encoding}</Badge>
            ) : null}
          </span>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center gap-2 p-4 text-sm text-zinc-400">
            <Spinner /> Loading file…
          </div>
        ) : error ? (
          <div className="p-3">
            <ErrorBanner title="Cannot display file" message={error} />
          </div>
        ) : content ? (
          <CodeLines content={content} highlight={highlight} highlightRef={highlightRef} />
        ) : null}
      </div>

      {content?.truncated ? (
        <footer className="flex-shrink-0 border-t border-zinc-800 bg-amber-950/30 px-3 py-1.5 text-[11px] text-amber-300/90">
          This view is truncated. Only part of the file was returned by the backend.
        </footer>
      ) : null}
    </div>
  );
}

function CodeLines({
  content,
  highlight,
  highlightRef,
}: {
  content: FileContent;
  highlight: HighlightRange | null;
  highlightRef: React.MutableRefObject<HTMLDivElement | null>;
}) {
  const lines = content.content.split("\n");
  // Drop a trailing empty element produced by a final newline.
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();

  let firstHighlightAssigned = false;

  return (
    <div className="min-w-full font-mono text-[13px] leading-5">
      {lines.map((line, i) => {
        const lineNumber = content.start_line + i;
        const highlighted =
          highlight != null && lineInRange(lineNumber, highlight.start, highlight.end);
        const isFirstHighlight = highlighted && !firstHighlightAssigned;
        if (isFirstHighlight) firstHighlightAssigned = true;

        return (
          <div
            key={lineNumber}
            ref={isFirstHighlight ? highlightRef : undefined}
            className={`flex ${highlighted ? "bg-amber-500/10" : ""}`}
          >
            <span
              className={`sticky left-0 select-none border-r px-3 text-right tabular-nums ${
                highlighted
                  ? "border-amber-500/40 bg-amber-500/10 text-amber-400"
                  : "border-zinc-800 bg-zinc-900/40 text-zinc-600"
              }`}
              style={{ minWidth: "3.5rem" }}
            >
              {lineNumber}
            </span>
            <code className="whitespace-pre px-3 text-zinc-200">{line || " "}</code>
          </div>
        );
      })}
    </div>
  );
}
