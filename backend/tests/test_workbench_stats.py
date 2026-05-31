"""Phase 7A tests — Statistics, Correlation, Hypothesis, Time-Series."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.workbench._common import WorkbenchError
from app.services.workbench.correlation import run_correlation
from app.services.workbench.describe import run_describe
from app.services.workbench.hypothesis import recommend_test, run_hypothesis_test
from app.services.workbench.timeseries import (
    run_acf_pacf,
    run_decompose,
    run_resample,
    run_stationarity,
)


# ===========================================================================
# Describe
# ===========================================================================

def test_describe_computes_correct_stats() -> None:
    df = pd.DataFrame({"x": list(range(1, 101))})  # 1..100
    out = run_describe(df, ["x"])
    stats = out["result"]["columns"][0]
    assert stats["mean"] == pytest.approx(50.5)
    assert stats["median"] == pytest.approx(50.5)
    assert stats["min"] == 1.0
    assert stats["max"] == 100.0
    assert stats["count"] == 100
    # Two charts: histogram + box.
    types = [c["spec"]["chart_type"] for c in out["charts"]]
    assert types == ["histogram", "box"]


def test_describe_flags_skewed_distribution() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"income": np.concatenate([rng.normal(100, 10, 200), [10_000] * 10])})
    out = run_describe(df, ["income"])
    interpretation = out["interpretation"].lower()
    assert "skew" in interpretation


def test_describe_rejects_missing_column() -> None:
    df = pd.DataFrame({"x": [1, 2, 3]})
    with pytest.raises(WorkbenchError):
        run_describe(df, ["missing"])


def test_describe_rejects_no_columns_picked() -> None:
    df = pd.DataFrame({"x": [1, 2, 3]})
    with pytest.raises(WorkbenchError):
        run_describe(df, [])


# ===========================================================================
# Correlation
# ===========================================================================

def test_correlation_self_is_one_and_negation_is_minus_one() -> None:
    x = list(range(50))
    df = pd.DataFrame({"x": x, "y": x, "z": [-v for v in x]})
    out = run_correlation(df, ["x", "y", "z"], method="pearson")
    cols = out["result"]["columns"]
    mat = out["result"]["matrix"]
    i, j, k = cols.index("x"), cols.index("y"), cols.index("z")
    assert mat[i][j] == pytest.approx(1.0, abs=1e-9)
    assert mat[i][i] == pytest.approx(1.0, abs=1e-9)
    assert mat[i][k] == pytest.approx(-1.0, abs=1e-9)


def test_correlation_top_pairs_ranked_by_absolute_value() -> None:
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1, 200)
    df = pd.DataFrame({
        "strong_pos": base,
        "strong_neg": -base + rng.normal(0, 0.05, 200),
        "weak": rng.normal(0, 1, 200),
    })
    out = run_correlation(df, ["strong_pos", "strong_neg", "weak"], method="pearson")
    top = out["result"]["top_pairs"]
    # The strongest pair is strong_pos ↔ strong_neg.
    first = top[0]
    assert {first["a"], first["b"]} == {"strong_pos", "strong_neg"}
    assert abs(first["r"]) > 0.9
    assert first["significant"] is True


def test_correlation_rejects_unknown_method() -> None:
    df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    with pytest.raises(WorkbenchError):
        run_correlation(df, ["x", "y"], method="bogus")  # type: ignore[arg-type]


def test_correlation_engine_is_echarts_heatmap() -> None:
    df = pd.DataFrame({"a": list(range(30)), "b": list(range(30, 60))})
    out = run_correlation(df, ["a", "b"])
    chart = out["charts"][0]
    assert chart["spec"]["chart_type"] == "heatmap"
    assert chart["data"]["engine"] == "echarts"


# ===========================================================================
# Hypothesis tests
# ===========================================================================

def test_one_sample_t_test_rejects_when_mean_is_different() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"v": rng.normal(loc=10.0, scale=1.0, size=200)})
    out = run_hypothesis_test(df, "ttest_one", value_col="v", popmean=0.0)
    assert out["result"]["p_value"] < 1e-10
    assert "reject" in out["interpretation"].lower()


def test_two_sample_t_test_rejects_on_clearly_different_groups() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "v": np.concatenate([rng.normal(0, 1, 100), rng.normal(5, 1, 100)]),
        "g": ["A"] * 100 + ["B"] * 100,
    })
    out = run_hypothesis_test(df, "ttest_two", value_col="v", group_col="g")
    assert out["result"]["p_value"] < 1e-10
    assert abs(out["result"]["cohens_d"]) > 1.5


def test_anova_fails_to_reject_for_identical_distributions() -> None:
    # Three groups drawn from the same distribution (different samples) — ANOVA
    # should fail to reject. Identical *arrays* would give 0/0 = NaN, so we
    # draw three independent samples instead.
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "v": np.concatenate([rng.normal(0, 1, 100) for _ in range(3)]),
        "g": ["A"] * 100 + ["B"] * 100 + ["C"] * 100,
    })
    out = run_hypothesis_test(df, "anova", value_col="v", group_col="g")
    assert out["result"]["p_value"] > 0.05


def test_anova_rejects_on_clearly_different_groups() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "v": np.concatenate([rng.normal(0, 1, 100), rng.normal(3, 1, 100), rng.normal(6, 1, 100)]),
        "g": ["A"] * 100 + ["B"] * 100 + ["C"] * 100,
    })
    out = run_hypothesis_test(df, "anova", value_col="v", group_col="g")
    assert out["result"]["p_value"] < 1e-10


def test_chi_square_rejects_for_dependent_table() -> None:
    # Rows clearly differ in column distribution → not independent.
    df = pd.DataFrame({
        "row": ["A"] * 100 + ["B"] * 100,
        "col": (["x"] * 90 + ["y"] * 10) + (["x"] * 10 + ["y"] * 90),
    })
    out = run_hypothesis_test(df, "chi_square", value_col="row", second_col="col")
    assert out["result"]["p_value"] < 1e-10


def test_chi_square_fails_to_reject_for_independent_table() -> None:
    # 50/50 split in both groups → independent.
    df = pd.DataFrame({
        "row": ["A"] * 100 + ["B"] * 100,
        "col": (["x"] * 50 + ["y"] * 50) * 2,
    })
    out = run_hypothesis_test(df, "chi_square", value_col="row", second_col="col")
    assert out["result"]["p_value"] > 0.05


def test_mann_whitney_rejects_on_distinct_distributions() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "v": np.concatenate([rng.normal(0, 1, 100), rng.normal(5, 1, 100)]),
        "g": ["A"] * 100 + ["B"] * 100,
    })
    out = run_hypothesis_test(df, "mann_whitney", value_col="v", group_col="g")
    assert out["result"]["p_value"] < 1e-10


def test_hypothesis_rejects_missing_required_params() -> None:
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0]})
    with pytest.raises(WorkbenchError):
        run_hypothesis_test(df, "ttest_two", value_col="v")  # no group_col


def test_recommend_test_suggests_chi_square_for_two_categoricals() -> None:
    cols = [
        {"name": "color", "semantic_type": "categorical", "unique_count": 3},
        {"name": "size", "semantic_type": "categorical", "unique_count": 4},
    ]
    rec = recommend_test(cols, ["color", "size"])
    assert rec["recommendation"] == "chi_square"


def test_recommend_test_suggests_two_sample_ttest_for_binary_group() -> None:
    cols = [
        {"name": "v", "semantic_type": "numeric", "unique_count": 100},
        {"name": "g", "semantic_type": "categorical", "unique_count": 2},
    ]
    rec = recommend_test(cols, ["v", "g"])
    assert rec["recommendation"] == "ttest_two"


def test_recommend_test_suggests_anova_for_multi_group() -> None:
    cols = [
        {"name": "v", "semantic_type": "numeric", "unique_count": 100},
        {"name": "g", "semantic_type": "categorical", "unique_count": 5},
    ]
    rec = recommend_test(cols, ["v", "g"])
    assert rec["recommendation"] == "anova"


# ===========================================================================
# Time-series
# ===========================================================================

def _stationary_series(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    values = rng.normal(0, 1, n)  # White noise → stationary.
    return pd.DataFrame({"d": dates, "v": values})


def _random_walk(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    steps = rng.normal(0, 1, n)
    values = np.cumsum(steps)  # Random walk → non-stationary.
    return pd.DataFrame({"d": dates, "v": values})


def test_resample_rolls_up_to_requested_frequency() -> None:
    df = _stationary_series(n=180)
    out = run_resample(df, x="d", y="v", freq="ME", agg="mean")
    # ~6 months of daily data → 6 months in the resampled series.
    assert len(out["result"]["x"]) >= 5
    assert out["charts"][0]["spec"]["chart_type"] == "line"


def test_decompose_components_reconstruct_observed() -> None:
    # Build a deterministic seasonal series.
    n = 24 * 12  # 24 months daily-ish
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    trend = np.linspace(0, 5, n)
    seasonal = np.sin(np.linspace(0, 4 * np.pi, n))
    df = pd.DataFrame({"d": dates, "v": trend + seasonal})
    out = run_decompose(df, x="d", y="v", freq="D", period=30, model="additive")
    r = out["result"]
    observed = np.array(r["observed"], dtype=float)
    trend_out = np.array([v if v is not None else np.nan for v in r["trend"]], dtype=float)
    seasonal_out = np.array(r["seasonal"], dtype=float)
    residual = np.array([v if v is not None else np.nan for v in r["residual"]], dtype=float)
    # observed ≈ trend + seasonal + residual (allowing for NaNs at the ends).
    reconstructed = trend_out + seasonal_out + residual
    mask = ~np.isnan(reconstructed)
    np.testing.assert_allclose(observed[mask], reconstructed[mask], atol=1e-6)


def test_acf_pacf_returns_requested_lags() -> None:
    df = _stationary_series(n=120)
    out = run_acf_pacf(df, x="d", y="v", freq="D", nlags=20)
    assert len(out["result"]["acf"]) == 21
    assert len(out["result"]["pacf"]) == 21
    # First lag of ACF is always 1.
    assert out["result"]["acf"][0] == pytest.approx(1.0)
    # Two charts (ACF + PACF).
    assert len(out["charts"]) == 2


def test_adf_flags_stationary_series() -> None:
    df = _stationary_series(n=300)
    out = run_stationarity(df, x="d", y="v", freq="D")
    assert out["result"]["is_stationary"] is True
    assert out["result"]["p_value"] < 0.05
    assert "stationary" in out["interpretation"].lower()


def test_adf_flags_random_walk_as_non_stationary() -> None:
    df = _random_walk(n=300)
    out = run_stationarity(df, x="d", y="v", freq="D")
    assert out["result"]["is_stationary"] is False
    assert out["result"]["p_value"] > 0.05
    assert "non-stationary" in out["interpretation"].lower()


def test_timeseries_rejects_unparseable_x() -> None:
    df = pd.DataFrame({"d": ["bad"] * 30, "v": list(range(30))})
    with pytest.raises(WorkbenchError):
        run_resample(df, x="d", y="v", freq="D")
