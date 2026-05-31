"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type {
  ColumnProfile,
  CorrelationMethod,
  CorrelationResult,
  WorkbenchEnvelope,
} from "@/types";
import { Button } from "@/components/ui/button";
import { parseWorkbenchError, WorkbenchShell } from "./workbench-shell";

interface Props {
  datasetId: string;
  columns: ColumnProfile[];
}

const METHODS: CorrelationMethod[] = ["pearson", "spearman", "kendall"];

export function CorrelationTab({ datasetId, columns }: Props) {
  const numeric = columns.filter((c) => c.semantic_type === "numeric");
  const [picked, setPicked] = useState<string[]>(() => numeric.map((c) => c.name));
  const [method, setMethod] = useState<CorrelationMethod>("pearson");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ReturnType<typeof parseWorkbenchError> | null>(null);
  const [data, setData] = useState<WorkbenchEnvelope<CorrelationResult> | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await apiPost<WorkbenchEnvelope<CorrelationResult>>(
        `/datasets/${datasetId}/workbench/correlation`,
        { columns: picked, method }
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

  return (
    <WorkbenchShell
      configPanel={
        <>
          <h3 className="text-sm font-medium">Correlation explorer</h3>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            Numeric columns only. Pick at least 2.
          </p>
          <div className="mt-3">
            <label className="mb-1 block text-xs text-[var(--color-muted)]">Method</label>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value as CorrelationMethod)}
              className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
            >
              {METHODS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <div className="mt-3 max-h-60 space-y-1 overflow-y-auto rounded-md border bg-[var(--color-bg)] p-2 text-xs">
            {numeric.length < 2 ? (
              <p className="text-[var(--color-muted)]">
                Need at least 2 numeric columns to compute correlations.
              </p>
            ) : (
              numeric.map((c) => (
                <label key={c.name} className="flex cursor-pointer items-center gap-2 px-1">
                  <input
                    type="checkbox"
                    checked={picked.includes(c.name)}
                    onChange={() => toggle(c.name)}
                    className="h-3.5 w-3.5 accent-[var(--color-accent)]"
                  />
                  <span className="font-mono">{c.name}</span>
                </label>
              ))
            )}
          </div>
          <Button
            className="mt-4 w-full"
            onClick={run}
            disabled={running || picked.length < 2}
          >
            {running ? "Computing…" : "Run correlation"}
          </Button>
        </>
      }
      running={running}
      error={error}
      result={
        data && data.result.top_pairs.length > 0 ? (
          <>
            <h4 className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Strongest pairs
            </h4>
            <table className="min-w-full text-xs">
              <thead className="border-b">
                <tr>
                  {["a", "b", "r", "p-value", "n", "significant"].map((h) => (
                    <th key={h} className="px-2 py-1 text-left font-medium text-[var(--color-muted)]">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.result.top_pairs.map((p, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="px-2 py-1 font-mono">{p.a}</td>
                    <td className="px-2 py-1 font-mono">{p.b}</td>
                    <td
                      className={`px-2 py-1 ${p.r > 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}
                    >
                      {p.r.toFixed(3)}
                    </td>
                    <td className="px-2 py-1">{p.p_value.toExponential(2)}</td>
                    <td className="px-2 py-1">{p.n}</td>
                    <td className="px-2 py-1">
                      {p.significant ? "✓" : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null
      }
      charts={data?.charts ?? []}
      interpretation={data?.interpretation}
    />
  );
}
