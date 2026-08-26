// Small pure helpers for working with citations and file paths.

import type { AgentEvent, AgentResult, Citation } from "./types";

/** Last path segment (POSIX or Windows separators). */
export function basename(path: string): string {
  const parts = path.split(/[/\\]/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : path;
}

/** Human label for a citation: "path:start-end", or "path:line" for one line. */
export function formatCitation(c: Citation): string {
  if (c.end_line <= c.start_line) {
    return `${c.path}:${c.start_line}`;
  }
  return `${c.path}:${c.start_line}-${c.end_line}`;
}

/** Just the line-range portion, e.g. "10-20" or "10". */
export function formatLineRange(start: number, end: number): string {
  return end <= start ? `${start}` : `${start}-${end}`;
}

/** Stable React key for a citation. */
export function citationKey(c: Citation, index: number): string {
  return `${index}:${c.path}:${c.start_line}-${c.end_line}`;
}

/** Whether a 1-based line falls within [start, end] inclusive. */
export function lineInRange(line: number, start: number, end: number): boolean {
  const lo = Math.min(start, end);
  const hi = Math.max(start, end);
  return line >= lo && line <= hi;
}

/** Remove duplicate citations (same path + range), preserving first-seen order. */
export function dedupeCitations(citations: Citation[]): Citation[] {
  const seen = new Set<string>();
  const out: Citation[] = [];
  for (const c of citations) {
    const key = `${c.path}:${c.start_line}-${c.end_line}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(c);
  }
  return out;
}

/**
 * Pull the final `AgentResult` out of an `answer` event. Returns null when the
 * event is not a well-formed answer payload.
 */
export function agentResultFromEvent(ev: AgentEvent): AgentResult | null {
  if (ev.type !== "answer" || !ev.data) return null;
  const data = ev.data;
  if (typeof data.answer !== "string") return null;
  return {
    answer: data.answer,
    citations: Array.isArray(data.citations) ? (data.citations as Citation[]) : [],
    task_type: typeof data.task_type === "string" ? data.task_type : "general",
    steps: typeof data.steps === "number" ? data.steps : 0,
    tool_calls: typeof data.tool_calls === "number" ? data.tool_calls : 0,
    files_read: Array.isArray(data.files_read) ? (data.files_read as string[]) : [],
    stop_reason: typeof data.stop_reason === "string" ? data.stop_reason : "answered",
    budget_exhausted: Boolean(data.budget_exhausted),
    snapshot_id: typeof data.snapshot_id === "string" ? data.snapshot_id : null,
    usage:
      data.usage && typeof data.usage === "object"
        ? (data.usage as Record<string, any>)
        : null,
  };
}
