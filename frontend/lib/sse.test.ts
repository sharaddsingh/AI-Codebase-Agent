import { describe, expect, it } from "vitest";
import {
  createSSEParser,
  iterateSSE,
  toAgentEvent,
  type SSEMessage,
} from "./sse";
import type { AgentEvent } from "./types";

/** Wrap raw strings as a byte-chunk async iterable, like a real response body. */
async function* bytes(chunks: string[]): AsyncIterable<Uint8Array> {
  const encoder = new TextEncoder();
  for (const c of chunks) {
    yield encoder.encode(c);
  }
}

async function collect(gen: AsyncGenerator<AgentEvent>): Promise<AgentEvent[]> {
  const out: AgentEvent[] = [];
  for await (const ev of gen) out.push(ev);
  return out;
}

describe("createSSEParser", () => {
  it("buffers partial lines across chunks and splits multiple frames", () => {
    const parser = createSSEParser();
    const first = parser.push("event: status\ndata: {\"type\":\"sta");
    expect(first).toEqual([]); // frame not complete yet

    const second = parser.push('tus","message":"hi"}\n\nevent: done\ndata: {"type":"done"}\n\n');
    expect(second).toEqual<SSEMessage[]>([
      { event: "status", data: '{"type":"status","message":"hi"}' },
      { event: "done", data: '{"type":"done"}' },
    ]);
  });

  it("ignores comment lines and blank keep-alive frames", () => {
    const parser = createSSEParser();
    const msgs = parser.push(": keep-alive\n\nevent: token\ndata: {\"type\":\"token\"}\n\n");
    expect(msgs).toEqual<SSEMessage[]>([
      { event: "token", data: '{"type":"token"}' },
    ]);
  });

  it("drains a trailing frame with no terminating blank line via flush", () => {
    const parser = createSSEParser();
    expect(parser.push("event: answer\ndata: {\"type\":\"answer\"}")).toEqual([]);
    expect(parser.flush()).toEqual<SSEMessage[]>([
      { event: "answer", data: '{"type":"answer"}' },
    ]);
  });

  it("joins multiple data: fields with newlines", () => {
    const parser = createSSEParser();
    const msgs = parser.push("data: line1\ndata: line2\n\n");
    expect(msgs).toEqual<SSEMessage[]>([{ event: null, data: "line1\nline2" }]);
  });
});

describe("toAgentEvent", () => {
  it("falls back to the SSE event name when JSON lacks a type", () => {
    const ev = toAgentEvent({
      event: "budget",
      data: '{"message":"limit","data":{"reason":"max_steps"},"step":4}',
    });
    expect(ev).not.toBeNull();
    expect(ev?.type).toBe("budget");
    expect(ev?.step).toBe(4);
    expect(ev?.data).toEqual({ reason: "max_steps" });
  });

  it("returns null for empty or non-JSON data", () => {
    expect(toAgentEvent({ event: "status", data: "" })).toBeNull();
    expect(toAgentEvent({ event: "status", data: "not json" })).toBeNull();
  });
});

describe("iterateSSE", () => {
  it("parses a realistic CRLF stream split across chunk boundaries", async () => {
    const stream = bytes([
      ": keep-alive\r\n\r\n" +
        'event: status\r\ndata: {"type":"status","message":"Loading","data":null,"step":0}\r\n\r\n' +
        "event: classi",
      'fied\r\ndata: {"type":"classified","message":null,"data":{"task_type":"how_it_works","snapshot_id":"git:abc"},"step":1}\r\n\r\n' +
        'event: answer\r\ndata: {"type":"an',
      'swer","message":null,"data":{"answer":"Hello `world`","citations":[{"path":"a.py","start_line":1,"end_line":3,"snapshot_id":null}],"task_type":"how_it_works","steps":2,"tool_calls":1,"files_read":["a.py"],"stop_reason":"answered","budget_exhausted":false,"snapshot_id":"git:abc","usage":null},"step":2}\r\n\r\n' +
        'event: done\r\ndata: {"type":"done","message":null,"data":{"stop_reason":"answered"},"step":null}\r\n\r\n',
    ]);

    const events = await collect(iterateSSE(stream));
    expect(events.map((e) => e.type)).toEqual([
      "status",
      "classified",
      "answer",
      "done",
    ]);

    const classified = events[1];
    expect(classified.data).toEqual({ task_type: "how_it_works", snapshot_id: "git:abc" });

    const answer = events[2];
    expect(answer.data?.answer).toBe("Hello `world`");
    expect(answer.data?.citations).toHaveLength(1);
    expect(answer.data?.citations[0]).toEqual({
      path: "a.py",
      start_line: 1,
      end_line: 3,
      snapshot_id: null,
    });
    expect(answer.step).toBe(2);
  });

  it("stops early when the signal is already aborted", async () => {
    const controller = new AbortController();
    controller.abort();
    const stream = bytes(['event: status\ndata: {"type":"status"}\n\n']);
    const events = await collect(iterateSSE(stream, controller.signal));
    expect(events).toEqual([]);
  });
});
