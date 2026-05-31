"""Tests for the cleaning engine.

Covers at least one operation per category and asserts the input DataFrame is
never mutated by the dispatcher.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.cleaner import REGISTRY, apply_steps, compute_diff, get_catalog


# =============================================================================
# Registry / catalog
# =============================================================================

def test_catalog_has_all_required_groups() -> None:
    catalog = get_catalog()
    assert {"core", "text", "datetime", "column", "transform"} <= set(catalog.keys())
    # Every op item is well-formed.
    for group, items in catalog.items():
        for item in items:
            assert {"id", "label", "description", "applies_to", "params"} <= set(item.keys())


def test_registry_covers_phase2_fix_strings() -> None:
    """Every Phase-2 fix string must be dispatchable."""
    phase2_fixes = [
        "impute_median", "impute_mean", "impute_mode",
        "fill_constant", "forward_fill",
        "drop_rows", "drop_column", "drop_duplicates",
        "convert_to_numeric", "convert_to_datetime",
        "convert_to_boolean", "convert_to_text",
        "cap", "winsorize", "remove", "log_transform",
        "keep", "leave_as_is", "review",
    ]
    missing = [f for f in phase2_fixes if f not in REGISTRY]
    assert not missing, f"missing ops: {missing}"


# =============================================================================
# Dispatcher safety
# =============================================================================

def test_dispatcher_does_not_mutate_input() -> None:
    df = pd.DataFrame({"x": [1.0, None, 3.0], "y": ["a", "b", "c"]})
    original = df.copy(deep=True)
    apply_steps(df, [{"op": "impute_median", "columns": ["x"]}])
    pd.testing.assert_frame_equal(df, original)


def test_dispatcher_aborts_on_first_failure() -> None:
    df = pd.DataFrame({"x": [1.0, None, 3.0]})
    with pytest.raises(RuntimeError) as ei:
        apply_steps(df, [
            {"op": "impute_median", "columns": ["x"]},          # ok
            {"op": "drop_column", "columns": ["does_not_exist"]},  # raises
            {"op": "drop_column", "columns": ["x"]},             # never runs
        ])
    assert "step 1" in str(ei.value)


def test_unknown_op_raises() -> None:
    df = pd.DataFrame({"x": [1, 2, 3]})
    with pytest.raises(ValueError):
        apply_steps(df, [{"op": "definitely_not_a_real_op"}])


# =============================================================================
# Missing-value imputation
# =============================================================================

def test_impute_median_fills_correct_count_and_value() -> None:
    df = pd.DataFrame({"x": [1.0, 3.0, None, None, 5.0]})
    out, log = apply_steps(df, [{"op": "impute_median", "columns": ["x"]}])
    assert out["x"].isna().sum() == 0
    # Median of [1, 3, 5] is 3, and the imputed cells (indices 2, 3) now hold 3.
    assert out["x"].iloc[2] == 3.0 and out["x"].iloc[3] == 3.0
    assert log[0]["cells_changed"] == 2
    assert log[0]["values_used"]["x"] == 3.0


def test_impute_mean_fills_correct_value() -> None:
    df = pd.DataFrame({"x": [10.0, 20.0, None, 30.0]})
    out, _ = apply_steps(df, [{"op": "impute_mean", "columns": ["x"]}])
    assert out["x"].isna().sum() == 0
    assert out.iloc[2]["x"] == 20.0  # mean of 10, 20, 30


def test_impute_mode_for_categorical() -> None:
    df = pd.DataFrame({"c": ["a", "a", "b", None, None]})
    out, _ = apply_steps(df, [{"op": "impute_mode", "columns": ["c"]}])
    assert out["c"].isna().sum() == 0
    assert (out["c"] == "a").sum() == 4


def test_fill_constant_uses_value_param() -> None:
    df = pd.DataFrame({"c": ["x", None, None]})
    out, _ = apply_steps(df, [
        {"op": "fill_constant", "columns": ["c"], "params": {"value": "MISSING"}},
    ])
    assert (out["c"] == "MISSING").sum() == 2


def test_forward_fill_and_backward_fill() -> None:
    df = pd.DataFrame({"x": [1.0, None, None, 4.0]})
    out_ff, _ = apply_steps(df, [{"op": "forward_fill", "columns": ["x"]}])
    assert out_ff["x"].tolist() == [1.0, 1.0, 1.0, 4.0]
    out_bf, _ = apply_steps(df, [{"op": "backward_fill", "columns": ["x"]}])
    assert out_bf["x"].tolist() == [1.0, 4.0, 4.0, 4.0]


def test_linear_interpolate() -> None:
    df = pd.DataFrame({"x": [1.0, None, None, 4.0]})
    out, _ = apply_steps(df, [{"op": "linear_interpolate", "columns": ["x"]}])
    assert out["x"].tolist() == [1.0, 2.0, 3.0, 4.0]


def test_knn_impute_fills_nulls() -> None:
    df = pd.DataFrame({
        "x": [1.0, 2.0, None, 4.0, 5.0],
        "y": [1.0, 2.0, 3.0, 4.0, 5.0],
    })
    out, _ = apply_steps(df, [
        {"op": "knn_impute", "columns": ["x", "y"], "params": {"n_neighbors": 2}},
    ])
    assert out["x"].isna().sum() == 0


# =============================================================================
# Drop rows / columns / duplicates
# =============================================================================

def test_drop_rows_with_nulls_drops_correct_count() -> None:
    df = pd.DataFrame({"x": [1.0, None, 3.0], "y": [None, "b", "c"]})
    out, _ = apply_steps(df, [{"op": "drop_rows", "columns": ["x"]}])
    assert len(out) == 2  # only the row where x is null is dropped


def test_drop_column() -> None:
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    out, _ = apply_steps(df, [{"op": "drop_column", "columns": ["b"]}])
    assert list(out.columns) == ["a"]


def test_drop_duplicates_removes_repeated_rows() -> None:
    df = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": ["x", "x", "y", "y", "z"]})
    out, log = apply_steps(df, [{"op": "drop_duplicates"}])
    assert len(out) == 3
    assert log[0]["rows_dropped"] == 2


# =============================================================================
# Type conversion
# =============================================================================

def test_convert_to_numeric_changes_dtype() -> None:
    df = pd.DataFrame({"x": ["1.5", "2", "bad"]})
    out, log = apply_steps(df, [{"op": "convert_to_numeric", "columns": ["x"]}])
    assert pd.api.types.is_numeric_dtype(out["x"])
    assert out["x"].isna().sum() == 1
    assert log[0]["coerced_to_nan"]["x"] == 1


def test_convert_to_datetime_changes_dtype() -> None:
    df = pd.DataFrame({"d": ["2024-01-15", "2024-02-20"]})
    out, _ = apply_steps(df, [{"op": "convert_to_datetime", "columns": ["d"]}])
    assert pd.api.types.is_datetime64_any_dtype(out["d"])


def test_convert_to_boolean_handles_truthy_falsy() -> None:
    df = pd.DataFrame({"b": ["yes", "no", "TRUE", "false", "junk"]})
    out, _ = apply_steps(df, [{"op": "convert_to_boolean", "columns": ["b"]}])
    assert out["b"].tolist()[:4] == [True, False, True, False]
    assert pd.isna(out["b"].iloc[4])


# =============================================================================
# Outliers
# =============================================================================

def test_cap_iqr_bounds_values() -> None:
    df = pd.DataFrame({"x": list(range(100)) + [10_000]})
    before_max = df["x"].max()
    out, log = apply_steps(df, [{"op": "cap", "columns": ["x"]}])
    assert out["x"].max() < before_max
    assert out["x"].max() <= log[0]["bounds"]["x"]["upper"]


def test_winsorize_clips_to_percentile_bounds() -> None:
    df = pd.DataFrame({"x": list(range(100))})
    out, log = apply_steps(df, [
        {"op": "winsorize", "columns": ["x"], "params": {"lower_pct": 10, "upper_pct": 90}},
    ])
    lo = log[0]["bounds"]["x"]["lower"]
    hi = log[0]["bounds"]["x"]["upper"]
    assert out["x"].min() >= lo
    assert out["x"].max() <= hi


def test_remove_outliers_drops_rows() -> None:
    df = pd.DataFrame({"x": list(range(100)) + [10_000, 20_000, 30_000]})
    out, _ = apply_steps(df, [
        {"op": "remove_outliers", "columns": ["x"], "params": {"method": "iqr"}},
    ])
    assert out["x"].max() < 10_000
    assert len(out) < len(df)


def test_log_transform_changes_values() -> None:
    df = pd.DataFrame({"x": [0.0, 1.0, np.e - 1, 10.0]})
    out, _ = apply_steps(df, [{"op": "log_transform", "columns": ["x"]}])
    # log1p(0) = 0, log1p(e-1) ≈ 1
    assert out["x"].iloc[0] == pytest.approx(0.0)
    assert out["x"].iloc[2] == pytest.approx(1.0, rel=1e-9)


# =============================================================================
# Text / categorical standardization
# =============================================================================

def test_trim_whitespace_and_case_ops() -> None:
    df = pd.DataFrame({"s": ["  Hello ", "WORLD", "MiXeD"]})
    out, _ = apply_steps(df, [
        {"op": "trim_whitespace", "columns": ["s"]},
        {"op": "lowercase", "columns": ["s"]},
    ])
    assert out["s"].tolist() == ["hello", "world", "mixed"]


def test_remove_special_chars_strips_punctuation() -> None:
    df = pd.DataFrame({"s": ["hello, world!", "$100.00"]})
    out, _ = apply_steps(df, [{"op": "remove_special_chars", "columns": ["s"]}])
    assert out["s"].tolist() == ["hello world", "10000"]


def test_regex_replace_uses_pattern_and_replacement() -> None:
    df = pd.DataFrame({"s": ["abc123", "x9y8"]})
    out, _ = apply_steps(df, [{
        "op": "regex_replace",
        "columns": ["s"],
        "params": {"pattern": r"\d+", "replacement": "#"},
    }])
    assert out["s"].tolist() == ["abc#", "x#y#"]


def test_standardize_categories_maps_variants() -> None:
    df = pd.DataFrame({"country": ["USA", "usa", "United States", "UK", "uk"]})
    out, log = apply_steps(df, [{
        "op": "standardize_categories",
        "columns": ["country"],
        "params": {
            "mapping": {"usa": "US", "united states": "US", "uk": "UK"},
            "case_insensitive": True,
        },
    }])
    assert out["country"].tolist() == ["US", "US", "US", "UK", "UK"]
    assert log[0]["cells_changed"] >= 3


# =============================================================================
# Datetime feature extraction
# =============================================================================

def test_extract_datetime_parts_creates_new_columns() -> None:
    df = pd.DataFrame({
        "d": pd.to_datetime(["2024-01-15 10:30:00", "2024-07-04 14:20:00"]),
    })
    out, log = apply_steps(df, [{
        "op": "extract_datetime_parts",
        "columns": ["d"],
        "params": {"parts": ["year", "month", "quarter", "hour"]},
    }])
    for col in ("d_year", "d_month", "d_quarter", "d_hour"):
        assert col in out.columns
    assert out["d_year"].tolist() == [2024, 2024]
    assert out["d_quarter"].tolist() == [1, 3]
    assert "d_year" in log[0]["columns_added"]


# =============================================================================
# Column ops
# =============================================================================

def test_rename_column() -> None:
    df = pd.DataFrame({"old": [1, 2, 3]})
    out, _ = apply_steps(df, [{
        "op": "rename_column",
        "columns": ["old"],
        "params": {"new_name": "new"},
    }])
    assert list(out.columns) == ["new"]


def test_reorder_columns() -> None:
    df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    out, _ = apply_steps(df, [{
        "op": "reorder_columns",
        "params": {"order": ["c", "a", "b"]},
    }])
    assert list(out.columns) == ["c", "a", "b"]


# =============================================================================
# Optional transforms
# =============================================================================

def test_onehot_encode_produces_one_column_per_category() -> None:
    df = pd.DataFrame({"color": ["red", "green", "blue", "red"]})
    out, log = apply_steps(df, [{"op": "onehot_encode", "columns": ["color"]}])
    assert "color" not in out.columns
    assert set(out.columns) == {"color_red", "color_green", "color_blue"}
    assert "color_red" in log[0]["columns_added"]


def test_label_encode_produces_integers() -> None:
    df = pd.DataFrame({"c": ["a", "b", "a", "c"]})
    out, _ = apply_steps(df, [{"op": "label_encode", "columns": ["c"]}])
    assert pd.api.types.is_numeric_dtype(out["c"])
    assert out["c"].nunique() == 3


def test_scale_standard_zero_mean_unit_std() -> None:
    df = pd.DataFrame({"x": list(range(100))})
    out, _ = apply_steps(df, [{"op": "scale_standard", "columns": ["x"]}])
    assert out["x"].mean() == pytest.approx(0.0, abs=1e-10)
    # sklearn's StandardScaler uses population std (ddof=0).
    assert out["x"].std(ddof=0) == pytest.approx(1.0, abs=1e-10)


def test_scale_minmax_to_unit_range() -> None:
    df = pd.DataFrame({"x": [10.0, 20.0, 30.0]})
    out, _ = apply_steps(df, [{"op": "scale_minmax", "columns": ["x"]}])
    assert out["x"].min() == pytest.approx(0.0)
    assert out["x"].max() == pytest.approx(1.0)


def test_bin_equal_width_creates_buckets() -> None:
    df = pd.DataFrame({"x": list(range(100))})
    out, _ = apply_steps(df, [{
        "op": "bin_equal_width",
        "columns": ["x"],
        "params": {"n_bins": 4},
    }])
    assert out["x"].nunique() == 4


# =============================================================================
# Diff
# =============================================================================

def test_compute_diff_captures_added_dropped_and_nulls() -> None:
    before = pd.DataFrame({
        "a": [1, 1, None, 2],
        "b": [10, 10, 30, 40],
    })
    after = pd.DataFrame({
        "a": [1.0, 99.0, 2.0],
        "c": ["x", "y", "z"],
    })
    diff = compute_diff(before, after)
    assert diff["rows_before"] == 4
    assert diff["rows_after"] == 3
    assert diff["columns_added"] == ["c"]
    assert diff["columns_dropped"] == ["b"]
    assert diff["null_counts"]["a"] == {"before": 1, "after": 0}


def test_full_pipeline_produces_meaningful_diff() -> None:
    df = pd.DataFrame({
        "x": [1.0, None, None, 4.0, 5.0, 1.0, 1.0],
        "tag": ["A", "A", "B", "C", "C", "A", "A"],
    })
    out, _ = apply_steps(df, [
        {"op": "impute_median", "columns": ["x"]},
        {"op": "drop_duplicates"},
    ])
    diff = compute_diff(df, out)
    assert diff["null_counts"]["x"] == {"before": 2, "after": 0}
    assert diff["duplicates_after"] == 0
    assert diff["rows_after"] < diff["rows_before"]
