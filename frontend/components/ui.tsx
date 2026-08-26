"use client";

import type { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

type BadgeTone = "neutral" | "green" | "amber" | "red" | "blue" | "violet";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-zinc-800 text-zinc-300 ring-zinc-700",
  green: "bg-emerald-950 text-emerald-300 ring-emerald-800",
  amber: "bg-amber-950 text-amber-300 ring-amber-800",
  red: "bg-red-950 text-red-300 ring-red-800",
  blue: "bg-sky-950 text-sky-300 ring-sky-800",
  violet: "bg-violet-950 text-violet-300 ring-violet-800",
};

export function Badge({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return <Loader2 className={`h-4 w-4 animate-spin ${className}`} aria-hidden />;
}

export function EmptyState({
  title,
  children,
  icon,
}: {
  title: string;
  children?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      {icon ? <div className="text-zinc-600">{icon}</div> : null}
      <p className="text-sm font-medium text-zinc-300">{title}</p>
      {children ? <div className="max-w-sm text-xs text-zinc-500">{children}</div> : null}
    </div>
  );
}

export function ErrorBanner({
  message,
  onDismiss,
  title = "Something went wrong",
}: {
  message: string;
  onDismiss?: () => void;
  title?: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-red-900 bg-red-950/60 px-3 py-2 text-sm text-red-200">
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 break-words text-red-300/90">{message}</p>
      </div>
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          className="flex-shrink-0 rounded px-1 text-xs text-red-400 hover:text-red-200"
        >
          Dismiss
        </button>
      ) : null}
    </div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="px-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
      {children}
    </h2>
  );
}
