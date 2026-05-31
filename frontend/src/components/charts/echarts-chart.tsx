"use client";

import dynamic from "next/dynamic";
import { forwardRef, useImperativeHandle, useMemo, useRef } from "react";
import type EChartsReactCore from "echarts-for-react";
import type { ChartDataResponse, ChartSpec } from "@/types";
import { type ChartTheme, paletteFor, useChartTheme } from "./theme";

// dynamic() strips the ref type; restore it so refs to getEchartsInstance() work.
const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center text-xs text-[var(--color-muted)]">
      Loading chart…
    </div>
  ),
}) as unknown as typeof EChartsReactCore;

export interface EChartsChartHandle {
  toImage: () => Promise<string | null>;
}

interface Props {
  spec: ChartSpec;
  data: ChartDataResponse;
  height?: number;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type EChartsRef = { getEchartsInstance?: () => any };

// eslint-disable-next-line react/display-name
export const EChartsChart = forwardRef<EChartsChartHandle, Props>(({ spec, data, height = 320 }, ref) => {
  const innerRef = useRef<EChartsRef | null>(null);
  const theme = useChartTheme();

  useImperativeHandle(ref, () => ({
    async toImage() {
      const inst = innerRef.current?.getEchartsInstance?.();
      if (!inst) return null;
      return inst.getDataURL({
        type: "png",
        pixelRatio: 2,
        backgroundColor: theme.paper,
      });
    },
  }));

  const option = useMemo(
    () => buildEChartsOption(spec, data, theme),
    [spec, data, theme],
  );

  return (
    <ReactECharts
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ref={(r: any) => (innerRef.current = r)}
      option={option}
      style={{ width: "100%", height }}
      notMerge
      lazyUpdate
      opts={{ renderer: "canvas" }}
    />
  );
});

// ---------------------------------------------------------------------------
// Per chart-type options
// ---------------------------------------------------------------------------

function commonOption(spec: ChartSpec, theme: ChartTheme): Record<string, unknown> {
  const p = spec.presentation ?? {};
  const palette = paletteFor(p.palette);
  return {
    backgroundColor: theme.paper,
    color: palette,
    textStyle: { color: theme.fg, fontFamily: theme.font },
    title: spec.title
      ? { text: spec.title, left: 8, top: 4, textStyle: { color: theme.fg, fontSize: 13 } }
      : undefined,
    grid: { left: 50, right: 16, top: spec.title ? 36 : 12, bottom: 40, containLabel: true },
    tooltip: {
      trigger: "item",
      backgroundColor: theme.panel,
      borderColor: theme.border,
      textStyle: { color: theme.fg },
    },
    legend: p.legend ? { show: true, textStyle: { color: theme.muted } } : { show: false },
  };
}

function axisLabelOverride(spec: ChartSpec, role: "x" | "y"): string | undefined {
  const p = spec.presentation ?? {};
  return role === "x" ? p.x_label : p.y_label;
}

function axisStyle(theme: ChartTheme) {
  return {
    axisLine: { lineStyle: { color: theme.border } },
    axisLabel: { color: theme.muted },
    splitLine: { lineStyle: { color: theme.border } },
  };
}

// Diverging colour ramp for correlation heatmaps — picks indigo↔rose endpoints
// with a theme-appropriate neutral midpoint.
function heatmapRamp(theme: ChartTheme): string[] {
  // -1 → rose, 0 → neutral border (so cells near zero blend in), +1 → indigo
  return ["#e11d48", theme.border, "#4f46e5"];
}

function buildEChartsOption(
  spec: ChartSpec,
  data: ChartDataResponse,
  theme: ChartTheme,
): Record<string, unknown> {
  const base = commonOption(spec, theme);
  const palette = paletteFor(spec.presentation?.palette);
  const xLabel = axisLabelOverride(spec, "x");
  const yLabel = axisLabelOverride(spec, "y");
  const ax = axisStyle(theme);

  switch (spec.chart_type) {
    case "bar": {
      const d = data.data as { categories: string[]; series: { name: string; values: number[] }[] };
      return {
        ...base,
        tooltip: { ...(base.tooltip as object), trigger: "axis" },
        xAxis: { type: "category", data: d.categories, ...ax, name: xLabel, nameLocation: "middle", nameGap: 28 },
        yAxis: { type: "value", ...ax, name: yLabel, nameLocation: "middle", nameGap: 40 },
        series: d.series.map((s, i) => ({
          name: s.name,
          type: "bar",
          data: s.values,
          itemStyle: { color: palette[i % palette.length] },
        })),
      };
    }
    case "line": {
      const d = data.data as { x: string[]; series: { name: string; values: number[] }[] };
      return {
        ...base,
        tooltip: { ...(base.tooltip as object), trigger: "axis" },
        xAxis: { type: "category", data: d.x, ...ax, boundaryGap: false, name: xLabel, nameLocation: "middle", nameGap: 28 },
        yAxis: { type: "value", ...ax, name: yLabel, nameLocation: "middle", nameGap: 40 },
        series: d.series.map((s, i) => ({
          name: s.name,
          type: "line",
          smooth: true,
          showSymbol: false,
          data: s.values,
          lineStyle: { color: palette[i % palette.length], width: 2 },
        })),
      };
    }
    case "pie": {
      const d = data.data as { categories: string[]; values: number[] };
      return {
        ...base,
        tooltip: { ...(base.tooltip as object), trigger: "item" },
        series: [{
          type: "pie",
          radius: ["45%", "70%"],
          data: d.categories.map((c, i) => ({ name: c, value: d.values[i] })),
          label: { color: theme.muted, fontSize: 11 },
          labelLine: { lineStyle: { color: theme.border } },
        }],
      };
    }
    case "scatter": {
      const d = data.data as { x: number[]; y: number[] };
      const points = d.x.map((xv, i) => [xv, d.y[i]]);
      return {
        ...base,
        tooltip: { ...(base.tooltip as object), trigger: "item" },
        xAxis: { type: "value", ...ax, name: xLabel ?? spec.encoding.x, nameLocation: "middle", nameGap: 28 },
        yAxis: { type: "value", ...ax, name: yLabel ?? spec.encoding.y, nameLocation: "middle", nameGap: 36 },
        dataZoom: [
          { type: "inside", xAxisIndex: 0 },
          { type: "inside", yAxisIndex: 0 },
        ],
        series: [{
          type: "scatter",
          data: points,
          symbolSize: 4,
          itemStyle: { color: palette[0], opacity: 0.7 },
        }],
      };
    }
    case "heatmap": {
      const d = data.data as { columns: string[]; values: number[][] };
      const points: Array<[number, number, number | null]> = [];
      for (let i = 0; i < d.values.length; i++) {
        for (let j = 0; j < d.values[i].length; j++) {
          points.push([j, i, d.values[i][j]]);
        }
      }
      return {
        ...base,
        tooltip: { ...(base.tooltip as object), position: "top" },
        grid: { ...(base.grid as object), top: 60 },
        xAxis: {
          type: "category",
          data: d.columns,
          ...ax,
          axisLabel: { ...ax.axisLabel, rotate: 30 },
        },
        yAxis: { type: "category", data: d.columns, ...ax },
        visualMap: {
          min: -1, max: 1,
          calculable: true,
          orient: "vertical",
          right: 10,
          top: "middle",
          inRange: { color: heatmapRamp(theme) },
          textStyle: { color: theme.muted },
        },
        series: [{
          type: "heatmap",
          data: points,
          label: {
            show: d.columns.length <= 12,
            color: theme.fg,
            formatter: (p: { value: [number, number, number | null] }) =>
              p.value[2] == null ? "" : (p.value[2] as number).toFixed(2),
            fontSize: 10,
          },
        }],
      };
    }
    default:
      return {
        ...base,
        xAxis: { type: "category", data: [], ...ax },
        yAxis: { type: "value", ...ax },
        series: [],
      };
  }
}
