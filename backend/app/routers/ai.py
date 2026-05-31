"""Phase 5 — AI endpoints.

Summary / story / insights are cached in `ai_outputs` per (version, type).
Ask-Your-Data uses the strict plan→validate→execute→explain engine and saves
each turn to `ai_conversations`.

All endpoints reuse the Phase-4 version-resolution helper so AI runs on the
same version the dashboard does (latest cleaned, else raw).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import Settings, get_settings
from ..deps import CurrentUser, get_current_user
from ..schemas.ai import (
    AskRequest,
    AskResponse,
    ConversationResponse,
    ConversationTurn,
    Finding,
    InsightsResponse,
    ResultTable,
    StoryResponse,
    SuggestedAnalysis,
    SummaryResponse,
)
from ..services.ai_context import build_ai_context
from ..services.ai_insights import (
    generate_auto_insights,
    generate_story,
    generate_summary,
)
from ..services.ask_data import AskRejected, ask
from ..services.data_loader import load_dataframe
from ..services.gemini_client import AIUnavailable, GeminiClient
from ..supabase_client import SupabaseClient
from .datasets import (
    _fetch_or_build_profile,
    _fetch_owned_dataset,
    _resolve_dashboard_version,
    _version_source_type,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["ai"])


# =============================================================================
# Helpers
# =============================================================================

async def _get_client(settings: Settings = Depends(get_settings)) -> SupabaseClient:
    return SupabaseClient(settings)


def _ai_client(settings: Settings = Depends(get_settings)) -> GeminiClient:
    return GeminiClient(settings)


def _raise_unavailable(exc: AIUnavailable) -> None:
    """Convert AIUnavailable into a clean 503 the FE knows how to render."""
    raise HTTPException(
        status_code=getattr(exc, "status_hint", 503),
        detail=str(exc),
    )


async def _get_cached_output(
    sb: SupabaseClient, version_id: str, output_type: str
) -> dict[str, Any] | None:
    rows = await sb.table_get(
        "ai_outputs",
        {
            "dataset_version_id": f"eq.{version_id}",
            "output_type": f"eq.{output_type}",
            "select": "content,created_at",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


async def _upsert_cached_output(
    sb: SupabaseClient, version_id: str, output_type: str, content: dict[str, Any]
) -> str | None:
    # PostgREST: insert with on_conflict for upsert.
    client = await sb._http()  # noqa: SLF001 — internal but stable
    r = await client.post(
        f"{sb.url}/rest/v1/ai_outputs",
        json={
            "dataset_version_id": version_id,
            "output_type": output_type,
            "content": content,
        },
        headers={
            "Prefer": "resolution=merge-duplicates,return=representation",
        },
        params={"on_conflict": "dataset_version_id,output_type"},
    )
    r.raise_for_status()
    out = r.json()
    if out and isinstance(out, list):
        return out[0].get("created_at")
    return None


async def _load_version_df(
    sb: SupabaseClient, version: dict[str, Any], source_type: str
):
    raw = await sb.storage_download("datasets", version["storage_path"])
    df, _ = load_dataframe(raw, source_type)
    return df


# =============================================================================
# Summary / Story
# =============================================================================

async def _summary_or_story(
    *,
    sb: SupabaseClient,
    ai: GeminiClient,
    dataset_id: str,
    user_id: str,
    version_id: str | None,
    refresh: bool,
    kind: str,
) -> dict[str, Any]:
    ds = await _fetch_owned_dataset(sb, dataset_id, user_id)
    version = await _resolve_dashboard_version(sb, dataset_id, version_id)
    cached = None if refresh else await _get_cached_output(sb, version["id"], kind)
    if cached:
        return {
            "version_id": version["id"],
            "version_label": version["label"],
            "text": (cached["content"] or {}).get("text", ""),
            "created_at": cached["created_at"],
            "cached": True,
        }

    profile = await _fetch_or_build_profile(sb, version, _version_source_type(version, ds))
    ctx = build_ai_context(
        dataset_name=ds["name"],
        version_label=version["label"],
        profile=profile,
        cleaning_steps=version.get("cleaning_steps") or [],
    )
    try:
        if kind == "summary":
            out = generate_summary(ctx, ai)
        elif kind == "story":
            out = generate_story(ctx, ai)
        else:  # pragma: no cover
            raise ValueError(kind)
    except AIUnavailable as exc:
        _raise_unavailable(exc)

    created_at = await _upsert_cached_output(sb, version["id"], kind, out)
    return {
        "version_id": version["id"],
        "version_label": version["label"],
        "text": out.get("text", ""),
        "created_at": created_at,
        "cached": False,
    }


@router.get("/{dataset_id}/ai/summary", response_model=SummaryResponse)
async def ai_summary(
    dataset_id: str,
    version_id: str | None = Query(default=None),
    refresh: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
    ai: GeminiClient = Depends(_ai_client),
) -> SummaryResponse:
    try:
        out = await _summary_or_story(
            sb=sb, ai=ai, dataset_id=dataset_id, user_id=user.id,
            version_id=version_id, refresh=refresh, kind="summary",
        )
        return SummaryResponse(**out)
    finally:
        await sb.close()


@router.get("/{dataset_id}/ai/story", response_model=StoryResponse)
async def ai_story(
    dataset_id: str,
    version_id: str | None = Query(default=None),
    refresh: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
    ai: GeminiClient = Depends(_ai_client),
) -> StoryResponse:
    try:
        out = await _summary_or_story(
            sb=sb, ai=ai, dataset_id=dataset_id, user_id=user.id,
            version_id=version_id, refresh=refresh, kind="story",
        )
        return StoryResponse(**out)
    finally:
        await sb.close()


# =============================================================================
# Auto-insights
# =============================================================================

@router.get("/{dataset_id}/ai/insights", response_model=InsightsResponse)
async def ai_insights(
    dataset_id: str,
    version_id: str | None = Query(default=None),
    refresh: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
    ai: GeminiClient = Depends(_ai_client),
) -> InsightsResponse:
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _resolve_dashboard_version(sb, dataset_id, version_id)
        cached = None if refresh else await _get_cached_output(sb, version["id"], "insights")
        if cached:
            content = cached["content"] or {}
            return InsightsResponse(
                version_id=version["id"],
                version_label=version["label"],
                findings=[Finding(**f) for f in content.get("findings", [])],
                suggested_analyses=[SuggestedAnalysis(**a) for a in content.get("suggested_analyses", [])],
                created_at=cached["created_at"],
                cached=True,
            )

        profile = await _fetch_or_build_profile(sb, version, _version_source_type(version, ds))
        ctx = build_ai_context(
            dataset_name=ds["name"],
            version_label=version["label"],
            profile=profile,
            cleaning_steps=version.get("cleaning_steps") or [],
        )
        try:
            out = generate_auto_insights(ctx, ai)
        except AIUnavailable as exc:
            _raise_unavailable(exc)

        created_at = await _upsert_cached_output(sb, version["id"], "insights", out)
        return InsightsResponse(
            version_id=version["id"],
            version_label=version["label"],
            findings=[Finding(**f) for f in out.get("findings", [])],
            suggested_analyses=[SuggestedAnalysis(**a) for a in out.get("suggested_analyses", [])],
            created_at=created_at,
            cached=False,
        )
    finally:
        await sb.close()


# =============================================================================
# Ask Your Data
# =============================================================================

@router.post("/{dataset_id}/ai/ask", response_model=AskResponse)
async def ai_ask(
    dataset_id: str,
    req: AskRequest,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
    ai: GeminiClient = Depends(_ai_client),
) -> AskResponse:
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _resolve_dashboard_version(sb, dataset_id, req.version_id)
        source_type = _version_source_type(version, ds)
        profile = await _fetch_or_build_profile(sb, version, source_type)
        df = await _load_version_df(sb, version, source_type)

        try:
            out = ask(question=req.question, profile=profile, df=df, client=ai)
        except AskRejected as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"reason": exc.reason, "message": str(exc)},
            ) from exc
        except AIUnavailable as exc:
            _raise_unavailable(exc)

        # Persist the turn pair to ai_conversations.
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        await sb.table_insert("ai_conversations", {
            "user_id": user.id,
            "dataset_id": dataset_id,
            "role": "user",
            "content": req.question,
            "created_at": now,
        }, returning="minimal")
        await sb.table_insert("ai_conversations", {
            "user_id": user.id,
            "dataset_id": dataset_id,
            "role": "assistant",
            "content": json.dumps({
                "answer": out["answer"],
                "analysis_spec": out["analysis_spec"],
                "result_table": out["result_table"],
                "suggested_chart": out["suggested_chart"],
            }),
            "created_at": now,
        }, returning="minimal")

        return AskResponse(
            version_id=version["id"],
            version_label=version["label"],
            question=req.question,
            answer=out["answer"],
            analysis_spec=out["analysis_spec"],
            result_table=ResultTable(**out["result_table"]),
            suggested_chart=out["suggested_chart"],
        )
    finally:
        await sb.close()


@router.get("/{dataset_id}/ai/conversation", response_model=ConversationResponse)
async def ai_conversation(
    dataset_id: str,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> ConversationResponse:
    try:
        await _fetch_owned_dataset(sb, dataset_id, user.id)
        rows = await sb.table_get(
            "ai_conversations",
            {
                "user_id": f"eq.{user.id}",
                "dataset_id": f"eq.{dataset_id}",
                "select": "role,content,created_at",
                "order": "created_at.asc",
                "limit": "200",
            },
        )
        turns: list[ConversationTurn] = []
        for r in rows:
            payload: dict[str, Any] | None = None
            content = r["content"]
            if r["role"] == "assistant":
                try:
                    parsed = json.loads(content)
                    payload = parsed
                    content = parsed.get("answer", "")
                except (json.JSONDecodeError, TypeError):
                    payload = None
            turns.append(ConversationTurn(
                role=r["role"],
                content=content,
                created_at=r["created_at"],
                payload=payload,
            ))
        return ConversationResponse(dataset_id=dataset_id, turns=turns)
    finally:
        await sb.close()
