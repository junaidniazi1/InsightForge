"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type {
  ClusteringResult,
  ColumnProfile,
  WorkbenchEnvelope,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { parseWorkbenchError, WorkbenchShell } from "./workbench-shell";

interface Props {
  datasetId: string;
  columns: ColumnProfile[];
}

export function ClusteringTab({ datasetId, columns }: Props) {
  const numeric = columns.filter((c) => c.semantic_type === "numeric");
  const [picked, setPicked] = useState<string[]>(() => numeric.map((c) => c.name));
  const [kMax, setKMax] = useState<string>("8");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ReturnType<typeof parseWorkbenchError> | null>(null);
  const [data, setData] = useState<WorkbenchEnvelope<ClusteringResult> | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await apiPost<WorkbenchEnvelope<ClusteringResult>>(
        `/datasets/${datasetId}/workbench/clustering`,
        { features: picked, k_max: Number(kMax) || 8 }
      );
      setData(r);
    } catch (e) {
      setError(parseWorkbenchError(e));
    } finally {
      setRunning(false);
    }
  }

  function toggle(name: string) {
    setPicked((p) => (p.includes(name) ? p.filter((x) => x !== name) : [...p, name]));
  }

  const disabled = numeric.length < 2;

  return (
    <WorkbenchShell
      configPanel={
        <>
          <h3 className="text-sm font-medium">Clustering (KMeans, auto-k)</h3>
          {disabled ? (
            <p className="mt-3 text-xs text-[var(--color-danger)]">
              Need at least 2 numeric columns.
            </p>
          ) : (
            <>
              <div className="mt-3">
                <label className="mb-1 block text-xs text-[var(--color-muted)]">
                  k max (sweeps 2..k_max, picks best by silhouette)
                </label>
                <Input
                  type="number"
                  value={kMax}
                  min={2}
                  max={12}
                  onChange={(e) => setKMax(e.target.value)}
                />
              </div>
              <div className="mt-3 max-h-60 space-y-1 overflow-y-auto rounded-md border bg-[var(--color-bg)] p-2 text-xs">
                {numeric.map((c) => (
                  <label key={c.name} className="flex cursor-pointer items-center gap-2 px-1">
                    <input
                      type="checkbox"
                      checked={picked.includes(c.name)}
                      onChange={() => toggle(c.name)}
                      className="h-3.5 w-3.5 accent-[var(--color-accent)]"
                    />
                    <span className="font-mono">{c.name}</span>
                  </label>
                ))}
              </div>
              <Button
                className="mt-4 w-full"
                onClick={run}
                disabled={running || picked.length < 2}
              >
                {running ? "Clustering…" : "Run clustering"}
              </Button>
            </>
          )}
        </>
      }
      running={running}
      error={error}
      result={
        data ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3 text-sm">
              <Stat label="Best k" value={String(data.result.best_k)} />
              <Stat
                label="Silhouette"
                value={data.result.best_silhouette.toFixed(3)}
              />
              <Stat label="Rows used" value={data.result.rows_used.toLocaleString()} />
            </div>
            <div>
              <h4 className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
                Cluster profiles
              </h4>
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead className="border-b">
                    <tr>
                      <th className="px-2 py-1 text-left font-medium text-[var(--color-muted)]">
                        Cluster
                      </th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--color-muted)]">
                        Size
                      </th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--color-muted)]">
                        Top features
                      </th>
                      {data.result.features.map((f) => (
                        <th
                          key={f}
                          className="px-2 py-1 text-left font-medium font-mono text-[var(--color-muted)]"
                        >
                          μ {f}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.result.cluster_profiles.map((p) => (
                      <tr key={p.cluster} className="border-b last:border-0">
                        <td className="px-2 py-1 font-mono">{p.cluster}</td>
                        <td className="px-2 py-1">
                          {p.size} ({p.size_pct.toFixed(1)}%)
                        </td>
                        <td className="px-2 py-1 font-mono text-[10px]">
                          {p.top_distinguishing_features.join(", ")}
                        </td>
                        {data.result.features.map((f) => (
                          <td key={f} className="px-2 py-1">
                            {p.means[f]?.toFixed(3) ?? "—"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
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
