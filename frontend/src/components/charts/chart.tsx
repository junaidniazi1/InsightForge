"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import type { ChartDataResponse, ChartSpec } from "@/types";
import { EChartsChart, type EChartsChartHandle } from "./echarts-chart";
import { KpiCard } from "./kpi-card";
import { PlotlyChart, type PlotlyChartHandle } from "./plotly-chart";

export interface ChartHandle {
  toImage: () => Promise<string | null>;
}

interface Props {
  spec: ChartSpec;
  data: ChartDataResponse;
  height?: number;
}

/**
 * The single chart router. Reads `data.engine` (stamped by the backend per the
 * shared CHART_ENGINE map) and renders the right component. No component
 * downstream needs to know which engine to use.
 */
// eslint-disable-next-line react/display-name
export const Chart = forwardRef<ChartHandle, Props>(({ spec, data, height }, ref) => {
  const plotlyRef = useRef<PlotlyChartHandle>(null);
  const echartsRef = useRef<EChartsChartHandle>(null);

  useImperativeHandle(ref, () => ({
    async toImage() {
      if (data.engine === "plotly") return plotlyRef.current?.toImage() ?? null;
      if (data.engine === "echarts") return echartsRef.current?.toImage() ?? null;
      return null;
    },
  }));

  if (data.engine === "kpi") return <KpiCard spec={spec} data={data} />;
  if (data.engine === "plotly") {
    return <PlotlyChart ref={plotlyRef} spec={spec} data={data} height={height} />;
  }
  if (data.engine === "echarts") {
    return <EChartsChart ref={echartsRef} spec={spec} data={data} height={height} />;
  }
  return (
    <div className="flex h-full items-center justify-center text-xs text-[var(--color-danger)]">
      unknown engine: {String(data.engine)}
    </div>
  );
});
