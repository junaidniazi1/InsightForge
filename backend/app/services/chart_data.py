"""Chart data: turn a chart spec + DataFrame into chart-ready JSON.

The frontend never gets the whole dataset — it gets aggregated/binned/sampled
arrays sized to render. Each chart type produces its own payload shape; the
chart-router on the frontend already knows which engine consumes which shape.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .chart_engine import engine_for
from .data_loader import to_json_safe

# --- caps -------------------------------------------------------------------
SCATTER_POINT_CAP = 5000
HEATMAP_MAX_COLS = 25            # avoid 100×100 correlation messes
TOP_VALUES_PER_FILTER = 200      # capped distinct values in filter options


# =============================================================================
# Filtering
# =============================================================================

def apply_filters(df: pd.DataFrame, filters: list[dict[str, Any]] | None) -> pd.DataFrame:
    if not filters:
        return df
    mask = pd.Series(True, index=df.index)
    for f in filters:
        col = f.get("column")
        if not col or col not in df.columns:
            continue
        ftype = f.get("type", "in")
        if ftype == "in":
            vals = f.get("values") or []
            if vals:
                mask &= df[col].isin(vals)
        elif ftype == "range":
            lo, hi = f.get("min"), f.get("max")
            s = df[col]
            if pd.api.types.is_datetime64_any_dtype(s) or _looks_like_datetime(s):
                s = pd.to_datetime(s, errors="coerce")
                if lo is not None:
                    mask &= s >= pd.to_datetime(lo, errors="coerce")
                if hi is not None:
                    mask &= s <= pd.to_datetime(hi, errors="coerce")
            else:
                s = pd.to_numeric(s, errors="coerce")
                if lo is not None:
                    mask &= s >= float(lo)
                if hi is not None:
                    mask &= s <= float(hi)
    return df[mask]


def _looks_like_datetime(s: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    if not pd.api.types.is_object_dtype(s):
        return False
    try:
        sample = s.dropna().head(20)
        if len(sample) == 0:
            return False
        coerced = pd.to_datetime(sample, errors="coerce")
        return coerced.notna().mean() >= 0.8
    except Exception:  # noqa: BLE001
        return False


# =============================================================================
# Aggregation helpers
# =============================================================================

_AGG_FNS = {"mean", "sum", "count", "min", "max", "median"}


def _aggregate(group: pd.Series, agg: str) -> Any:
    if agg == "count":
        return int(group.count())
    if agg == "count_rows":
        return int(len(group))
    s = pd.to_numeric(group, errors="coerce")
    if agg == "mean":
        return float(s.mean())
    if agg == "sum":
        return float(s.sum())
    if agg == "min":
        return float(s.min())
    if agg == "max":
        return float(s.max())
    if agg == "median":
        return float(s.median())
    raise ValueError(f"unsupported agg: {agg}")


def _pick_resample_freq(s: pd.Series) -> str:
    """Choose a sensible resample frequency from the datetime range."""
    s_clean = pd.to_datetime(s, errors="coerce").dropna()
    if len(s_clean) == 0:
        return "D"
    span_days = (s_clean.max() - s_clean.min()).days or 1
    if span_days <= 100:
        return "D"
    if span_days <= 365 * 2:
        return "W"
    if span_days <= 365 * 10:
        return "ME"
    return "YE"


# =============================================================================
# Per-chart builders
# =============================================================================

def _build_kpi(df: pd.DataFrame, encoding: dict[str, Any]) -> dict[str, Any]:
    agg = encoding.get("agg", "count_rows")
    if agg == "count_rows":
        return {"value": int(len(df)), "format": "integer"}
    y = encoding.get("y")
    if not y or y not in df.columns:
        raise ValueError(f"kpi needs y column; got {y!r}")
    val = _aggregate(df[y], agg)
    return {"value": val, "format": "number"}


def _build_histogram(df: pd.DataFrame, encoding: dict[str, Any], bins: int | None) -> dict[str, Any]:
    x = encoding["x"]
    if x not in df.columns:
        raise ValueError(f"column not found: {x}")
    arr = pd.to_numeric(df[x], errors="coerce").dropna().to_numpy()
    n_bins = bins or 30
    if len(arr) == 0:
        return {"x": [], "y": [], "edges": []}
    counts, edges = np.histogram(arr, bins=n_bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return {
        "x": [float(v) for v in centers],
        "y": [int(v) for v in counts],
        "edges": [float(v) for v in edges],
    }


def _build_box(df: pd.DataFrame, encoding: dict[str, Any]) -> dict[str, Any]:
    y = encoding.get("y") or encoding.get("x")
    if not y or y not in df.columns:
        raise ValueError(f"box needs a column; got {y!r}")
    arr = pd.to_numeric(df[y], errors="coerce").dropna()
    if len(arr) == 0:
        return {"name": y, "values": []}
    return {"name": str(y), "values": arr.tolist()}


def _build_scatter(df: pd.DataFrame, encoding: dict[str, Any]) -> dict[str, Any]:
    x, y = encoding["x"], encoding["y"]
    color = encoding.get("color")
    if x not in df.columns or y not in df.columns:
        raise ValueError(f"scatter needs x and y; got x={x!r}, y={y!r}")
    sub = df[[x, y] + ([color] if color and color in df.columns else [])].dropna()
    n = len(sub)
    sampled = False
    if n > SCATTER_POINT_CAP:
        sub = sub.sample(SCATTER_POINT_CAP, random_state=0)
        sampled = True
    payload: dict[str, Any] = {
        "x": pd.to_numeric(sub[x], errors="coerce").tolist(),
        "y": pd.to_numeric(sub[y], errors="coerce").tolist(),
        "n_rows": int(n),
        "sampled": sampled,
        "shown": int(len(sub)),
    }
    if color and color in df.columns:
        payload["color"] = sub[color].astype(str).tolist()
    return payload


def _build_line(df: pd.DataFrame, encoding: dict[str, Any]) -> dict[str, Any]:
    x, y = encoding["x"], encoding["y"]
    agg = encoding.get("agg", "mean")
    if x not in df.columns or y not in df.columns:
        raise ValueError(f"line needs x and y; got x={x!r}, y={y!r}")
    s = pd.to_datetime(df[x], errors="coerce")
    sub = pd.DataFrame({"_t": s, "_y": pd.to_numeric(df[y], errors="coerce")}).dropna()
    if len(sub) == 0:
        return {"x": [], "series": [{"name": str(y), "values": []}]}
    freq = _pick_resample_freq(sub["_t"])
    sub = sub.set_index("_t").sort_index()
    resampled = sub["_y"].resample(freq).agg(agg if agg in _AGG_FNS else "mean").dropna()
    return {
        "x": [t.isoformat() for t in resampled.index],
        "series": [{"name": str(y), "values": [float(v) for v in resampled.values]}],
        "freq": freq,
    }


def _build_bar(df: pd.DataFrame, encoding: dict[str, Any], top_n: int | None) -> dict[str, Any]:
    x = encoding["x"]
    if x not in df.columns:
        raise ValueError(f"column not found: {x}")
    agg = encoding.get("agg", "count")
    y = encoding.get("y")
    if agg == "count":
        vc = df[x].value_counts(dropna=False)
        if top_n:
            vc = vc.head(top_n)
        return {
            "categories": [str(v) for v in vc.index],
            "series": [{"name": "count", "values": [int(v) for v in vc.values]}],
        }
    if not y or y not in df.columns:
        raise ValueError(f"bar with agg={agg} needs y; got {y!r}")
    grouped = df.groupby(df[x].astype(str), dropna=False)[y].apply(lambda g: _aggregate(g, agg))
    grouped = grouped.sort_values(ascending=False)
    if top_n:
        grouped = grouped.head(top_n)
    return {
        "categories": [str(v) for v in grouped.index],
        "series": [{"name": f"{agg}({y})", "values": [float(v) for v in grouped.values]}],
    }


def _build_pie(df: pd.DataFrame, encoding: dict[str, Any]) -> dict[str, Any]:
    x = encoding["x"]
    if x not in df.columns:
        raise ValueError(f"column not found: {x}")
    vc = df[x].value_counts(dropna=False)
    return {
        "categories": [str(v) for v in vc.index],
        "values": [int(v) for v in vc.values],
    }


def _build_heatmap(df: pd.DataFrame, encoding: dict[str, Any]) -> dict[str, Any]:
    cols = encoding.get("columns")
    method = encoding.get("method", "pearson")
    if not cols:
        # Auto: pick all numeric columns we have.
        cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    cols = [c for c in cols if c in df.columns]
    if len(cols) > HEATMAP_MAX_COLS:
        cols = cols[:HEATMAP_MAX_COLS]
    if len(cols) < 2:
        return {"columns": cols, "values": []}
    num = df[cols].apply(pd.to_numeric, errors="coerce")
    corr = num.corr(method=method)
    matrix = corr.values
    safe: list[list[float | None]] = []
    for row in matrix:
        safe_row: list[float | None] = []
        for v in row:
            fv = float(v) if v is not None else None
            if fv is None or math.isnan(fv) or math.isinf(fv):
                safe_row.append(None)
            else:
                safe_row.append(fv)
        safe.append(safe_row)
    return {
        "columns": [str(c) for c in cols],
        "values": safe,
        "method": method,
    }


def _build_violin(df: pd.DataFrame, encoding: dict[str, Any]) -> dict[str, Any]:
    y = encoding.get("y") or encoding.get("x")
    if not y or y not in df.columns:
        raise ValueError(f"violin needs a column; got {y!r}")
    arr = pd.to_numeric(df[y], errors="coerce").dropna()
    return {"name": str(y), "values": arr.tolist()}


# =============================================================================
# Top-level dispatcher
# =============================================================================

_BUILDERS = {
    "histogram": lambda df, spec: _build_histogram(df, spec["encoding"], spec.get("bins")),
    "box": lambda df, spec: _build_box(df, spec["encoding"]),
    "violin": lambda df, spec: _build_violin(df, spec["encoding"]),
    "kde": lambda df, spec: _build_box(df, spec["encoding"]),   # KDE rendered from raw values by Plotly
    "scatter": lambda df, spec: _build_scatter(df, spec["encoding"]),
    "line": lambda df, spec: _build_line(df, spec["encoding"]),
    "bar": lambda df, spec: _build_bar(df, spec["encoding"], spec.get("top_n")),
    "pie": lambda df, spec: _build_pie(df, spec["encoding"]),
    "heatmap": lambda df, spec: _build_heatmap(df, spec["encoding"]),
    "kpi": lambda df, spec: _build_kpi(df, spec["encoding"]),
}


def build_chart_data(df: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    chart_type = spec["chart_type"]
    if chart_type not in _BUILDERS:
        raise ValueError(f"unsupported chart_type: {chart_type}")
    filtered = apply_filters(df, spec.get("filters"))
    payload = _BUILDERS[chart_type](filtered, spec)
    meta: dict[str, Any] = {
        "rows_after_filter": int(len(filtered)),
        "rows_total": int(len(df)),
    }
    if isinstance(payload, dict) and payload.get("sampled"):
        meta["sampled"] = True
        meta["sample_cap"] = SCATTER_POINT_CAP
    return to_json_safe({
        "chart_type": chart_type,
        "engine": engine_for(chart_type),
        "data": payload,
        "meta": meta,
    })


# =============================================================================
# Filter options
# =============================================================================

def build_filter_options(df: pd.DataFrame, profile_columns: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """For each filterable column, give the frontend everything it needs to
    render a control: kind, choices, or min/max."""
    type_by_name: dict[str, str] = {}
    if profile_columns:
        type_by_name = {c["name"]: c["semantic_type"] for c in profile_columns}

    out: list[dict[str, Any]] = []
    for c in df.columns:
        s = df[c]
        sem = type_by_name.get(c)
        if pd.api.types.is_datetime64_any_dtype(s) or sem == "datetime":
            s_dt = pd.to_datetime(s, errors="coerce").dropna()
            if len(s_dt) == 0:
                continue
            out.append({
                "column": str(c),
                "kind": "datetime_range",
                "min": s_dt.min().isoformat(),
                "max": s_dt.max().isoformat(),
            })
        elif pd.api.types.is_numeric_dtype(s) and sem != "boolean":
            arr = pd.to_numeric(s, errors="coerce").dropna()
            if len(arr) == 0:
                continue
            out.append({
                "column": str(c),
                "kind": "numeric_range",
                "min": float(arr.min()),
                "max": float(arr.max()),
            })
        else:
            uniq = s.dropna().unique()
            if len(uniq) > TOP_VALUES_PER_FILTER:
                continue  # too many — would hurt the UI more than help
            out.append({
                "column": str(c),
                "kind": "categorical",
                "values": [str(v) for v in uniq.tolist()],
            })
    return to_json_safe({"filters": out})


__all__ = ["apply_filters", "build_chart_data", "build_filter_options"]
