"""Descriptive deep-dive (Phase 7A, tool 1).

Per selected column(s): count, mean, median, mode, std, variance, min/max,
range, IQR, quartiles, skewness, kurtosis, coefficient of variation, %% missing.
Plus histogram + box-plot chart data. Interpretation flags skew/heavy tails.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sci_stats

from ._common import WorkbenchError, chart, envelope, require_columns, require_min_rows


def _stats_for_column(s: pd.Series) -> dict[str, Any]:
    arr = pd.to_numeric(s, errors="coerce")
    total = len(arr)
    clean = arr.dropna()
    n = len(clean)
    if n == 0:
        raise WorkbenchError(
            f"column '{s.name}' has no numeric values to describe.",
            reason="no_numeric_values",
        )

    arr_sorted = clean.sort_values().to_numpy()
    q1, q2, q3 = np.quantile(arr_sorted, [0.25, 0.50, 0.75])
    mean = float(clean.mean())
    std = float(clean.std(ddof=1)) if n > 1 else 0.0
    mode_vals = clean.mode()
    mode = float(mode_vals.iloc[0]) if not mode_vals.empty else None
    cov = (std / mean) if mean not in (0, None) and not np.isnan(mean) else None

    return {
        "name": str(s.name),
        "count": int(n),
        "missing": int(total - n),
        "missing_pct": round((total - n) / total * 100.0, 2) if total else 0.0,
        "mean": mean,
        "median": float(q2),
        "mode": mode,
        "std": std,
        "variance": float(clean.var(ddof=1)) if n > 1 else 0.0,
        "min": float(arr_sorted[0]),
        "max": float(arr_sorted[-1]),
        "range": float(arr_sorted[-1] - arr_sorted[0]),
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(q3 - q1),
        "skewness": float(sci_stats.skew(arr_sorted)) if n > 2 else 0.0,
        "kurtosis": float(sci_stats.kurtosis(arr_sorted)) if n > 3 else 0.0,
        "coef_variation": float(cov) if cov is not None else None,
    }


def _histogram(s: pd.Series, bins: int = 30) -> dict[str, Any]:
    arr = pd.to_numeric(s, errors="coerce").dropna().to_numpy()
    counts, edges = np.histogram(arr, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return {
        "x": [float(v) for v in centers],
        "y": [int(v) for v in counts],
        "edges": [float(v) for v in edges],
    }


def _box(s: pd.Series) -> dict[str, Any]:
    arr = pd.to_numeric(s, errors="coerce").dropna()
    return {"name": str(s.name), "values": arr.tolist()}


def _interpretation_for(stats: dict[str, Any]) -> str:
    name = stats["name"]
    parts: list[str] = []
    parts.append(
        f"`{name}` has {stats['count']:,} non-null values "
        f"(mean {stats['mean']:.3g}, median {stats['median']:.3g}, std {stats['std']:.3g})."
    )
    skew = stats["skewness"]
    if abs(skew) > 1:
        direction = "right" if skew > 0 else "left"
        parts.append(
            f"The distribution is heavily {direction}-skewed (skewness = {skew:.2f}); "
            "the median is more representative than the mean."
        )
    elif abs(skew) > 0.5:
        direction = "right" if skew > 0 else "left"
        parts.append(f"The distribution is moderately {direction}-skewed (skewness = {skew:.2f}).")
    kurt = stats["kurtosis"]
    if kurt > 3:
        parts.append(f"Heavy tails relative to a normal distribution (excess kurtosis = {kurt:.2f}).")
    elif kurt < -1:
        parts.append(f"Light tails / flat distribution (excess kurtosis = {kurt:.2f}).")
    if stats["missing"] > 0:
        parts.append(f"{stats['missing_pct']:.1f}% of values are missing.")
    cov = stats["coef_variation"]
    if cov is not None and cov > 1:
        parts.append("Coefficient of variation > 1: very high relative dispersion.")
    return " ".join(parts)


def run_describe(df: pd.DataFrame, columns: list[str], *, bins: int = 30) -> dict[str, Any]:
    if not columns:
        raise WorkbenchError("Pick at least one column to describe.", reason="missing_columns")
    require_columns(df, columns)
    require_min_rows(len(df), minimum=5, what="describe")

    per_col: list[dict[str, Any]] = []
    charts_out: list[dict[str, Any]] = []
    for c in columns:
        st = _stats_for_column(df[c])
        per_col.append(st)
        charts_out.append(chart(
            title=f"Distribution of {c}",
            chart_type="histogram",
            encoding={"x": c},
            data=_histogram(df[c], bins=bins),
        ))
        charts_out.append(chart(
            title=f"Spread of {c}",
            chart_type="box",
            encoding={"y": c},
            data=_box(df[c]),
        ))

    interpretation = "\n".join(_interpretation_for(s) for s in per_col)
    return envelope(
        result={"columns": per_col, "n_rows": int(len(df))},
        charts=charts_out,
        interpretation=interpretation,
    )


__all__ = ["run_describe"]
