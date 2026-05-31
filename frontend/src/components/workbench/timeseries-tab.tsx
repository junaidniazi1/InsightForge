"use client";

import { useMemo, useState } from "react";
import { apiPost } from "@/lib/api";
import type {
  ColumnProfile,
  TsAgg,
  TsFrequency,
  TsMode,
  WorkbenchEnvelope,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { parseWorkbenchError, WorkbenchShell } from "./workbench-shell";

interface Props {
  datasetId: string;
  columns: ColumnProfile[];
}

const MODES: { value: TsMode; label: string }[] = [
  { value: "resample", label: "Resample + rolling" },
  { value: "decompose", label: "Seasonal decomposition" },
  { value: "acf_pacf", label: "ACF / PACF" },
  { value: "stationarity", label: "Stationarity (ADF)" },
];

const FREQS: TsFrequency[] = ["D", "W", "ME", "QE", "YE"];
const AGGS: TsAgg[] = ["mean", "sum", "min", "max", "median"];

export function TimeseriesTab({ datasetId, columns }: Props) {
  const datetimeCols = useMemo(() => columns.filter((c) => c.semantic_type === "datetime"), [columns]);
  const numericCols = useMemo(() => columns.filter((c) => c.semantic_type === "numeric"), [columns]);

  const [mode, setMode] = useState<TsMode>("resample");
  const [x, setX] = useState<string>(() => datetimeCols[0]?.name ?? "");
  const [y, setY] = useState<string>(() => numericCols[0]?.name ?? "");
  const [freq, setFreq] = useState<TsFrequency>("ME");
  const [agg, setAgg] = useState<TsAgg>("mean");
  const [rolling, setRolling] = useState<string>("");
  const [period, setPeriod] = useState<string>("");
  const [nlags, setNlags] = useState<string>("30");

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ReturnType<typeof parseWorkbenchError> | null>(null);
  const [data, setData] = useState<WorkbenchEnvelope | null>(null);

  const disabled = datetimeCols.length === 0 || numericCols.length === 0;

  async function run() {
    if (!x || !y) return;
    setRunning(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { mode, x, y, freq, agg };
      if (mode === "resample" && rolling) body.rolling_window = Number(rolling);
      if (mode === "decompose" && period) body.period = Number(period);
      if (mode === "acf_pacf") body.nlags = Number(nlags || "30");
      const r = await apiPost<WorkbenchEnvelope>(
        `/datasets/${datasetId}/workbench/timeseries`,
        body
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
          <h3 className="text-sm font-medium">Time-series</h3>
          {disabled ? (
            <p className="mt-3 text-xs text-[var(--color-danger)]">
              Time-series tools need at least one datetime column and one numeric column.
              {datetimeCols.length === 0 && " No datetime column detected — try Data Health to convert one."}
            </p>
          ) : (
            <>
              <div className="mt-3">
                <label className="mb-1 block text-xs text-[var(--color-muted)]">Mode</label>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value as TsMode)}
                  className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
                >
                  {MODES.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs text-[var(--color-muted)]">
                    Datetime (x)
                  </label>
                  <select
                    value={x}
                    onChange={(e) => setX(e.target.value)}
                    className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
                  >
                    {datetimeCols.map((c) => (
                      <option key={c.name} value={c.name}>{c.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-[var(--color-muted)]">
                    Numeric (y)
                  </label>
                  <select
                    value={y}
                    onChange={(e) => setY(e.target.value)}
                    className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
                  >
                    {numericCols.map((c) => (
                      <option key={c.name} value={c.name}>{c.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-[var(--color-muted)]">Frequency</label>
                  <select
                    value={freq}
                    onChange={(e) => setFreq(e.target.value as TsFrequency)}
                    className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
                  >
                    {FREQS.map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-[var(--color-muted)]">Agg</label>
                  <select
                    value={agg}
                    onChange={(e) => setAgg(e.target.value as TsAgg)}
                    className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
                  >
                    {AGGS.map((a) => (
                      <option key={a} value={a}>{a}</option>
                    ))}
                  </select>
                </div>
              </div>
              {mode === "resample" && (
                <div className="mt-3">
                  <label className="mb-1 block text-xs text-[var(--color-muted)]">
                    Rolling window (optional)
                  </label>
                  <Input
                    type="number"
                    placeholder="e.g. 3"
                    value={rolling}
                    onChange={(e) => setRolling(e.target.value)}
                  />
                </div>
              )}
              {mode === "decompose" && (
                <div className="mt-3">
                  <label className="mb-1 block text-xs text-[var(--color-muted)]">
                    Period (optional, default by freq)
                  </label>
                  <Input
                    type="number"
                    placeholder="e.g. 12 for monthly"
                    value={period}
                    onChange={(e) => setPeriod(e.target.value)}
                  />
                </div>
              )}
              {mode === "acf_pacf" && (
                <div className="mt-3">
                  <label className="mb-1 block text-xs text-[var(--color-muted)]">Lags</label>
                  <Input
                    type="number"
                    value={nlags}
                    onChange={(e) => setNlags(e.target.value)}
                  />
                </div>
              )}
              <Button
                className="mt-4 w-full"
                onClick={run}
                disabled={running || !x || !y}
              >
                {running ? "Running…" : "Run"}
              </Button>
            </>
          )}
        </>
      }
      running={running}
      error={error}
      result={
        data ? (
          <details className="text-xs">
            <summary className="cursor-pointer text-[var(--color-muted)] hover:text-[var(--color-fg)]">
              Raw result JSON
            </summary>
            <pre className="mt-2 overflow-x-auto rounded bg-[var(--color-bg)]/40 p-2 font-mono text-[10px]">
              {JSON.stringify(data.result, null, 2)}
            </pre>
          </details>
        ) : null
      }
      charts={data?.charts ?? []}
      interpretation={data?.interpretation}
    />
  );
}
