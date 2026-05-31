"use client";

import { useMemo, useState } from "react";
import type {
  ChartSpec,
  ChartType,
  ColumnProfile,
  SemanticType,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PALETTE_NAMES } from "./theme";

interface Props {
  spec: ChartSpec;
  columns: ColumnProfile[];
  onCancel: () => void;
  onApply: (next: ChartSpec) => void;
}

const ALL_CHART_TYPES: { value: ChartType; label: string }[] = [
  { value: "histogram", label: "Histogram" },
  { value: "box", label: "Box plot" },
  { value: "violin", label: "Violin" },
  { value: "bar", label: "Bar" },
  { value: "pie", label: "Pie" },
  { value: "scatter", label: "Scatter" },
  { value: "line", label: "Line" },
  { value: "heatmap", label: "Heatmap" },
  { value: "kpi", label: "KPI" },
];

const AGGS = ["mean", "sum", "count", "min", "max", "median"];

/**
 * Decide which chart types are compatible with the current encoding columns.
 * We don't allow flipping to a type that the existing columns can't satisfy.
 */
function compatibleTypes(
  spec: ChartSpec,
  cols: ColumnProfile[]
): ChartType[] {
  const typeOf = new Map(cols.map((c) => [c.name, c.semantic_type]));
  const isNumeric = (n?: string) => !!n && typeOf.get(n) === "numeric";
  const isCat = (n?: string) =>
    !!n && (typeOf.get(n) === "categorical" || typeOf.get(n) === "boolean");
  const isDt = (n?: string) => !!n && typeOf.get(n) === "datetime";

  const x = spec.encoding.x;
  const y = spec.encoding.y;

  const out: ChartType[] = [];
  for (const { value: t } of ALL_CHART_TYPES) {
    switch (t) {
      case "histogram":
      case "box":
      case "violin":
        if (isNumeric(x) || isNumeric(y)) out.push(t);
        break;
      case "bar":
      case "pie":
        if (x) out.push(t); // x is required; y optional
        break;
      case "scatter":
        if (isNumeric(x) && isNumeric(y)) out.push(t);
        break;
      case "line":
        if (isDt(x) && isNumeric(y)) out.push(t);
        break;
      case "heatmap":
        if ((spec.encoding.columns ?? []).length >= 2) out.push(t);
        break;
      case "kpi":
        if (!y || isNumeric(y)) out.push(t);
        break;
      default:
        out.push(t);
    }
  }
  // Always include the current type so we don't lock the user out.
  if (!out.includes(spec.chart_type)) out.push(spec.chart_type);
  return out;
}

function pickerFor(
  cols: ColumnProfile[],
  role: "x" | "y" | "color",
  chart: ChartType
): ColumnProfile[] {
  const onlyNumeric: ChartType[] = ["scatter", "histogram", "box", "violin", "kpi"];
  const onlyCat: ChartType[] = ["pie"];
  const xDt: ChartType[] = ["line"];

  if (role === "y") {
    return cols.filter((c) => c.semantic_type === "numeric");
  }
  if (role === "color") {
    return cols.filter(
      (c) => c.semantic_type === "categorical" || c.semantic_type === "boolean"
    );
  }
  // x role
  if (xDt.includes(chart)) return cols.filter((c) => c.semantic_type === "datetime");
  if (onlyCat.includes(chart))
    return cols.filter(
      (c) => c.semantic_type === "categorical" || c.semantic_type === "boolean"
    );
  if (onlyNumeric.includes(chart))
    return cols.filter((c) => c.semantic_type === "numeric");
  return cols;
}

