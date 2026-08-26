"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Send, Square } from "lucide-react";
import type { AgentEvent, AgentResult, Citation } from "@/lib/types";
import { ApiError } from "@/lib/api";
import { streamAgentChat } from "@/lib/sse";
import { agentResultFromEvent } from "@/lib/citations";
import { ActivityTimeline } from "./ActivityTimeline";
import { CitationList } from "./CitationList";
import { Badge, ErrorBanner, SectionLabel } from "./ui";

const TIMEOUT_MS = 120_000;

export function ChatPanel({
  repoId,
  modelConfigured,
  onOpenCitation,
}: {
  repoId: string | null;
  modelConfigured: boolean;
  onOpenCitation: (c: Citation) => void;
}) {
  const [question, setQuestion] = useState("");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [result, setResult] = useState<AgentResult | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const [stopped, setStopped] = useState(false);

  const controllerRef = useRef<AbortController | null>(null);
  const timedOutRef = useRef(false);

  useEffect(() => {
    // Abort any in-flight stream if the component unmounts.
    return () => controllerRef.current?.abort();
  }, []);

  const canChat = Boolean(repoId) && modelConfigured;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || !repoId || !canChat || streaming) return;

    setEvents([]);
    setStreamingAnswer("");
    setResult(null);
    setError(null);
    setTimedOut(false);
    setStopped(false);
    setStreaming(true);

    const controller = new AbortController();
    controllerRef.current = controller;
    timedOutRef.current = false;
    const timeout = setTimeout(() => {
      timedOutRef.current = true;
      setTimedOut(true);
      controller.abort();
    }, TIMEOUT_MS);

    try {
      for await (const ev of streamAgentChat({ repoId, question: q, signal: controller.signal })) {
        setEvents((prev) => [...prev, ev]);
        if (ev.type === "token") {
          const piece =
            typeof ev.data?.token === "string" ? ev.data.token : ev.message ?? "";
          if (piece) setStreamingAnswer((prev) => prev + piece);
        } else if (ev.type === "answer") {
          const r = agentResultFromEvent(ev);
          if (r) setResult(r);
        } else if (ev.type === "error") {
          setError(ev.message ?? "The agent reported an error.");
        } else if (ev.type === "done") {
          break;
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        if (timedOutRef.current) {
          setTimedOut(true);
        } else {
          setStopped(true);
        }
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Unexpected error while streaming the answer.");
      }
    } finally {
      clearTimeout(timeout);
      setStreaming(false);
      controllerRef.current = null;
    }
  }

  function onStop() {
    controllerRef.current?.abort();
  }

  const showAnswer = !error && (result != null || (streaming && streamingAnswer !== ""));

  return (
    <div className="flex h-full flex-col">
      <form onSubmit={onSubmit} className="flex flex-shrink-0 flex-col gap-2 border-b border-zinc-800 p-3">
        <SectionLabel>Ask the agent</SectionLabel>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              void onSubmit(e as unknown as React.FormEvent);
            }
          }}
          rows={3}
          disabled={!canChat || streaming}
          placeholder={
            repoId
              ? "How does authentication work? Where is X used? Why might this return 401?"
              : "Register and select a repository first."
          }
          className="w-full resize-y rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-sky-600 focus:outline-none disabled:opacity-60"
        />
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-zinc-600">Ctrl/⌘ + Enter to send</span>
          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              className="inline-flex items-center gap-1.5 rounded-md border border-zinc-600 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-700"
            >
              <Square className="h-3.5 w-3.5" /> Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canChat || question.trim() === ""}
              className="inline-flex items-center gap-1.5 rounded-md bg-sky-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send className="h-3.5 w-3.5" /> Send
            </button>
          )}
        </div>
        {!modelConfigured ? (
          <p className="rounded-md border border-amber-900 bg-amber-950/40 px-2.5 py-2 text-[11px] text-amber-300">
            Chat is disabled: the backend has no model configured. Set{" "}
            <code className="font-mono text-amber-200">ANTHROPIC_API_KEY</code> in the backend
            environment and restart it.
          </p>
        ) : null}
      </form>

      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-3">
        {events.length === 0 && !streaming && !error && !result ? (
          <p className="text-xs text-zinc-600">
            The agent&apos;s investigation steps, answer, and file citations will appear here.
          </p>
        ) : null}

        {timedOut ? (
          <ErrorBanner
            title="Request timed out"
            message={`The agent did not finish within ${TIMEOUT_MS / 1000}s and was aborted.`}
          />
        ) : null}
        {stopped ? (
          <ErrorBanner title="Stopped" message="You stopped the investigation before it finished." />
        ) : null}
        {error ? <ErrorBanner title="Agent error" message={error} /> : null}

        {events.length > 0 || streaming ? (
          <div className="rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
            <SectionLabel>Activity</SectionLabel>
            <div className="mt-2">
              <ActivityTimeline events={events} streaming={streaming} />
            </div>
          </div>
        ) : null}

        {showAnswer ? (
          <div className="space-y-3">
            <SectionLabel>Answer</SectionLabel>
            <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-sm leading-relaxed text-zinc-200">
              <AnswerMarkdown text={result ? result.answer : streamingAnswer} />
              {streaming && !result ? <span className="ml-0.5 animate-pulse">▍</span> : null}
            </div>
            {result ? (
              <>
                <CitationList citations={result.citations} onOpen={onOpenCitation} />
                <RunStats result={result} />
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RunStats({ result }: { result: AgentResult }) {
  return (
    <div className="flex flex-col gap-1.5">
      <SectionLabel>Run stats</SectionLabel>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="blue">{result.task_type}</Badge>
        <Badge tone="neutral">{result.steps} steps</Badge>
        <Badge tone="neutral">{result.tool_calls} tool calls</Badge>
        <Badge tone="neutral">{result.files_read.length} files read</Badge>
        <Badge tone={result.stop_reason === "answered" ? "green" : "amber"}>
          {result.stop_reason}
        </Badge>
        {result.budget_exhausted ? <Badge tone="amber">budget exhausted</Badge> : null}
      </div>
      {result.files_read.length > 0 ? (
        <details className="text-[11px] text-zinc-500">
          <summary className="cursor-pointer select-none hover:text-zinc-300">
            Files read ({result.files_read.length})
          </summary>
          <ul className="mt-1 space-y-0.5 font-mono">
            {result.files_read.map((f) => (
              <li key={f} className="truncate" title={f}>
                {f}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

// ---- Minimal, dependency-free markdown rendering ----
// Preserves line breaks, renders fenced code blocks, inline `code`, simple
// headings, and bullet / numbered lists. Everything goes through React children
// (never dangerouslySetInnerHTML), so repo content cannot inject markup.

function renderInline(text: string, keyBase: string): ReactNode[] {
  const parts = text.split("`");
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <code
        key={`${keyBase}-c${i}`}
        className="rounded bg-zinc-800 px-1 py-0.5 font-mono text-[0.85em] text-sky-300"
      >
        {part}
      </code>
    ) : (
      <span key={`${keyBase}-t${i}`}>{part}</span>
    ),
  );
}

function TextBlock({ text, keyBase }: { text: string; keyBase: string }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => {
        const key = `${keyBase}-l${i}`;
        if (line.trim() === "") return <div key={key} className="h-2" />;

        const heading = /^(#{1,6})\s+(.*)$/.exec(line);
        if (heading) {
          return (
            <div key={key} className="mb-1 mt-2 font-semibold text-zinc-100">
              {renderInline(heading[2], key)}
            </div>
          );
        }
        const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
        if (bullet) {
          return (
            <div key={key} className="flex gap-2">
              <span className="select-none text-zinc-600">•</span>
              <span>{renderInline(bullet[1], key)}</span>
            </div>
          );
        }
        const numbered = /^\s*(\d+)\.\s+(.*)$/.exec(line);
        if (numbered) {
          return (
            <div key={key} className="flex gap-2">
              <span className="select-none text-zinc-600">{numbered[1]}.</span>
              <span>{renderInline(numbered[2], key)}</span>
            </div>
          );
        }
        return (
          <p key={key} className="whitespace-pre-wrap">
            {renderInline(line, key)}
          </p>
        );
      })}
    </>
  );
}

function AnswerMarkdown({ text }: { text: string }) {
  const segments = text.split("```");
  return (
    <div className="space-y-1">
      {segments.map((seg, idx) => {
        if (idx % 2 === 1) {
          const nl = seg.indexOf("\n");
          const body = nl === -1 ? seg : seg.slice(nl + 1);
          return (
            <pre
              key={`code-${idx}`}
              className="overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs text-zinc-200"
            >
              <code>{body.replace(/\n$/, "")}</code>
            </pre>
          );
        }
        return <TextBlock key={`text-${idx}`} text={seg} keyBase={`t${idx}`} />;
      })}
    </div>
  );
}
