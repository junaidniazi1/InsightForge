"""Tests for the profiler service.

We build small DataFrames with known properties (nulls, duplicates, string-typed
numbers, a constant column, obvious outliers) and assert each issue is detected
and that the three outlier methods are returned as separate groups.
"""

from __future__ import annotations

import io
import json

import numpy as np
import pandas as pd
import pytest

from app.services.data_loader import load_dataframe
from app.services.profiler import profile_dataframe, profile_from_bytes


def _profile(df: pd.DataFrame) -> dict:
    return profile_dataframe(df, truncated=False)


def _issues_by_type(p: dict, type_: str) -> list[dict]:
    return [i for i in p["issues"] if i["issue_type"] == type_]


def _col(p: dict, name: str) -> dict:
    return next(c for c in p["columns"] if c["name"] == name)


# =============================================================================
# Shape / JSON safety
# =============================================================================

def test_profile_is_json_safe_with_nan_inf() -> None:
    df = pd.DataFrame({
        "x": [1.0, float("nan"), float("inf"), -float("inf"), 4.0],
        "y": ["a", "b", None, "d", "e"],
    })
    p = _profile(df)
    # Should round-trip through JSON without raising.
    s = json.dumps(p)
    assert isinstance(s, str)


def test_profile_top_level_shape() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    p = _profile(df)
    assert set(p.keys()) == {"summary", "columns", "issues", "outliers"}
    assert {"iqr", "zscore", "isolation_forest"} <= set(p["outliers"].keys())
    assert "quality_score" in p["summary"]
    assert 0 <= p["summary"]["quality_score"] <= 100


# =============================================================================
# Issue detection
# =============================================================================

def test_detects_missing_values() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, None, None, 5.0, None]})
    p = _profile(df)
    miss = _issues_by_type(p, "missing_values")
    assert len(miss) == 1
    assert miss[0]["column"] == "x"
    assert miss[0]["severity"] in ("low", "medium", "high")
    # 50% nulls → high
    assert miss[0]["severity"] == "high"
    assert "impute_median" in miss[0]["fix_options"]


def test_detects_numeric_stored_as_text() -> None:
    df = pd.DataFrame({"price": ["1.50", "2.75", "3.00", "4.20", "5.10"]})
    p = _profile(df)
    type_issues = _issues_by_type(p, "numeric_as_text")
    assert len(type_issues) == 1
    assert type_issues[0]["column"] == "price"
    assert "convert_to_numeric" in type_issues[0]["fix_options"]


def test_detects_date_stored_as_text() -> None:
    df = pd.DataFrame({
        "d": ["2024-01-01", "2024-02-15", "2024-03-30", "2024-04-10", "2024-05-22"],
    })
    p = _profile(df)
    date_issues = _issues_by_type(p, "date_as_text")
    assert len(date_issues) == 1
    assert date_issues[0]["column"] == "d"


def test_detects_boolean_stored_as_string() -> None:
    df = pd.DataFrame({"active": ["yes", "no", "yes", "no", "yes"]})
    p = _profile(df)
    bool_issues = _issues_by_type(p, "boolean_as_string")
    assert len(bool_issues) == 1


def test_detects_mixed_types() -> None:
    df = pd.DataFrame({"mixed": [1, "two", 3, "four", 5, "six"]})
    p = _profile(df)
    assert len(_issues_by_type(p, "mixed_types")) == 1


def test_detects_duplicate_rows() -> None:
    df = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": ["x", "x", "y", "y", "z"]})
    p = _profile(df)
    dups = _issues_by_type(p, "duplicate_rows")
    assert len(dups) == 1
    assert dups[0]["column"] is None
    assert "drop_duplicates" in dups[0]["fix_options"]
    assert p["summary"]["duplicate_row_count"] == 2


def test_detects_constant_column() -> None:
    df = pd.DataFrame({"k": ["same"] * 50, "v": list(range(50))})
    p = _profile(df)
    assert len(_issues_by_type(p, "constant_column")) == 1


def test_detects_near_constant_column() -> None:
    vals = ["A"] * 97 + ["B"] * 3
    df = pd.DataFrame({"flag": vals, "x": list(range(100))})
    p = _profile(df)
    assert len(_issues_by_type(p, "near_constant_column")) == 1


def test_detects_id_like_column() -> None:
    df = pd.DataFrame({"user_id": list(range(1000, 1100)), "v": [1] * 100})
    p = _profile(df)
    assert len(_issues_by_type(p, "id_like_column")) == 1
    assert _col(p, "user_id")["semantic_type"] == "id_like"


