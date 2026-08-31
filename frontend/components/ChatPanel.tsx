"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Send, Square } from "lucide-react";
import type { AgentEvent, AgentResult, Citation } from "@/lib/types";
import { ApiError } from "@/lib/api";
import { streamAgentChat } from "@/lib/sse";
import { agentResultFromEvent } from "@/lib/citations";
import { ActivityTimeline } from "./ActivityTimeline";
import { CitationList } from "./CitationList";
import { Badge, Button, ErrorBanner, SectionLabel } from "./ui";

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
    <div className="flex h-full flex-col bg-slate-base">
      <form
        onSubmit={onSubmit}
        className="flex flex-shrink-0 flex-col gap-2 border-b border-slate-line p-3"
      >
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
              : "Pick a repository on the left to begin."
          }
          className="w-full resize-y rounded-btn border border-slate-line bg-slate-raised px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-violet-brand focus:outline-none focus:ring-1 focus:ring-violet-brand/40 disabled:opacity-60"
        />
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-zinc-600">Ctrl/⌘ + Enter to send</span>
          {streaming ? (
            <Button variant="subtle" onClick={onStop} icon={<Square className="h-3.5 w-3.5" />}>
              Stop
            </Button>
          ) : (
            <button
              type="submit"
              disabled={!canChat || question.trim() === ""}
              className="inline-flex items-center justify-center gap-1.5 rounded-btn bg-gradient-to-r from-violet-brand to-cyan-brand px-3 py-1.5 text-xs font-semibold text-white shadow-glow transition-all duration-200 hover:brightness-110 hover:shadow-elevated disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            >
              <Send className="h-3.5 w-3.5" aria-hidden />
              Send
            </button>
          )}
        </div>
      </form>

      <div className="min-h-0 flex-1 overflow-auto p-3">
        {timedOut ? (
          <div className="mb-3 rounded-btn border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
            The agent was stopped after the {Math.round(TIMEOUT_MS / 1000)}s timeout.
          </div>
        ) : null}
        {stopped ? (
          <div className="mb-3 rounded-btn border border-slate-line bg-slate-panel/60 px-3 py-2 text-[11px] text-zinc-400">
            Stopped by user.
          </div>
        ) : null}
        {error ? (
          <div className="mb-3">
            <ErrorBanner title="Agent error" message={error} />
          </div>
        ) : null}

        <ActivityTimeline events={events} streaming={streaming} />

        {showAnswer ? (
          <div className="mt-4 flex flex-col gap-3">
            <SectionLabel>Answer</SectionLabel>
            <div className="rounded-card border border-slate-line bg-slate-panel/40 p-4 text-sm leading-relaxed text-zinc-200 animate-fade-in">
              <AnswerMarkdown text={result ? result.answer : streamingAnswer} />
              {streaming && !result ? <span className="ml-0.5 animate-pulse">▍</span> : null}
            </div>
            {result ? (
              <>
                {result.budget_exhausted ? (
                  <p className="rounded-btn border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
                    The agent stopped because its investigation budget was reached, so this
                    answer may be partial. Try narrowing the question or naming a specific file
                    or symbol.
                  </p>
                ) : null}
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
        className="rounded bg-slate-base px-1 py-0.5 font-mono text-[0.85em] text-cyan-brand-soft"
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
              className="overflow-auto rounded-btn border border-slate-line bg-slate-base p-3 font-mono text-xs text-zinc-200"
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