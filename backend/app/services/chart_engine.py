"""Shared CHART_ENGINE map — the single source of truth for which library
renders which chart type. The frontend's chart-router reads `engine` off the
chart spec; the backend stamps it onto every recommendation and chart-data
response. Both sides agree because they read this one map.

Rule of thumb:
  - Plotly: statistical / distribution / 3D (its strength).
  - ECharts: high-perf canvas charts and heatmaps (its strength).
"""

from __future__ import annotations

CHART_ENGINE: dict[str, str] = {
    # Plotly — distribution / statistical / 3D
    "histogram": "plotly",
    "box": "plotly",
    "violin": "plotly",
    "kde": "plotly",
    "scatter_3d": "plotly",
    # ECharts — perf / matrix / multi-series
    "heatmap": "echarts",
    "scatter": "echarts",
    "line": "echarts",
    "bar": "echarts",
    "pie": "echarts",
}

# KPI isn't a chart, but the recommender returns it through the same envelope.
KPI_ENGINE = "kpi"


def engine_for(chart_type: str) -> str:
    if chart_type == "kpi":
        return KPI_ENGINE
    try:
        return CHART_ENGINE[chart_type]
    except KeyError as exc:
        raise ValueError(f"unknown chart_type: {chart_type}") from exc


__all__ = ["CHART_ENGINE", "KPI_ENGINE", "engine_for"]
