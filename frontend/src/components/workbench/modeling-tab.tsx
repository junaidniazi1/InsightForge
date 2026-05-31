"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import { downloadAuthed } from "@/lib/download";
import type {
  ColumnProfile,
  ModelMetricsClassification,
  ModelMetricsRegression,
  ModelResult,
  WorkbenchEnvelope,
} from "@/types";
import { Button } from "@/components/ui/button";
import { parseWorkbenchError, WorkbenchShell } from "./workbench-shell";

interface Props {
  datasetId: string;
  columns: ColumnProfile[];
}

export function ModelingTab({ datasetId, columns }: Props) {
  const [target, setTarget] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ReturnType<typeof parseWorkbenchError> | null>(null);
  const [data, setData] = useState<WorkbenchEnvelope<ModelResult> | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);
  const [dlBusy, setDlBusy] = useState(false);

  async function run() {
    if (!target) return;
    setRunning(true);
    setError(null);
    try {
      const r = await apiPost<WorkbenchEnvelope<ModelResult>>(
        `/datasets/${datasetId}/workbench/model`,
        { target }
      );
      setData(r);
    } catch (e) {
      setError(parseWorkbenchError(e));
    } finally {
      setRunning(false);
    }
  }

  async function downloadPredictions() {
    setDlBusy(true);
    setDlError(null);
    try {
      await downloadAuthed(
        `/datasets/${datasetId}/workbench/model/predictions.csv`,
        `predictions-${target}.csv`
      );
    } catch (e) {
      setDlError(e instanceof Error ? e.message : String(e));
    } finally {
      setDlBusy(false);
    }
  }

  return (
    <WorkbenchShell
      configPanel={
        <>
          <h3 className="text-sm font-medium">Baseline predictive model</h3>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            Pick a target. Trains two baselines side-by-side; you can download the test-set predictions.
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
            {running ? "Training…" : "Train baseline models"}
          </Button>
          {data && (
            <div className="mt-3 space-y-2">
              <Button
                variant="secondary"
                onClick={downloadPredictions}
                disabled={dlBusy}
                className="w-full text-xs"
              >
                {dlBusy ? "Preparing…" : "Download predictions (CSV)"}
              </Button>
              {dlError && (
                <p className="text-xs text-[var(--color-danger)]">{dlError}</p>
              )}
              <p className="text-[10px] text-[var(--color-muted)]">
                {data.result.predictions_count.toLocaleString()} test-set rows cached.
              </p>
            </div>
          )}
        </>
      }
      running={running}
      error={error}
      result={
        data ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3 text-sm">
              <Stat label="Problem" value={data.result.problem_type} />
              <Stat label="Train / Test" value={`${data.result.n_train} / ${data.result.n_test}`} />
              <Stat label="Best model" value={data.result.best_model} />
            </div>

            {data.result.problem_type === "regression" ? (
              <MetricsTableRegression metrics={data.result.metrics as ModelMetricsRegression[]} best={data.result.best_model} />
            ) : (
              <MetricsTableClassification
                metrics={data.result.metrics as ModelMetricsClassification[]}
                best={data.result.best_model}
                classes={data.result.classes ?? []}
              />
            )}

            {data.result.warnings.length > 0 && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">
                {data.result.warnings.map((w, i) => (
                  <p key={i}>⚠ {w}</p>
                ))}
              </div>
            )}

            <div>
              <h4 className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
                Top features (Random Forest)
              </h4>
              <div className="max-h-60 overflow-y-auto rounded border bg-[var(--color-bg)]/40">
                <table className="min-w-full text-xs">
                  <thead className="border-b">
                    <tr>
                      <th className="px-2 py-1 text-left text-[var(--color-muted)]">#</th>
                      <th className="px-2 py-1 text-left text-[var(--color-muted)]">feature</th>
                      <th className="px-2 py-1 text-left text-[var(--color-muted)]">importance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.result.feature_importances.map((f, i) => (
                      <tr key={f.feature} className="border-b last:border-0">
                        <td className="px-2 py-1 font-mono">{i + 1}</td>
                        <td className="px-2 py-1 font-mono">{f.feature}</td>
                        <td className="px-2 py-1">{f.importance.toFixed(4)}</td>
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

function MetricsTableRegression({
  metrics,
  best,
}: {
  metrics: ModelMetricsRegression[];
  best: string;
}) {
  return (
    <div>
      <h4 className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
        Metrics
      </h4>
      <table className="min-w-full text-xs">
        <thead className="border-b">
          <tr>
            {["model", "R²", "RMSE", "MAE"].map((h) => (
              <th key={h} className="px-2 py-1 text-left text-[var(--color-muted)]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.model} className={m.model === best ? "bg-[var(--color-accent)]/10" : ""}>
              <td className="px-2 py-1 font-mono">
                {m.model === best && "★ "}
                {m.model}
              </td>
              <td className="px-2 py-1">{m.r2.toFixed(3)}</td>
              <td className="px-2 py-1">{m.rmse.toFixed(3)}</td>
              <td className="px-2 py-1">{m.mae.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricsTableClassification({
  metrics,
  best,
  classes,
}: {
  metrics: ModelMetricsClassification[];
  best: string;
  classes: string[];
}) {
  return (
    <div>
      <h4 className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
        Metrics ({classes.length} classes)
      </h4>
      <table className="min-w-full text-xs">
        <thead className="border-b">
          <tr>
            {["model", "accuracy", "precision (macro)", "recall (macro)", "F1 (macro)"].map((h) => (
              <th key={h} className="px-2 py-1 text-left text-[var(--color-muted)]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.model} className={m.model === best ? "bg-[var(--color-accent)]/10" : ""}>
              <td className="px-2 py-1 font-mono">
                {m.model === best && "★ "}
                {m.model}
              </td>
              <td className="px-2 py-1">{m.accuracy.toFixed(3)}</td>
              <td className="px-2 py-1">{m.precision_macro.toFixed(3)}</td>
              <td className="px-2 py-1">{m.recall_macro.toFixed(3)}</td>
              <td className="px-2 py-1">{m.f1_macro.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
