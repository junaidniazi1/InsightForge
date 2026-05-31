import { clsx } from "clsx";
import type { HTMLAttributes } from "react";

type Variant = "neutral" | "accent" | "info" | "success" | "warning" | "danger" | "low" | "medium" | "high";

const VARIANT: Record<Variant, string> = {
  neutral:
    "border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-muted)]",
  accent:
    "border border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-300",
  info:
    "border border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300",
  success:
    "border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300",
  warning:
    "border border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300",
  danger:
    "border border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300",
  // Severity shortcuts so issue cards can read straight off the API value.
  low: "border border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300",
  medium:
    "border border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300",
  high: "border border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300",
};

interface Props extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
  /** Visually quieter (smaller padding, all-caps tracking) — used in headers. */
  compact?: boolean;
}

export function Badge({ variant = "neutral", compact = false, className, ...rest }: Props) {
  return (
    <span
      {...rest}
      className={clsx(
        "inline-flex items-center rounded-full font-medium",
        compact
          ? "px-2 py-0.5 text-[10px] uppercase tracking-wide"
          : "px-2.5 py-0.5 text-xs",
        VARIANT[variant],
        className,
      )}
    />
  );
}
