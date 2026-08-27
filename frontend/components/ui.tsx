"use client";

import { forwardRef, useEffect, useRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
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

type ButtonVariant = "primary" | "subtle" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-1 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-50";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-sky-700 text-white hover:bg-sky-600",
  subtle: "border border-zinc-700 bg-zinc-900 text-zinc-200 hover:border-zinc-600 hover:bg-zinc-800",
  ghost: "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100",
  danger: "bg-red-700 text-white hover:bg-red-600",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "px-2 py-1 text-[11px]",
  md: "px-2.5 py-1.5 text-xs",
};

type ButtonProps = {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Show a spinner (in place of `icon`) and disable the button. */
  busy?: boolean;
  /** Optional leading icon, hidden while `busy`. */
  icon?: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>;

/** Shared button primitive: single sky accent, subtle/ghost/danger variants. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    children,
    variant = "primary",
    size = "md",
    busy = false,
    icon,
    className = "",
    type = "button",
    disabled,
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      // eslint-disable-next-line react/button-has-type
      type={type}
      disabled={disabled || busy}
      className={`${BUTTON_BASE} ${BUTTON_VARIANTS[variant]} ${BUTTON_SIZES[size]} ${className}`}
      {...props}
    >
      {busy ? <Spinner className="h-3.5 w-3.5" /> : icon}
      {children}
    </button>
  );
});

/**
 * Accessible confirmation modal. Renders nothing when `open` is false. While
 * open it traps focus, restores focus to the trigger on close, and treats Esc
 * (and a backdrop click) as cancel. Used for destructive confirmations such as
 * "Remove repository?" — the action itself lives in `onConfirm`.
 */
export function ConfirmDialog({
  open,
  title,
  message,
  detail,
  error,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "default",
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  /** De-emphasized reassurance line under the message. */
  detail?: ReactNode;
  /** Inline error shown when the confirmed action fails (dialog stays open). */
  error?: string | null;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  // Keep the latest onCancel without re-running the effect (and re-stealing
  // focus) every time the parent re-renders it (e.g. while `busy` toggles).
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    // Move focus into the dialog. Cancel is the safe default for a destructive
    // action, so Enter/Space won't accidentally confirm.
    cancelButtonRef.current?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancelRef.current();
        return;
      }
      if (e.key === "Tab") {
        const focusables = panelRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusables || focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  const isDanger = tone === "danger";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-[1px]"
        onClick={() => onCancelRef.current()}
        aria-hidden
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-desc"
        className="relative z-10 w-full max-w-sm rounded-lg border border-zinc-700 bg-zinc-900 p-4 shadow-2xl shadow-black/60"
      >
        <div className="flex items-start gap-2.5">
          {isDanger ? (
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" aria-hidden />
          ) : null}
          <div className="min-w-0 flex-1">
            <h2 id="confirm-dialog-title" className="text-sm font-semibold text-zinc-100">
              {title}
            </h2>
            <div id="confirm-dialog-desc" className="mt-1.5 space-y-1 text-xs text-zinc-400">
              <p>{message}</p>
              {detail ? <p className="text-zinc-500">{detail}</p> : null}
            </div>
          </div>
        </div>
        {error ? (
          <p
            role="alert"
            className="mt-3 rounded border border-red-900 bg-red-950/60 px-2 py-1 text-[11px] text-red-300"
          >
            {error}
          </p>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <Button ref={cancelButtonRef} variant="subtle" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant={isDanger ? "danger" : "primary"} onClick={onConfirm} busy={busy}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
