"use client";

import { useState } from "react";
import { clsx } from "clsx";
import type { ChartSpec, ChartSuggestion, FilterClause } from "@/types";
import { ChartTile } from "./chart-tile";

interface Props {
  datasetId: string;
  versionId: string | null;
  suggestions: ChartSuggestion[];
  filters: FilterClause[];
  addedKeys: Set<string>;
  onAdd: (spec: ChartSpec) => void;
}

export function suggestionKey(s: ChartSuggestion | ChartSpec): string {
  // Used to detect duplicates in the pipeline. Stable across re-renders.
  return JSON.stringify({
    chart_type: s.chart_type,
    encoding: s.encoding,
    bins: (s as ChartSpec).bins,
    top_n: (s as ChartSpec).top_n,
  });
}

function toSpec(s: ChartSuggestion): ChartSpec {
  return {
    chart_type: s.chart_type,
    encoding: s.encoding,
    title: s.title,
    bins: s.bins ?? null,
    top_n: s.top_n ?? null,
    filters: [],
  };
}

export function SuggestionsGallery({
  datasetId,
  versionId,
  suggestions,
  filters,
  addedKeys,
  onAdd,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? suggestions : suggestions.slice(0, 6);

  if (suggestions.length === 0) {
    return (
      <p className="text-sm text-[var(--color-muted)]">
        No chart suggestions for this dataset — try uploading one with numeric or
        categorical columns.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {visible.map((s) => {
          const spec = toSpec(s);
          const added = addedKeys.has(suggestionKey(s));
          return (
            <div
              key={suggestionKey(s)}
              className={clsx(
                "flex flex-col rounded-lg border bg-[var(--color-panel)] transition-colors",
                added && "border-[var(--color-success)]/60 ring-1 ring-[var(--color-success)]/30"
              )}
            >
              <div className="space-y-1 border-b px-3 py-2">
                <p className="text-sm font-medium">{s.title}</p>
                <p className="text-[11px] text-[var(--color-muted)]">{s.rationale}</p>
                <p className="text-[10px] uppercase tracking-wide text-[var(--color-muted)]">
                  {s.chart_type} · {s.engine} · score {s.score.toFixed(2)}
                </p>
              </div>
              <div className="h-36">
                <ChartTile
                  datasetId={datasetId}
                  versionId={versionId}
                  spec={spec}
                  filters={filters}
                  compact
                  showHeader={false}
                  height={140}
                />
              </div>
              <div className="border-t px-3 py-2 text-right">
                <button
                  type="button"
                  onClick={() => onAdd(spec)}
                  disabled={added}
                  className={clsx(
                    "rounded px-2 py-1 text-xs font-medium",
                    added
                      ? "text-[var(--color-success)]"
                      : "bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-strong)]"
                  )}
                >
                  {added ? "✓ Added" : "Add to dashboard"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
      {suggestions.length > 6 && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]"
        >
          {expanded ? "Show fewer" : `Show ${suggestions.length - 6} more suggestion(s)`}
        </button>
      )}
    </div>
  );
}
