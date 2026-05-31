"use client";

import type { ChartDataResponse, ChartSpec } from "@/types";

interface Props {
  spec: ChartSpec;
  data: ChartDataResponse;
}

function format(value: unknown, fmt?: string): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (fmt === "integer" || Number.isInteger(value)) {
      return value.toLocaleString();
    }
    // Big numbers → 2 decimals, small → up to 4
    if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(value);
}

export function KpiCard({ spec, data }: Props) {
  const d = data.data as { value?: unknown; format?: string };
  return (
    <div className="rounded-lg border bg-[var(--color-panel)] px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
        {spec.title ?? "KPI"}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{format(d.value, d.format)}</p>
      {typeof data.meta?.rows_after_filter === "number" && (
        <p className="mt-0.5 text-[10px] text-[var(--color-muted)]">
          {(data.meta.rows_after_filter as number).toLocaleString()} rows
        </p>
      )}
    </div>
  );
}
