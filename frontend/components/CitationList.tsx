"use client";

import { FileText } from "lucide-react";
import type { Citation } from "@/lib/types";
import { basename, citationKey, dedupeCitations, formatLineRange } from "@/lib/citations";
import { SectionLabel } from "./ui";

export function CitationList({
  citations,
  onOpen,
}: {
  citations: Citation[];
  onOpen: (citation: Citation) => void;
}) {
  const unique = dedupeCitations(citations);
  if (unique.length === 0) return null;

  return (
    <div className="flex flex-col gap-1.5">
      <SectionLabel>Citations ({unique.length})</SectionLabel>
      <div className="flex flex-wrap gap-1.5">
        {unique.map((c, i) => (
          <button
            key={citationKey(c, i)}
            type="button"
            onClick={() => onOpen(c)}
            title={`${c.path}${c.snapshot_id ? ` @ ${c.snapshot_id}` : ""}`}
            className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 transition-colors hover:border-sky-600 hover:bg-sky-950/40 hover:text-sky-200"
          >
            <FileText className="h-3.5 w-3.5 flex-shrink-0 text-zinc-500" aria-hidden />
            <span className="truncate font-mono">
              {basename(c.path)}
              <span className="text-zinc-500">:{formatLineRange(c.start_line, c.end_line)}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
