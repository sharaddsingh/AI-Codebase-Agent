"use client";

import { useEffect, useRef, useState } from "react";
import { FileWarning, Sparkles } from "lucide-react";
import type { FileContent } from "@/lib/types";
import { ApiError, getFile } from "@/lib/api";
import { basename, lineInRange } from "@/lib/citations";
import type { HighlightRange } from "@/lib/openFiles";
import { Badge, EmptyState, ErrorBanner, Spinner } from "./ui";

export type { HighlightRange };

const CONTEXT_LINES = 60;

const HINT_STORAGE_KEY = "acba.viewerHintSeen";

/**
 * One-time onboarding hint under the empty-viewer copy.
 *
 * Shows on a user's first visit and fades out on their first interaction
 * (pointer or key), then never returns — the "seen" flag is persisted so a
 * reload doesn't bring it back. localStorage access is wrapped because it
 * throws in private-mode / storage-blocked browsers.
 */
function ViewerHint() {
  const [phase, setPhase] = useState<"hidden" | "shown" | "leaving">("hidden");

  useEffect(() => {
    let seen = false;
    try {
      seen = window.localStorage.getItem(HINT_STORAGE_KEY) === "1";
    } catch {
      // storage blocked — treat as unseen; the hint is cosmetic
    }
    if (seen) return;
    setPhase("shown");

    let timer: number | undefined;
    const dismiss = () => {
      try {
        window.localStorage.setItem(HINT_STORAGE_KEY, "1");
      } catch {
        // ignore
      }
      setPhase("leaving");
      timer = window.setTimeout(() => setPhase("hidden"), 350);
    };

    window.addEventListener("pointerdown", dismiss, { once: true });
    window.addEventListener("keydown", dismiss, { once: true });
    return () => {
      window.removeEventListener("pointerdown", dismiss);
      window.removeEventListener("keydown", dismiss);
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  if (phase === "hidden") return null;

  return (
    <span
      className={
        "mt-3 inline-flex items-center gap-1.5 rounded-full border border-violet-brand/30 bg-violet-brand/10 px-2.5 py-1 text-[11px] text-violet-brand-soft transition-opacity duration-350 ease-layout " +
        (phase === "leaving" ? "opacity-0" : "animate-chip-in opacity-100")
      }
    >
      <Sparkles className="h-3 w-3 flex-shrink-0" aria-hidden />
      Every answer cites file:line — citations jump straight to the source.
    </span>
  );
}

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
  const [beamKey, setBeamKey] = useState(0);
  const highlightRef = useRef<HTMLDivElement | null>(null);

  // Bump the beam key whenever the cited line range changes; the beam is
  // keyed by this so its CSS animation re-fires on every new citation click.
  // We depend on the *range* (start/end) rather than the `highlight` object
  // identity so the beam doesn't re-fire on unrelated parent re-renders.
  const hlStart = highlight?.start ?? null;
  const hlEnd = highlight?.end ?? null;
  useEffect(() => {
    if (hlStart != null && hlEnd != null) setBeamKey((k) => k + 1);
  }, [hlStart, hlEnd]);

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
        title="Pick a file in the tree"
        icon={<FileWarning className="h-8 w-8" />}
      >
        Or click a citation from an answer to open it here.
        <ViewerHint />
      </EmptyState>
    );
  }

  return (
    <div className="flex h-full flex-col bg-slate-base">
      <header className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-slate-line bg-slate-raised/70 px-4 py-2 backdrop-blur-sm">
        <span className="min-w-0 font-mono text-xs">
          <span className="text-zinc-500">
            {path.slice(0, path.length - basename(path).length)}
          </span>
          <span className="font-medium text-zinc-100">{basename(path)}</span>
        </span>
        {content ? (
          <span className="ml-auto flex items-center gap-1.5">
            <Badge tone="neutral" title="Lines shown">
              {content.start_line}-{content.end_line} of {content.total_lines}
            </Badge>
            {content.truncated ? <Badge tone="amber">truncated</Badge> : null}
            {content.encoding && content.encoding !== "utf-8" ? (
              <Badge tone="neutral">{content.encoding}</Badge>
            ) : null}
          </span>
        ) : null}
      </header>

      <div className="relative min-h-0 flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center gap-2 p-4 text-sm text-zinc-400">
            <Spinner /> Loading file…
          </div>
        ) : error ? (
          <div className="p-3">
            <ErrorBanner title="Cannot display file" message={error} />
          </div>
        ) : content ? (
          <CodeLines
            content={content}
            highlight={highlight}
            highlightRef={highlightRef}
            beamKey={beamKey}
          />
        ) : null}
      </div>

      {content?.truncated ? (
        <footer className="flex-shrink-0 border-t border-slate-line bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-300/90">
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
  beamKey,
}: {
  content: FileContent;
  highlight: HighlightRange | null;
  highlightRef: React.MutableRefObject<HTMLDivElement | null>;
  beamKey: number;
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
            className={
              "relative flex transition-colors " +
              (highlighted
                ? "bg-gradient-to-r from-violet-brand/15 via-violet-brand/10 to-transparent"
                : "")
            }
          >
            {isFirstHighlight && highlight ? (
              <span
                key={`beam-${beamKey}`}
                aria-hidden
                className="citation-beam pointer-events-none absolute inset-y-0 left-0 right-0 z-10 origin-left"
                style={{
                  background:
                    "linear-gradient(90deg, rgba(124,92,255,0.55), rgba(34,211,238,0.45) 60%, transparent)",
                  boxShadow: "0 0 24px -2px rgba(124,92,255,0.55)",
                }}
              />
            ) : null}
            <span
              className={
                "sticky left-0 z-20 select-none border-r px-3 text-right tabular-nums " +
                (highlighted
                  ? "border-violet-brand/40 bg-violet-brand/15 text-violet-brand-soft"
                  : "border-slate-line bg-slate-raised/70 text-zinc-600")
              }
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