export function ChartEditor({ spec, columns, onCancel, onApply }: Props) {
  const [draft, setDraft] = useState<ChartSpec>(() => ({
    ...spec,
    encoding: { ...spec.encoding },
    presentation: { ...(spec.presentation ?? {}) },
  }));

  const validTypes = useMemo(() => compatibleTypes(spec, columns), [spec, columns]);

  function setEnc<K extends keyof typeof draft.encoding>(k: K, v: string | undefined) {
    setDraft((d) => ({ ...d, encoding: { ...d.encoding, [k]: v } }));
  }
  function setPres<K extends keyof NonNullable<typeof draft.presentation>>(
    k: K,
    v: NonNullable<typeof draft.presentation>[K]
  ) {
    setDraft((d) => ({ ...d, presentation: { ...(d.presentation ?? {}), [k]: v } }));
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <Label>Title</Label>
          <Input
            value={draft.title ?? ""}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            placeholder="Chart title"
          />
        </div>
        <div>
          <Label>Chart type</Label>
          <select
            value={draft.chart_type}
            onChange={(e) => setDraft({ ...draft, chart_type: e.target.value as ChartType })}
            className={selectClass}
          >
            {ALL_CHART_TYPES.filter((c) => validTypes.includes(c.value)).map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>

        <ColumnSelect
          label="X column"
          value={draft.encoding.x ?? ""}
          options={pickerFor(columns, "x", draft.chart_type)}
          onChange={(v) => setEnc("x", v || undefined)}
        />
        <ColumnSelect
          label="Y column"
          value={draft.encoding.y ?? ""}
          options={pickerFor(columns, "y", draft.chart_type)}
          onChange={(v) => setEnc("y", v || undefined)}
        />
        <ColumnSelect
          label="Color column"
          value={draft.encoding.color ?? ""}
          options={pickerFor(columns, "color", draft.chart_type)}
          onChange={(v) => setEnc("color", v || undefined)}
        />
        <div>
          <Label>Aggregation</Label>
          <select
            value={draft.encoding.agg ?? "mean"}
            onChange={(e) => setEnc("agg", e.target.value)}
            className={selectClass}
          >
            {AGGS.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </div>
      </div>

      <fieldset className="space-y-3 rounded-md border bg-[var(--color-bg)]/40 p-3">
        <legend className="px-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
          Presentation (no refetch)
        </legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label>Palette</Label>
            <select
              value={draft.presentation?.palette ?? "default"}
              onChange={(e) => setPres("palette", e.target.value)}
              className={selectClass}
            >
              {PALETTE_NAMES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.presentation?.legend ?? false}
                onChange={(e) => setPres("legend", e.target.checked)}
                className="h-4 w-4 accent-[var(--color-accent)]"
              />
              Show legend
            </label>
          </div>
          <div>
            <Label>X-axis label</Label>
            <Input
              value={draft.presentation?.x_label ?? ""}
              onChange={(e) => setPres("x_label", e.target.value)}
              placeholder="Override (empty = column name)"
            />
          </div>
          <div>
            <Label>Y-axis label</Label>
            <Input
              value={draft.presentation?.y_label ?? ""}
              onChange={(e) => setPres("y_label", e.target.value)}
              placeholder="Override (empty = column name)"
            />
          </div>
        </div>
      </fieldset>

      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={() => onApply(draft)}>Apply</Button>
      </div>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="mb-1 block text-xs text-[var(--color-muted)]">{children}</label>;
}

const selectClass = "w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm";

function ColumnSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: ColumnProfile[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <Label>{label}</Label>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={selectClass}>
        <option value="">— none —</option>
        {options.map((c) => (
          <option key={c.name} value={c.name}>
            {c.name} ({(c.semantic_type as SemanticType)})
          </option>
        ))}
      </select>
    </div>
  );
}

/** Detect which fields force a /chart-data refetch when changed. */
export function specShapeChanged(a: ChartSpec, b: ChartSpec): boolean {
  // Title / labels / palette / legend are presentation-only.
  const keys: Array<keyof ChartSpec> = ["chart_type", "encoding", "bins", "top_n", "filters"];
  for (const k of keys) {
    if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) return true;
  }
  return false;
}
