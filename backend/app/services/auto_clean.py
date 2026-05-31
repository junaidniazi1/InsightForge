"""Auto-clean agent.

Given a Phase-2 data profile, propose a complete ordered cleaning pipeline
with a one-line rationale per step. The user reviews and applies via the
existing Phase-3 `/clean` endpoint — we never auto-apply.

Hard rules:
  - Deterministic from the profile. No LLM dependency for the plan itself.
  - Never propose row removal for outliers (cap only).
  - Never drop id-like columns automatically (they may be the join key).
  - For >60% null columns: drop and don't bother imputing.
  - Ordering matters: convert types → trim text → drop bad columns →
    drop duplicates → impute remaining nulls → cap outliers.
"""

from __future__ import annotations

from typing import Any

# Severity thresholds
HIGH_NULL_PCT = 60.0       # >60% null → drop the column outright
OUTLIER_PCT_FLOOR = 1.0    # only cap when at least this % of rows are IQR outliers


def _step(op: str, columns: list[str], rationale: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "op": op,
        "columns": columns,
        "params": params or {},
        "rationale": rationale,
    }


def build_auto_plan(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return an ordered list of {op, columns, params, rationale} dicts."""
    cols = profile.get("columns") or []
    issues = profile.get("issues") or []
    outliers = profile.get("outliers") or {}

    # Index issues by column for O(1) lookup.
    issues_by_col: dict[str | None, list[dict[str, Any]]] = {}
    for issue in issues:
        issues_by_col.setdefault(issue.get("column"), []).append(issue)

    type_steps: list[dict[str, Any]] = []
    text_steps: list[dict[str, Any]] = []
    drop_steps: list[dict[str, Any]] = []
    impute_steps: list[dict[str, Any]] = []
    cap_steps: list[dict[str, Any]] = []
    dataset_steps: list[dict[str, Any]] = []

    dropped: set[str] = set()

    # -- per-column decisions ------------------------------------------------
    for col in cols:
        name = col["name"]
        sem = col["semantic_type"]
        null_pct = col.get("null_pct", 0.0) or 0.0
        col_issue_types = {i["issue_type"] for i in issues_by_col.get(name, [])}

        # id_like columns: never drop, never impute — they may be join keys.
        if sem == "id_like":
            continue

        # >60% null → drop and move on. No type convert / impute / cap.
        if null_pct >= HIGH_NULL_PCT:
            drop_steps.append(_step(
                "drop_column",
                [name],
                f"Column has {null_pct:g}% nulls — too sparse to keep.",
            ))
            dropped.add(name)
            continue

        # Constant / near-constant: drop. No further work needed.
        if "constant_column" in col_issue_types:
            drop_steps.append(_step(
                "drop_column",
                [name],
                f"Column '{name}' is constant — no analytic signal.",
            ))
            dropped.add(name)
            continue
        if "near_constant_column" in col_issue_types:
            drop_steps.append(_step(
                "drop_column",
                [name],
                f"Column '{name}' is dominated by one value — drops noise.",
            ))
            dropped.add(name)
            continue

        # Type conversions (do these first so subsequent imputation sees real types).
        if "numeric_as_text" in col_issue_types:
            type_steps.append(_step(
                "convert_to_numeric",
                [name],
                f"Column '{name}' looks numeric but is stored as text — coercing.",
            ))
        if "date_as_text" in col_issue_types:
            type_steps.append(_step(
                "convert_to_datetime",
                [name],
                f"Column '{name}' looks like dates but is stored as text — parsing.",
            ))
        if "boolean_as_string" in col_issue_types:
            type_steps.append(_step(
                "convert_to_boolean",
                [name],
                f"Column '{name}' is yes/no-style text — converting to boolean.",
            ))
        # mixed_types: don't auto-fix. Force to text would be lossy.

        # Trim whitespace on text-ish columns (after converts).
        if sem in ("text", "categorical"):
            text_steps.append(_step(
                "trim_whitespace",
                [name],
                f"Strip stray whitespace in '{name}'.",
            ))

        # Imputation for remaining nulls (not dropped, not too sparse).
        if null_pct > 0:
            null_count = col.get("null_count", 0)
            if sem == "numeric" or "numeric_as_text" in col_issue_types:
                impute_steps.append(_step(
                    "impute_median",
                    [name],
                    f"Replace {null_count} null(s) in '{name}' with column median.",
                ))
            elif sem in ("categorical", "boolean"):
                impute_steps.append(_step(
                    "impute_mode",
                    [name],
                    f"Replace {null_count} null(s) in '{name}' with the most common value.",
                ))
            # text / datetime: skip — no clearly-safe automatic imputation.

    # -- dataset-level: duplicates ------------------------------------------
    dup_issues = [i for i in issues if i["issue_type"] == "duplicate_rows"]
    if dup_issues:
        dataset_steps.append(_step(
            "drop_duplicates",
            [],
            dup_issues[0]["description"],
        ))

    # -- outliers: cap only, never remove rows ------------------------------
    iqr = outliers.get("iqr") or {}
    for o in iqr.get("columns") or []:
        col_name = o.get("column")
        if not col_name or col_name in dropped:
            continue
        if (o.get("outlier_pct") or 0) < OUTLIER_PCT_FLOOR:
            continue
        cap_steps.append(_step(
            "cap",
            [col_name],
            f"Cap {o.get('outlier_count', 0)} IQR outlier(s) in '{col_name}' "
            "(never auto-removes rows).",
        ))

    # Final order:
    #  1. type conversions
    #  2. text trim
    #  3. drop columns (rules out further work on them)
    #  4. drop duplicate rows
    #  5. impute nulls in kept columns
    #  6. cap outliers
    plan: list[dict[str, Any]] = (
        type_steps + text_steps + drop_steps + dataset_steps + impute_steps + cap_steps
    )
    return plan


def plan_summary(plan: list[dict[str, Any]]) -> str:
    """A short human-readable digest of the plan, used for the friendly Gemini hand-off."""
    if not plan:
        return "No issues detected — your data already looks clean."
    ops: dict[str, int] = {}
    for s in plan:
        ops[s["op"]] = ops.get(s["op"], 0) + 1
    parts = [f"{count} × {op}" for op, count in ops.items()]
    return f"{len(plan)} step(s): " + ", ".join(parts)


__all__ = ["build_auto_plan", "plan_summary", "HIGH_NULL_PCT", "OUTLIER_PCT_FLOOR"]
