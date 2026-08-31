"use client";

import type { ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Gauge,
  ListChecks,
  Search,
  Tags,
  Terminal,
  XCircle,
} from "lucide-react";
import type { AgentEvent, AgentEventType } from "@/lib/types";
import { Spinner } from "./ui";

// Tokens are aggregated into the streaming answer elsewhere; the terminal
// answer/done frames are rendered separately. Everything else is timeline noise
// worth showing.
const HIDDEN: ReadonlySet<AgentEventType> = new Set(["token", "answer", "done"]);

function summarize(ev: AgentEvent): {
  icon: ReactNode;
  title: string;
  detail: string | null;
  tone: string;
  rail: string;
} {
  const data = ev.data ?? {};
  switch (ev.type) {
    case "classified":
      return {
        icon: <Tags className="h-3.5 w-3.5" />,
        title: "Classified task",
        detail: typeof data.task_type === "string" ? data.task_type : ev.message,
        tone: "text-cyan-brand-soft",
        rail: "bg-cyan-brand/40",
      };
    case "plan":
      return {
        icon: <ListChecks className="h-3.5 w-3.5" />,
        title: "Planned strategy",
        detail: typeof data.strategy === "string" ? data.strategy : ev.message,
        tone: "text-violet-brand-soft",
        rail: "bg-violet-brand/40",
      };
    case "tool_call": {
      const tool = typeof data.tool === "string" ? data.tool : "tool";
      let args = "";
      if (data.arguments && typeof data.arguments === "object") {
        try {
          args = JSON.stringify(data.arguments);
        } catch {
          args = "";
        }
      }
      return {
        icon: <Terminal className="h-3.5 w-3.5" />,
        title: `Called ${tool}`,
        detail: args || ev.message,
        tone: "text-emerald-300",
        rail: "bg-emerald-400/40",
      };
    }
    case "tool_result": {
      const ok = data.ok !== false;
      return {
        icon: ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />,
        title: ev.message ?? (ok ? "Tool succeeded" : "Tool failed"),
        detail: typeof data.error === "string" ? data.error : null,
        tone: ok ? "text-emerald-400" : "text-red-400",
        rail: ok ? "bg-emerald-400/40" : "bg-red-400/40",
      };
    }
    case "budget":
      return {
        icon: <Gauge className="h-3.5 w-3.5" />,
        title: "Budget limit",
        detail: typeof data.reason === "string" ? data.reason : ev.message,
        tone: "text-amber-300",
        rail: "bg-amber-400/40",
      };
    case "error":
      return {
        icon: <AlertTriangle className="h-3.5 w-3.5" />,
        title: "Error",
        detail: ev.message,
        tone: "text-red-400",
        rail: "bg-red-400/40",
      };
    case "status":
    default:
      return {
        icon:
          ev.message && /search|grep|find/i.test(ev.message) ? (
            <Search className="h-3.5 w-3.5" />
          ) : (
            <Activity className="h-3.5 w-3.5" />
          ),
        title: ev.message ?? "Working…",
        detail: null,
        tone: "text-zinc-400",
        rail: "bg-slate-line",
      };
  }
}

export function ActivityTimeline({
  events,
  streaming,
}: {
  events: AgentEvent[];
  streaming: boolean;
}) {
  const visible = events.filter((e) => !HIDDEN.has(e.type));

  if (visible.length === 0 && !streaming) return null;

  return (
    <ol className="relative ml-2 flex flex-col gap-2 border-l border-slate-line/80 pl-5">
      {visible.map((ev, i) => {
        const { icon, title, detail, tone, rail } = summarize(ev);
        return (
          <li
            key={i}
            style={{ animationDelay: `${Math.min(i * 60, 600)}ms` }}
            className="relative animate-rail-pop"
          >
            <span
              aria-hidden
              className={
                "absolute -left-[26px] top-1.5 flex h-4 w-4 items-center justify-center rounded-full border border-slate-base " +
                rail
              }
            >
              <span className="h-1.5 w-1.5 rounded-full bg-white/60" />
            </span>
            <div className="flex items-baseline gap-1.5 text-xs">
              <span className={"flex-shrink-0 " + tone}>{icon}</span>
              <span className="font-medium text-zinc-200">{title}</span>
              {ev.step != null ? (
                <span className="text-[10px] text-zinc-600">step {ev.step}</span>
              ) : null}
            </div>
            {detail ? (
              <p className="mt-0.5 break-words font-mono text-[11px] text-zinc-500">
                {detail.length > 240 ? `${detail.slice(0, 240)}…` : detail}
              </p>
            ) : null}
          </li>
        );
      })}
      {streaming ? (
        <li className="relative animate-rail-pop">
          <span
            aria-hidden
            className="absolute -left-[26px] top-1.5 flex h-4 w-4 items-center justify-center rounded-full border border-slate-base bg-violet-brand/40"
          >
            <Spinner className="h-3 w-3 text-white" />
          </span>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <span>Investigating…</span>
          </div>
        </li>
      ) : null}
    </ol>
  );
}