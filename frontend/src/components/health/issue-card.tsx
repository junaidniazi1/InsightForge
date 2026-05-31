"use client";

import { clsx } from "clsx";
import type { Issue } from "@/types";
import { SeverityBadge } from "./severity-badge";

interface Props {
  issue: Issue;
  selectedFix: string;
  accepted: boolean;
  onFixChange: (fix: string) => void;
  onAcceptChange: (accepted: boolean) => void;
}

// Human-readable label for a fix option key.
const FIX_LABELS: Record<string, string> = {
  impute_median: "Impute with median",
  impute_mean: "Impute with mean",
  impute_mode: "Impute with mode",
  fill_constant: "Fill with constant",
  forward_fill: "Forward-fill",
  drop_rows: "Drop affected rows",
  drop_column: "Drop column",
  drop_duplicates: "Drop duplicate rows",
  convert_to_numeric: "Convert to numeric",
  convert_to_datetime: "Convert to datetime",
  convert_to_boolean: "Convert to boolean",
  convert_to_text: "Convert to text",
  leave_as_is: "Leave as-is",
  keep: "Keep",
  cap: "Cap to bounds",
  winsorize: "Winsorize (5% / 95%)",
  remove: "Remove outliers",
  remove_rows: "Remove flagged rows",
  log_transform: "Log-transform",
  review: "Review manually",
};

export function IssueCard({
  issue,
  selectedFix,
  accepted,
  onFixChange,
  onAcceptChange,
}: Props) {
  return (
    <div
      className={clsx(
        "rounded-lg border bg-[var(--color-panel)] p-4 transition-colors",
        accepted && "border-[var(--color-accent)]/60 ring-1 ring-[var(--color-accent)]/30"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex items-center gap-2">
            <SeverityBadge severity={issue.severity} />
            <span className="text-xs font-mono text-[var(--color-muted)]">{issue.issue_type}</span>
            {issue.column && (
              <span className="text-xs text-[var(--color-muted)]">
                · column <span className="font-mono text-[var(--color-fg)]">{issue.column}</span>
              </span>
            )}
          </div>
          <p className="text-sm">{issue.description}</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="text-xs text-[var(--color-muted)]">Fix:</label>
        <select
          value={selectedFix}
          onChange={(e) => onFixChange(e.target.value)}
          className="rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm outline-none focus:border-[var(--color-accent)]"
        >
          {issue.fix_options.map((opt) => (
            <option key={opt} value={opt}>
              {FIX_LABELS[opt] ?? opt}
            </option>
          ))}
        </select>
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(e) => onAcceptChange(e.target.checked)}
            className="h-4 w-4 accent-[var(--color-accent)]"
          />
          <span className={accepted ? "text-[var(--color-accent)]" : "text-[var(--color-muted)]"}>
            {accepted ? "Accepted" : "Accept fix"}
          </span>
        </label>
      </div>
    </div>
  );
}
