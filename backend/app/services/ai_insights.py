"""Summary, story, and auto-insights generators.

Each function takes the row-free `ctx` from ai_context + an injected
GeminiClient (so tests can pass a stub). Errors bubble up as AIUnavailable.

System prompts (including the shared safety base) live in `ai_prompts.py` so
every Gemini call in the app shares the same guarantees. Per-call temperatures
also come from there.
"""

from __future__ import annotations

import json
from typing import Any

from .ai_prompts import (
    INSIGHTS_SYSTEM,
    STORY_SYSTEM,
    SUMMARY_SYSTEM,
    TEMPERATURE_INSIGHTS,
    TEMPERATURE_STORY,
    TEMPERATURE_SUMMARY,
)
from .gemini_client import GeminiClient


# =============================================================================
# Structured-output schemas
# =============================================================================

# Subset of OpenAPI-ish schema accepted by Gemini's response_schema.
INSIGHTS_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "findings": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "detail": {"type": "STRING"},
                    "severity": {
                        "type": "STRING",
                        "enum": ["info", "notable", "concern"],
                    },
                    "columns": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["title", "detail", "severity"],
            },
        },
        "suggested_analyses": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "label": {"type": "STRING"},
                    "question": {"type": "STRING"},
                },
                "required": ["label"],
            },
        },
    },
    "required": ["findings"],
}


# =============================================================================
# Prompts (user-side)
# =============================================================================

def _user_prompt(ctx: dict[str, Any]) -> str:
    return (
        "Dataset profile JSON follows. Use it to ground every claim.\n\n"
        f"{json.dumps(ctx, indent=2, default=str)}"
    )


# =============================================================================
# Entry points
# =============================================================================

def generate_summary(ctx: dict[str, Any], client: GeminiClient) -> dict[str, Any]:
    text = client.generate_text(SUMMARY_SYSTEM, _user_prompt(ctx), temperature=TEMPERATURE_SUMMARY)
    return {"text": text, "ctx_keys": sorted(ctx.keys())}


def generate_story(ctx: dict[str, Any], client: GeminiClient) -> dict[str, Any]:
    text = client.generate_text(STORY_SYSTEM, _user_prompt(ctx), temperature=TEMPERATURE_STORY)
    return {"text": text, "ctx_keys": sorted(ctx.keys())}


def generate_auto_insights(ctx: dict[str, Any], client: GeminiClient) -> dict[str, Any]:
    raw = client.generate_json(
        INSIGHTS_SYSTEM,
        _user_prompt(ctx),
        INSIGHTS_SCHEMA,
        temperature=TEMPERATURE_INSIGHTS,
    )
    findings = list(raw.get("findings") or [])[:5]
    suggested = list(raw.get("suggested_analyses") or [])[:5]
    # Defensive normalisation — Gemini sometimes lower-cases enum values.
    for f in findings:
        sev = str(f.get("severity", "info")).lower()
        f["severity"] = sev if sev in ("info", "notable", "concern") else "info"
    return {"findings": findings, "suggested_analyses": suggested}


__all__ = ["generate_summary", "generate_story", "generate_auto_insights"]
