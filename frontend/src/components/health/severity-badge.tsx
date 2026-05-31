import { clsx } from "clsx";
import type { Severity } from "@/types";

const STYLES: Record<Severity, string> = {
  high: "bg-[var(--color-danger)]/15 text-[var(--color-danger)] border-[var(--color-danger)]/40",
  medium: "bg-amber-500/15 text-amber-400 border-amber-500/40",
  low: "bg-sky-500/15 text-sky-400 border-sky-500/40",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
        STYLES[severity]
      )}
    >
      {severity}
    </span>
  );
}
