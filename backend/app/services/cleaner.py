"""Cleaning / preprocessing engine.

This is the project's complete preprocessing hub. Every supported operation is
registered here as a function `(df, columns, params) -> (df, log_entry)`. The
dispatcher applies an ordered list of steps and accumulates the log.

Hard rules:
  - The caller passes a DataFrame; we never mutate the input — every runner
    works on a copy.
  - Each runner returns a NEW DataFrame plus a JSON-safe log entry describing
    exactly what changed ("Imputed 42 nulls in `age` with median = 34.0").
  - If a runner raises, the dispatcher aborts the whole run with a clear
    error — the caller (router) makes sure nothing is persisted.

Operation IDs are deliberately picked to be a SUPERSET of every Phase-2 `fix`
string, so accepted fixes dispatch straight through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.impute import KNNImputer
from sklearn.preprocessing import (
    KBinsDiscretizer,
    LabelEncoder,
    MinMaxScaler,
    OrdinalEncoder,
    RobustScaler,
    StandardScaler,
)

from .data_loader import to_json_safe


# =============================================================================
# Registry
# =============================================================================

LogEntry = dict[str, Any]
StepParams = dict[str, Any]
Runner = Callable[[pd.DataFrame, list[str], StepParams], tuple[pd.DataFrame, LogEntry]]


@dataclass
class Operation:
    id: str
    label: str
    description: str
    group: str
    applies_to: str
    params: list[dict[str, Any]] = field(default_factory=list)
    runner: Runner | None = None


REGISTRY: dict[str, Operation] = {}


def _register(op: Operation) -> Operation:
    REGISTRY[op.id] = op
    return op


def op(
    id: str,
    *,
    label: str,
    description: str,
    group: str,
    applies_to: str,
    params: list[dict[str, Any]] | None = None,
) -> Callable[[Runner], Runner]:
    """Decorator: register an operation runner."""
    def deco(fn: Runner) -> Runner:
        _register(Operation(
            id=id,
            label=label,
            description=description,
            group=group,
            applies_to=applies_to,
            params=params or [],
            runner=fn,
        ))
        return fn
    return deco


def get_catalog() -> dict[str, list[dict[str, Any]]]:
    """Catalog grouped for the manual-toolbox UI."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for op_obj in REGISTRY.values():
        groups.setdefault(op_obj.group, []).append({
            "id": op_obj.id,
            "label": op_obj.label,
            "description": op_obj.description,
            "applies_to": op_obj.applies_to,
            "params": op_obj.params,
        })
    # Stable order inside each group.
    for g in groups.values():
        g.sort(key=lambda x: x["label"])
    return groups


# =============================================================================
# Shared helpers
# =============================================================================

def _require_cols(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"column(s) not found: {missing}")


def _entry(op_id: str, columns: list[str], params: StepParams, **extra: Any) -> LogEntry:
    return {
        "op": op_id,
        "columns": columns,
        "params": params,
        **extra,
    }


def _cells_changed(before: pd.Series, after: pd.Series) -> int:
    # Treat NaN==NaN as equal so imputation counts correctly.
    a, b = before, after
    same = (a == b) | (a.isna() & b.isna())
    return int((~same).sum())


# =============================================================================
# MISSING VALUES — core
# =============================================================================

