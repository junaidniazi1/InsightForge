"""Shared helpers for the workbench tools.

Every tool returns the same envelope so the frontend treats them uniformly:

    {
      "result":         { ... numbers, tables ... },
      "charts":         [ { "title": str, "spec": ChartSpec, "data": ChartData } ],
      "interpretation": "Plain-language description of what was found."
    }

Charts are pre-rendered into the Phase-4 envelope so the frontend can pass them
directly to the `<Chart>` router without a second backend round-trip.
"""

from __future__ import annotations

from typing import Any

from ..chart_engine import engine_for
from ..data_loader import to_json_safe

# Hard ceiling so a 5M-row file can't OOM the worker. Tools cap input here.
WORKBENCH_MAX_ROWS = 200_000


class WorkbenchError(ValueError):
    """Domain error — user-fixable. Router maps to 400 with a clear message."""

    def __init__(self, message: str, *, reason: str = "bad_input") -> None:
        super().__init__(message)
        self.reason = reason


def require_min_rows(n: int, *, minimum: int, what: str) -> None:
    if n < minimum:
        raise WorkbenchError(
            f"{what} needs at least {minimum} rows; got {n}.",
            reason="too_few_rows",
        )


def require_columns(df, columns: list[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise WorkbenchError(
            f"column(s) not found in this dataset: {missing}",
            reason="missing_columns",
        )


def chart(
    *,
    title: str,
    chart_type: str,
    data: dict[str, Any],
    encoding: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    presentation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a single chart payload the Phase-4 router can render directly."""
    spec: dict[str, Any] = {
        "chart_type": chart_type,
        "encoding": encoding or {},
        "title": title,
    }
    if presentation:
        spec["presentation"] = presentation
    return {
        "title": title,
        "spec": spec,
        "data": {
            "chart_type": chart_type,
            "engine": engine_for(chart_type),
            "data": data,
            "meta": meta or {},
        },
    }


def envelope(
    *,
    result: dict[str, Any],
    charts: list[dict[str, Any]] | None = None,
    interpretation: str = "",
) -> dict[str, Any]:
    return to_json_safe({
        "result": result,
        "charts": charts or [],
        "interpretation": interpretation,
    })


__all__ = [
    "WORKBENCH_MAX_ROWS",
    "WorkbenchError",
    "require_min_rows",
    "require_columns",
    "chart",
    "envelope",
]
