"use client";

import { useState } from "react";
import type { ColumnProfile, SemanticType } from "@/types";

interface Props {
  columns: ColumnProfile[];
}

// Each semantic type gets a colour-coded label. Two shades per type so the
// labels stay readable on the light slate-50 page background AND on the dark
// slate-950 one.
const SEMANTIC_COLOR: Record<SemanticType, string> = {
  numeric: "text-sky-600 dark:text-sky-300",
  categorical: "text-violet-600 dark:text-violet-300",
  datetime: "text-emerald-600 dark:text-emerald-300",
  boolean: "text-amber-600 dark:text-amber-300",
  text: "text-[var(--color-muted)]",
  id_like: "text-rose-600 dark:text-rose-300",
};

function fmt(n: number | null | undefined, digits = 3): string {
  if (n === null || n === undefined) return "—";
  if (Number.isInteger(n)) return n.toString();
  return n.toFixed(digits);
}

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function renderSample(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function ColumnRow({ col }: { col: ColumnProfile }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b last:border-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-[var(--color-border)]/20"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm">{col.name}</span>
            <span className={`text-xs font-medium ${SEMANTIC_COLOR[col.semantic_type]}`}>
              {col.semantic_type}
            </span>
            <span className="text-xs text-[var(--color-muted)]">({col.dtype})</span>
          </div>
          <p className="mt-0.5 text-xs text-[var(--color-muted)]">
            {col.null_count} nulls ({col.null_pct}%) · {col.unique_count} unique ({col.unique_pct}%)
            · {bytes(col.memory_bytes)}
          </p>
        </div>
        <span className="text-xs text-[var(--color-muted)]">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="grid gap-4 border-t bg-[var(--color-bg)]/40 px-4 py-3 md:grid-cols-2">
          {col.numeric_stats && (
            <div>
              <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">
                Numeric stats
              </h4>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <dt className="text-[var(--color-muted)]">min</dt>
                <dd className="font-mono">{fmt(col.numeric_stats.min)}</dd>
                <dt className="text-[var(--color-muted)]">max</dt>
                <dd className="font-mono">{fmt(col.numeric_stats.max)}</dd>
                <dt className="text-[var(--color-muted)]">mean</dt>
                <dd className="font-mono">{fmt(col.numeric_stats.mean)}</dd>
                <dt className="text-[var(--color-muted)]">median</dt>
                <dd className="font-mono">{fmt(col.numeric_stats.median)}</dd>
                <dt className="text-[var(--color-muted)]">std</dt>
                <dd className="font-mono">{fmt(col.numeric_stats.std)}</dd>
                <dt className="text-[var(--color-muted)]">Q1 / Q3</dt>
                <dd className="font-mono">
                  {fmt(col.numeric_stats.q1)} / {fmt(col.numeric_stats.q3)}
                </dd>
                <dt className="text-[var(--color-muted)]">skew</dt>
                <dd className="font-mono">{fmt(col.numeric_stats.skewness)}</dd>
                <dt className="text-[var(--color-muted)]">kurtosis</dt>
                <dd className="font-mono">{fmt(col.numeric_stats.kurtosis)}</dd>
              </dl>
            </div>
          )}
          {col.top_values && col.top_values.length > 0 && (
            <div>
              <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">
                Top values
              </h4>
              <ul className="space-y-1 text-xs">
                {col.top_values.map((tv, i) => (
                  <li key={i} className="flex items-center justify-between gap-3">
                    <span className="truncate font-mono">{renderSample(tv.value)}</span>
                    <span className="shrink-0 text-[var(--color-muted)]">
                      {tv.count} ({tv.pct}%)
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {col.sample_values.length > 0 && (
            <div className="md:col-span-2">
              <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">
                Sample values
              </h4>
              <p className="break-all font-mono text-xs text-[var(--color-muted)]">
                {col.sample_values.map(renderSample).join(", ")}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ColumnDetails({ columns }: Props) {
  return (
    <div className="rounded-lg border bg-[var(--color-panel)]">
      {columns.map((c) => (
        <ColumnRow key={c.name} col={c} />
      ))}
    </div>
  );
}
