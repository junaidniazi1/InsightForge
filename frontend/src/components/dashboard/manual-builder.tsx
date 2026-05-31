"use client";

import { useMemo, useState } from "react";
import type { ChartSpec, ChartType, ColumnProfile, FilterClause } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChartTile } from "./chart-tile";

interface Props {
  datasetId: string;
  versionId: string | null;
  columns: ColumnProfile[];
  filters: FilterClause[];
  onAdd: (spec: ChartSpec) => void;
}

const CHART_TYPES: { value: ChartType; label: string; needs: ("x" | "y" | "agg" | "columns")[] }[] = [
  { value: "histogram", label: "Histogram", needs: ["x"] },
  { value: "box", label: "Box plot", needs: ["y"] },
  { value: "violin", label: "Violin", needs: ["y"] },
  { value: "bar", label: "Bar (count or aggregate)", needs: ["x", "agg"] },
  { value: "pie", label: "Pie", needs: ["x"] },
  { value: "scatter", label: "Scatter", needs: ["x", "y"] },
  { value: "line", label: "Line (time series)", needs: ["x", "y", "agg"] },
  { value: "heatmap", label: "Correlation heatmap", needs: ["columns"] },
];

const AGGS = ["mean", "sum", "count", "min", "max", "median"];

export function ManualBuilder({ datasetId, versionId, columns, filters, onAdd }: Props) {
  const [chartType, setChartType] = useState<ChartType>("histogram");
  const [x, setX] = useState<string>("");
  const [y, setY] = useState<string>("");
  const [agg, setAgg] = useState<string>("mean");
  const [chosenCols, setChosenCols] = useState<string[]>([]);
  const [title, setTitle] = useState<string>("");

  const def = CHART_TYPES.find((c) => c.value === chartType)!;
  const numericCols = useMemo(() => columns.filter((c) => c.semantic_type === "numeric"), [columns]);
  const categoricalCols = useMemo(
    () => columns.filter((c) => c.semantic_type === "categorical" || c.semantic_type === "boolean"),
    [columns]
  );
  const datetimeCols = useMemo(() => columns.filter((c) => c.semantic_type === "datetime"), [columns]);
  const anyCols = columns;

  function colsForRole(role: "x" | "y" | "columns"): ColumnProfile[] {
    if (chartType === "histogram" || chartType === "box" || chartType === "violin") return numericCols;
    if (chartType === "scatter") return numericCols;
    if (chartType === "line") {
      if (role === "x") return datetimeCols;
      if (role === "y") return numericCols;
    }
    if (chartType === "bar") {
      if (role === "x") return categoricalCols.length ? categoricalCols : anyCols;
      if (role === "y") return numericCols;
    }
    if (chartType === "pie") return categoricalCols.length ? categoricalCols : anyCols;
    if (chartType === "heatmap") return numericCols;
    return anyCols;
  }

  const spec = useMemo<ChartSpec | null>(() => {
    const encoding: Record<string, unknown> = {};
    if (def.needs.includes("x") && x) encoding.x = x;
    if (def.needs.includes("y") && y) encoding.y = y;
    if (def.needs.includes("agg")) encoding.agg = chartType === "bar" && !y ? "count" : agg;
    if (def.needs.includes("columns")) encoding.columns = chosenCols.length ? chosenCols : numericCols.map((c) => c.name);

    // Sanity-check completeness
    if (def.needs.includes("x") && !x) return null;
    if (def.needs.includes("y") && !y && !(chartType === "bar" && encoding.agg === "count")) return null;
    if (def.needs.includes("columns") && (chosenCols.length === 0 && numericCols.length < 2)) return null;

    return {
      chart_type: chartType,
      encoding: encoding as ChartSpec["encoding"],
      title: title || `${chartType}: ${x || y || "preview"}`,
      bins: chartType === "histogram" ? 30 : null,
      top_n: null,
      filters: [],
    };
  }, [chartType, x, y, agg, chosenCols, title, def, numericCols]);

  const xRoleCols = colsForRole("x");
  const yRoleCols = colsForRole("y");
  const columnRoleCols = colsForRole("columns");

  function toggleCol(c: string) {
    setChosenCols((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs text-[var(--color-muted)]">Chart type</label>
          <select
            value={chartType}
            onChange={(e) => setChartType(e.target.value as ChartType)}
            className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
          >
            {CHART_TYPES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-[var(--color-muted)]">Title</label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Optional" />
        </div>
        {def.needs.includes("x") && (
          <ColumnPicker label="X column" cols={xRoleCols} value={x} onChange={setX} />
        )}
        {def.needs.includes("y") && (
          <ColumnPicker label={chartType === "bar" ? "Y column (optional for count)" : "Y column"} cols={yRoleCols} value={y} onChange={setY} />
        )}
        {def.needs.includes("agg") && y && (
          <div>
            <label className="mb-1 block text-xs text-[var(--color-muted)]">Aggregation</label>
            <select
              value={agg}
              onChange={(e) => setAgg(e.target.value)}
              className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
            >
              {AGGS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
        )}
        {def.needs.includes("columns") && (
          <div className="sm:col-span-2">
            <label className="mb-1 block text-xs text-[var(--color-muted)]">
              Numeric columns ({chosenCols.length || numericCols.length} selected)
            </label>
            <div className="flex flex-wrap gap-1">
              {columnRoleCols.map((c) => {
                const active = chosenCols.includes(c.name);
                return (
                  <button
                    type="button"
                    key={c.name}
                    onClick={() => toggleCol(c.name)}
                    className={
                      "rounded-full border px-2 py-0.5 text-[11px] " +
                      (active
                        ? "border-[var(--color-accent)] bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                        : "text-[var(--color-muted)] hover:text-[var(--color-fg)]")
                    }
                  >
                    {c.name}
                  </button>
                );
              })}
            </div>
            <p className="mt-1 text-[10px] text-[var(--color-muted)]">
              Empty selection uses all numeric columns.
            </p>
          </div>
        )}
      </div>

      {/* Live preview */}
      {spec ? (
        <div className="rounded border bg-[var(--color-bg)]/40">
          <ChartTile
            datasetId={datasetId}
            versionId={versionId}
            spec={spec}
            filters={filters}
            height={240}
            showHeader={false}
          />
        </div>
      ) : (
        <p className="text-xs text-[var(--color-muted)]">
          Pick the required columns to preview the chart.
        </p>
      )}

      <div className="flex justify-end">
        <Button onClick={() => spec && onAdd(spec)} disabled={!spec}>
          Add to dashboard
        </Button>
      </div>
    </div>
  );
}

function ColumnPicker({
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