# =============================================================================
# Outliers — three SEPARATE groups
# =============================================================================

def test_outliers_returned_as_three_separate_groups() -> None:
    # Build a numeric column with clear outliers.
    rng = np.random.default_rng(seed=0)
    normal = rng.normal(loc=0, scale=1, size=200)
    with_outliers = np.concatenate([normal, [100.0, -100.0, 200.0]])
    df = pd.DataFrame({
        "x": with_outliers,
        "y": rng.normal(loc=50, scale=5, size=len(with_outliers)),
    })
    p = _profile(df)

    iqr = p["outliers"]["iqr"]
    z = p["outliers"]["zscore"]
    iso = p["outliers"]["isolation_forest"]

    # All three present and labeled.
    assert iqr["method"] == "iqr"
    assert z["method"] == "zscore"
    assert iso["method"] == "isolation_forest"

    # Each carries its own method description so the UI can explain the difference.
    assert "Q1" in iqr["method_description"] or "IQR" in iqr["method_description"]
    assert "standard deviation" in z["method_description"].lower()
    assert "multivariate" in iso["method_description"].lower()

    # IQR / Z-score per-column buckets exist for the noisy column.
    iqr_cols = {c["column"] for c in iqr["columns"]}
    z_cols = {c["column"] for c in z["columns"]}
    assert "x" in iqr_cols and "x" in z_cols

    # Each per-column entry carries its own bounds + suggested fix.
    x_iqr = next(c for c in iqr["columns"] if c["column"] == "x")
    assert x_iqr["lower_bound"] < x_iqr["upper_bound"]
    assert x_iqr["suggested_fix"] in {"cap", "winsorize", "remove", "log_transform", "keep"}

    # Isolation Forest reports row-level (not column-level).
    assert iso["available"] is True
    assert iso["outlier_row_count"] >= 1


def test_outliers_isolation_forest_unavailable_without_numeric() -> None:
    df = pd.DataFrame({"label": ["a", "b", "c", "d", "e"]})
    p = _profile(df)
    assert p["outliers"]["isolation_forest"]["available"] is False


# =============================================================================
# Per-column profile + numeric stats
# =============================================================================

def test_numeric_stats_present_for_numeric_columns() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
    p = _profile(df)
    stats = _col(p, "x")["numeric_stats"]
    assert stats is not None
    assert stats["min"] == 1.0 and stats["max"] == 5.0
    assert stats["median"] == 3.0


def test_top_values_present_for_categorical_columns() -> None:
    df = pd.DataFrame({"cat": ["a", "a", "b", "c", "a", "b"]})
    p = _profile(df)
    tops = _col(p, "cat")["top_values"]
    assert tops is not None
    assert tops[0]["value"] == "a"
    assert tops[0]["count"] == 3


# =============================================================================
# Quality score
# =============================================================================

def test_clean_data_has_high_quality_score() -> None:
    df = pd.DataFrame({
        "x": list(range(100)),
        "y": [f"label_{i % 10}" for i in range(100)],
    })
    p = _profile(df)
    assert p["summary"]["quality_score"] >= 90


def test_messy_data_has_lower_quality_score() -> None:
    df = pd.DataFrame({
        "x": [None, None, None, None, 5.0, 6.0, None, None],  # 75% null → high
        "y": ["a"] * 8,                                         # constant
        "dup1": [1, 1, 2, 2, 3, 3, 4, 4],                       # duplicates with dup2
        "dup2": ["x", "x", "y", "y", "z", "z", "w", "w"],
    })
    clean = pd.DataFrame({"x": list(range(50)), "y": list(range(50, 100))})
    pm = _profile(df)
    pc = _profile(clean)
    assert pm["summary"]["quality_score"] < pc["summary"]["quality_score"]


# =============================================================================
# Integration: bytes → profile (used by the background worker)
# =============================================================================

def test_profile_from_csv_bytes() -> None:
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": ["x", "y", "z", "x", "y"]})
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    p = profile_from_bytes(buf.getvalue(), "file_csv")
    assert p["summary"]["row_count"] == 5
    assert p["summary"]["column_count"] == 2


def test_profile_rejects_unknown_source_type() -> None:
    with pytest.raises(ValueError):
        profile_from_bytes(b"x", "file_parquet")  # not supported
