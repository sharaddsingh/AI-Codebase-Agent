import { describe, expect, it } from "vitest";
import {
  agentResultFromEvent,
  basename,
  citationKey,
  dedupeCitations,
  formatCitation,
  formatLineRange,
  lineInRange,
} from "./citations";
import type { AgentEvent, Citation } from "./types";

const cite = (path: string, start: number, end: number): Citation => ({
  path,
  start_line: start,
  end_line: end,
  snapshot_id: null,
});

describe("basename", () => {
  it("returns the last segment for posix and windows paths", () => {
    expect(basename("src/lib/api.ts")).toBe("api.ts");
    expect(basename("a\\b\\c.py")).toBe("c.py");
    expect(basename("README.md")).toBe("README.md");
  });
});

describe("formatCitation / formatLineRange", () => {
  it("collapses single-line ranges", () => {
    expect(formatCitation(cite("a.ts", 5, 5))).toBe("a.ts:5");
    expect(formatLineRange(5, 5)).toBe("5");
  });

  it("shows start-end for multi-line ranges", () => {
    expect(formatCitation(cite("a.ts", 5, 12))).toBe("a.ts:5-12");
    expect(formatLineRange(5, 12)).toBe("5-12");
  });

  it("treats end < start as a single line", () => {
    expect(formatCitation(cite("a.ts", 9, 2))).toBe("a.ts:9");
  });
});

describe("lineInRange", () => {
  it("is inclusive and order-independent", () => {
    expect(lineInRange(5, 5, 10)).toBe(true);
    expect(lineInRange(10, 5, 10)).toBe(true);
    expect(lineInRange(11, 5, 10)).toBe(false);
    expect(lineInRange(7, 10, 5)).toBe(true);
  });
});

describe("citationKey", () => {
  it("is stable and unique per range", () => {
    expect(citationKey(cite("a.ts", 1, 2), 0)).toBe("0:a.ts:1-2");
    expect(citationKey(cite("a.ts", 1, 2), 1)).not.toBe(
      citationKey(cite("a.ts", 1, 2), 0),
    );
  });
});

describe("dedupeCitations", () => {
  it("removes exact duplicates but keeps distinct ranges, preserving order", () => {
    const input = [
      cite("a.ts", 1, 5),
      cite("a.ts", 1, 5),
      cite("b.ts", 2, 2),
      cite("a.ts", 6, 9),
    ];
    const out = dedupeCitations(input);
    expect(out).toHaveLength(3);
    expect(out.map(formatCitation)).toEqual(["a.ts:1-5", "b.ts:2", "a.ts:6-9"]);
  });
});

describe("agentResultFromEvent", () => {
  it("extracts a well-formed AgentResult from an answer event", () => {
    const ev: AgentEvent = {
      type: "answer",
      message: null,
      step: 3,
      data: {
        answer: "Because the router mounts it.",
        citations: [cite("backend/main.py", 90, 95)],
        task_type: "how_it_works",
        steps: 3,
        tool_calls: 2,
        files_read: ["backend/main.py"],
        stop_reason: "answered",
        budget_exhausted: false,
        snapshot_id: "git:abc",
        usage: { total_tokens: 42 },
      },
    };
    const result = agentResultFromEvent(ev);
    expect(result).not.toBeNull();
    expect(result?.answer).toBe("Because the router mounts it.");
    expect(result?.citations).toHaveLength(1);
    expect(result?.tool_calls).toBe(2);
    expect(result?.usage).toEqual({ total_tokens: 42 });
  });

  it("returns null for non-answer events or malformed payloads", () => {
    expect(
      agentResultFromEvent({ type: "status", message: "x", data: null, step: 0 }),
    ).toBeNull();
    expect(
      agentResultFromEvent({ type: "answer", message: null, data: {}, step: 0 }),
    ).toBeNull();
  });
});