@op(
    "impute_median",
    label="Impute with median",
    description="Replace nulls in numeric column(s) with the column median.",
    group="core",
    applies_to="numeric",
)
def _impute_median(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    filled: dict[str, Any] = {}
    cells = 0
    for c in columns:
        s = pd.to_numeric(df[c], errors="coerce")
        med = float(s.median())
        before = df[c].copy()
        df[c] = s.fillna(med)
        cells += _cells_changed(before, df[c])
        filled[c] = med
    return df, _entry(
        "impute_median", columns, params,
        cells_changed=cells,
        values_used=filled,
        summary=f"Imputed nulls in {columns} with median ({cells} cells changed).",
    )


@op(
    "impute_mean",
    label="Impute with mean",
    description="Replace nulls in numeric column(s) with the column mean.",
    group="core",
    applies_to="numeric",
)
def _impute_mean(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    filled, cells = {}, 0
    for c in columns:
        s = pd.to_numeric(df[c], errors="coerce")
        mean = float(s.mean())
        before = df[c].copy()
        df[c] = s.fillna(mean)
        cells += _cells_changed(before, df[c])
        filled[c] = mean
    return df, _entry(
        "impute_mean", columns, params,
        cells_changed=cells, values_used=filled,
        summary=f"Imputed nulls in {columns} with mean ({cells} cells changed).",
    )


@op(
    "impute_mode",
    label="Impute with mode",
    description="Replace nulls with the most common value in the column.",
    group="core",
    applies_to="any",
)
def _impute_mode(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    filled, cells = {}, 0
    for c in columns:
        mode_vals = df[c].mode(dropna=True)
        if mode_vals.empty:
            continue
        mode = mode_vals.iloc[0]
        before = df[c].copy()
        df[c] = df[c].fillna(mode)
        cells += _cells_changed(before, df[c])
        filled[c] = mode
    return df, _entry(
        "impute_mode", columns, params,
        cells_changed=cells, values_used=filled,
        summary=f"Imputed nulls in {columns} with mode ({cells} cells changed).",
    )


@op(
    "fill_constant",
    label="Fill nulls with constant",
    description="Replace nulls with a value you provide.",
    group="core",
    applies_to="any",
    params=[{"name": "value", "type": "string", "label": "Value", "default": ""}],
)
def _fill_constant(df, columns, params):
    _require_cols(df, columns)
    val = params.get("value", "")
    df = df.copy()
    cells = 0
    for c in columns:
        before = df[c].copy()
        df[c] = df[c].fillna(val)
        cells += _cells_changed(before, df[c])
    return df, _entry(
        "fill_constant", columns, params,
        cells_changed=cells,
        summary=f"Filled nulls in {columns} with {val!r} ({cells} cells changed).",
    )


@op(
    "forward_fill",
    label="Forward-fill nulls",
    description="Carry the last non-null value forward to fill nulls.",
    group="core",
    applies_to="any",
)
def _forward_fill(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    cells = 0
    for c in columns:
        before = df[c].copy()
        df[c] = df[c].ffill()
        cells += _cells_changed(before, df[c])
    return df, _entry(
        "forward_fill", columns, params,
        cells_changed=cells,
        summary=f"Forward-filled nulls in {columns} ({cells} cells changed).",
    )


@op(
    "backward_fill",
    label="Backward-fill nulls",
    description="Carry the next non-null value backward to fill nulls.",
    group="core",
    applies_to="any",
)
def _backward_fill(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    cells = 0
    for c in columns:
        before = df[c].copy()
        df[c] = df[c].bfill()
        cells += _cells_changed(before, df[c])
    return df, _entry(
        "backward_fill", columns, params,
        cells_changed=cells,
        summary=f"Backward-filled nulls in {columns} ({cells} cells changed).",
    )


@op(
    "linear_interpolate",
    label="Linearly interpolate nulls",
    description="Estimate missing numeric values by linear interpolation between neighbours.",
    group="core",
    applies_to="numeric",
)
def _linear_interpolate(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    cells = 0
    for c in columns:
        before = df[c].copy()
        df[c] = pd.to_numeric(df[c], errors="coerce").interpolate(method="linear")
        cells += _cells_changed(before, df[c])
    return df, _entry(
        "linear_interpolate", columns, params,
        cells_changed=cells,
        summary=f"Linearly interpolated nulls in {columns} ({cells} cells changed).",
    )


@op(
    "knn_impute",
    label="KNN-impute nulls",
    description=(
        "Impute missing numeric values by averaging the K nearest neighbours "
        "across all selected numeric columns. Slow on big files."
    ),
    group="core",
    applies_to="numeric",
    params=[{"name": "n_neighbors", "type": "number", "label": "K", "default": 5}],
)
def _knn_impute(df, columns, params):
    _require_cols(df, columns)
    k = int(params.get("n_neighbors", 5))
    sub = df[columns].apply(pd.to_numeric, errors="coerce")
    imputer = KNNImputer(n_neighbors=k)
    filled = imputer.fit_transform(sub.values)
    df = df.copy()
    cells = 0
    for i, c in enumerate(columns):
        before = df[c].copy()
        df[c] = filled[:, i]
        cells += _cells_changed(before, df[c])
    return df, _entry(
        "knn_impute", columns, params,
        cells_changed=cells,
        summary=f"KNN-imputed (K={k}) nulls in {columns} ({cells} cells changed).",
    )


@op(
    "drop_rows",
    label="Drop rows with nulls",
    description="Drop rows that have a null in any of the chosen columns (or any column if none given).",
    group="core",
    applies_to="dataset",
)
def _drop_rows(df, columns, params):
    if columns:
        _require_cols(df, columns)
        before = len(df)
        df = df.dropna(subset=columns).reset_index(drop=True)
    else:
        before = len(df)
        df = df.dropna().reset_index(drop=True)
    dropped = before - len(df)
    return df, _entry(
        "drop_rows", columns, params,
        rows_dropped=dropped,
        summary=f"Dropped {dropped} row(s) with nulls.",
    )


@op(
    "drop_column",
    label="Drop column(s)",
    description="Remove one or more columns entirely.",
    group="column",
    applies_to="any",
)
def _drop_column(df, columns, params):
    _require_cols(df, columns)
    df = df.drop(columns=columns)
    return df, _entry(
        "drop_column", columns, params,
        columns_dropped=columns,
        summary=f"Dropped column(s): {columns}.",
    )


# =============================================================================
# DUPLICATES
# =============================================================================

@op(
    "drop_duplicates",
    label="Drop duplicate rows",
    description="Remove rows that duplicate another row (across all columns or a subset).",
    group="core",
    applies_to="dataset",
    params=[
        {"name": "keep", "type": "select", "label": "Keep", "default": "first",
         "options": ["first", "last"]},
    ],
)
def _drop_duplicates(df, columns, params):
    keep = params.get("keep", "first")
    subset = columns or None
    if subset:
        _require_cols(df, subset)
    before = len(df)
    df = df.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)
    dropped = before - len(df)
    return df, _entry(
        "drop_duplicates", columns, params,
        rows_dropped=dropped,
        summary=f"Dropped {dropped} duplicate row(s) (keep={keep}).",
    )


# =============================================================================
# TYPE CONVERSION
# =============================================================================

@op(
    "convert_to_numeric",
    label="Convert to numeric",
    description="Parse strings as numbers; values that don't parse become NaN.",
    group="core",
    applies_to="any",
)
def _convert_to_numeric(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    coerced = {}
    for c in columns:
        before_nulls = int(df[c].isna().sum())
        df[c] = pd.to_numeric(df[c], errors="coerce")
        after_nulls = int(df[c].isna().sum())
        coerced[c] = after_nulls - before_nulls
    return df, _entry(
        "convert_to_numeric", columns, params,
        coerced_to_nan=coerced,
        summary=f"Converted {columns} to numeric ({sum(coerced.values())} value(s) failed to parse).",
    )


@op(
    "convert_to_datetime",
    label="Convert to datetime",
    description="Parse strings as datetimes; optional explicit format.",
    group="core",
    applies_to="any",
    params=[{"name": "format", "type": "string", "label": "Format (optional)", "default": ""}],
)
def _convert_to_datetime(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    fmt = params.get("format") or None
    coerced = {}
    for c in columns:
        before_nulls = int(df[c].isna().sum())
        df[c] = pd.to_datetime(df[c], errors="coerce", format=fmt or "mixed")
        coerced[c] = int(df[c].isna().sum()) - before_nulls
    return df, _entry(
        "convert_to_datetime", columns, params,
        coerced_to_nat=coerced,
        summary=f"Converted {columns} to datetime ({sum(coerced.values())} value(s) failed to parse).",
    )


@op(
    "convert_to_categorical",
    label="Convert to categorical",
    description="Mark column(s) as pandas categorical (lower memory, ordered string buckets).",
    group="core",
    applies_to="any",
)
def _convert_to_categorical(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    for c in columns:
        df[c] = df[c].astype("category")
    return df, _entry(
        "convert_to_categorical", columns, params,
        summary=f"Converted {columns} to categorical dtype.",
    )


_TRUTHY = {"true", "t", "yes", "y", "1", 1, True}
_FALSY = {"false", "f", "no", "n", "0", 0, False}


@op(
    "convert_to_boolean",
    label="Convert to boolean",
    description="Map common truthy/falsy strings (yes/no, 1/0, true/false…) to real booleans.",
    group="core",
    applies_to="any",
)
def _convert_to_boolean(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    coerced = {}
    for c in columns:
        before_nulls = int(df[c].isna().sum())
        def to_bool(v: Any) -> Any:
            if pd.isna(v):
                return np.nan
            k = v.strip().lower() if isinstance(v, str) else v
            if k in _TRUTHY:
                return True
            if k in _FALSY:
                return False
            return np.nan
        df[c] = df[c].map(to_bool)
        coerced[c] = int(df[c].isna().sum()) - before_nulls
    return df, _entry(
        "convert_to_boolean", columns, params,
        coerced_to_nan=coerced,
        summary=f"Converted {columns} to boolean ({sum(coerced.values())} unparseable value(s)).",
    )


@op(
    "convert_to_text",
    label="Convert to text",
    description="Force column(s) to string dtype.",
    group="core",
    applies_to="any",
)
def _convert_to_text(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    for c in columns:
        df[c] = df[c].astype("string")
    return df, _entry(
        "convert_to_text", columns, params,
        summary=f"Converted {columns} to string dtype.",
    )


# =============================================================================
# OUTLIERS
# =============================================================================

def _iqr_bounds(s: pd.Series) -> tuple[float, float]:
    arr = pd.to_numeric(s, errors="coerce").dropna()
    q1, q3 = np.quantile(arr, [0.25, 0.75])
    iqr = q3 - q1
    return float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


def _zscore_bounds(s: pd.Series, threshold: float = 3.0) -> tuple[float, float]:
    arr = pd.to_numeric(s, errors="coerce").dropna()
    mean = float(arr.mean())
    std = float(arr.std(ddof=1))
    return mean - threshold * std, mean + threshold * std


@op(
    "cap",
    label="Cap outliers to IQR bounds",
    description="Clip values outside [Q1−1.5·IQR, Q3+1.5·IQR] to the bound.",
    group="core",
    applies_to="numeric",
)
def _cap(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    cells = 0
    bounds = {}
    for c in columns:
        s = pd.to_numeric(df[c], errors="coerce")
        lo, hi = _iqr_bounds(s)
        before = df[c].copy()
        df[c] = s.clip(lower=lo, upper=hi)
        cells += _cells_changed(before, df[c])
        bounds[c] = {"lower": lo, "upper": hi}
    return df, _entry(
        "cap", columns, params,
        bounds=bounds, cells_changed=cells,
        summary=f"Capped IQR outliers in {columns} ({cells} cells changed).",
    )


# Alias for explicit-IQR / explicit-Z-score variants.
@op(
    "cap_iqr",
    label="Cap to IQR bounds",
    description="Alias of `cap` — clip values to [Q1−1.5·IQR, Q3+1.5·IQR].",
    group="core",
    applies_to="numeric",
)
def _cap_iqr(df, columns, params):
    return _cap(df, columns, params)


@op(
    "cap_zscore",
    label="Cap to ±3σ bounds",
    description="Clip values to within ±3 standard deviations of the mean.",
    group="core",
    applies_to="numeric",
    params=[{"name": "threshold", "type": "number", "label": "Z threshold", "default": 3.0}],
)
def _cap_zscore(df, columns, params):
    _require_cols(df, columns)
    threshold = float(params.get("threshold", 3.0))
    df = df.copy()
    cells = 0
    bounds = {}
    for c in columns:
        s = pd.to_numeric(df[c], errors="coerce")
        lo, hi = _zscore_bounds(s, threshold)
        before = df[c].copy()
        df[c] = s.clip(lower=lo, upper=hi)
        cells += _cells_changed(before, df[c])
        bounds[c] = {"lower": lo, "upper": hi}
    return df, _entry(
        "cap_zscore", columns, params,
        bounds=bounds, cells_changed=cells,
        summary=f"Capped ±{threshold}σ outliers in {columns} ({cells} cells changed).",
    )


@op(
    "winsorize",
    label="Winsorize",
    description="Clip values to chosen percentile bounds (default 5% / 95%).",
    group="core",
    applies_to="numeric",
    params=[
        {"name": "lower_pct", "type": "number", "label": "Lower percentile", "default": 5},
        {"name": "upper_pct", "type": "number", "label": "Upper percentile", "default": 95},
    ],
)
def _winsorize(df, columns, params):
    _require_cols(df, columns)
    lo_p = float(params.get("lower_pct", 5)) / 100.0
    hi_p = float(params.get("upper_pct", 95)) / 100.0
    df = df.copy()
    cells = 0
    bounds = {}
    for c in columns:
        arr = pd.to_numeric(df[c], errors="coerce")
        clean = arr.dropna()
        lo, hi = float(np.quantile(clean, lo_p)), float(np.quantile(clean, hi_p))
        before = df[c].copy()
        df[c] = arr.clip(lower=lo, upper=hi)
        cells += _cells_changed(before, df[c])
        bounds[c] = {"lower": lo, "upper": hi}
    return df, _entry(
        "winsorize", columns, params,
        bounds=bounds, cells_changed=cells,
        summary=f"Winsorized {columns} to [{lo_p*100:g}%, {hi_p*100:g}%] ({cells} cells changed).",
    )


@op(
    "remove_outliers",
    label="Remove outlier rows",
    description="Drop rows where the chosen column(s) fall outside IQR or ±3σ bounds.",
    group="core",
    applies_to="numeric",
    params=[{"name": "method", "type": "select", "label": "Method",
             "default": "iqr", "options": ["iqr", "zscore"]}],
)
def _remove_outliers(df, columns, params):
    _require_cols(df, columns)
    method = params.get("method", "iqr")
    before = len(df)
    mask = pd.Series(True, index=df.index)
    bounds = {}
    for c in columns:
        s = pd.to_numeric(df[c], errors="coerce")
        if method == "zscore":
            lo, hi = _zscore_bounds(s)
        else:
            lo, hi = _iqr_bounds(s)
        bounds[c] = {"lower": lo, "upper": hi}
        mask &= s.between(lo, hi)
    df = df[mask].reset_index(drop=True)
    return df, _entry(
        "remove_outliers", columns, params,
        bounds=bounds, rows_dropped=before - len(df),
        summary=f"Removed {before - len(df)} outlier row(s) via {method}.",
    )


# Phase-2 alias: "remove" === remove_outliers (default IQR).
@op(
    "remove",
    label="Remove outlier rows (IQR)",
    description="Alias of `remove_outliers` with method=iqr — drops rows outside IQR bounds.",
    group="core",
    applies_to="numeric",
)
def _remove_alias(df, columns, params):
    return _remove_outliers(df, columns, {"method": "iqr"})


@op(
    "remove_rows_by_index",
    label="Remove rows by index",
    description="Drop rows whose 0-based positions match the given list (used for Isolation-Forest hits).",
    group="core",
    applies_to="dataset",
    params=[{"name": "indices", "type": "list", "label": "Row indices", "default": []}],
)
def _remove_rows_by_index(df, columns, params):
    idx = [int(i) for i in params.get("indices", [])]
    before = len(df)
    keep_mask = ~df.reset_index(drop=True).index.isin(idx)
    df = df.reset_index(drop=True)[keep_mask].reset_index(drop=True)
    return df, _entry(
        "remove_rows_by_index", columns, params,
        rows_dropped=before - len(df),
        summary=f"Removed {before - len(df)} row(s) by index.",
    )


@op(
    "log_transform",
    label="Log-transform",
    description="Apply log(1 + x) to numeric column(s). Tames heavy-tailed distributions.",
    group="core",
    applies_to="numeric",
)
def _log_transform(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    for c in columns:
        s = pd.to_numeric(df[c], errors="coerce")
        df[c] = np.log1p(s)
    return df, _entry(
        "log_transform", columns, params,
        summary=f"Applied log(1+x) to {columns}.",
    )


@op(
    "sqrt_transform",
    label="Square-root transform",
    description="Apply √x to numeric column(s) (after clipping negatives to 0).",
    group="core",
    applies_to="numeric",
)
def _sqrt_transform(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    for c in columns:
        s = pd.to_numeric(df[c], errors="coerce").clip(lower=0)
        df[c] = np.sqrt(s)
    return df, _entry(
        "sqrt_transform", columns, params,
        summary=f"Applied √x to {columns}.",
    )


# =============================================================================
# TEXT / CATEGORICAL STANDARDIZATION
# =============================================================================

def _str_op(df: pd.DataFrame, columns: list[str], fn) -> tuple[pd.DataFrame, int]:
    df = df.copy()
    cells = 0
    for c in columns:
        before = df[c].copy()
        df[c] = df[c].astype("string").map(lambda v: fn(v) if isinstance(v, str) else v)
        cells += _cells_changed(before, df[c])
    return df, cells


@op("trim_whitespace", label="Trim whitespace", description="Strip leading/trailing whitespace.",
    group="text", applies_to="text")
def _trim_whitespace(df, columns, params):
    _require_cols(df, columns)
    df, cells = _str_op(df, columns, str.strip)
    return df, _entry("trim_whitespace", columns, params, cells_changed=cells,
                      summary=f"Trimmed whitespace in {columns} ({cells} cells changed).")


@op("lowercase", label="Lowercase", description="Convert text to lowercase.",
    group="text", applies_to="text")
def _lowercase(df, columns, params):
    _require_cols(df, columns)
    df, cells = _str_op(df, columns, str.lower)
    return df, _entry("lowercase", columns, params, cells_changed=cells,
                      summary=f"Lowercased {columns} ({cells} cells changed).")


@op("uppercase", label="Uppercase", description="Convert text to uppercase.",
    group="text", applies_to="text")
def _uppercase(df, columns, params):
    _require_cols(df, columns)
    df, cells = _str_op(df, columns, str.upper)
    return df, _entry("uppercase", columns, params, cells_changed=cells,
                      summary=f"Uppercased {columns} ({cells} cells changed).")


@op("titlecase", label="Title case", description="Title-Case each word.",
    group="text", applies_to="text")
def _titlecase(df, columns, params):
    _require_cols(df, columns)
    df, cells = _str_op(df, columns, str.title)
    return df, _entry("titlecase", columns, params, cells_changed=cells,
                      summary=f"Title-cased {columns} ({cells} cells changed).")


@op(
    "remove_special_chars",
    label="Remove special characters",
    description="Strip non-alphanumeric characters (keeps letters, digits, spaces).",
    group="text",
    applies_to="text",
)
def _remove_special_chars(df, columns, params):
    _require_cols(df, columns)
    pat = re.compile(r"[^A-Za-z0-9 ]+")
    df, cells = _str_op(df, columns, lambda v: pat.sub("", v))
    return df, _entry("remove_special_chars", columns, params, cells_changed=cells,
                      summary=f"Stripped special chars in {columns} ({cells} cells changed).")


@op(
    "regex_replace",
    label="Regex find & replace",
    description="Replace text matching a regex with another string.",
    group="text",
    applies_to="text",
    params=[
        {"name": "pattern", "type": "string", "label": "Pattern (regex)"},
        {"name": "replacement", "type": "string", "label": "Replacement", "default": ""},
    ],
)
def _regex_replace(df, columns, params):
    _require_cols(df, columns)
    pat = re.compile(params["pattern"])
    repl = params.get("replacement", "")
    df, cells = _str_op(df, columns, lambda v: pat.sub(repl, v))
    return df, _entry("regex_replace", columns, params, cells_changed=cells,
                      summary=f"Regex-replaced /{params['pattern']}/ in {columns} "
                              f"({cells} cells changed).")


@op(
    "standardize_categories",
    label="Standardize categories",
    description="Map messy category variants to a canonical value (e.g. USA/usa → US).",
    group="text",
    applies_to="categorical",
    params=[
        {"name": "mapping", "type": "mapping", "label": "Mapping",
         "description": "{ \"variant\": \"canonical\", ... }"},
        {"name": "case_insensitive", "type": "boolean", "label": "Case-insensitive", "default": True},
    ],
)
def _standardize_categories(df, columns, params):
    _require_cols(df, columns)
    raw_map: dict[str, str] = params.get("mapping", {}) or {}
    if not raw_map:
        raise ValueError("standardize_categories requires a non-empty mapping")
    ci = bool(params.get("case_insensitive", True))
    norm = {(k.lower() if ci else k): v for k, v in raw_map.items()}
    df = df.copy()
    cells = 0
    for c in columns:
        before = df[c].copy()
        def remap(v: Any) -> Any:
            if not isinstance(v, str):
                return v
            key = v.lower() if ci else v
            return norm.get(key, v)
        df[c] = df[c].map(remap)
        cells += _cells_changed(before, df[c])
    return df, _entry("standardize_categories", columns, params, cells_changed=cells,
                      summary=f"Standardized categories in {columns} "
                              f"({cells} cells changed via {len(raw_map)} mapping(s)).")


# =============================================================================
# DATETIME FEATURE EXTRACTION
# =============================================================================

_DT_PARTS = {
    "year": lambda s: s.dt.year,
    "month": lambda s: s.dt.month,
    "day": lambda s: s.dt.day,
    "weekday": lambda s: s.dt.weekday,
    "quarter": lambda s: s.dt.quarter,
    "hour": lambda s: s.dt.hour,
}


@op(
    "extract_datetime_parts",
    label="Extract date parts",
    description="Create new columns with year/month/day/weekday/quarter/hour from a datetime column.",
    group="datetime",
    applies_to="datetime",
    params=[
        {"name": "parts", "type": "list", "label": "Parts",
         "default": ["year", "month", "day"],
         "options": list(_DT_PARTS.keys())},
    ],
)
def _extract_datetime_parts(df, columns, params):
    _require_cols(df, columns)
    parts = params.get("parts") or ["year", "month", "day"]
    unknown = [p for p in parts if p not in _DT_PARTS]
    if unknown:
        raise ValueError(f"unknown datetime parts: {unknown}")
    df = df.copy()
    new_cols: list[str] = []
    for c in columns:
        s = pd.to_datetime(df[c], errors="coerce")
        for p in parts:
            new = f"{c}_{p}"
            df[new] = _DT_PARTS[p](s)
            new_cols.append(new)
    return df, _entry("extract_datetime_parts", columns, params,
                      columns_added=new_cols,
                      summary=f"Extracted {parts} from {columns} into {new_cols}.")


# =============================================================================
# COLUMN OPERATIONS
# =============================================================================

@op(
    "rename_column",
    label="Rename column",
    description="Rename one column.",
    group="column",
    applies_to="any",
    params=[{"name": "new_name", "type": "string", "label": "New name"}],
)
def _rename_column(df, columns, params):
    _require_cols(df, columns)
    if len(columns) != 1:
        raise ValueError("rename_column expects exactly one column")
    new = params.get("new_name", "").strip()
    if not new:
        raise ValueError("new_name is required")
    df = df.rename(columns={columns[0]: new})
    return df, _entry("rename_column", columns, params,
                      summary=f"Renamed {columns[0]!r} to {new!r}.")


@op(
    "reorder_columns",
    label="Reorder columns",
    description="Re-order all columns to the order you provide (must list every column).",
    group="column",
    applies_to="dataset",
    params=[{"name": "order", "type": "list", "label": "New order"}],
)
def _reorder_columns(df, columns, params):
    order = list(params.get("order") or [])
    missing = set(df.columns) - set(order)
    extra = set(order) - set(df.columns)
    if missing or extra:
        raise ValueError(f"order must list every column once. missing={missing}, extra={extra}")
    df = df[order]
    return df, _entry("reorder_columns", columns, params,
                      summary="Reordered columns.")


# =============================================================================
# TRANSFORMATIONS (optional — for modelling. Never auto-applied.)
# =============================================================================

@op(
    "onehot_encode",
    label="One-hot encode",
    description="Expand a categorical column into one boolean column per category.",
    group="transform",
    applies_to="categorical",
    params=[{"name": "drop_first", "type": "boolean", "label": "Drop first category", "default": False}],
)
def _onehot_encode(df, columns, params):
    _require_cols(df, columns)
    drop_first = bool(params.get("drop_first", False))
    dummies = pd.get_dummies(df[columns], drop_first=drop_first)
    new_cols = list(dummies.columns)
    df = pd.concat([df.drop(columns=columns), dummies], axis=1)
    return df, _entry("onehot_encode", columns, params,
                      columns_added=new_cols, columns_dropped=columns,
                      summary=f"One-hot encoded {columns} into {len(new_cols)} new column(s).")


@op(
    "label_encode",
    label="Label encode",
    description="Replace each unique category with an integer code (0..N−1).",
    group="transform",
    applies_to="categorical",
)
def _label_encode(df, columns, params):
    _require_cols(df, columns)
    df = df.copy()
    for c in columns:
        le = LabelEncoder()
        non_null = df[c].notna()
        df.loc[non_null, c] = le.fit_transform(df.loc[non_null, c].astype(str))
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, _entry("label_encode", columns, params,
                      summary=f"Label-encoded {columns}.")


@op(
    "ordinal_encode",
    label="Ordinal encode",
    description="Replace categories with integers using the explicit order you provide.",
    group="transform",
    applies_to="categorical",
    params=[{"name": "order", "type": "list", "label": "Category order (low → high)"}],
)
def _ordinal_encode(df, columns, params):
    _require_cols(df, columns)
    order = params.get("order") or []
    if not order:
        raise ValueError("ordinal_encode requires an `order` list")
    enc = OrdinalEncoder(categories=[order] * len(columns), handle_unknown="use_encoded_value",
                         unknown_value=np.nan)
    df = df.copy()
    df[columns] = enc.fit_transform(df[columns].astype(str))
    return df, _entry("ordinal_encode", columns, params,
                      summary=f"Ordinal-encoded {columns} with order {order}.")


def _scale(df, columns, params, scaler, name, op_id):
    _require_cols(df, columns)
    df = df.copy()
    df[columns] = scaler.fit_transform(df[columns].apply(pd.to_numeric, errors="coerce"))
    return df, _entry(op_id, columns, params, summary=f"{name}-scaled {columns}.")


@op("scale_standard", label="Standard scale (z-score)",
    description="Subtract mean, divide by std. Result has mean≈0, std≈1.",
    group="transform", applies_to="numeric")
def _scale_standard(df, columns, params):
    return _scale(df, columns, params, StandardScaler(), "Standard", "scale_standard")


@op("scale_minmax", label="Min-max scale",
    description="Scale to [0, 1] using observed min/max.",
    group="transform", applies_to="numeric")
def _scale_minmax(df, columns, params):
    return _scale(df, columns, params, MinMaxScaler(), "Min-max", "scale_minmax")


@op("scale_robust", label="Robust scale",
    description="Centre on median, scale by IQR. Less sensitive to outliers than standard scale.",
    group="transform", applies_to="numeric")
def _scale_robust(df, columns, params):
    return _scale(df, columns, params, RobustScaler(), "Robust", "scale_robust")


def _bin(df, columns, params, op_id, strategy=None, edges=None):
    _require_cols(df, columns)
    df = df.copy()
    if edges is not None:
        for c in columns:
            df[c] = pd.cut(pd.to_numeric(df[c], errors="coerce"), bins=edges, include_lowest=True)
            df[c] = df[c].astype("string")
        return df, _entry(op_id, columns, params,
                          summary=f"Custom-binned {columns} with edges {edges}.")
    n_bins = int(params.get("n_bins", 5))
    disc = KBinsDiscretizer(n_bins=n_bins, encode="ordinal", strategy=strategy)
    df[columns] = disc.fit_transform(df[columns].apply(pd.to_numeric, errors="coerce"))
    return df, _entry(op_id, columns, params,
                      summary=f"{strategy} binning of {columns} into {n_bins} bins.")


@op("bin_equal_width", label="Bin into equal-width buckets",
    description="Split the value range into N equal-width buckets.",
    group="transform", applies_to="numeric",
    params=[{"name": "n_bins", "type": "number", "label": "Bins", "default": 5}])
def _bin_equal_width(df, columns, params):
    return _bin(df, columns, params, "bin_equal_width", strategy="uniform")


@op("bin_equal_freq", label="Bin into equal-frequency buckets",
    description="Split values so each bucket holds roughly the same number of rows.",
    group="transform", applies_to="numeric",
    params=[{"name": "n_bins", "type": "number", "label": "Bins", "default": 5}])
def _bin_equal_freq(df, columns, params):
    return _bin(df, columns, params, "bin_equal_freq", strategy="quantile")


@op("bin_custom", label="Bin into custom buckets",
    description="Split values at the explicit edges you provide.",
    group="transform", applies_to="numeric",
    params=[{"name": "edges", "type": "list", "label": "Edges (ascending numbers)"}])
def _bin_custom(df, columns, params):
    edges = [float(e) for e in (params.get("edges") or [])]
    if len(edges) < 2:
        raise ValueError("bin_custom needs at least two edge values")
    return _bin(df, columns, params, "bin_custom", edges=edges)


# =============================================================================
# No-ops — for Phase-2 fix strings that mean "user chose to keep as-is"
# =============================================================================

for _noop_id in ("keep", "leave_as_is", "review"):
    def _make_noop(op_id: str) -> Runner:
        def runner(df, columns, params):
            return df, _entry(op_id, columns, params, summary=f"No-op ({op_id}).")
        return runner

    _register(Operation(
        id=_noop_id,
        label="Keep as-is",
        description="No-op. Selecting this means the user explicitly chose not to change anything.",
        group="core",
        applies_to="any",
        runner=_make_noop(_noop_id),
    ))


# =============================================================================
# Dispatcher
# =============================================================================

def apply_steps(
    df: pd.DataFrame, steps: list[dict[str, Any]]
) -> tuple[pd.DataFrame, list[LogEntry]]:
    """Apply steps in order. Raises on the first failure with a clear message."""
    log: list[LogEntry] = []
    out = df
    for i, step in enumerate(steps):
        op_id = step.get("op")
        if not op_id or op_id not in REGISTRY:
            raise ValueError(f"unknown op at step {i}: {op_id!r}")
        runner = REGISTRY[op_id].runner
        if runner is None:
            raise RuntimeError(f"op {op_id} has no runner")
        columns = list(step.get("columns") or [])
        params = dict(step.get("params") or {})
        try:
            out, entry = runner(out, columns, params)
        except Exception as exc:
            raise RuntimeError(f"step {i} ({op_id}) failed: {exc}") from exc
        log.append(to_json_safe(entry))
    return out, log


# =============================================================================
# Before / after diff
# =============================================================================

def compute_diff(
    before: pd.DataFrame,
    after: pd.DataFrame,
    *,
    sample: int = 5,
) -> dict[str, Any]:
    cols_b = list(before.columns)
    cols_a = list(after.columns)
    added = [c for c in cols_a if c not in cols_b]
    dropped = [c for c in cols_b if c not in cols_a]

    null_counts: dict[str, dict[str, int]] = {}
    for c in cols_b:
        if c in cols_a:
            null_counts[c] = {
                "before": int(before[c].isna().sum()),
                "after": int(after[c].isna().sum()),
            }

    # Sample of rows that exist in both before and after AND have a changed value.
    common_idx = before.index.intersection(after.index)
    common_cols = [c for c in cols_b if c in cols_a]
    changed_rows_sample: list[dict[str, Any]] = []
    if len(common_idx) and common_cols:
        b_sub = before.loc[common_idx, common_cols]
        a_sub = after.loc[common_idx, common_cols]
        # Cell-level mismatch ignoring NaN==NaN.
        mismatch = (b_sub.ne(a_sub)) & ~(b_sub.isna() & a_sub.isna())
        changed_mask = mismatch.any(axis=1)
        changed_idx = changed_mask[changed_mask].index[:sample]
        for idx in changed_idx:
            before_row = {c: before.at[idx, c] for c in common_cols}
            after_row = {c: after.at[idx, c] for c in common_cols}
            changed_rows_sample.append({
                "index": int(idx),
                "before": before_row,
                "after": after_row,
            })

    diff = {
        "rows_before": int(len(before)),
        "rows_after": int(len(after)),
        "columns_before": int(len(cols_b)),
        "columns_after": int(len(cols_a)),
        "duplicates_before": int(before.duplicated().sum()),
        "duplicates_after": int(after.duplicated().sum()),
        "columns_added": added,
        "columns_dropped": dropped,
        "null_counts": null_counts,
        "changed_rows_sample": changed_rows_sample,
    }
    return to_json_safe(diff)


__all__ = ["REGISTRY", "apply_steps", "compute_diff", "get_catalog"]
