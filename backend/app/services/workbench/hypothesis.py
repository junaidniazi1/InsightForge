"""Hypothesis tests (Phase 7A, tool 3).

One-sample / two-sample t-test, one-way ANOVA, chi-square independence,
Mann-Whitney U. Each returns the statistic, p-value, an effect-size measure
where applicable, the relevant assumption checks (Shapiro / Levene), and a
plain-language verdict. Plus a small "which test should I use?" helper.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats as sci_stats

from ._common import WorkbenchError, chart, envelope, require_columns, require_min_rows


TestKind = Literal["ttest_one", "ttest_two", "anova", "chi_square", "mann_whitney"]

ALPHA = 0.05
SHAPIRO_MAX_N = 5000   # Shapiro-Wilk dislikes huge samples; sample down.


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------

def _verdict(p: float, *, what: str) -> str:
    if p < ALPHA:
        return f"At α = {ALPHA}, we reject the null hypothesis (p = {p:.4g}). {what}"
    return f"At α = {ALPHA}, we fail to reject the null hypothesis (p = {p:.4g}). {what}"


def _shapiro(name: str, arr: np.ndarray) -> dict[str, Any]:
    if len(arr) < 3:
        return {"column": name, "applicable": False, "reason": "fewer than 3 values"}
    sample = arr if len(arr) <= SHAPIRO_MAX_N else np.random.default_rng(0).choice(arr, SHAPIRO_MAX_N, replace=False)
    stat, p = sci_stats.shapiro(sample)
    return {
        "column": name,
        "applicable": True,
        "statistic": float(stat),
        "p_value": float(p),
        "normal_like": bool(p > ALPHA),
        "sampled": bool(len(arr) > SHAPIRO_MAX_N),
    }


def _levene(samples: list[np.ndarray]) -> dict[str, Any]:
    if len(samples) < 2 or any(len(s) < 2 for s in samples):
        return {"applicable": False}
    stat, p = sci_stats.levene(*samples, center="median")
    return {
        "applicable": True,
        "statistic": float(stat),
        "p_value": float(p),
        "equal_variance": bool(p > ALPHA),
    }


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    pooled = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    if pooled == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


# ---------------------------------------------------------------------------
# Test runners
# ---------------------------------------------------------------------------

def _ttest_one_sample(df: pd.DataFrame, value_col: str, popmean: float) -> dict[str, Any]:
    arr = pd.to_numeric(df[value_col], errors="coerce").dropna().to_numpy()
    require_min_rows(len(arr), minimum=3, what=f"one-sample t-test on `{value_col}`")
    stat, p = sci_stats.ttest_1samp(arr, popmean)
    assumptions = {"shapiro": _shapiro(value_col, arr)}
    mean = float(arr.mean())
    direction = "greater than" if mean > popmean else "less than" if mean < popmean else "equal to"
    summary = (
        f"`{value_col}` mean is {mean:.3g} (target {popmean:.3g})."
        if p < ALPHA else
        f"`{value_col}` mean is {mean:.3g}; not significantly different from {popmean:.3g}."
    )
    return {
        "test": "ttest_one",
        "statistic": float(stat),
        "p_value": float(p),
        "n": int(len(arr)),
        "popmean": float(popmean),
        "sample_mean": mean,
        "assumptions": assumptions,
        "interpretation": _verdict(
            float(p),
            what=f"The mean of `{value_col}` ({mean:.3g}) is {direction} {popmean:.3g}.",
        ),
        "result_summary": summary,
    }


def _ttest_two_sample(df: pd.DataFrame, value_col: str, group_col: str) -> dict[str, Any]:
    sub = df[[value_col, group_col]].copy()
    sub[value_col] = pd.to_numeric(sub[value_col], errors="coerce")
    sub = sub.dropna()
    groups = list(sub[group_col].unique())
    if len(groups) != 2:
        raise WorkbenchError(
            f"`{group_col}` has {len(groups)} groups; two-sample t-test needs exactly 2.",
            reason="bad_group_count",
        )
    a = sub.loc[sub[group_col] == groups[0], value_col].to_numpy()
    b = sub.loc[sub[group_col] == groups[1], value_col].to_numpy()
    require_min_rows(min(len(a), len(b)), minimum=3, what=f"two-sample t-test on `{value_col}` by `{group_col}`")

    levene = _levene([a, b])
    equal_var = levene.get("equal_variance", True) if levene["applicable"] else True
    stat, p = sci_stats.ttest_ind(a, b, equal_var=equal_var)
    d = _cohens_d(a, b)
    assumptions = {
        "shapiro": [_shapiro(str(groups[0]), a), _shapiro(str(groups[1]), b)],
        "levene": levene,
        "used_welch": bool(not equal_var),
    }
    return {
        "test": "ttest_two",
        "groups": [str(g) for g in groups],
        "statistic": float(stat),
        "p_value": float(p),
        "cohens_d": d,
        "n_per_group": [int(len(a)), int(len(b))],
        "means": [float(a.mean()), float(b.mean())],
        "assumptions": assumptions,
        "interpretation": _verdict(
            float(p),
            what=(
                f"Group means differ: {groups[0]} = {a.mean():.3g}, {groups[1]} = {b.mean():.3g} "
                f"(Cohen's d = {d:.2f})."
            ),
        ),
    }


def _anova(df: pd.DataFrame, value_col: str, group_col: str) -> dict[str, Any]:
    sub = df[[value_col, group_col]].copy()
    sub[value_col] = pd.to_numeric(sub[value_col], errors="coerce")
    sub = sub.dropna()
    groups: dict[str, np.ndarray] = {
        str(k): v[value_col].to_numpy() for k, v in sub.groupby(group_col)
    }
    if len(groups) < 2:
        raise WorkbenchError(
            "ANOVA needs at least 2 groups.", reason="too_few_groups",
        )
    arrays = list(groups.values())
    if any(len(a) < 2 for a in arrays):
        raise WorkbenchError(
            "Each group needs at least 2 observations.", reason="too_few_rows",
        )
    stat, p = sci_stats.f_oneway(*arrays)
    means = {g: float(a.mean()) for g, a in groups.items()}
    largest = max(means.items(), key=lambda kv: kv[1])
    smallest = min(means.items(), key=lambda kv: kv[1])
    return {
        "test": "anova",
        "statistic": float(stat),
        "p_value": float(p),
        "groups": list(groups.keys()),
        "group_means": means,
        "group_sizes": {g: int(len(a)) for g, a in groups.items()},
        "assumptions": {"levene": _levene(arrays)},
        "interpretation": _verdict(
            float(p),
            what=(
                f"Largest mean: `{largest[0]}` ({largest[1]:.3g}); "
                f"smallest mean: `{smallest[0]}` ({smallest[1]:.3g})."
            ),
        ),
    }


def _chi_square(df: pd.DataFrame, a_col: str, b_col: str) -> dict[str, Any]:
    table = pd.crosstab(df[a_col], df[b_col])
    if table.size == 0 or min(table.shape) < 2:
        raise WorkbenchError(
            "Chi-square needs at least 2 categories in each column.",
            reason="too_few_categories",
        )
    chi2, p, dof, expected = sci_stats.chi2_contingency(table.values)
    n = int(table.values.sum())
    # Cramér's V — effect size for chi-square.
    k = min(table.shape) - 1
    v = float(np.sqrt(chi2 / (n * max(k, 1))))
    return {
        "test": "chi_square",
        "statistic": float(chi2),
        "p_value": float(p),
        "dof": int(dof),
        "cramers_v": v,
        "n": n,
        "table": table.to_dict(),
        "row_categories": [str(x) for x in table.index],
        "col_categories": [str(x) for x in table.columns],
        "assumptions": {
            "min_expected_freq": float(expected.min()),
            "low_expected_warning": bool(expected.min() < 5),
        },
        "interpretation": _verdict(
            float(p),
            what=(
                f"`{a_col}` and `{b_col}` are "
                + ("associated" if p < ALPHA else "independent")
                + f" (Cramér's V = {v:.2f})."
            ),
        ),
    }


def _mann_whitney(df: pd.DataFrame, value_col: str, group_col: str) -> dict[str, Any]:
    sub = df[[value_col, group_col]].copy()
    sub[value_col] = pd.to_numeric(sub[value_col], errors="coerce")
    sub = sub.dropna()
    groups = list(sub[group_col].unique())
    if len(groups) != 2:
        raise WorkbenchError(
            f"`{group_col}` has {len(groups)} groups; Mann-Whitney needs exactly 2.",
            reason="bad_group_count",
        )
    a = sub.loc[sub[group_col] == groups[0], value_col].to_numpy()
    b = sub.loc[sub[group_col] == groups[1], value_col].to_numpy()
    require_min_rows(min(len(a), len(b)), minimum=3, what="Mann-Whitney U")
    stat, p = sci_stats.mannwhitneyu(a, b, alternative="two-sided")
    # Rank-biserial effect size.
    u_max = float(len(a) * len(b))
    rbc = 1.0 - (2.0 * float(stat) / u_max) if u_max else 0.0
    return {
        "test": "mann_whitney",
        "groups": [str(g) for g in groups],
        "statistic": float(stat),
        "p_value": float(p),
        "rank_biserial": float(rbc),
        "medians": [float(np.median(a)), float(np.median(b))],
        "n_per_group": [int(len(a)), int(len(b))],
        "interpretation": _verdict(
            float(p),
            what=(
                f"Group medians differ: {groups[0]} = {np.median(a):.3g}, "
                f"{groups[1]} = {np.median(b):.3g}."
            ),
        ),
    }


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def run_hypothesis_test(
    df: pd.DataFrame,
    test: TestKind,
    *,
    value_col: str | None = None,
    group_col: str | None = None,
    second_col: str | None = None,
    popmean: float | None = None,
) -> dict[str, Any]:
    if test == "ttest_one":
        if not value_col or popmean is None:
            raise WorkbenchError("One-sample t-test needs value_col and popmean.", reason="missing_param")
        require_columns(df, [value_col])
        res = _ttest_one_sample(df, value_col, float(popmean))
    elif test == "ttest_two":
        if not value_col or not group_col:
            raise WorkbenchError("Two-sample t-test needs value_col and group_col.", reason="missing_param")
        require_columns(df, [value_col, group_col])
        res = _ttest_two_sample(df, value_col, group_col)
    elif test == "anova":
        if not value_col or not group_col:
            raise WorkbenchError("ANOVA needs value_col and group_col.", reason="missing_param")
        require_columns(df, [value_col, group_col])
        res = _anova(df, value_col, group_col)
    elif test == "chi_square":
        if not value_col or not second_col:
            raise WorkbenchError("Chi-square needs two categorical columns.", reason="missing_param")
        require_columns(df, [value_col, second_col])
        res = _chi_square(df, value_col, second_col)
    elif test == "mann_whitney":
        if not value_col or not group_col:
            raise WorkbenchError("Mann-Whitney needs value_col and group_col.", reason="missing_param")
        require_columns(df, [value_col, group_col])
        res = _mann_whitney(df, value_col, group_col)
    else:
        raise WorkbenchError(f"unknown test: {test}", reason="bad_test")

    charts_out = _charts_for(test, df, res, value_col=value_col, group_col=group_col, second_col=second_col)
    return envelope(result=res, charts=charts_out, interpretation=res["interpretation"])


def _charts_for(
    test: TestKind,
    df: pd.DataFrame,
    res: dict[str, Any],
    *,
    value_col: str | None,
    group_col: str | None,
    second_col: str | None,
) -> list[dict[str, Any]]:
    charts_out: list[dict[str, Any]] = []
    if test in ("ttest_two", "anova", "mann_whitney") and value_col and group_col:
        sub = df[[value_col, group_col]].copy()
        sub[value_col] = pd.to_numeric(sub[value_col], errors="coerce")
        sub = sub.dropna()
        grouped = sub.groupby(group_col)[value_col].mean()
        charts_out.append(chart(
            title=f"Mean of {value_col} by {group_col}",
            chart_type="bar",
            encoding={"x": group_col, "y": value_col, "agg": "mean"},
            data={
                "categories": [str(k) for k in grouped.index],
                "series": [{"name": f"mean({value_col})", "values": [float(v) for v in grouped.values]}],
            },
        ))
    elif test == "chi_square" and value_col and second_col:
        charts_out.append(chart(
            title=f"{value_col} × {second_col} (counts)",
            chart_type="heatmap",
            encoding={"columns": res["col_categories"], "method": "counts"},
            data={
                "columns": [str(c) for c in res["col_categories"]],
                "values": [
                    [float(res["table"][col][row]) for col in res["col_categories"]]
                    for row in res["row_categories"]
                ],
                "rows": [str(r) for r in res["row_categories"]],
            },
        ))
    elif test == "ttest_one" and value_col:
        charts_out.append(chart(
            title=f"Distribution of {value_col}",
            chart_type="histogram",
            encoding={"x": value_col},
            data=_quick_histogram(df[value_col]),
        ))
    return charts_out


def _quick_histogram(s: pd.Series, bins: int = 30) -> dict[str, Any]:
    arr = pd.to_numeric(s, errors="coerce").dropna().to_numpy()
    counts, edges = np.histogram(arr, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return {
        "x": [float(v) for v in centers],
        "y": [int(v) for v in counts],
        "edges": [float(v) for v in edges],
    }


# ---------------------------------------------------------------------------
# "Which test should I use?" recommender
# ---------------------------------------------------------------------------

def recommend_test(profile_columns: list[dict[str, Any]], picks: list[str]) -> dict[str, Any]:
    """Suggest a test from the chosen columns' semantic types.

    Doesn't run anything — just helps the user pick.
    """
    by_name = {c["name"]: c for c in profile_columns}
    chosen = [by_name[p] for p in picks if p in by_name]
    types = [c["semantic_type"] for c in chosen]

    if len(types) == 1 and types[0] == "numeric":
        return {
            "recommendation": "ttest_one",
            "reason": "Single numeric column — one-sample t-test (against a target mean).",
        }
    if len(types) == 2:
        if "numeric" in types and ("categorical" in types or "boolean" in types):
            cat_idx = next(i for i, t in enumerate(types) if t in ("categorical", "boolean"))
            cat = chosen[cat_idx]
            n_groups = cat.get("unique_count", 0)
            if n_groups == 2:
                return {
                    "recommendation": "ttest_two",
                    "reason": "Numeric + 2-level categorical → two-sample t-test (Mann-Whitney if non-normal).",
                }
            if n_groups >= 3:
                return {
                    "recommendation": "anova",
                    "reason": "Numeric + 3+-level categorical → one-way ANOVA.",
                }
        if all(t in ("categorical", "boolean") for t in types):
            return {
                "recommendation": "chi_square",
                "reason": "Two categorical columns → chi-square test of independence.",
            }
    return {
        "recommendation": None,
        "reason": "Pick a numeric column for a mean test, or two categoricals for chi-square.",
    }


__all__ = ["run_hypothesis_test", "recommend_test"]
