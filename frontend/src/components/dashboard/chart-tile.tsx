"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { apiPost } from "@/lib/api";
import type {
  ChartDataResponse,
  ChartSpec,
  ColumnProfile,
  FilterClause,
} from "@/types";
import { Chart, type ChartHandle } from "@/components/charts/chart";
import { ChartEditor, specShapeChanged } from "@/components/charts/chart-editor";
import { SkeletonLine } from "@/components/ui/skeleton";

interface Props {
  datasetId: string;
  versionId: string | null;
  spec: ChartSpec;
  filters: FilterClause[];
  // Compact thumbnail mode (used in the suggestions gallery).
  compact?: boolean;
  height?: number;
  onRemove?: () => void;
  showHeader?: boolean;
  // Phase 6 — edit/save flow.
  onEdit?: (next: ChartSpec) => void;
  columns?: ColumnProfile[];
  // Phase 6 — let the report export reach the chart's toImage handle.
  registerHandle?: (handle: ChartHandle | null) => void;
}

export function ChartTile({
  datasetId,
  versionId,
  spec,
  filters,
  compact = false,
  height,
  onRemove,
  showHeader = true,
  onEdit,
  columns,
  registerHandle,
}: Props) {
  const [data, setData] = useState<ChartDataResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const chartRef = useRef<ChartHandle>(null);

  // Measure the body so the chart fills its grid cell instead of sitting in a
  // hardcoded 260px box. Without this, dragging a dashboard tile taller leaves
  // empty space below the chart; shorter screens clip the chart.
  const bodyRef = useRef<HTMLDivElement>(null);
  const [bodyHeight, setBodyHeight] = useState<number | null>(null);

  useEffect(() => {
    const el = bodyRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        const h = Math.round(e.contentRect.height);
        // Ignore the first sub-pixel flicker during mount.
        if (h > 8) setBodyHeight(h);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const fullSpec = useMemo<ChartSpec>(
    () => ({ ...spec, filters }),
    [spec, filters]
  );

  // Track the last spec shape so presentation-only edits don't refetch.
  const lastShapeRef = useRef<ChartSpec | null>(null);

  useEffect(() => {
    // Skip fetch when ONLY presentation fields changed (title/labels/palette/legend).
    if (lastShapeRef.current && !specShapeChanged(lastShapeRef.current, fullSpec)) {
      lastShapeRef.current = fullSpec;
      return;
    }
    lastShapeRef.current = fullSpec;

    let cancelled = false;
    setLoading(true);
    setError(null);
    const q = versionId ? `?version_id=${versionId}` : "";
    apiPost<ChartDataResponse>(`/datasets/${datasetId}/chart-data${q}`, fullSpec)
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, versionId, JSON.stringify(fullSpec)]);

  // Forward the inner chart's PNG handle so the report export can reach it.
  useEffect(() => {
    if (!registerHandle) return;
    registerHandle(chartRef.current);
    return () => registerHandle(null);
    // chartRef.current updates after Chart mounts; we re-register on each render.
  }, [registerHandle, data]);

  async function exportPng() {
    const url = await chartRef.current?.toImage();
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${spec.title ?? spec.chart_type}.png`;
    a.click();
  }

  return (
    <div className="flex h-full flex-col rounded-lg border bg-[var(--color-panel)]">
      {showHeader && (
        <header className="drag-handle flex shrink-0 items-center justify-between gap-2 border-b px-3 py-2 cursor-move">
          <div className="min-w-0">
            <p className="truncate text-xs font-medium">{spec.title ?? spec.chart_type}</p>
            {data?.meta?.sampled === true && (
              <p className="text-[10px] text-amber-400">
                sampled to {String((data.meta as Record<string, unknown>).sample_cap ?? "5000")} points
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {onEdit && (
              <button
                onClick={() => setEditing(true)}
                className="rounded border px-1.5 py-0.5 text-[10px] text-[var(--color-muted)] hover:text-[var(--color-fg)]"
                title="Edit chart"
                type="button"
                onMouseDown={(e) => e.stopPropagation()}
              >
                Edit
              </button>
            )}
            {data?.engine !== "kpi" && data && (
              <button
                onClick={exportPng}
                className="rounded border px-1.5 py-0.5 text-[10px] text-[var(--color-muted)] hover:text-[var(--color-fg)]"
                title="Export PNG"
                type="button"
                onMouseDown={(e) => e.stopPropagation()}
              >
                PNG
              </button>
            )}
            {onRemove && (
              <button
                onClick={onRemove}
                className="rounded border border-[var(--color-danger)]/40 px-1.5 py-0.5 text-[10px] text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10"
                title="Remove"
                type="button"
                onMouseDown={(e) => e.stopPropagation()}
              >
                ✕
              </button>
            )}
          </div>
        </header>
      )}
      <div ref={bodyRef} className="min-h-0 flex-1 overflow-hidden">
        {editing && onEdit && columns ? (
          <div className="h-full overflow-y-auto p-3">
            <ChartEditor
              spec={spec}
              columns={columns}
              onCancel={() => setEditing(false)}
              onApply={(next) => {
                onEdit(next);
                setEditing(false);
              }}
            />
          </div>
        ) : error ? (
          <p className="p-3 text-xs text-[var(--color-danger)]">{error}</p>
        ) : loading || !data ? (
          <div className="flex h-full flex-col gap-3 p-4">
            <SkeletonLine width="40%" height={10} />
            <div className="flex-1 animate-pulse rounded-md bg-[var(--color-border)]" />
          </div>
        ) : (
          // Height: explicit prop wins; otherwise the live measured body
          // height; otherwise a sensible default for the very first paint
          // before ResizeObserver fires.
          <Chart
            ref={chartRef}
            spec={fullSpec}
            data={data}
            height={height ?? bodyHeight ?? (compact ? 140 : 260)}
          />
        )}
      </div>
    </div>
  );
}
