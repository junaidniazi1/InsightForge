"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type {
  AnomalyResult,
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

export function AnomalyTab({ datasetId, columns }: Props) {
  const numeric = columns.filter((c) => c.semantic_type === "numeric");
  const [picked, setPicked] = useState<string[]>(() => numeric.map((c) => c.name));
  const [contamination, setContamination] = useState<string>("0.05");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ReturnType<typeof parseWorkbenchError> | null>(null);
  const [data, setData] = useState<WorkbenchEnvelope<AnomalyResult> | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await apiPost<WorkbenchEnvelope<AnomalyResult>>(
        `/datasets/${datasetId}/workbench/anomaly`,
        {
          features: picked,
          contamination: Math.max(0.001, Math.min(Number(contamination) || 0.05, 0.5)),
        }
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
          <h3 className="text-sm font-medium">Anomaly detection (Isolation Forest)</h3>
          {disabled ? (
            <p className="mt-3 text-xs text-[var(--color-danger)]">
              Need at least 2 numeric columns.
            </p>
          ) : (
            <>
              <div className="mt-3">
                <label className="mb-1 block text-xs text-[var(--color-muted)]">
                  Contamination (fraction of rows to flag)
                </label>
                <Input
                  type="number"
                  step="0.01"
                  min="0.001"
                  max="0.5"
                  value={contamination}
                  onChange={(e) => setContamination(e.target.value)}
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
                {running ? "Detecting…" : "Run anomaly detection"}
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
              <Stat label="Flagged" value={data.result.flagged_count.toLocaleString()} />
              <Stat label="% of rows" value={`${data.result.flagged_pct}%`} />
              <Stat label="Contamination" value={data.result.contamination.toFixed(3)} />
            </div>
            <div>
              <h4 className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
                Flagged rows {data.result.truncated && `(showing first ${data.result.max_flagged})`}
              </h4>
              <div className="max-h-72 overflow-y-auto rounded border bg-[var(--color-bg)]/40">
                <table className="min-w-full text-xs">
                  <thead className="border-b bg-[var(--color-bg)]/60 sticky top-0">
                    <tr>
                      <th className="px-2 py-1 text-left font-medium text-[var(--color-muted)]">
                        row idx
                      </th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--color-muted)]">
                        score
                      </th>
                      {data.result.features.map((f) => (
                        <th key={f} className="px-2 py-1 text-left font-mono font-medium text-[var(--color-muted)]">
                          {f}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.result.flagged_rows.slice(0, 50).map((row) => (
                      <tr key={row.__index} className="border-b last:border-0">
                        <td className="px-2 py-1 font-mono">{row.__index}</td>
                        <td className="px-2 py-1">{row.__score.toFixed(3)}</td>
                        {data.result.features.map((f) => (
                          <td key={f} className="px-2 py-1 font-mono">
                            {typeof row[f] === "number" ? (row[f] as number).toFixed(3) : "—"}
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
