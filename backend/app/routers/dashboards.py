from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..config import Settings, get_settings
from ..deps import CurrentUser, get_current_user
from ..schemas.charts import (
    DashboardChartIn,
    DashboardChartOut,
    DashboardCreate,
    DashboardListItem,
    DashboardOut,
    DashboardUpdate,
)
from ..supabase_client import SupabaseClient

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


async def _get_client(settings: Settings = Depends(get_settings)) -> SupabaseClient:
    return SupabaseClient(settings)


# =============================================================================
# Helpers
# =============================================================================

async def _verify_dataset_owned(sb: SupabaseClient, dataset_id: str, user_id: str) -> None:
    rows = await sb.table_get(
        "datasets",
        {
            "id": f"eq.{dataset_id}",
            "user_id": f"eq.{user_id}",
            "select": "id",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")


async def _fetch_owned_dashboard(
    sb: SupabaseClient, dashboard_id: str, user_id: str
) -> dict[str, Any]:
    rows = await sb.table_get(
        "dashboards",
        {
            "id": f"eq.{dashboard_id}",
            "user_id": f"eq.{user_id}",
            "select": "id,user_id,dataset_id,name,layout,created_at",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dashboard not found")
    return rows[0]


async def _fetch_charts(sb: SupabaseClient, dashboard_id: str) -> list[dict[str, Any]]:
    rows = await sb.table_get(
        "charts",
        {
            "dashboard_id": f"eq.{dashboard_id}",
            "select": "id,dashboard_id,chart_type,config,position",
            "order": "position.asc",
        },
    )
    return rows


async def _replace_charts(
    sb: SupabaseClient, dashboard_id: str, charts: list[DashboardChartIn]
) -> list[dict[str, Any]]:
    await sb.table_delete("charts", {"dashboard_id": f"eq.{dashboard_id}"})
    if not charts:
        return []
    payload = [
        {
            "dashboard_id": dashboard_id,
            "chart_type": c.chart_type,
            "config": c.config,
            "position": c.position,
        }
        for c in charts
    ]
    # PostgREST supports bulk insert via list body.
    inserted: list[dict[str, Any]] = []
    for row in payload:
        r = await sb.table_insert("charts", row)
        inserted.extend(r)
    return inserted


# =============================================================================
# Endpoints
# =============================================================================

@router.post("", response_model=DashboardOut, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    body: DashboardCreate,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> DashboardOut:
    try:
        await _verify_dataset_owned(sb, body.dataset_id, user.id)
        created = await sb.table_insert(
            "dashboards",
            {
                "user_id": user.id,
                "dataset_id": body.dataset_id,
                "name": body.name,
                "layout": body.layout,
            },
        )
        d = created[0]
        charts = await _replace_charts(sb, d["id"], body.charts)
        return DashboardOut(
            id=d["id"],
            user_id=d["user_id"],
            dataset_id=d["dataset_id"],
            name=d["name"],
            layout=d["layout"] or {},
            created_at=d["created_at"],
            charts=[DashboardChartOut(**c) for c in charts],
        )
    finally:
        await sb.close()


@router.get("", response_model=list[DashboardListItem])
async def list_dashboards(
    dataset_id: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> list[DashboardListItem]:
    try:
        await _verify_dataset_owned(sb, dataset_id, user.id)
        rows = await sb.table_get(
            "dashboards",
            {
                "user_id": f"eq.{user.id}",
                "dataset_id": f"eq.{dataset_id}",
                "select": "id,name,dataset_id,layout,created_at",
                "order": "created_at.desc",
            },
        )
        # Count charts per dashboard. PostgREST lacks GROUP BY in REST; loop is
        # acceptable for v1 dashboards (small N per user).
        items: list[DashboardListItem] = []
        for r in rows:
            ch = await sb.table_get(
                "charts",
                {"dashboard_id": f"eq.{r['id']}", "select": "id"},
            )
            items.append(DashboardListItem(
                id=r["id"],
                name=r["name"],
                dataset_id=r["dataset_id"],
                layout=r["layout"] or {},
                created_at=r["created_at"],
                chart_count=len(ch),
            ))
        return items
    finally:
        await sb.close()


@router.get("/{dashboard_id}", response_model=DashboardOut)
async def get_dashboard(
    dashboard_id: str,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> DashboardOut:
    try:
        d = await _fetch_owned_dashboard(sb, dashboard_id, user.id)
        charts = await _fetch_charts(sb, dashboard_id)
        return DashboardOut(
            id=d["id"],
            user_id=d["user_id"],
            dataset_id=d["dataset_id"],
            name=d["name"],
            layout=d["layout"] or {},
            created_at=d["created_at"],
            charts=[DashboardChartOut(**c) for c in charts],
        )
    finally:
        await sb.close()


@router.patch("/{dashboard_id}", response_model=DashboardOut)
async def update_dashboard(
    dashboard_id: str,
    body: DashboardUpdate,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> DashboardOut:
    try:
        d = await _fetch_owned_dashboard(sb, dashboard_id, user.id)
        patch: dict[str, Any] = {}
        if body.name is not None:
            patch["name"] = body.name
        if body.layout is not None:
            patch["layout"] = body.layout
        if patch:
            updated = await sb.table_update("dashboards", {"id": f"eq.{dashboard_id}"}, patch)
            d = updated[0]
        if body.charts is not None:
            charts = await _replace_charts(sb, dashboard_id, body.charts)
        else:
            charts = await _fetch_charts(sb, dashboard_id)
        return DashboardOut(
            id=d["id"],
            user_id=d["user_id"],
            dataset_id=d["dataset_id"],
            name=d["name"],
            layout=d["layout"] or {},
            created_at=d["created_at"],
            charts=[DashboardChartOut(**c) for c in charts],
        )
    finally:
        await sb.close()


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_dashboard(
    dashboard_id: str,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> Response:
    try:
        await _fetch_owned_dashboard(sb, dashboard_id, user.id)
        # FK ON DELETE CASCADE removes charts.
        await sb.table_delete("dashboards", {"id": f"eq.{dashboard_id}"})
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    finally:
        await sb.close()
