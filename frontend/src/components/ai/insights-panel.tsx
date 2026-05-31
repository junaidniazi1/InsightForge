"use client";

import { useEffect, useState } from "react";
import { clsx } from "clsx";
import { apiGet } from "@/lib/api";
import type { AIInsightsResponse, FindingSeverity } from "@/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SkeletonLine } from "@/components/ui/skeleton";
import { AIError } from "./ai-error";

interface Props {
  datasetId: string;
  onAskSuggested?: (question: string) => void;
}

const SEVERITY_STYLE: Record<FindingSeverity, string> = {
  info: "border-sky-500/40 bg-sky-500/10 text-sky-200",
  notable: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  concern: "border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 text-[var(--color-danger)]",
};

export function InsightsPanel({ datasetId, onAskSuggested }: Props) {
  const [data, setData] = useState<AIInsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const r = await apiGet<AIInsightsResponse>(
        `/datasets/${datasetId}/ai/insights${refresh ? "?refresh=true" : ""}`
      );
      setData(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId]);

  return (
    <Card>
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium">Auto-insights</h2>
          <p className="text-xs text-[var(--color-muted)]">
            What stands out, ranked by severity.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => void load(true)}
          disabled={loading}
          className="text-xs"
        >
          {loading ? "…" : "Regenerate"}
        </Button>
      </header>

      {error ? (
        <AIError error={error} onRetry={() => void load()} />
      ) : loading && !data ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="space-y-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]/30 p-3"
            >
              <SkeletonLine width="30%" height={8} />
              <SkeletonLine width="80%" height={12} />
              <SkeletonLine width="100%" height={10} />
              <SkeletonLine width="65%" height={10} />
            </div>
          ))}
        </div>
      ) : data ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {data.findings.map((f, i) => (
              <div
                key={i}
                className={clsx(
                  "rounded-md border p-3",
                  SEVERITY_STYLE[f.severity]
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-[10px] uppercase tracking-wide">{f.severity}</span>
                  {f.columns && f.columns.length > 0 && (
                    <span className="text-[10px] font-mono opacity-80">
                      {f.columns.join(", ")}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm font-medium">{f.title}</p>
                <p className="mt-0.5 text-xs opacity-90">{f.detail}</p>
              </div>
            ))}
          </div>

          {data.suggested_analyses.length > 0 && (
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
                Suggested follow-ups
              </p>
              <div className="flex flex-wrap gap-2">
                {data.suggested_analyses.map((a, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onAskSuggested?.(a.question || a.label)}
                    className="rounded-full border border-[var(--color-accent)]/40 bg-[var(--color-accent)]/10 px-3 py-1 text-xs text-[var(--color-accent)] hover:bg-[var(--color-accent)]/20"
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <p className="text-[10px] text-[var(--color-muted)]">
            {data.cached ? "Cached" : "Fresh"}
            {data.created_at && ` · ${new Date(data.created_at).toLocaleString()}`}
          </p>
        </div>
      ) : null}
    </Card>
  );
}
