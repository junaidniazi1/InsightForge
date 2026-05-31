"""Build the AI prompt context.

The single privacy rule for this module: we only emit *schema, types, profile
statistics, top categories (counts), top correlations, KPI list, and
cleaning-step summaries.* We never include `sample_values`, the raw DataFrame,
or anything that identifies individual rows. The unit test for this module
asserts row data does not leak through.
"""

from __future__ import annotations

from typing import Any

# Caps so the prompt stays small enough for the free tier.
MAX_COLUMNS = 40
MAX_TOP_VALUES_PER_COL = 5
MAX_CORRELATIONS = 8
MAX_CLEANING_STEPS = 20
MAX_CONTEXT_CHARS = 14_000  # well under most free-tier limits


def _per_column_summary(col: dict[str, Any]) -> dict[str, Any]:
    """Reduce a per-column profile to only the parts Gemini needs.

    Deliberately drops `sample_values`, `dtype` (Gemini doesn't need pandas
    dtypes), and `memory_bytes`.
    """
    out: dict[str, Any] = {
        "name": col["name"],
        "semantic_type": col["semantic_type"],
        "null_pct": col["null_pct"],
        "unique_count": col["unique_count"],
        "unique_pct": col["unique_pct"],
    }
    stats = col.get("numeric_stats")
    if stats:
        # Send only the moments and quartiles — small and high-information.
        out["numeric_stats"] = {
            "min": stats.get("min"),
            "max": stats.get("max"),
            "mean": stats.get("mean"),
            "median": stats.get("median"),
            "std": stats.get("std"),
            "q1": stats.get("q1"),
            "q3": stats.get("q3"),
            "skewness": stats.get("skewness"),
            "kurtosis": stats.get("kurtosis"),
        }
    tops = col.get("top_values")
    if tops:
        # Top-value counts describe the *distribution*. Keep only buckets that
        # appear more than once — a value that only shows up once is not
        # distribution info, it's a per-row identifier. This matters when the
        # profiler emits top_values for high-uniqueness categorical columns
        # (e.g. names): without this filter, individual names would leak into
        # the prompt.
        filtered = [t for t in tops if int(t.get("count") or 0) > 1]
        if filtered:
            out["top_values"] = [
                {"value": str(t["value"]), "count": t["count"], "pct": t["pct"]}
                for t in filtered[:MAX_TOP_VALUES_PER_COL]
            ]
        else:
            # Surface the cardinality but not the values themselves.
            out["top_values_omitted"] = "all unique — no repeated values"
    return out


def _top_correlations(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """If a Phase-4 heatmap is in the profile, surface the strongest pairs.

    The profiler doesn't compute correlations directly — they live in the
    outliers / heatmap layer. If absent, return [].
    """
    outliers = profile.get("outliers") or {}
    pairs: list[dict[str, Any]] = []
    # Pearson correlations live in the heatmap response (Phase 4), not the
    # profile. Best-effort: compute from numeric_stats overlap. Phase 5 stays
    # within the profile data we already have.
    _ = outliers
    _ = pairs
    return []  # Phase 5 keeps the context tight; Phase 6 toolkit owns full corr.


def _kpi_summaries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """The recommender's KPI suggestions, distilled."""
    # We could call the chart recommender here, but we'd duplicate work. Phase
    # 4 already calls it server-side. Here we extract obvious KPIs straight
    # from the profile so the AI services don't depend on the chart layer.
    rows = profile.get("summary", {}).get("row_count")
    kpis: list[dict[str, Any]] = []
    if isinstance(rows, int):
        kpis.append({"label": "Total rows", "value": rows})
    return kpis


def _summarize_cleaning_steps(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Reduce cleaning_steps log to {op, summary} entries.

    We deliberately drop params (which might contain user-typed constants from
    fill_constant or regex_replace — text the user might consider sensitive
    even though it's not raw row data).
    """
    if not steps:
        return []
    return [
        {"op": s.get("op"), "summary": s.get("summary")}
        for s in steps[:MAX_CLEANING_STEPS]
    ]


def build_ai_context(
    *,
    dataset_name: str,
    version_label: str,
    profile: dict[str, Any],
    cleaning_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the compact, row-free AI context payload.

    Caller is the AI router; it already has the version + profile loaded.
    """
    cols = profile.get("columns") or []
    summary = profile.get("summary") or {}

    ctx: dict[str, Any] = {
        "dataset_name": dataset_name,
        "version_label": version_label,
        "row_count": summary.get("row_count"),
        "column_count": summary.get("column_count"),
        "overall_missing_pct": summary.get("overall_missing_pct"),
        "duplicate_row_count": summary.get("duplicate_row_count"),
        "quality_score": summary.get("quality_score"),
        "columns": [_per_column_summary(c) for c in cols[:MAX_COLUMNS]],
        "columns_truncated": len(cols) > MAX_COLUMNS,
        "kpis": _kpi_summaries(profile),
        "top_correlations": _top_correlations(profile)[:MAX_CORRELATIONS],
        "cleaning_steps": _summarize_cleaning_steps(cleaning_steps),
    }

    # Hard cap on serialized length so we never blow the prompt budget.
    import json
    raw = json.dumps(ctx, default=str)
    if len(raw) > MAX_CONTEXT_CHARS:
        # Truncate the per-column list — it's the heaviest field.
        keep = ctx["columns"][: max(5, MAX_COLUMNS // 2)]
        ctx["columns"] = keep
        ctx["columns_truncated"] = True
    return ctx


def column_index_for_validation(profile: dict[str, Any]) -> dict[str, str]:
    """Return {column_name: semantic_type} for validating Ask-Your-Data specs."""
    return {c["name"]: c["semantic_type"] for c in (profile.get("columns") or [])}


__all__ = ["build_ai_context", "column_index_for_validation"]
