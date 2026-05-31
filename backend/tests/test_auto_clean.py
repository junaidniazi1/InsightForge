"""Phase-6 tests for the auto-clean agent."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.auto_clean import build_auto_plan, plan_summary
from app.services.cleaner import apply_steps
from app.services.profiler import profile_dataframe


def _profile(df: pd.DataFrame) -> dict:
    return profile_dataframe(df, truncated=False)


def _ops(plan: list[dict]) -> list[str]:
    return [s["op"] for s in plan]


def _dropped_columns(plan: list[dict]) -> set[str]:
    return {s["columns"][0] for s in plan if s["op"] == "drop_column"}


# ---------------------------------------------------------------------------
# Fixture: one DataFrame that intentionally exercises every code path
# ---------------------------------------------------------------------------

@pytest.fixture
def messy() -> pd.DataFrame:
    """A deliberately ugly dataset.

    Includes:
      - numeric column with ~25% nulls       → should impute_median
      - numeric-as-text column               → should convert_to_numeric
      - date-as-text column                  → should convert_to_datetime
      - >60% null column                     → should drop_column
      - constant column                      → should drop_column
      - low-card categorical with whitespace → should trim + impute_mode
      - numeric column with one big outlier  → should cap (NOT remove rows)
      - duplicate rows                       → should drop_duplicates
    """
    df = pd.DataFrame({
        "age":         [25.0, 30.0, None, None, 40.0, 35.0, 28.0, 33.0],
        "price_text":  ["1.50", "2.00", "3.50", "4.20", "5.00", "6.10", "7.30", "8.40"],
        "joined_text": ["2024-01-01", "2024-02-15", "2024-03-30", "2024-04-10",
                        "2024-05-22", "2024-06-04", "2024-07-19", "2024-08-30"],
        "mostly_null": [None, None, None, None, None, None, 1.0, 2.0],
        "constant":    ["X"] * 8,
        "region":      ["US ", "  EU", "US", "EU", "US ", None, "EU ", " US"],
        "spend":       [10.0, 12.0, 11.0, 13.0, 9.0, 10.5, 11.5, 5_000.0],
        "filler":      [1, 2, 3, 4, 5, 6, 7, 8],
    })
    # Add real duplicates of the first row so duplicate_rows is detected.
    return pd.concat([df, df.iloc[[0, 0]]], ignore_index=True)


def test_includes_drop_duplicates(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    assert "drop_duplicates" in _ops(plan)


def test_drops_high_null_column(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    assert "mostly_null" in _dropped_columns(plan)
    # And does NOT also propose an impute step for it.
    impute_targets = [s["columns"][0] for s in plan if s["op"].startswith("impute_")]
    assert "mostly_null" not in impute_targets


def test_drops_constant_column(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    assert "constant" in _dropped_columns(plan)


def test_converts_numeric_as_text(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    convert_targets = [s["columns"][0] for s in plan if s["op"] == "convert_to_numeric"]
    assert "price_text" in convert_targets


def test_converts_date_as_text(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    convert_targets = [s["columns"][0] for s in plan if s["op"] == "convert_to_datetime"]
    assert "joined_text" in convert_targets


def test_imputes_numeric_nulls_with_median(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    impute_targets = [s["columns"][0] for s in plan if s["op"] == "impute_median"]
    assert "age" in impute_targets


def test_imputes_categorical_nulls_with_mode(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    impute_targets = [s["columns"][0] for s in plan if s["op"] == "impute_mode"]
    assert "region" in impute_targets


def test_trims_whitespace_on_categorical(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    trim_targets = [s["columns"][0] for s in plan if s["op"] == "trim_whitespace"]
    assert "region" in trim_targets


def test_caps_outliers_without_removing_rows(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    ops = _ops(plan)
    cap_targets = [s["columns"][0] for s in plan if s["op"] == "cap"]
    assert "spend" in cap_targets
    # Never propose row-removal for outliers.
    assert "remove_outliers" not in ops
    assert "remove" not in ops
    assert "drop_rows" not in ops
    assert "remove_rows_by_index" not in ops


def test_each_step_has_rationale(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    assert plan
    for s in plan:
        assert isinstance(s["rationale"], str) and s["rationale"].strip()


def test_step_ordering_is_deterministic(messy: pd.DataFrame) -> None:
    plan_a = build_auto_plan(_profile(messy))
    plan_b = build_auto_plan(_profile(messy))
    assert plan_a == plan_b


def test_step_ordering_runs_converts_before_imputes(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    ops = _ops(plan)
    if "convert_to_numeric" in ops and "impute_median" in ops:
        assert ops.index("convert_to_numeric") < ops.index("impute_median")
    if "drop_column" in ops and "drop_duplicates" in ops:
        # column drops happen before row-level work
        assert ops.index("drop_column") < ops.index("drop_duplicates")


def test_pipeline_is_valid_runs_through_apply_steps(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    # Strip rationale before handing to the dispatcher.
    steps = [{"op": s["op"], "columns": s["columns"], "params": s["params"]} for s in plan]
    out, log = apply_steps(messy, steps)
    assert len(out) < len(messy)              # duplicates dropped
    assert "mostly_null" not in out.columns
    assert "constant" not in out.columns
    assert out["age"].isna().sum() == 0       # imputed
    assert out["spend"].max() < 5_000.0       # capped


def test_empty_profile_yields_empty_plan() -> None:
    df = pd.DataFrame({"x": list(range(100))})  # nothing to clean
    plan = build_auto_plan(_profile(df))
    # The clean column shouldn't get any per-column steps.
    drops = _dropped_columns(plan)
    assert "x" not in drops


def test_id_like_columns_are_never_dropped() -> None:
    df = pd.DataFrame({
        "user_id": list(range(1000, 1050)),
        "v": list(range(50)),
    })
    plan = build_auto_plan(_profile(df))
    assert "user_id" not in _dropped_columns(plan)


def test_plan_summary_reports_step_count(messy: pd.DataFrame) -> None:
    plan = build_auto_plan(_profile(messy))
    summary = plan_summary(plan)
    assert str(len(plan)) in summary
