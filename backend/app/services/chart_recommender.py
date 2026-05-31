"""Chart recommender.

Inputs a Phase-2 profile (semantic types + per-column stats) and returns a
ranked list of chart suggestions plus a KPI list. Each suggestion carries the
engine, a rationale, and a numeric score used for ranking.

Why this exists: opening a fresh dataset shouldn't make the user pick chart
types from scratch. We use semantic types and cardinality to pick what will
actually be useful for *this* data — distributions for numeric, frequency for
low-card categoricals, time series for datetimes, correlation overview for
all-numeric pairs.
"""

from __future__ import annotations

from typing import Any

from .chart_engine import KPI_ENGINE, engine_for

# Tunables — collected here so they're easy to find.
LOW_CARDINALITY_MAX = 20        # bar / pie only useful at this size or smaller
TOP_N_DEFAULT = 15              # for top-N bars on high-card categoricals
MAX_CAT_NUM_PAIRS = 8           # cap on suggested category×numeric aggregated bars
MAX_NUM_NUM_PAIRS = 6           # cap on suggested scatters
MAX_TIMESERIES_PAIRS = 6        # cap on datetime×numeric line charts
KPI_LIMIT = 6                   # number of KPI cards


# =============================================================================
# Helpers
# =============================================================================

def _is_useful_numeric(col: dict[str, Any]) -> bool:
    if col["semantic_type"] != "numeric":
        return False
    stats = col.get("numeric_stats") or {}
    # Skip constants (std == 0) so we don't waste a slot.
    if stats.get("std") is not None and stats["std"] == 0:
        return False
    return True


def _is_useful_categorical(col: dict[str, Any]) -> bool:
    if col["semantic_type"] not in ("categorical", "boolean"):
        return False
    # Skip single-value (constant) cols.
    if col["unique_count"] <= 1:
        return False
    return True


def _is_useful_datetime(col: dict[str, Any]) -> bool:
    return col["semantic_type"] == "datetime" and col["unique_count"] > 1


