"""Correlation explorer (Phase 7A, tool 2).

Full matrix in Pearson / Spearman / Kendall + a ranked list of the strongest
pairs with p-values. Heatmap-ready output. Interpretation calls out the top
relationships and warns correlation != causation.
"""

from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats as sci_stats

from ._common import WorkbenchError, chart, envelope, require_columns, require_min_rows


Method = Literal["pearson", "spearman", "kendall"]

_METHODS = ("pearson", "spearman", "kendall")
_PAIRWISE_CAPS = {"max_columns": 25, "top_pairs": 12}


def _pairwise_pvalue(x: np.ndarray, y: np.ndarray, method: Method) -> tuple[float, float]:
    if method == "pearson":
        r, p = sci_stats.pearsonr(x, y)
    elif method == "spearman":
        r, p = sci_stats.spearmanr(x, y)
    elif method == "kendall":
        r, p = sci_stats.kendalltau(x, y)
    else:  # pragma: no cover - validated upstream
        raise WorkbenchError(f"unknown correlation method: {method}", reason="bad_method")
    return float(r), float(p)


def _safe_floats(arr: np.ndarray) -> list[float | None]:
    out: list[float | None] = []
    for v in arr:
        vf = float(v)
        out.append(None if math.isnan(vf) or math.isinf(vf) else vf)
    return out


def _interpretation(top_pairs: list[dict[str, Any]], method: Method, n_cols: int) -> str:
    if not top_pairs:
        return "No correlations could be computed — at least two numeric columns with overlapping data are needed."
    label = {"pearson": "Pearson", "spearman": "Spearman", "kendall": "Kendall"}[method]
    parts = [f"{label} correlation matrix across {n_cols} numeric columns."]
    strong = [p for p in top_pairs if abs(p["r"]) >= 0.7 and p["p_value"] < 0.05]
    moderate = [
        p for p in top_pairs
        if 0.4 <= abs(p["r"]) < 0.7 and p["p_value"] < 0.05
    ]
    if strong:
        first = strong[0]
        parts.append(
            f"Strongest relationship: `{first['a']}` ↔ `{first['b']}` "
            f"(r = {first['r']:.2f}, p = {first['p_value']:.1e})."
        )
        if len(strong) > 1:
            parts.append(f"{len(strong)} other strong pair(s) found.")
    elif moderate:
        first = moderate[0]
        parts.append(
            f"Strongest relationship is moderate: `{first['a']}` ↔ `{first['b']}` "
            f"(r = {first['r']:.2f}, p = {first['p_value']:.1e})."
        )
    else:
        parts.append("No strong correlations detected at the conventional thresholds.")
    parts.append("Remember: correlation does not imply causation.")
    return " ".join(parts)


def run_correlation(
    df: pd.DataFrame,
    columns: list[str],
    *,
    method: Method = "pearson",
) -> dict[str, Any]:
    if method not in _METHODS:
        raise WorkbenchError(
            f"method must be one of {_METHODS}; got {method!r}", reason="bad_method"
        )
    if not columns:
        # Auto-pick all numeric columns.
        columns = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    require_columns(df, columns)
    if len(columns) > _PAIRWISE_CAPS["max_columns"]:
        columns = columns[: _PAIRWISE_CAPS["max_columns"]]
    if len(columns) < 2:
        raise WorkbenchError(
            "Correlation needs at least 2 numeric columns.", reason="too_few_columns"
        )
    require_min_rows(len(df), minimum=5, what="correlation")

    num = df[columns].apply(pd.to_numeric, errors="coerce")
    matrix = num.corr(method=method).values

    safe_matrix: list[list[float | None]] = []
    for row in matrix:
        safe_matrix.append(_safe_floats(row))

    # Ranked pairs (only upper triangle).
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(columns):
        x = num[a].to_numpy()
        for j in range(i + 1, len(columns)):
            b = columns[j]
            y = num[b].to_numpy()
            mask = ~(np.isnan(x) | np.isnan(y))
            xc, yc = x[mask], y[mask]
            if len(xc) < 3 or np.nanstd(xc) == 0 or np.nanstd(yc) == 0:
                continue
            r, p = _pairwise_pvalue(xc, yc, method)
            if math.isnan(r):
                continue
            pairs.append({
                "a": a,
                "b": b,
                "r": r,
                "p_value": p,
                "n": int(len(xc)),
                "significant": bool(p < 0.05),
            })

    pairs.sort(key=lambda p: abs(p["r"]), reverse=True)
    top_pairs = pairs[: _PAIRWISE_CAPS["top_pairs"]]

    heatmap = chart(
        title=f"{method.capitalize()} correlation",
        chart_type="heatmap",
        encoding={"columns": columns, "method": method},
        data={"columns": columns, "values": safe_matrix, "method": method},
    )

    return envelope(
        result={"method": method, "columns": columns, "matrix": safe_matrix, "top_pairs": top_pairs},
        charts=[heatmap],
        interpretation=_interpretation(top_pairs, method, len(columns)),
    )


__all__ = ["run_correlation"]
