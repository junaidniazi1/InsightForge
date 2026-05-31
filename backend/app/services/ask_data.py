"""Ask-Your-Data engine.

Three strict steps:
  1. **Plan.** Send the user's question + the column list (no rows) to Gemini in
     JSON mode. Gemini returns an *analysis spec* — a structured object
     describing what computation it wants. The schema only allows a small
     allowlist of operations.
  2. **Validate + execute.** The backend validates the spec against the
     allowlist and the dataset's known columns / types. **Anything outside the
     allowlist, or referencing unknown columns, is rejected.** Execution uses
     pandas (and reuses Phase-4 helpers), never anything the model writes.
  3. **Explain.** Send only the small aggregated *result* back to Gemini, which
     produces a natural-language answer.

Throughout we treat the model output as untrusted input.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

import pandas as pd

from .ai_context import column_index_for_validation
from .ai_prompts import (
    EXPLAINER_SYSTEM,
    PLANNER_SYSTEM,
    TEMPERATURE_EXPLAINER,
    TEMPERATURE_PLANNER,
)
from .chart_data import apply_filters
from .data_loader import to_json_safe
from .gemini_client import GeminiClient


# =============================================================================
# Allowlist
# =============================================================================

Operation = Literal[
    "describe",
    "value_counts",
    "groupby_aggregate",
    "correlation",
    "filter_aggregate",
    "top_n",
    "time_series",
]

ALLOWED_OPERATIONS: set[str] = {
    "describe",
    "value_counts",
    "groupby_aggregate",
    "correlation",
    "filter_aggregate",
    "top_n",
    "time_series",
}

ALLOWED_AGGS: set[str] = {"mean", "sum", "count", "min", "max", "median"}

MAX_RESULT_ROWS = 100
MAX_QUESTION_CHARS = 500


# =============================================================================
# Errors
# =============================================================================

class AskRejected(ValueError):
    """Raised when the LLM-produced spec fails validation."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


# =============================================================================
# Structured-output schema sent to Gemini
# =============================================================================

PLAN_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "operation": {
            # "unsupported" lets the planner explicitly refuse instead of
            # contorting the question into a bad spec.
            "type": "STRING",
            "enum": sorted(ALLOWED_OPERATIONS | {"unsupported"}),
        },
        "columns": {"type": "ARRAY", "items": {"type": "STRING"}},
        "group_by": {"type": "STRING"},
        "agg_column": {"type": "STRING"},
        "agg": {"type": "STRING", "enum": sorted(ALLOWED_AGGS)},
        "filters": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "column": {"type": "STRING"},
                    "type": {"type": "STRING", "enum": ["in", "range"]},
                    "values": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "min": {"type": "STRING"},
                    "max": {"type": "STRING"},
                },
                "required": ["column", "type"],
            },
        },
        "top_n": {"type": "INTEGER"},
        "explanation": {"type": "STRING"},
        "reason": {"type": "STRING"},
    },
    "required": ["operation"],
}


def _plan_prompt(question: str, columns: list[dict[str, Any]]) -> str:
    return (
        "User question:\n"
        f"  {question}\n\n"
        "Dataset columns (name, semantic_type):\n"
        + "\n".join(f"  - {c['name']} ({c['semantic_type']})" for c in columns)
        + "\n\nReturn the analysis spec."
    )


def _explain_prompt(question: str, spec: dict[str, Any], result: dict[str, Any]) -> str:
    return (
        f"User question:\n  {question}\n\n"
        f"Analysis spec used:\n{json.dumps(spec, indent=2, default=str)}\n\n"
        f"Result table:\n{json.dumps(result, indent=2, default=str)}"
    )


# =============================================================================
# Validation
# =============================================================================

# Soft injection-style heuristic: reject obviously hostile prompts before we
# even pay for the LLM round-trip.
_INJECTION_PATTERNS = [
    re.compile(r"\bignore\s+(?:previous|prior|all)\s+instructions?\b", re.I),
    re.compile(r"\bdrop\s+table\b", re.I),
    re.compile(r"\bdelete\s+(?:from|all)\b", re.I),
    re.compile(r";\s*(?:--|/\*)", re.I),
    re.compile(r"\b(?:rm\s+-rf|os\.system|subprocess|eval\()", re.I),
    re.compile(r"```\s*(?:python|sql)\b", re.I),
]


