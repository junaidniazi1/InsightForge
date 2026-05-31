"""Data Health profiler.

Given a raw CSV/Excel file (as bytes + source_type), produces a structured
profile with:
  - dataset-level summary (counts, memory, duplicate rows, quality score)
  - per-column profile (semantic type, nulls, uniques, stats, top values)
  - issue list (type / missing / duplicate / low-value, each with suggested fix)
  - three SEPARATE outlier groups (IQR, Z-score, Isolation Forest)

Important design choice: single-column outlier methods (IQR, Z-score) and the
multivariate method (Isolation Forest) flag *different* rows and are reported
in three distinct groups, not merged. The frontend explains the difference.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sci_stats
from sklearn.ensemble import IsolationForest

from .data_loader import load_dataframe, to_json_safe

# --- caps so profiling stays fast on big files --------------------------------
ISOLATION_FOREST_SAMPLE_CAP = 50_000
TOP_VALUES_K = 10
SAMPLE_VALUES_K = 5

# --- thresholds (tweakable in one place) --------------------------------------
HIGH_NULL_PCT = 50.0     # >50% nulls = high severity
MED_NULL_PCT = 20.0      # 20-50% nulls = medium
NEAR_CONST_PCT = 95.0    # >95% same value = near-constant
ID_LIKE_UNIQUE_PCT = 95.0
ZSCORE_THRESHOLD = 3.0
ISO_CONTAMINATION = "auto"


# =============================================================================
# Semantic type inference
# =============================================================================

_BOOL_STRINGS = {"true", "false", "yes", "no", "t", "f", "y", "n", "0", "1"}


def _infer_semantic_type(s: pd.Series, name: str) -> str:
    non_null = s.dropna()
    n = len(non_null)
    if n == 0:
        return "text"  # can't tell anything

    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    if pd.api.types.is_numeric_dtype(s):
        unique_pct = s.nunique(dropna=True) / max(n, 1) * 100.0
        # Numeric column is "id-like" only if it both (a) has nearly unique
        # values AND (b) looks like an identifier — integer-typed with an
        # id-shaped name. Random floats with high uniqueness stay "numeric"
        # so they go through outlier detection.
        is_integer_like = pd.api.types.is_integer_dtype(s) or (
            non_null.apply(lambda v: float(v).is_integer() if pd.notna(v) else True).all()
        )
        name_looks_idy = any(tok in name.lower() for tok in ("id", "uuid", "guid", "key"))
        if unique_pct >= ID_LIKE_UNIQUE_PCT and is_integer_like and name_looks_idy:
            return "id_like"
        return "numeric"

    # object dtype — could be text, categorical, or stringly-typed boolean
    sample = non_null.astype(str).str.strip().str.lower()
    uniques = set(sample.unique()[:32])
    if uniques and uniques.issubset(_BOOL_STRINGS):
        return "boolean"

    unique_count = s.nunique(dropna=True)
    unique_pct = unique_count / max(n, 1) * 100.0
    if unique_pct >= ID_LIKE_UNIQUE_PCT and unique_count > 20:
        return "id_like"
    if unique_count <= 50 or unique_pct < 5:
        return "categorical"
    return "text"


# =============================================================================
# Detection helpers
# =============================================================================

def _could_be_numeric(s: pd.Series) -> bool:
    if not pd.api.types.is_object_dtype(s):
        return False
    non_null = s.dropna().astype(str).str.strip()
    if len(non_null) == 0:
        return False
    coerced = pd.to_numeric(non_null, errors="coerce")
    return coerced.notna().mean() >= 0.9  # 90%+ values are numeric


def _could_be_datetime(s: pd.Series) -> bool:
    if not pd.api.types.is_object_dtype(s):
        return False
    non_null = s.dropna().astype(str)
    if len(non_null) == 0:
        return False
    sample = non_null.sample(min(len(non_null), 500), random_state=0)
    try:
        coerced = pd.to_datetime(sample, errors="coerce", format="mixed")
    except (ValueError, TypeError):
        return False
    return coerced.notna().mean() >= 0.9


def _is_mixed_type(s: pd.Series) -> bool:
    if not pd.api.types.is_object_dtype(s):
        return False
    non_null = s.dropna()
    if len(non_null) < 2:
        return False
    types = non_null.iloc[: min(len(non_null), 1000)].map(type).nunique()
    return types > 1


def _is_bool_as_string(s: pd.Series) -> bool:
    if not pd.api.types.is_object_dtype(s):
        return False
    non_null = s.dropna().astype(str).str.strip().str.lower()
    if len(non_null) == 0:
        return False
    return set(non_null.unique()).issubset(_BOOL_STRINGS) and non_null.nunique() <= 4


# =============================================================================
# Per-column profile
# =============================================================================

def _numeric_stats(s: pd.Series) -> dict[str, Any]:
    arr = pd.to_numeric(s, errors="coerce").dropna()
    if len(arr) == 0:
        return {
            "min": None, "max": None, "mean": None, "median": None,
            "std": None, "q1": None, "q2": None, "q3": None,
            "skewness": None, "kurtosis": None,
        }
    q1, q2, q3 = np.quantile(arr, [0.25, 0.5, 0.75])
    return {
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "median": float(arr.median()),
        "std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        "q1": float(q1),
        "q2": float(q2),
        "q3": float(q3),
        "skewness": float(sci_stats.skew(arr)) if len(arr) > 2 else 0.0,
        "kurtosis": float(sci_stats.kurtosis(arr)) if len(arr) > 3 else 0.0,
    }


def _top_values(s: pd.Series, k: int = TOP_VALUES_K) -> list[dict[str, Any]]:
    vc = s.dropna().value_counts().head(k)
    total = len(s)
    return [
        {"value": v, "count": int(c), "pct": round(c / total * 100.0, 2) if total else 0.0}
        for v, c in vc.items()
    ]


def _column_profile(s: pd.Series, name: str, n_rows: int) -> dict[str, Any]:
    null_count = int(s.isna().sum())
    null_pct = round(null_count / n_rows * 100.0, 2) if n_rows else 0.0
    unique_count = int(s.nunique(dropna=True))
    unique_pct = round(unique_count / n_rows * 100.0, 2) if n_rows else 0.0
    semantic = _infer_semantic_type(s, name)

    col: dict[str, Any] = {
        "name": name,
        "dtype": str(s.dtype),
        "semantic_type": semantic,
        "null_count": null_count,
        "null_pct": null_pct,
        "unique_count": unique_count,
        "unique_pct": unique_pct,
        "sample_values": list(s.dropna().head(SAMPLE_VALUES_K).tolist()),
        "memory_bytes": int(s.memory_usage(deep=True)),
        "numeric_stats": None,
        "top_values": None,
    }

    if pd.api.types.is_numeric_dtype(s) and semantic != "boolean":
        col["numeric_stats"] = _numeric_stats(s)
    if semantic in ("categorical", "text", "boolean", "id_like"):
        col["top_values"] = _top_values(s)
    return col


# =============================================================================
# Issue detection
# =============================================================================

def _severity_from_null_pct(pct: float) -> str:
    if pct >= HIGH_NULL_PCT:
        return "high"
    if pct >= MED_NULL_PCT:
        return "medium"
    return "low"


def _detect_issues(df: pd.DataFrame, col_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    n_rows = len(df)

    # --- dataset-level: duplicate rows ----------------------------------------
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        sev = "high" if dup_count / max(n_rows, 1) > 0.1 else "medium" if dup_count > 5 else "low"
        issues.append({
            "id": "duplicates:all",
            "column": None,
            "issue_type": "duplicate_rows",
            "severity": sev,
            "description": f"{dup_count} fully duplicate row(s) found ({dup_count / n_rows * 100:.1f}% of dataset).",
            "suggested_fix": "drop_duplicates",
            "fix_options": ["drop_duplicates", "keep"],
        })

    # --- per-column issues ----------------------------------------------------
    for col_p in col_profiles:
        name = col_p["name"]
        s = df[name]

        # Missing data
        if col_p["null_count"] > 0:
            pct = col_p["null_pct"]
            sev = _severity_from_null_pct(pct)
            if col_p["semantic_type"] == "numeric":
                suggested = "impute_median"
                opts = ["impute_median", "impute_mean", "fill_constant", "forward_fill", "drop_rows", "drop_column"]
            elif col_p["semantic_type"] in ("categorical", "boolean"):
                suggested = "impute_mode"
                opts = ["impute_mode", "fill_constant", "drop_rows", "drop_column"]
            else:
                suggested = "fill_constant"
                opts = ["fill_constant", "forward_fill", "drop_rows", "drop_column"]
            if pct >= HIGH_NULL_PCT:
                suggested = "drop_column"
            issues.append({
                "id": f"missing:{name}",
                "column": name,
                "issue_type": "missing_values",
                "severity": sev,
                "description": f"{col_p['null_count']} null(s) ({pct}%) in column \"{name}\".",
                "suggested_fix": suggested,
                "fix_options": opts,
            })

        # Type issues
        if _could_be_numeric(s) and pd.api.types.is_object_dtype(s):
            issues.append({
                "id": f"type_numeric_as_text:{name}",
                "column": name,
                "issue_type": "numeric_as_text",
                "severity": "medium",
                "description": f"Column \"{name}\" looks numeric but is stored as text.",
                "suggested_fix": "convert_to_numeric",
                "fix_options": ["convert_to_numeric", "leave_as_is"],
            })
        if _could_be_datetime(s) and pd.api.types.is_object_dtype(s):
            issues.append({
                "id": f"type_date_as_text:{name}",
                "column": name,
                "issue_type": "date_as_text",
                "severity": "medium",
                "description": f"Column \"{name}\" looks like dates but is stored as text.",
                "suggested_fix": "convert_to_datetime",
                "fix_options": ["convert_to_datetime", "leave_as_is"],
            })
        if _is_bool_as_string(s):
            issues.append({
                "id": f"type_bool_as_string:{name}",
                "column": name,
                "issue_type": "boolean_as_string",
                "severity": "low",
                "description": f"Column \"{name}\" looks boolean but is stored as text.",
                "suggested_fix": "convert_to_boolean",
                "fix_options": ["convert_to_boolean", "leave_as_is"],
            })
        if _is_mixed_type(s):
            issues.append({
                "id": f"type_mixed:{name}",
                "column": name,
                "issue_type": "mixed_types",
                "severity": "medium",
                "description": f"Column \"{name}\" contains values of multiple Python types.",
                "suggested_fix": "convert_to_text",
                "fix_options": ["convert_to_text", "convert_to_numeric", "leave_as_is"],
            })

        # Low-value columns
        if col_p["unique_count"] <= 1 and col_p["null_count"] < n_rows:
            issues.append({
                "id": f"constant:{name}",
                "column": name,
                "issue_type": "constant_column",
                "severity": "medium",
                "description": f"Column \"{name}\" has only one unique value.",
                "suggested_fix": "drop_column",
                "fix_options": ["drop_column", "keep"],
            })
        elif col_p["unique_count"] >= 2 and n_rows > 0:
            # near-constant: most common value covers >NEAR_CONST_PCT of non-null rows
            non_null = s.dropna()
            if len(non_null) > 0:
                top_pct = non_null.value_counts().iloc[0] / len(non_null) * 100.0
                if top_pct >= NEAR_CONST_PCT and col_p["unique_count"] < 10:
                    issues.append({
                        "id": f"near_constant:{name}",
                        "column": name,
                        "issue_type": "near_constant_column",
                        "severity": "low",
                        "description": (
                            f"Column \"{name}\" is dominated by one value "
                            f"({top_pct:.1f}% of non-null rows)."
                        ),
                        "suggested_fix": "drop_column",
                        "fix_options": ["drop_column", "keep"],
                    })

        if col_p["semantic_type"] == "id_like":
            issues.append({
                "id": f"id_like:{name}",
                "column": name,
                "issue_type": "id_like_column",
                "severity": "low",
                "description": (
                    f"Column \"{name}\" looks like an identifier "
                    f"({col_p['unique_pct']}% unique values) — unlikely to be useful for modelling."
                ),
                "suggested_fix": "keep",
                "fix_options": ["drop_column", "keep"],
            })

    return issues


# =============================================================================
# Outliers — THREE SEPARATE GROUPS (not merged)
# =============================================================================

def _iqr_outliers(df: pd.DataFrame, numeric_cols: list[str]) -> dict[str, Any]:
    cols_out: list[dict[str, Any]] = []
    for c in numeric_cols:
        arr = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(arr) < 4:
            continue
        q1, q3 = np.quantile(arr, [0.25, 0.75])
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = (arr < lo) | (arr > hi)
        count = int(mask.sum())
        if count == 0:
            continue
        pct = round(count / len(arr) * 100.0, 2)
        severity = "high" if pct > 5 else "medium" if pct > 1 else "low"
        cols_out.append({
            "column": c,
            "outlier_count": count,
            "outlier_pct": pct,
            "lower_bound": float(lo),
            "upper_bound": float(hi),
            "severity": severity,
            "suggested_fix": "cap",
            "fix_options": ["cap", "winsorize", "remove", "log_transform", "keep"],
        })
    return {
        "method": "iqr",
        "method_description": (
            "Per-column. Flags values outside [Q1 − 1.5·IQR, Q3 + 1.5·IQR]. "
            "Classic Tukey rule; treats each column independently."
        ),
        "columns": cols_out,
    }


def _zscore_outliers(df: pd.DataFrame, numeric_cols: list[str]) -> dict[str, Any]:
    cols_out: list[dict[str, Any]] = []
    for c in numeric_cols:
        arr = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(arr) < 4 or arr.std(ddof=1) == 0:
            continue
        z = np.abs(sci_stats.zscore(arr, nan_policy="omit"))
        mask = z > ZSCORE_THRESHOLD
        count = int(mask.sum())
        if count == 0:
            continue
        pct = round(count / len(arr) * 100.0, 2)
        severity = "high" if pct > 5 else "medium" if pct > 1 else "low"
        cols_out.append({
            "column": c,
            "outlier_count": count,
            "outlier_pct": pct,
            "threshold": ZSCORE_THRESHOLD,
            "mean": float(arr.mean()),
            "std": float(arr.std(ddof=1)),
            "severity": severity,
            "suggested_fix": "winsorize",
            "fix_options": ["cap", "winsorize", "remove", "log_transform", "keep"],
        })
    return {
        "method": "zscore",
        "method_description": (
            f"Per-column. Flags values where |z| > {ZSCORE_THRESHOLD} "
            f"(more than {ZSCORE_THRESHOLD:g} standard deviations from the mean). "
            "Assumes the column is roughly normal — heavy-tailed columns get over-flagged."
        ),
        "columns": cols_out,
    }


def _isolation_forest_outliers(df: pd.DataFrame, numeric_cols: list[str]) -> dict[str, Any]:
    if not numeric_cols:
        return {
            "method": "isolation_forest",
            "method_description": _IFOREST_DESC,
            "available": False,
            "reason": "No numeric columns to fit on.",
        }
    X = df[numeric_cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(X) < 20:
        return {
            "method": "isolation_forest",
            "method_description": _IFOREST_DESC,
            "available": False,
            "reason": "Need at least 20 fully-numeric rows to fit Isolation Forest.",
        }

    # Sample for speed; record what we did.
    sample = X
    sampled = False
    if len(X) > ISOLATION_FOREST_SAMPLE_CAP:
        sample = X.sample(ISOLATION_FOREST_SAMPLE_CAP, random_state=0)
        sampled = True

    iso = IsolationForest(
        n_estimators=100,
        contamination=ISO_CONTAMINATION,
        random_state=0,
    )
    preds = iso.fit_predict(sample.values)
    outlier_idx = sample.index[preds == -1]
    count = int(len(outlier_idx))
    pct = round(count / len(sample) * 100.0, 2)
    severity = "high" if pct > 5 else "medium" if pct > 1 else "low"
    return {
        "method": "isolation_forest",
        "method_description": _IFOREST_DESC,
        "available": True,
        "outlier_row_count": count,
        "outlier_row_pct": pct,
        "row_indices_sample": [int(i) for i in outlier_idx[:100]],
        "fitted_on_rows": int(len(sample)),
        "sampled": sampled,
        "numeric_columns_used": numeric_cols,
        "contamination": str(ISO_CONTAMINATION),
        "severity": severity,
        "suggested_fix": "review",
        "fix_options": ["remove_rows", "review", "keep"],
    }


_IFOREST_DESC = (
    "Multivariate. Fits Isolation Forest across all numeric columns at once and "
    "flags whole *rows* that look anomalous when their columns are considered jointly. "
    "Catches outliers the per-column methods miss (e.g. plausible values in each column "
    "but an unusual combination)."
)


# =============================================================================
# Quality score
# =============================================================================

def _quality_score(issues: list[dict[str, Any]], outliers: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    """
    Quality score in [0, 100], start at 100, subtract weighted penalties.

    Formula (documented for the user-visible breakdown):
      - per high-severity issue:    -10  (capped at -40 total from this bucket)
      - per medium-severity issue:  -5   (capped at -25)
      - per low-severity issue:     -2   (capped at -10)
      - overall missing-cell %:     -0.2 per percentage point (capped at -15)
      - duplicate row ratio:        -20 if >10%, -10 if >1%, 0 otherwise
      - isolation-forest pct:       -0.5 per percentage point flagged (capped at -10)
    Floored at 0.
    """
    deductions: list[dict[str, Any]] = []
    score = 100.0

    sev_counts = {"high": 0, "medium": 0, "low": 0}
    for i in issues:
        if i["issue_type"] == "duplicate_rows":
            continue  # counted separately below
        sev_counts[i["severity"]] = sev_counts.get(i["severity"], 0) + 1

    high_d = min(sev_counts["high"] * 10, 40)
    med_d = min(sev_counts["medium"] * 5, 25)
    low_d = min(sev_counts["low"] * 2, 10)
    if high_d:
        deductions.append({"reason": f"{sev_counts['high']} high-severity issue(s)", "points": -high_d})
    if med_d:
        deductions.append({"reason": f"{sev_counts['medium']} medium-severity issue(s)", "points": -med_d})
    if low_d:
        deductions.append({"reason": f"{sev_counts['low']} low-severity issue(s)", "points": -low_d})
    score -= high_d + med_d + low_d

    miss_d = min(summary["overall_missing_pct"] * 0.2, 15)
    if miss_d > 0:
        deductions.append({
            "reason": f"{summary['overall_missing_pct']:.1f}% of cells are missing",
            "points": -round(miss_d, 1),
        })
        score -= miss_d

    dup_ratio = summary["duplicate_row_count"] / max(summary["row_count"], 1)
    if dup_ratio > 0.1:
        deductions.append({"reason": "More than 10% duplicate rows", "points": -20})
        score -= 20
    elif dup_ratio > 0.01:
        deductions.append({"reason": "1–10% duplicate rows", "points": -10})
        score -= 10

    iso = outliers.get("isolation_forest", {})
    iso_pct = iso.get("outlier_row_pct", 0) or 0
    if iso_pct:
        iso_d = min(iso_pct * 0.5, 10)
        deductions.append({
            "reason": f"{iso_pct:.1f}% of rows flagged by Isolation Forest",
            "points": -round(iso_d, 1),
        })
        score -= iso_d

    score = max(0, round(score))
    return {"score": int(score), "deductions": deductions}


# =============================================================================
# Entry point
# =============================================================================

def profile_dataframe(df: pd.DataFrame, *, truncated: bool) -> dict[str, Any]:
    """Build the full profile JSON from an already-loaded DataFrame."""
    n_rows = len(df)
    n_cols = df.shape[1]

    col_profiles = [_column_profile(df[c], str(c), n_rows) for c in df.columns]

    duplicate_row_count = int(df.duplicated().sum())
    total_cells = max(n_rows * n_cols, 1)
    missing_cells = int(df.isna().sum().sum())
    overall_missing_pct = round(missing_cells / total_cells * 100.0, 2)
    total_memory_bytes = int(df.memory_usage(deep=True).sum())

    summary = {
        "row_count": n_rows,
        "column_count": n_cols,
        "duplicate_row_count": duplicate_row_count,
        "total_memory_bytes": total_memory_bytes,
        "overall_missing_pct": overall_missing_pct,
        "sampled": truncated,
        "sample_rows_used": n_rows,
        "profiled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    issues = _detect_issues(df, col_profiles)

    # Pick numeric columns for outlier methods (skip ids and booleans).
    numeric_cols = [
        c["name"] for c in col_profiles
        if c["semantic_type"] == "numeric"
    ]
    outliers = {
        "iqr": _iqr_outliers(df, numeric_cols),
        "zscore": _zscore_outliers(df, numeric_cols),
        "isolation_forest": _isolation_forest_outliers(df, numeric_cols),
    }

    quality = _quality_score(issues, outliers, summary)
    summary["quality_score"] = quality["score"]
    summary["quality_breakdown"] = quality["deductions"]

    profile = {
        "summary": summary,
        "columns": col_profiles,
        "issues": issues,
        "outliers": outliers,
    }
    return to_json_safe(profile)


def profile_from_bytes(raw: bytes, source_type: str) -> dict[str, Any]:
    """Convenience wrapper: bytes → DataFrame → profile."""
    df, truncated = load_dataframe(raw, source_type)
    return profile_dataframe(df, truncated=truncated)


__all__ = ["profile_dataframe", "profile_from_bytes"]
