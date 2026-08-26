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

function summarize(ev: AgentEvent): { icon: ReactNode; title: string; detail: string | null; tone: string } {
  const data = ev.data ?? {};
  switch (ev.type) {
    case "classified":
      return {
        icon: <Tags className="h-3.5 w-3.5" />,
        title: "Classified task",
        detail: typeof data.task_type === "string" ? data.task_type : ev.message,
        tone: "text-sky-400",
      };
    case "plan":
      return {
        icon: <ListChecks className="h-3.5 w-3.5" />,
        title: "Planned strategy",
        detail: typeof data.strategy === "string" ? data.strategy : ev.message,
        tone: "text-violet-400",
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
        tone: "text-emerald-400",
      };
    }
    case "tool_result": {
      const ok = data.ok !== false;
      return {
        icon: ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />,
        title: ev.message ?? (ok ? "Tool succeeded" : "Tool failed"),
        detail: typeof data.error === "string" ? data.error : null,
        tone: ok ? "text-emerald-500" : "text-red-400",
      };
    }
    case "budget":
      return {
        icon: <Gauge className="h-3.5 w-3.5" />,
        title: "Budget limit",
        detail: typeof data.reason === "string" ? data.reason : ev.message,
        tone: "text-amber-400",
      };
    case "error":
      return {
        icon: <AlertTriangle className="h-3.5 w-3.5" />,
        title: "Error",
        detail: ev.message,
        tone: "text-red-400",
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
    <ol className="flex flex-col gap-1.5">
      {visible.map((ev, i) => {
        const { icon, title, detail, tone } = summarize(ev);
        return (
          <li key={i} className="flex items-start gap-2 text-xs">
            <span className={`mt-0.5 flex-shrink-0 ${tone}`}>{icon}</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-1.5">
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
            </div>
          </li>
        );
      })}
      {streaming ? (
        <li className="flex items-center gap-2 text-xs text-zinc-500">
          <Spinner className="h-3.5 w-3.5" />
          <span>Investigating…</span>
        </li>
      ) : null}
    </ol>
  );
}
