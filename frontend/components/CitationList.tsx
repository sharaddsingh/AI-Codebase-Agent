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
    <div className="flex flex-col gap-1.5 animate-fade-in">
      <SectionLabel>Citations ({unique.length})</SectionLabel>
      <div className="flex flex-wrap gap-1.5">
        {unique.map((c, i) => (
          <button
            key={citationKey(c, i)}
            type="button"
            onClick={() => onOpen(c)}
            title={`${c.path}${c.snapshot_id ? ` @ ${c.snapshot_id}` : ""}`}
            style={{ animationDelay: `${i * 40}ms` }}
            className="inline-flex max-w-full animate-chip-in items-center gap-1.5 rounded-full border border-slate-line bg-slate-panel/80 px-2.5 py-1 font-mono text-[11px] text-zinc-300 transition-all duration-200 hover:-translate-y-0.5 hover:border-violet-brand/60 hover:bg-violet-brand/10 hover:text-violet-brand-soft hover:shadow-glow focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-brand focus-visible:ring-offset-1 focus-visible:ring-offset-slate-base"
          >
            <FileText className="h-3 w-3 flex-shrink-0 text-zinc-500" aria-hidden />
            <span className="truncate">
              {basename(c.path)}
              <span className="text-zinc-500">:{formatLineRange(c.start_line, c.end_line)}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}