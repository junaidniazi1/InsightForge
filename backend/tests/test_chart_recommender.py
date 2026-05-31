"""Phase-4 tests: chart recommender + chart-data + engine map."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.chart_data import (
    SCATTER_POINT_CAP,
    apply_filters,
    build_chart_data,
    build_filter_options,
)
from app.services.chart_engine import CHART_ENGINE, engine_for
from app.services.chart_recommender import recommend
from app.services.profiler import profile_dataframe


def _profile(df: pd.DataFrame) -> dict:
    return profile_dataframe(df, truncated=False)


def _types(suggestions: list[dict]) -> list[str]:
    return [s["chart_type"] for s in suggestions]


# =============================================================================
# Engine map
# =============================================================================

def test_engine_map_plotly_for_distribution_and_3d() -> None:
    for t in ("histogram", "box", "violin", "kde", "scatter_3d"):
        assert CHART_ENGINE[t] == "plotly", t
        assert engine_for(t) == "plotly"


def test_engine_map_echarts_for_perf_and_matrix() -> None:
    for t in ("heatmap", "scatter", "line", "bar", "pie"):
        assert CHART_ENGINE[t] == "echarts", t
        assert engine_for(t) == "echarts"


def test_engine_map_kpi() -> None:
    assert engine_for("kpi") == "kpi"


def test_engine_map_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        engine_for("not_a_real_chart")


# =============================================================================
# Recommender
# =============================================================================

def test_single_numeric_yields_histogram_and_box() -> None:
    df = pd.DataFrame({"x": list(range(100))})
    rec = recommend(_profile(df))
    types = _types(rec["suggestions"])
    assert "histogram" in types
    assert "box" in types


def test_datetime_plus_numeric_yields_line() -> None:
    df = pd.DataFrame({
        "d": pd.date_range("2024-01-01", periods=60, freq="D"),
        "v": list(range(60)),
    })
    rec = recommend(_profile(df))
    lines = [s for s in rec["suggestions"] if s["chart_type"] == "line"]
    assert lines
    assert lines[0]["encoding"]["x"] == "d"
    assert lines[0]["encoding"]["y"] == "v"


def test_two_numerics_yield_scatter() -> None:
    df = pd.DataFrame({"x": list(range(50)), "y": list(range(0, 100, 2))})
    rec = recommend(_profile(df))
    assert "scatter" in _types(rec["suggestions"])


def test_all_numeric_frame_yields_heatmap() -> None:
    df = pd.DataFrame({"a": range(50), "b": range(50, 100), "c": range(100, 150)})
    rec = recommend(_profile(df))
    assert "heatmap" in _types(rec["suggestions"])
    hm = next(s for s in rec["suggestions"] if s["chart_type"] == "heatmap")
    assert hm["encoding"]["method"] == "pearson"
    assert {"a", "b", "c"} <= set(hm["encoding"]["columns"])


def test_low_cardinality_categorical_yields_bar_and_pie() -> None:
    df = pd.DataFrame({"color": ["red", "blue", "green", "red", "blue"] * 10})
    rec = recommend(_profile(df))
    types = _types(rec["suggestions"])
    assert "bar" in types
    assert "pie" in types


def test_high_cardinality_categorical_yields_topn_bar() -> None:
    # 30 distinct cities, each repeated ~10×. Categorical, not id-like.
    cities = [f"city_{i}" for i in range(30)] * 10
    df = pd.DataFrame({"city": cities})
    rec = recommend(_profile(df))
    bars = [s for s in rec["suggestions"] if s["chart_type"] == "bar"]
    assert bars, "expected at least one bar suggestion"
    # The high-card variant carries a top_n cap.
    assert any(b.get("top_n") for b in bars)


def test_id_like_columns_are_skipped() -> None:
    df = pd.DataFrame({
        "user_id": list(range(100, 200)),
        "value": list(range(100)),
    })
    rec = recommend(_profile(df))
    # No suggestion's encoding should reference user_id.
    referenced = []
    for s in rec["suggestions"]:
        for v in s["encoding"].values():
            if isinstance(v, str):
                referenced.append(v)
            elif isinstance(v, list):
                referenced.extend([x for x in v if isinstance(x, str)])
    assert "user_id" not in referenced


def test_constant_column_is_skipped() -> None:
    df = pd.DataFrame({"k": [1.0] * 50, "v": list(range(50))})
    rec = recommend(_profile(df))
    referenced: list[str] = []
    for s in rec["suggestions"]:
        for v in s["encoding"].values():
            if isinstance(v, str):
                referenced.append(v)
    assert "k" not in referenced


def test_suggestions_sorted_by_score_desc() -> None:
    df = pd.DataFrame({
        "d": pd.date_range("2024-01-01", periods=30, freq="D"),
        "v": list(range(30)),
        "g": ["A", "B", "C"] * 10,
    })
    rec = recommend(_profile(df))
    scores = [s["score"] for s in rec["suggestions"]]
    assert scores == sorted(scores, reverse=True)


def test_recommender_always_returns_total_rows_kpi() -> None:
    df = pd.DataFrame({"x": list(range(10))})
    rec = recommend(_profile(df))
    assert any(k["title"] == "Total rows" for k in rec["kpis"])


# =============================================================================
# Chart-data aggregation correctness
# =============================================================================

def test_bar_mean_by_category_is_correct() -> None:
    df = pd.DataFrame({
        "g": ["A", "A", "B", "B"],
        "v": [10.0, 20.0, 30.0, 50.0],
    })
    out = build_chart_data(df, {
        "chart_type": "bar",
        "encoding": {"x": "g", "y": "v", "agg": "mean"},
    })
    assert out["engine"] == "echarts"
    categories = out["data"]["categories"]
    values = out["data"]["series"][0]["values"]
    pairs = dict(zip(categories, values))
    assert pairs["A"] == pytest.approx(15.0)
    assert pairs["B"] == pytest.approx(40.0)


def test_bar_count_returns_value_counts() -> None:
    df = pd.DataFrame({"c": ["x", "x", "y", "z", "z", "z"]})
    out = build_chart_data(df, {"chart_type": "bar", "encoding": {"x": "c", "agg": "count"}})
    pairs = dict(zip(out["data"]["categories"], out["data"]["series"][0]["values"]))
    assert pairs == {"z": 3, "x": 2, "y": 1}


def test_kpi_count_rows_uses_filtered_count() -> None:
    df = pd.DataFrame({"v": list(range(10)), "g": ["A"] * 5 + ["B"] * 5})
    out = build_chart_data(df, {
        "chart_type": "kpi",
        "encoding": {"agg": "count_rows"},
        "filters": [{"column": "g", "type": "in", "values": ["A"]}],
    })
    assert out["data"]["value"] == 5


def test_kpi_mean_aggregates_correctly() -> None:
    df = pd.DataFrame({"v": [10.0, 20.0, 30.0]})
    out = build_chart_data(df, {"chart_type": "kpi", "encoding": {"y": "v", "agg": "mean"}})
    assert out["data"]["value"] == pytest.approx(20.0)


def test_heatmap_is_correlation_matrix() -> None:
    df = pd.DataFrame({
        "a": list(range(20)),
        "b": list(range(0, 40, 2)),       # perfectly correlated with a
        "c": list(range(20, 0, -1)),      # perfectly anti-correlated with a
    })
    out = build_chart_data(df, {
        "chart_type": "heatmap",
        "encoding": {"columns": ["a", "b", "c"], "method": "pearson"},
    })
    cols = out["data"]["columns"]
    mat = out["data"]["values"]
    i, j, k = cols.index("a"), cols.index("b"), cols.index("c")
    assert mat[i][j] == pytest.approx(1.0, abs=1e-9)
    assert mat[i][k] == pytest.approx(-1.0, abs=1e-9)


def test_scatter_caps_point_count_and_marks_sampled() -> None:
    n = SCATTER_POINT_CAP + 1000
    df = pd.DataFrame({"x": list(range(n)), "y": list(range(n))})
    out = build_chart_data(df, {"chart_type": "scatter", "encoding": {"x": "x", "y": "y"}})
    assert out["data"]["sampled"] is True
    assert out["data"]["shown"] <= SCATTER_POINT_CAP
    assert out["data"]["n_rows"] == n


def test_histogram_returns_bins_and_counts() -> None:
    df = pd.DataFrame({"x": list(range(100))})
    out = build_chart_data(df, {"chart_type": "histogram", "encoding": {"x": "x"}, "bins": 10})
    assert len(out["data"]["y"]) == 10
    assert sum(out["data"]["y"]) == 100


def test_line_resamples_datetime() -> None:
    df = pd.DataFrame({
        "d": pd.date_range("2024-01-01", periods=30, freq="D"),
        "v": list(range(30)),
    })
    out = build_chart_data(df, {
        "chart_type": "line",
        "encoding": {"x": "d", "y": "v", "agg": "mean"},
    })
    assert out["data"]["freq"] in ("D", "W", "ME", "YE")
    assert len(out["data"]["x"]) == len(out["data"]["series"][0]["values"])


# =============================================================================
# Filtering
# =============================================================================

def test_apply_filters_in_clause() -> None:
    df = pd.DataFrame({"c": ["A", "B", "C", "A"], "v": [1, 2, 3, 4]})
    out = apply_filters(df, [{"column": "c", "type": "in", "values": ["A", "C"]}])
    assert sorted(out["v"].tolist()) == [1, 3, 4]


def test_apply_filters_numeric_range() -> None:
    df = pd.DataFrame({"v": list(range(10))})
    out = apply_filters(df, [{"column": "v", "type": "range", "min": 3, "max": 7}])
    assert out["v"].tolist() == [3, 4, 5, 6, 7]


def test_apply_filters_datetime_range() -> None:
    df = pd.DataFrame({"d": pd.date_range("2024-01-01", periods=10, freq="D")})
    out = apply_filters(df, [{
        "column": "d", "type": "range",
        "min": "2024-01-03", "max": "2024-01-05",
    }])
    assert len(out) == 3


# =============================================================================
# Filter options
# =============================================================================

def test_filter_options_returns_categorical_and_range() -> None:
    df = pd.DataFrame({
        "tag": ["x", "y", "z", "x"],
        "v": [1.0, 2.0, 3.0, 4.0],
        "d": pd.date_range("2024-01-01", periods=4, freq="D"),
    })
    out = build_filter_options(df, [
        {"name": "tag", "semantic_type": "categorical"},
        {"name": "v", "semantic_type": "numeric"},
        {"name": "d", "semantic_type": "datetime"},
    ])
    by_col = {f["column"]: f for f in out["filters"]}
    assert by_col["tag"]["kind"] == "categorical"
    assert set(by_col["tag"]["values"]) == {"x", "y", "z"}
    assert by_col["v"]["kind"] == "numeric_range"
    assert by_col["v"]["min"] == 1.0 and by_col["v"]["max"] == 4.0
    assert by_col["d"]["kind"] == "datetime_range"


# =============================================================================
# Sanity: full suite stays green and recommendations are JSON-safe
# =============================================================================

def test_recommender_output_is_json_safe() -> None:
    import json
    df = pd.DataFrame({"x": [1.0, float("nan"), 3.0]})
    rec = recommend(_profile(df))
    json.dumps(rec)  # would raise if unsafe
