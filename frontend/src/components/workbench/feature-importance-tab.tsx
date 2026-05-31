"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type {
  ColumnProfile,
  FeatureImportanceResult,
  WorkbenchEnvelope,
} from "@/types";
import { Button } from "@/components/ui/button";
import { parseWorkbenchError, WorkbenchShell } from "./workbench-shell";

interface Props {
  datasetId: string;
  columns: ColumnProfile[];
}

export function FeatureImportanceTab({ datasetId, columns }: Props) {
  const [target, setTarget] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ReturnType<typeof parseWorkbenchError> | null>(null);
  const [data, setData] = useState<WorkbenchEnvelope<FeatureImportanceResult> | null>(null);

  async function run() {
    if (!target) return;
    setRunning(true);
    setError(null);
    try {
      const r = await apiPost<WorkbenchEnvelope<FeatureImportanceResult>>(
        `/datasets/${datasetId}/workbench/feature-importance`,
        { target }
      );
      setData(r);
    } catch (e) {
      setError(parseWorkbenchError(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <WorkbenchShell
      configPanel={
        <>
          <h3 className="text-sm font-medium">Feature importance (Random Forest)</h3>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            Pick a target. Numeric target → regression; otherwise classification.
          </p>
          <div className="mt-3">
            <label className="mb-1 block text-xs text-[var(--color-muted)]">Target column</label>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
            >
              <option value="">— pick —</option>
              {columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.semantic_type})
                </option>
              ))}
            </select>
          </div>
          <Button className="mt-4 w-full" onClick={run} disabled={running || !target}>
            {running ? "Training RF…" : "Compute importances"}
          </Button>
        </>
      }
      running={running}
      error={error}
      result={
        data ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3 text-sm">
              <Stat label="Problem" value={data.result.problem_type} />
              <Stat label="OOB score" value={data.result.oob_score.toFixed(3)} />
              <Stat label="Rows used" value={data.result.n_rows_used.toLocaleString()} />
            </div>
            <div>
              <h4 className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
                Ranked importances
              </h4>
              <div className="max-h-72 overflow-y-auto rounded border bg-[var(--color-bg)]/40">
                <table className="min-w-full text-xs">
                  <thead className="border-b">
                    <tr>
                      <th className="px-2 py-1 text-left font-medium text-[var(--color-muted)]">#</th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--color-muted)]">feature</th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--color-muted)]">importance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.result.feature_importances.map((imp, i) => (
                      <tr key={imp.feature} className="border-b last:border-0">
                        <td className="px-2 py-1 font-mono">{i + 1}</td>
                        <td className="px-2 py-1 font-mono">{imp.feature}</td>
                        <td className="px-2 py-1">{imp.importance.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {data.result.dropped_features.length > 0 && (
              <p className="text-[10px] text-[var(--color-muted)]">
                Dropped from features (high-cardinality / datetime / empty):{" "}
                <span className="font-mono">{data.result.dropped_features.join(", ")}</span>
              </p>
            )}
          </div>
        ) : null
      }
      charts={data?.charts ?? []}
      interpretation={data?.interpretation}
    />
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border bg-[var(--color-bg)]/40 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-[var(--color-muted)]">{label}</p>
      <p className="mt-0.5 font-mono text-sm">{value}</p>
    </div>
  );
}
