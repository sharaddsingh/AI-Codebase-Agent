"use client";

import { Github, Sparkles } from "lucide-react";
import type { HealthResponse } from "@/lib/types";
import { Orb } from "./Orb";

interface HeaderProps {
  health: HealthResponse | null;
  healthError: string | null;
}

const GITHUB_REPO_URL = "https://github.com/example/ai-codebase-agent";
const GITHUB_STAR_MOCK = 1240; // Static placeholder; wire to the GitHub API later.

export function Header({ health, healthError }: HeaderProps) {
  const modelLabel = health
    ? `${health.model_provider}${health.model ? " · " + health.model : ""}`
    : null;
  const modelReady = !!health?.model_configured;

  return (
    <header className="relative z-10 flex flex-shrink-0 items-center gap-3 border-b border-slate-line/80 bg-slate-base/70 px-4 py-3 backdrop-blur-md">
      <div className="flex items-center gap-2.5">
        <Orb size={36} />
        <div className="flex min-w-0 flex-col">
          <h1 className="truncate text-[15px] font-semibold leading-none text-shimmer">
            AI Codebase Agent
          </h1>
          <p className="mt-1 hidden truncate text-[11px] leading-none text-zinc-500 sm:block">
            Read-only answers with file/line citations
          </p>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <a
          href={GITHUB_REPO_URL}
          target="_blank"
          rel="noreferrer noopener"
          className="group hidden items-center gap-1.5 rounded-btn border border-slate-line bg-slate-panel/60 px-2.5 py-1.5 text-xs text-zinc-300 transition-colors hover:border-violet-brand/50 hover:bg-slate-panel hover:text-zinc-100 sm:inline-flex"
          title="Star on GitHub"
        >
          <Github className="h-3.5 w-3.5 text-zinc-400 group-hover:text-violet-brand-soft" />
          <span className="font-medium tabular-nums">
            {GITHUB_STAR_MOCK.toLocaleString()}
          </span>
        </a>

        {modelLabel ? (
          <span
            className={
              "inline-flex items-center gap-1.5 rounded-btn border px-2.5 py-1.5 text-[11px] font-medium " +
              (modelReady
                ? "border-cyan-brand/30 bg-cyan-brand/10 text-cyan-brand-soft"
                : "border-amber-500/30 bg-amber-500/10 text-amber-300")
            }
            title={
              modelReady
                ? `Model ${modelLabel} ready`
                : `Model ${modelLabel} is not configured`
            }
          >
            <span
              className={
                "h-1.5 w-1.5 rounded-full " +
                (modelReady ? "bg-cyan-brand animate-pulse-soft" : "bg-amber-400")
              }
            />
            <Sparkles className="h-3 w-3" aria-hidden />
            <span className="font-mono uppercase tracking-wide">{modelLabel}</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-btn border border-slate-line bg-slate-panel/60 px-2.5 py-1.5 text-[11px] text-zinc-400">
            <span className="h-1.5 w-1.5 rounded-full bg-zinc-500 animate-pulse-soft" />
            {healthError ? "Backend offline" : "Checking model…"}
          </span>
        )}
      </div>
    </header>
  );
}