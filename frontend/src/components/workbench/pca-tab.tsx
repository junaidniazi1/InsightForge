"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type {
  ColumnProfile,
  PCAResult,
  WorkbenchEnvelope,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { parseWorkbenchError, WorkbenchShell } from "./workbench-shell";

interface Props {
  datasetId: string;
  columns: ColumnProfile[];
}

export function PCATab({ datasetId, columns }: Props) {
  const numeric = columns.filter((c) => c.semantic_type === "numeric");
  const [picked, setPicked] = useState<string[]>(() => numeric.map((c) => c.name));
  const [nComp, setNComp] = useState<string>("2");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ReturnType<typeof parseWorkbenchError> | null>(null);
  const [data, setData] = useState<WorkbenchEnvelope<PCAResult> | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await apiPost<WorkbenchEnvelope<PCAResult>>(
        `/datasets/${datasetId}/workbench/pca`,
        { features: picked, n_components: Number(nComp) || 2 }
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
  const maxComp = Math.max(2, picked.length || numeric.length);

  return (
    <WorkbenchShell
      configPanel={
        <>
          <h3 className="text-sm font-medium">PCA</h3>
          {disabled ? (
            <p className="mt-3 text-xs text-[var(--color-danger)]">
              Need at least 2 numeric columns.
            </p>
          ) : (
            <>
              <div className="mt-3">
                <label className="mb-1 block text-xs text-[var(--color-muted)]">
                  Components (max {Math.min(12, maxComp)})
                </label>
                <Input
                  type="number"
                  min={2}
                  max={Math.min(12, maxComp)}
                  value={nComp}
                  onChange={(e) => setNComp(e.target.value)}
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
                {running ? "Running PCA…" : "Run PCA"}
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
              <Stat label="Components" value={String(data.result.n_components)} />
              <Stat label="n for 90%" value={String(data.result.n_for_90pct)} />
              <Stat label="Rows used" value={data.result.rows_used.toLocaleString()} />
            </div>
            <div className="space-y-3">
              <h4 className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                Top loadings per component
              </h4>
              {data.result.components.map((comp) => (
                <div key={comp.component} className="rounded border bg-[var(--color-bg)]/40 p-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono">{comp.component}</span>
                    <span className="text-[var(--color-muted)]">
                      {(comp.explained_variance * 100).toFixed(1)}% variance · cum.{" "}
                      {(comp.cumulative * 100).toFixed(1)}%
                    </span>
                  </div>
                  <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    {comp.loadings.map((l) => (
                      <li key={l.feature} className="flex justify-between font-mono">
                        <span>{l.feature}</span>
                        <span
                          className={
                            l.loading > 0
                              ? "text-[var(--color-success)]"
                              : "text-[var(--color-danger)]"
                          }
                        >
                          {l.loading >= 0 ? "+" : ""}
                          {l.loading.toFixed(3)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
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
