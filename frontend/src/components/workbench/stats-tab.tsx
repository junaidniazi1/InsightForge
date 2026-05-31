"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type {
  ColumnProfile,
  DescribeResult,
  WorkbenchEnvelope,
} from "@/types";
import { Button } from "@/components/ui/button";
import { parseWorkbenchError, WorkbenchShell } from "./workbench-shell";

interface Props {
  datasetId: string;
  columns: ColumnProfile[];
}

export function StatsTab({ datasetId, columns }: Props) {
  const numeric = columns.filter((c) => c.semantic_type === "numeric");
  const [picked, setPicked] = useState<string[]>(() =>
    numeric.slice(0, 1).map((c) => c.name)
  );
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ReturnType<typeof parseWorkbenchError> | null>(null);
  const [data, setData] = useState<WorkbenchEnvelope<DescribeResult> | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await apiPost<WorkbenchEnvelope<DescribeResult>>(
        `/datasets/${datasetId}/workbench/describe`,
        { columns: picked, bins: 30 }
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
          <h3 className="text-sm font-medium">Descriptive deep-dive</h3>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            Pick numeric column(s) to summarise.
          </p>
          <div className="mt-3 max-h-72 space-y-1 overflow-y-auto rounded-md border bg-[var(--color-bg)] p-2 text-xs">
            {numeric.length === 0 ? (
              <p className="text-[var(--color-muted)]">No numeric columns in this dataset.</p>
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
            disabled={running || picked.length === 0}
          >
            {running ? "Running…" : "Describe"}
          </Button>
        </>
      }
      running={running}
      error={error}
      result={
        data && data.result.columns.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead className="border-b">
                <tr>
                  {["column", "n", "missing", "mean", "median", "std", "min", "max", "skew", "kurt"].map((h) => (
                    <th
                      key={h}
                      className="px-2 py-1 text-left font-medium uppercase tracking-wide text-[var(--color-muted)]"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.result.columns.map((c) => (
                  <tr key={c.name} className="border-b last:border-0">
                    <td className="px-2 py-1 font-mono">{c.name}</td>
                    <td className="px-2 py-1">{c.count.toLocaleString()}</td>
                    <td className="px-2 py-1">
                      {c.missing} ({c.missing_pct}%)
                    </td>
                    <td className="px-2 py-1">{fmt(c.mean)}</td>
                    <td className="px-2 py-1">{fmt(c.median)}</td>
                    <td className="px-2 py-1">{fmt(c.std)}</td>
                    <td className="px-2 py-1">{fmt(c.min)}</td>
                    <td className="px-2 py-1">{fmt(c.max)}</td>
                    <td className="px-2 py-1">{fmt(c.skewness)}</td>
                    <td className="px-2 py-1">{fmt(c.kurtosis)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null
      }
      charts={data?.charts ?? []}
      interpretation={data?.interpretation}
    />
  );
}

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (Math.abs(v) >= 1000 || Math.abs(v) < 0.001) return v.toExponential(2);
  return v.toFixed(3);
}