def _suggestion(
    *,
    chart_type: str,
    title: str,
    encoding: dict[str, Any],
    rationale: str,
    score: float,
    bins: int | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    s: dict[str, Any] = {
        "chart_type": chart_type,
        "engine": engine_for(chart_type),
        "title": title,
        "encoding": encoding,
        "rationale": rationale,
        "score": round(float(score), 3),
    }
    if bins is not None:
        s["bins"] = bins
    if top_n is not None:
        s["top_n"] = top_n
    return s


# =============================================================================
# Recommendation builders
# =============================================================================

def _suggest_distributions(numerics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for col in numerics:
        stats = col.get("numeric_stats") or {}
        skew = abs(stats.get("skewness") or 0)
        # Skewed distributions are more interesting → higher score.
        base = 0.55 + min(skew * 0.05, 0.25)
        out.append(_suggestion(
            chart_type="histogram",
            title=f"Distribution of {col['name']}",
            encoding={"x": col["name"]},
            rationale=f"Histogram of `{col['name']}` reveals shape, skew, and gaps.",
            score=base,
            bins=30,
        ))
        out.append(_suggestion(
            chart_type="box",
            title=f"Spread of {col['name']}",
            encoding={"y": col["name"]},
            rationale=f"Box plot of `{col['name']}` summarises median, IQR, and outliers.",
            score=base - 0.05,
        ))
    return out


def _suggest_categorical_frequency(categoricals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for col in categoricals:
        card = col["unique_count"]
        if card <= LOW_CARDINALITY_MAX:
            score = 0.7 - 0.01 * card  # fewer categories → cleaner chart
            out.append(_suggestion(
                chart_type="bar",
                title=f"{col['name']} by count",
                encoding={"x": col["name"], "agg": "count"},
                rationale=f"Frequency of each `{col['name']}` value ({card} categories).",
                score=score,
            ))
            if card <= 8:
                out.append(_suggestion(
                    chart_type="pie",
                    title=f"{col['name']} share",
                    encoding={"x": col["name"], "agg": "count"},
                    rationale=f"Share of total for each `{col['name']}` value.",
                    score=score - 0.1,
                ))
        else:
            out.append(_suggestion(
                chart_type="bar",
                title=f"Top {TOP_N_DEFAULT} {col['name']} values",
                encoding={"x": col["name"], "agg": "count"},
                rationale=(
                    f"`{col['name']}` has {card} unique values — showing the most "
                    f"common {TOP_N_DEFAULT}."
                ),
                score=0.55,
                top_n=TOP_N_DEFAULT,
            ))
    return out


def _suggest_cat_x_num(
    categoricals: list[dict[str, Any]], numerics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Aggregated bar: mean numeric grouped by low-card categorical."""
    out: list[dict[str, Any]] = []
    low_card_cats = [c for c in categoricals if c["unique_count"] <= LOW_CARDINALITY_MAX]
    for cat in low_card_cats:
        for num in numerics:
            score = 0.72 - 0.005 * cat["unique_count"]
            out.append(_suggestion(
                chart_type="bar",
                title=f"Mean of {num['name']} by {cat['name']}",
                encoding={"x": cat["name"], "y": num["name"], "agg": "mean"},
                rationale=(
                    f"Comparing the mean of `{num['name']}` across "
                    f"`{cat['name']}` highlights group differences."
                ),
                score=score,
            ))
    out.sort(key=lambda s: -s["score"])
    return out[:MAX_CAT_NUM_PAIRS]


def _suggest_num_x_num(numerics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, a in enumerate(numerics):
        for b in numerics[i + 1 :]:
            out.append(_suggestion(
                chart_type="scatter",
                title=f"{a['name']} vs {b['name']}",
                encoding={"x": a["name"], "y": b["name"]},
                rationale=f"Relationship between `{a['name']}` and `{b['name']}`.",
                score=0.5,
            ))
    return out[:MAX_NUM_NUM_PAIRS]


def _suggest_timeseries(
    datetimes: list[dict[str, Any]], numerics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in datetimes:
        for n in numerics:
            out.append(_suggestion(
                chart_type="line",
                title=f"{n['name']} over time ({d['name']})",
                encoding={"x": d["name"], "y": n["name"], "agg": "mean"},
                rationale=(
                    f"`{n['name']}` over `{d['name']}` shows trend and seasonality."
                ),
                score=0.85,  # time series are usually the most useful
            ))
    out.sort(key=lambda s: -s["score"])
    return out[:MAX_TIMESERIES_PAIRS]


def _suggest_heatmap(numerics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(numerics) < 2:
        return []
    return [_suggestion(
        chart_type="heatmap",
        title="Correlation between numeric columns",
        encoding={"columns": [c["name"] for c in numerics], "method": "pearson"},
        rationale=(
            f"Correlation matrix across {len(numerics)} numeric columns — "
            "a fast overview of which pairs move together."
        ),
        score=0.9,
    )]


def _suggest_kpis(numerics: list[dict[str, Any]], n_rows: int) -> list[dict[str, Any]]:
    """KPI cards. Always include a row count; pick a handful of useful numerics."""
    kpis: list[dict[str, Any]] = []
    kpis.append({
        "chart_type": "kpi",
        "engine": KPI_ENGINE,
        "title": "Total rows",
        "encoding": {"agg": "count_rows"},
        "rationale": "Total record count in this version.",
        "score": 1.0,
    })
    # Sort numerics by name to keep selections stable run-to-run.
    sorted_nums = sorted(numerics, key=lambda c: c["name"])[: KPI_LIMIT - 1]
    for col in sorted_nums:
        # Pick `sum` for integer-ish columns, `mean` otherwise.
        agg = "sum" if (col.get("numeric_stats") or {}).get("skewness") is not None and \
            col["dtype"].startswith("int") else "mean"
        kpis.append({
            "chart_type": "kpi",
            "engine": KPI_ENGINE,
            "title": f"{agg.capitalize()} of {col['name']}",
            "encoding": {"y": col["name"], "agg": agg},
            "rationale": f"{agg.capitalize()} of `{col['name']}`.",
            "score": 0.8,
        })
    _ = n_rows  # reserved for future heuristics
    return kpis


# =============================================================================
# Entry point
# =============================================================================

def recommend(profile: dict[str, Any]) -> dict[str, Any]:
    """Return {kpis, suggestions} given a profile JSON."""
    cols = profile.get("columns") or []
    n_rows = (profile.get("summary") or {}).get("row_count", 0)

    # Filter out columns we never want to chart.
    usable = [c for c in cols if c["semantic_type"] != "id_like"]
    numerics = [c for c in usable if _is_useful_numeric(c)]
    categoricals = [c for c in usable if _is_useful_categorical(c)]
    datetimes = [c for c in usable if _is_useful_datetime(c)]

    suggestions: list[dict[str, Any]] = []
    suggestions += _suggest_heatmap(numerics)
    suggestions += _suggest_timeseries(datetimes, numerics)
    suggestions += _suggest_cat_x_num(categoricals, numerics)
    suggestions += _suggest_categorical_frequency(categoricals)
    suggestions += _suggest_distributions(numerics)
    suggestions += _suggest_num_x_num(numerics)

    suggestions.sort(key=lambda s: -s["score"])
    kpis = _suggest_kpis(numerics, n_rows)
    return {"kpis": kpis, "suggestions": suggestions}


__all__ = ["recommend"]
