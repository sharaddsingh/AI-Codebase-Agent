// SSE-over-POST. `EventSource` can only issue GET requests, so we POST with
// `fetch` and parse the `text/event-stream` body ourselves. The parser is split
// into small, pure pieces so it can be unit-tested without a network:
//
//   createSSEParser()  -> low-level frame parser (buffers partial lines)
//   iterateSSE(chunks) -> async generator of AgentEvents over a byte stream
//   streamAgentChat()  -> wires fetch() into iterateSSE() with an AbortSignal
//
// SSE framing rules handled here: frames are separated by a blank line; a line
// may end with LF, CR, or CRLF; `data:` fields accumulate (joined with "\n");
// lines beginning with ":" are comments and ignored.

import { API_BASE_URL, ApiError } from "./api";
import type { AgentEvent, AgentEventType } from "./types";

export interface SSEMessage {
  event: string | null;
  data: string;
}

const FRAME_SEPARATOR = /\r\n\r\n|\n\n|\r\r/;
const LINE_SEPARATOR = /\r\n|\n|\r/;

const KNOWN_EVENT_TYPES: ReadonlySet<string> = new Set<AgentEventType>([
  "status",
  "classified",
  "plan",
  "tool_call",
  "tool_result",
  "token",
  "answer",
  "error",
  "budget",
  "done",
]);

function parseBlock(block: string): SSEMessage | null {
  let event: string | null = null;
  const dataLines: string[] = [];
  let sawField = false;

  for (const rawLine of block.split(LINE_SEPARATOR)) {
    if (rawLine === "") continue;
    if (rawLine.startsWith(":")) continue; // comment

    const colon = rawLine.indexOf(":");
    let field: string;
    let value: string;
    if (colon === -1) {
      field = rawLine;
      value = "";
    } else {
      field = rawLine.slice(0, colon);
      value = rawLine.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
    }

    if (field === "event") {
      event = value;
      sawField = true;
    } else if (field === "data") {
      dataLines.push(value);
      sawField = true;
    }
    // `id`, `retry`, and unknown fields are intentionally ignored.
  }

  if (!sawField) return null;
  return { event, data: dataLines.join("\n") };
}

/**
 * Stateful, incremental SSE frame parser. Feed it decoded text chunks (which
 * may split lines or frames anywhere) via `push`; it returns any complete
 * messages. Call `flush` at end-of-stream to drain a trailing frame that was
 * not terminated by a blank line.
 */
export function createSSEParser() {
  let buffer = "";
  return {
    push(chunk: string): SSEMessage[] {
      buffer += chunk;
      const out: SSEMessage[] = [];
      let match: RegExpExecArray | null;
      while ((match = FRAME_SEPARATOR.exec(buffer)) !== null) {
        const block = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        const msg = parseBlock(block);
        if (msg) out.push(msg);
      }
      return out;
    },
    flush(): SSEMessage[] {
      const rest = buffer;
      buffer = "";
      if (rest.trim() === "") return [];
      const msg = parseBlock(rest);
      return msg ? [msg] : [];
    },
  };
}

/** Convert a raw SSE message into a typed AgentEvent (or null to skip it). */
export function toAgentEvent(msg: SSEMessage): AgentEvent | null {
  if (msg.data === "") return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(msg.data);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;

  const obj = parsed as Record<string, unknown>;
  // Prefer the type embedded in the JSON payload; fall back to the SSE
  // `event:` field name.
  const rawType =
    typeof obj.type === "string" ? obj.type : msg.event ?? "";
  const type = (KNOWN_EVENT_TYPES.has(rawType) ? rawType : "status") as AgentEventType;

  return {
    type,
    message: typeof obj.message === "string" ? obj.message : null,
    data:
      obj.data && typeof obj.data === "object"
        ? (obj.data as Record<string, any>)
        : null,
    step: typeof obj.step === "number" ? obj.step : null,
  };
}

/**
 * Turn a byte-chunk stream into a stream of AgentEvents. Exposed separately so
 * tests can feed a hand-written byte stream without any network involved.
 */
export async function* iterateSSE(
  chunks: AsyncIterable<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const decoder = new TextDecoder();
  const parser = createSSEParser();

  for await (const chunk of chunks) {
    if (signal?.aborted) return;
    const text = decoder.decode(chunk, { stream: true });
    if (text) {
      for (const msg of parser.push(text)) {
        const ev = toAgentEvent(msg);
        if (ev) yield ev;
      }
    }
  }

  const tail = decoder.decode();
  if (tail) {
    for (const msg of parser.push(tail)) {
      const ev = toAgentEvent(msg);
      if (ev) yield ev;
    }
  }
  for (const msg of parser.flush()) {
    const ev = toAgentEvent(msg);
    if (ev) yield ev;
  }
}

/** Adapt a browser ReadableStream to an async iterable of byte chunks. */
async function* readStream(
  stream: ReadableStream<Uint8Array>,
): AsyncIterable<Uint8Array> {
  const reader = stream.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      if (value) yield value;
    }
  } finally {
    reader.releaseLock();
  }
}

export interface StreamAgentChatOptions {
  repoId: string;
  question: string;
  signal?: AbortSignal;
}

/**
 * POST to `/api/agent/chat` and yield the streamed AgentEvents. Throws an
 * `ApiError` for a non-2xx response (unwrapping the error envelope) or a failed
 * connection. Aborting `signal` cancels the in-flight request.
 */
export async function* streamAgentChat(
  opts: StreamAgentChatOptions,
): AsyncGenerator<AgentEvent> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/agent/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ repo_id: opts.repoId, question: opts.question }),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(
      `Could not reach the backend at ${API_BASE_URL}. Is it running?`,
      "network_error",
      0,
    );
  }

  if (!res.ok) {
    let message = res.statusText || `Request failed (${res.status})`;
    let code = "http_error";
    try {
      const body: unknown = await res.json();
      if (
        body &&
        typeof body === "object" &&
        "error" in body &&
        body.error &&
        typeof body.error === "object"
      ) {
        const envelope = (body as { error: { code?: string; message?: string } }).error;
        if (typeof envelope.message === "string") message = envelope.message;
        if (typeof envelope.code === "string") code = envelope.code;
      }
    } catch {
      // ignore
    }
    throw new ApiError(message, code, res.status);
  }

  if (!res.body) {
    throw new ApiError("The backend returned an empty response body.", "empty_body", res.status);
  }

  yield* iterateSSE(readStream(res.body), opts.signal);
}
