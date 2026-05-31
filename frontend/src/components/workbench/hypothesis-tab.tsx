"use client";

import { useMemo, useState } from "react";
import { apiPost } from "@/lib/api";
import type {
  ColumnProfile,
  HypothesisRecommendation,
  HypothesisTest,
  WorkbenchEnvelope,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { parseWorkbenchError, WorkbenchShell } from "./workbench-shell";

interface Props {
  datasetId: string;
  columns: ColumnProfile[];
}

const TESTS: { value: HypothesisTest; label: string; description: string }[] = [
  { value: "ttest_one", label: "One-sample t-test", description: "Numeric column vs a target mean." },
  { value: "ttest_two", label: "Two-sample t-test", description: "Numeric column compared across 2 groups." },
  { value: "anova", label: "ANOVA (one-way)", description: "Numeric column compared across 3+ groups." },
  { value: "chi_square", label: "Chi-square independence", description: "Two categorical columns." },
  { value: "mann_whitney", label: "Mann-Whitney U", description: "Two-sample t-test alternative (non-normal)." },
];

export function HypothesisTab({ datasetId, columns }: Props) {
  const numeric = useMemo(() => columns.filter((c) => c.semantic_type === "numeric"), [columns]);
  const categorical = useMemo(
    () => columns.filter((c) => c.semantic_type === "categorical" || c.semantic_type === "boolean"),
    [columns]
  );

  const [test, setTest] = useState<HypothesisTest>("ttest_two");
  const [valueCol, setValueCol] = useState<string>("");
  const [groupCol, setGroupCol] = useState<string>("");
  const [secondCol, setSecondCol] = useState<string>("");
  const [popmean, setPopmean] = useState<string>("0");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ReturnType<typeof parseWorkbenchError> | null>(null);
  const [data, setData] = useState<WorkbenchEnvelope | null>(null);
  const [recommendation, setRecommendation] = useState<HypothesisRecommendation | null>(null);

  async function suggest() {
    const pick = [valueCol, groupCol].filter(Boolean);
    if (pick.length === 0) return;
    try {
      const r = await apiPost<HypothesisRecommendation>(
        `/datasets/${datasetId}/workbench/hypothesis/recommend`,
        { columns: pick }
      );
      setRecommendation(r);
      if (r.recommendation) setTest(r.recommendation);
    } catch (e) {
      // Recommender failures are non-fatal.
      console.warn(e);
    }
  }

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { test };
      if (test === "ttest_one") {
        body.value_col = valueCol;
        body.popmean = Number(popmean);
      } else if (test === "chi_square") {
        body.value_col = valueCol;
        body.second_col = secondCol;
      } else {
        body.value_col = valueCol;
        body.group_col = groupCol;
      }
      const r = await apiPost<WorkbenchEnvelope>(
        `/datasets/${datasetId}/workbench/hypothesis`,
        body
      );
      setData(r);
    } catch (e) {
      setError(parseWorkbenchError(e));
    } finally {
      setRunning(false);
    }
  }

  // Per-test column picker source
  const numericLabel = (
    <ColumnSelect
      label="Numeric column"
      cols={numeric}
      value={valueCol}
      onChange={setValueCol}
    />
  );
  const groupLabel = (
    <ColumnSelect
      label="Group column (categorical)"
      cols={categorical}
      value={groupCol}
      onChange={setGroupCol}
    />
  );

  return (
    <WorkbenchShell
      configPanel={
        <>
          <h3 className="text-sm font-medium">Hypothesis tests</h3>
          <div className="mt-3">
            <label className="mb-1 block text-xs text-[var(--color-muted)]">Test</label>
            <select
              value={test}
              onChange={(e) => setTest(e.target.value as HypothesisTest)}
              className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
            >
              {TESTS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-[var(--color-muted)]">
              {TESTS.find((t) => t.value === test)?.description}
            </p>
          </div>

          <div className="mt-3 space-y-3">
            {test === "chi_square" ? (
              <>
                <ColumnSelect
                  label="Categorical column A"
                  cols={categorical}
                  value={valueCol}
                  onChange={setValueCol}
                />
                <ColumnSelect
                  label="Categorical column B"
                  cols={categorical}
                  value={secondCol}
                  onChange={setSecondCol}
                />
              </>
            ) : test === "ttest_one" ? (
              <>
                {numericLabel}
                <div>
                  <label className="mb-1 block text-xs text-[var(--color-muted)]">
                    Population mean (μ₀)
                  </label>
                  <Input
                    type="number"
                    value={popmean}
                    onChange={(e) => setPopmean(e.target.value)}
                  />
                </div>
              </>
            ) : (
              <>
                {numericLabel}
                {groupLabel}
              </>
            )}
          </div>

          <div className="mt-4 flex gap-2">
            <Button variant="secondary" onClick={suggest} className="text-xs">
              Suggest a test
            </Button>
            <Button onClick={run} disabled={running} className="flex-1 text-xs">
              {running ? "Running…" : "Run"}
            </Button>
          </div>
          {recommendation && (
            <p className="mt-3 rounded border bg-[var(--color-bg)]/40 p-2 text-xs">
              <span className="text-[var(--color-muted)]">recommended:</span>{" "}
              <span className="font-medium">
                {recommendation.recommendation ?? "—"}
              </span>{" "}
              · {recommendation.reason}
            </p>
          )}
        </>
      }
      running={running}
      error={error}
      result={
        data ? (
          <pre className="overflow-x-auto rounded bg-[var(--color-bg)]/40 p-3 font-mono text-[11px] leading-relaxed">
            {JSON.stringify(data.result, null, 2)}
          </pre>
        ) : null
      }
      charts={data?.charts ?? []}
      interpretation={data?.interpretation}
    />
  );
}

function ColumnSelect({
  label,
  cols,
  value,
  onChange,
}: {
  label: string;
  cols: ColumnProfile[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-[var(--color-muted)]">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
      >
        <option value="">— pick —</option>
        {cols.map((c) => (
          <option key={c.name} value={c.name}>
            {c.name} ({c.semantic_type})
          </option>
        ))}
      </select>
    </div>
  );
}
