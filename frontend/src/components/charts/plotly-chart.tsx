"use client";

import dynamic from "next/dynamic";
import { forwardRef, useImperativeHandle, useMemo, useRef } from "react";
import type { ChartDataResponse, ChartSpec } from "@/types";
import { type ChartTheme, paletteFor, useChartTheme } from "./theme";

// Plotly is huge and uses window; never SSR.
const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <ChartSkeleton />,
});

function ChartSkeleton() {
  return (
    <div className="flex h-full w-full items-center justify-center text-xs text-[var(--color-muted)]">
      Loading chart…
    </div>
  );
}

export interface PlotlyChartHandle {
  toImage: () => Promise<string | null>;
}

interface Props {
  spec: ChartSpec;
  data: ChartDataResponse;
  height?: number;
}

function baseLayout(spec: ChartSpec, theme: ChartTheme) {
  const p = spec.presentation ?? {};
  const palette = paletteFor(p.palette);
  return {
    paper_bgcolor: theme.paper,
    plot_bgcolor: theme.bg,
    font: { color: theme.fg, family: theme.font, size: 11 },
    margin: { t: 30, r: 16, b: 40, l: 50 },
    xaxis: {
      gridcolor: theme.border,
      zerolinecolor: theme.border,
      tickcolor: theme.border,
      linecolor: theme.border,
      title: p.x_label ? { text: p.x_label, font: { color: theme.muted } } : undefined,
    },
    yaxis: {
      gridcolor: theme.border,
      zerolinecolor: theme.border,
      tickcolor: theme.border,
      linecolor: theme.border,
      title: p.y_label ? { text: p.y_label, font: { color: theme.muted } } : undefined,
    },
    colorway: palette,
    showlegend: p.legend ?? false,
    legend: {
      font: { color: theme.muted },
      bgcolor: "rgba(0,0,0,0)",
    },
  } as Record<string, unknown>;
}

// eslint-disable-next-line react/display-name
export const PlotlyChart = forwardRef<PlotlyChartHandle, Props>(({ spec, data, height = 320 }, ref) => {
  const plotRef = useRef<{ el?: HTMLElement | null }>({});
  const theme = useChartTheme();

  useImperativeHandle(ref, () => ({
    async toImage() {
      const Plotly = (await import("plotly.js-dist-min")).default;
      const el = plotRef.current.el;
      if (!el) return null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return Plotly.toImage(el as any, { format: "png", width: 1200, height: 700 });
    },
  }));

  const { traces, layout } = useMemo(
    () => buildPlotlyConfig(spec, data, theme),
    [spec, data, theme],
  );

  return (
    <Plot
      data={traces}
      layout={{
        ...layout,
        title: spec.title ? { text: spec.title, font: { color: theme.fg } } : undefined,
        autosize: true,
        height,
      }}
      useResizeHandler
      style={{ width: "100%", height }}
      config={{ displayModeBar: false, responsive: true }}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onInitialized={(_fig: unknown, gd: any) => (plotRef.current.el = gd)}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onUpdate={(_fig: unknown, gd: any) => (plotRef.current.el = gd)}
    />
  );
});

// ---------------------------------------------------------------------------
// Per chart-type config
// ---------------------------------------------------------------------------

interface PlotlyConfig {
  traces: Array<Record<string, unknown>>;
  layout: Record<string, unknown>;
}

function buildPlotlyConfig(
  spec: ChartSpec,
  data: ChartDataResponse,
  theme: ChartTheme,
): PlotlyConfig {
  const layout = baseLayout(spec, theme);
  const palette = paletteFor(spec.presentation?.palette);

  switch (spec.chart_type) {
    case "histogram": {
      const d = data.data as { x: number[]; y: number[] };
      return {
        traces: [{
          type: "bar",
          x: d.x,
          y: d.y,
          marker: { color: palette[0] },
        }],
        layout: {
          ...layout,
          xaxis: {
            ...(layout.xaxis as object),
            title: { text: spec.encoding.x, font: { color: theme.muted } },
          },
          yaxis: {
            ...(layout.yaxis as object),
            title: { text: "count", font: { color: theme.muted } },
          },
          bargap: 0.02,
        },
      };
    }
    case "box": {
      const d = data.data as { name: string; values: number[] };
      return {
        traces: [{
          type: "box",
          y: d.values,
          name: d.name,
          marker: { color: palette[0] },
          boxmean: true,
        }],
        layout,
      };
    }
    case "violin":
    case "kde": {
      const d = data.data as { name: string; values: number[] };
      return {
        traces: [{
          type: "violin",
          y: d.values,
          name: d.name,
          marker: { color: palette[0] },
          line: { color: palette[0] },
          box: { visible: true },
          meanline: { visible: true },
        }],
        layout,
      };
    }
    default:
      return {
        traces: [{ type: "scatter", x: [], y: [] }],
        layout,
      };
  }
}