def precheck_question(question: str) -> None:
    if not isinstance(question, str) or not question.strip():
        raise AskRejected("question must be a non-empty string", reason="empty_question")
    if len(question) > MAX_QUESTION_CHARS:
        raise AskRejected(
            f"question too long ({len(question)} chars; max {MAX_QUESTION_CHARS})",
            reason="too_long",
        )
    for pat in _INJECTION_PATTERNS:
        if pat.search(question):
            raise AskRejected(
                "Question looks like a prompt-injection or code-execution attempt.",
                reason="injection_pattern",
            )


# Compatibility map between op and the semantic types it accepts.
_COMPATIBLE_TYPES = {
    "describe": {"numeric"},
    "value_counts": {"categorical", "boolean", "text", "id_like"},
    "groupby_aggregate": {  # group_by side
        "categorical", "boolean", "datetime",
    },
    "correlation": {"numeric"},
    "filter_aggregate": None,    # any
    "top_n": {"categorical", "boolean", "text", "id_like"},
    "time_series": {"datetime"},  # x-axis side
}


def validate_spec(spec: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Validate the model-produced spec against the allowlist + known columns.

    Returns the validated spec (with unknown fields stripped) or raises
    AskRejected with a precise reason.
    """
    if not isinstance(spec, dict):
        raise AskRejected("spec is not an object", reason="bad_shape")

    op = spec.get("operation")
    if op == "unsupported":
        # The planner explicitly chose to refuse — pass the reason through
        # so the FE can show *why*. This is the polite path; we don't pretend
        # the question was answerable.
        why = str(spec.get("reason") or spec.get("explanation") or "").strip()
        raise AskRejected(
            (
                "I can't answer this from the available columns. "
                + (f"({why})" if why else "")
            ).strip(),
            reason="unsupported",
        )
    if op not in ALLOWED_OPERATIONS:
        raise AskRejected(f"operation '{op}' not in allowlist", reason="bad_operation")

    cols = column_index_for_validation(profile)

    def _must_exist(name: str, role: str) -> None:
        if not isinstance(name, str) or not name:
            raise AskRejected(f"missing {role}", reason="missing_column")
        if name not in cols:
            raise AskRejected(
                f"unknown column '{name}' referenced as {role}",
                reason="unknown_column",
            )

    def _type_ok(name: str, allowed: set[str] | None) -> None:
        if allowed is None:
            return
        if cols[name] not in allowed:
            raise AskRejected(
                f"column '{name}' has type '{cols[name]}', not in {sorted(allowed)}",
                reason="bad_type",
            )

    cleaned: dict[str, Any] = {"operation": op, "explanation": str(spec.get("explanation") or "")}

    # Operation-specific required fields.
    if op == "describe" or op == "correlation":
        listed = spec.get("columns") or []
        if not isinstance(listed, list) or not listed:
            raise AskRejected(f"{op} requires a non-empty columns list", reason="missing_columns")
        for c in listed:
            _must_exist(c, "column")
            _type_ok(c, _COMPATIBLE_TYPES[op])
        cleaned["columns"] = list(listed)

    elif op == "value_counts" or op == "top_n":
        target = spec.get("group_by") or spec.get("agg_column") or (spec.get("columns") or [None])[0]
        _must_exist(target, "value_counts column")
        _type_ok(target, _COMPATIBLE_TYPES[op])
        cleaned["column"] = target
        if op == "top_n":
            n = spec.get("top_n", 10)
            try:
                cleaned["top_n"] = max(1, min(int(n), 50))
            except (TypeError, ValueError):
                cleaned["top_n"] = 10

    elif op == "groupby_aggregate":
        gb = spec.get("group_by")
        ac = spec.get("agg_column")
        agg = spec.get("agg", "mean")
        _must_exist(gb, "group_by")
        _type_ok(gb, _COMPATIBLE_TYPES[op])
        _must_exist(ac, "agg_column")
        _type_ok(ac, {"numeric"})
        if agg not in ALLOWED_AGGS:
            raise AskRejected(f"agg '{agg}' not in allowlist", reason="bad_agg")
        cleaned.update(group_by=gb, agg_column=ac, agg=agg)

    elif op == "filter_aggregate":
        ac = spec.get("agg_column")
        agg = spec.get("agg", "count")
        if agg == "count":
            cleaned["agg"] = "count_rows"
        else:
            _must_exist(ac, "agg_column")
            _type_ok(ac, {"numeric"})
            if agg not in ALLOWED_AGGS:
                raise AskRejected(f"agg '{agg}' not in allowlist", reason="bad_agg")
            cleaned.update(agg_column=ac, agg=agg)

    elif op == "time_series":
        x = spec.get("group_by") or (spec.get("columns") or [None])[0]
        y = spec.get("agg_column")
        agg = spec.get("agg", "mean")
        _must_exist(x, "datetime column")
        _type_ok(x, _COMPATIBLE_TYPES[op])
        _must_exist(y, "agg_column")
        _type_ok(y, {"numeric"})
        if agg not in ALLOWED_AGGS:
            raise AskRejected(f"agg '{agg}' not in allowlist", reason="bad_agg")
        cleaned.update(x=x, y=y, agg=agg)

    # Filters: validate columns + type field.
    raw_filters = spec.get("filters") or []
    valid_filters: list[dict[str, Any]] = []
    for f in raw_filters:
        if not isinstance(f, dict):
            continue
        col = f.get("column")
        if not isinstance(col, str) or col not in cols:
            raise AskRejected(
                f"filter references unknown column '{col}'",
                reason="unknown_column",
            )
        ftype = f.get("type", "in")
        if ftype not in ("in", "range"):
            raise AskRejected(f"filter type '{ftype}' not allowed", reason="bad_filter")
        clean_f: dict[str, Any] = {"column": col, "type": ftype}
        if ftype == "in":
            vals = f.get("values") or []
            if isinstance(vals, list):
                clean_f["values"] = [str(v) for v in vals[:50]]
        else:
            clean_f["min"] = f.get("min")
            clean_f["max"] = f.get("max")
        valid_filters.append(clean_f)
    if valid_filters:
        cleaned["filters"] = valid_filters

    return cleaned


# =============================================================================
# Execution
# =============================================================================

def _result_envelope(
    df: pd.DataFrame, *, name: str | None = None
) -> dict[str, Any]:
    """Cap to MAX_RESULT_ROWS, JSON-safe."""
    truncated = False
    if len(df) > MAX_RESULT_ROWS:
        df = df.head(MAX_RESULT_ROWS)
        truncated = True
    return {
        "name": name,
        "columns": [str(c) for c in df.columns],
        "rows": to_json_safe(df.to_dict(orient="records")),
        "truncated": truncated,
        "row_count": int(len(df)),
    }


def execute_spec(df: pd.DataFrame, spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Execute a validated spec. Returns (result_envelope, suggested_chart_spec_or_None)."""
    filters = spec.get("filters") or []
    df = apply_filters(df, filters)

    op = spec["operation"]
    suggested_chart: dict[str, Any] | None = None

    if op == "describe":
        out = df[spec["columns"]].apply(pd.to_numeric, errors="coerce").describe().reset_index()
        out = out.rename(columns={"index": "statistic"})
        result = _result_envelope(out, name="describe")

    elif op == "correlation":
        corr = df[spec["columns"]].apply(pd.to_numeric, errors="coerce").corr()
        out = corr.reset_index().rename(columns={"index": "column"})
        result = _result_envelope(out, name="correlation")
        suggested_chart = {
            "chart_type": "heatmap",
            "encoding": {"columns": spec["columns"], "method": "pearson"},
            "title": "Correlation",
        }

    elif op == "value_counts":
        col = spec["column"]
        vc = df[col].value_counts(dropna=False).reset_index()
        vc.columns = [col, "count"]
        result = _result_envelope(vc, name=f"value_counts({col})")
        suggested_chart = {
            "chart_type": "bar",
            "encoding": {"x": col, "agg": "count"},
            "title": f"Counts of {col}",
        }

    elif op == "top_n":
        col = spec["column"]
        n = spec.get("top_n", 10)
        vc = df[col].value_counts(dropna=False).head(n).reset_index()
        vc.columns = [col, "count"]
        result = _result_envelope(vc, name=f"top_{n}({col})")
        suggested_chart = {
            "chart_type": "bar",
            "encoding": {"x": col, "agg": "count"},
            "title": f"Top {n} {col}",
            "top_n": n,
        }

    elif op == "groupby_aggregate":
        gb, ac, agg = spec["group_by"], spec["agg_column"], spec["agg"]
        grouped = (
            df.groupby(df[gb].astype(str), dropna=False)[ac]
            .apply(lambda g: _agg_one(g, agg))
            .reset_index()
        )
        grouped.columns = [gb, f"{agg}({ac})"]
        grouped = grouped.sort_values(by=f"{agg}({ac})", ascending=False)
        result = _result_envelope(grouped, name=f"{agg} of {ac} by {gb}")
        suggested_chart = {
            "chart_type": "bar",
            "encoding": {"x": gb, "y": ac, "agg": agg},
            "title": f"{agg} of {ac} by {gb}",
        }

    elif op == "filter_aggregate":
        if spec.get("agg") == "count_rows":
            value = int(len(df))
            result = {
                "name": "filtered_count",
                "columns": ["count"],
                "rows": [{"count": value}],
                "truncated": False,
                "row_count": 1,
            }
            suggested_chart = {
                "chart_type": "kpi",
                "encoding": {"agg": "count_rows"},
                "title": "Filtered count",
            }
        else:
            ac, agg = spec["agg_column"], spec["agg"]
            value = _agg_one(df[ac], agg)
            result = {
                "name": f"{agg}({ac})",
                "columns": [f"{agg}({ac})"],
                "rows": [{f"{agg}({ac})": value}],
                "truncated": False,
                "row_count": 1,
            }
            suggested_chart = {
                "chart_type": "kpi",
                "encoding": {"y": ac, "agg": agg},
                "title": f"{agg} of {ac}",
            }

    elif op == "time_series":
        x, y, agg = spec["x"], spec["y"], spec["agg"]
        s = pd.to_datetime(df[x], errors="coerce")
        sub = pd.DataFrame({"_t": s, "_y": pd.to_numeric(df[y], errors="coerce")}).dropna()
        if len(sub) == 0:
            result = _result_envelope(pd.DataFrame({x: [], f"{agg}({y})": []}), name=f"{agg} of {y} over {x}")
        else:
            grouped = sub.set_index("_t").sort_index()["_y"].resample("D").agg(agg).dropna().reset_index()
            grouped.columns = [x, f"{agg}({y})"]
            result = _result_envelope(grouped, name=f"{agg} of {y} over {x}")
        suggested_chart = {
            "chart_type": "line",
            "encoding": {"x": x, "y": y, "agg": agg},
            "title": f"{agg} of {y} over {x}",
        }

    else:  # pragma: no cover — validation prevented it
        raise AskRejected(f"unsupported operation: {op}", reason="bad_operation")

    return result, suggested_chart


def _agg_one(series: pd.Series, agg: str) -> Any:
    if agg == "count":
        return int(series.count())
    s = pd.to_numeric(series, errors="coerce")
    if agg == "mean":
        return float(s.mean())
    if agg == "sum":
        return float(s.sum())
    if agg == "min":
        return float(s.min())
    if agg == "max":
        return float(s.max())
    if agg == "median":
        return float(s.median())
    raise AskRejected(f"agg '{agg}' not allowed", reason="bad_agg")


# =============================================================================
# Public entry point
# =============================================================================

def ask(
    *,
    question: str,
    profile: dict[str, Any],
    df: pd.DataFrame,
    client: GeminiClient,
) -> dict[str, Any]:
    """Plan → validate → execute → explain."""
    precheck_question(question)

    # 1. Plan
    columns = [
        {"name": c["name"], "semantic_type": c["semantic_type"]}
        for c in (profile.get("columns") or [])
    ]
    raw_spec = client.generate_json(
        PLANNER_SYSTEM,
        _plan_prompt(question, columns),
        PLAN_SCHEMA,
        temperature=TEMPERATURE_PLANNER,
    )
    spec = validate_spec(raw_spec, profile)

    # 2. Execute
    result, suggested_chart = execute_spec(df, spec)

    # 3. Explain
    answer = client.generate_text(
        EXPLAINER_SYSTEM,
        _explain_prompt(question, spec, result),
        temperature=TEMPERATURE_EXPLAINER,
    )

    return {
        "answer": answer.strip(),
        "analysis_spec": spec,
        "result_table": result,
        "suggested_chart": suggested_chart,
    }


__all__ = [
    "ALLOWED_OPERATIONS",
    "ALLOWED_AGGS",
    "AskRejected",
    "ask",
    "execute_spec",
    "precheck_question",
    "validate_spec",
]
