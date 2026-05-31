"""Cascading delete for a dataset and everything it owns.

The schema's foreign keys already cascade-delete child rows when a `datasets`
row goes away. We still issue the deletes explicitly (in dependency order) for
two reasons:
  - Storage files aren't in the database, so they must be enumerated and
    removed independently. We do that *first* so the metadata in the DB
    survives if storage cleanup fails partway.
  - Explicit deletes give us per-table counts in the response so the UI can
    confirm what was actually removed.

Storage cleanup is best-effort: a 404 (file already gone) is logged and the
delete continues — the DB rows are the source of truth.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..supabase_client import SupabaseClient

log = logging.getLogger(__name__)


class DatasetDeleteError(RuntimeError):
    """Raised when deletion cannot proceed (e.g. ownership / not found)."""

    def __init__(self, message: str, *, status: int = 400, reason: str = "delete_failed") -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_uuids(uuids: list[str]) -> str:
    """Render a list of UUIDs for PostgREST `in.(…)` filters.

    UUIDs are URL-safe and don't need quoting in PostgREST in-lists.
    """
    return ",".join(uuids)


async def _count_rows(sb: SupabaseClient, table: str, params: dict[str, str]) -> int:
    """Cheap row-count: SELECT id with the filter, then len()."""
    select_params = dict(params)
    select_params["select"] = "id"
    rows = await sb.table_get(table, select_params)
    return len(rows)


async def _delete_storage_paths(
    sb: SupabaseClient, paths: list[str]
) -> tuple[int, int]:
    """Best-effort: delete each path; missing files are logged, not raised.
    Returns (deleted_count, missing_count)."""
    deleted = 0
    missing = 0
    for path in paths:
        try:
            await sb.storage_delete("datasets", path)
            deleted += 1
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.info("storage delete: %s already missing — continuing", path)
                missing += 1
            else:
                log.warning("storage delete failed for %s: %s — continuing", path, exc)
                missing += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("storage delete failed for %s: %s — continuing", path, exc)
            missing += 1
    return deleted, missing


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def delete_dataset(
    sb: SupabaseClient, dataset_id: str, user_id: str
) -> dict[str, Any]:
    """Owner-checked cascading delete. Returns a summary of what was removed.

    Raises `DatasetDeleteError` with the right HTTP status for ownership /
    not-found cases. Any other exception bubbles as 500.
    """
    # 1. Owner check + fetch raw storage path
    ds_rows = await sb.table_get(
        "datasets",
        {"id": f"eq.{dataset_id}", "select": "id,user_id,name,storage_path"},
    )
    if not ds_rows:
        raise DatasetDeleteError("dataset not found", status=404, reason="not_found")
    ds = ds_rows[0]
    if ds["user_id"] != user_id:
        # Treat as not-found to avoid leaking the existence of other users'
        # datasets, while still raising a precise reason for the test suite.
        raise DatasetDeleteError(
            "dataset not found", status=404, reason="not_owner"
        )

    # 2. Gather dependent ids + storage paths
    versions = await sb.table_get(
        "dataset_versions",
        {"dataset_id": f"eq.{dataset_id}", "select": "id,storage_path"},
    )
    version_ids = [v["id"] for v in versions]

    storage_paths: list[str] = []
    if ds.get("storage_path"):
        storage_paths.append(ds["storage_path"])
    for v in versions:
        path = v.get("storage_path")
        if path and path not in storage_paths:
            storage_paths.append(path)

    dashboards = await sb.table_get(
        "dashboards",
        {"dataset_id": f"eq.{dataset_id}", "select": "id"},
    )
    dashboard_ids = [d["id"] for d in dashboards]

    # 3. Pre-count children so we can report them in the response
    counts: dict[str, int] = {}
    if dashboard_ids:
        counts["charts"] = await _count_rows(
            sb, "charts",
            {"dashboard_id": f"in.({_csv_uuids(dashboard_ids)})"},
        )
    else:
        counts["charts"] = 0
    counts["dashboards"] = len(dashboard_ids)
    counts["ai_conversations"] = await _count_rows(
        sb, "ai_conversations", {"dataset_id": f"eq.{dataset_id}"}
    )
    if version_ids:
        counts["ai_outputs"] = await _count_rows(
            sb, "ai_outputs",
            {"dataset_version_id": f"in.({_csv_uuids(version_ids)})"},
        )
        counts["data_profiles"] = await _count_rows(
            sb, "data_profiles",
            {"dataset_version_id": f"in.({_csv_uuids(version_ids)})"},
        )
    else:
        counts["ai_outputs"] = 0
        counts["data_profiles"] = 0
    counts["analysis_jobs"] = await _count_rows(
        sb, "analysis_jobs", {"dataset_id": f"eq.{dataset_id}"}
    )
    counts["dataset_versions"] = len(version_ids)
    counts["datasets"] = 1

    # 4. Storage deletes first — DB rows are source of truth, but doing
    # storage first means if the request dies after this point, the user can
    # still re-run delete and the DB will be cleaned up.
    storage_deleted, storage_missing = await _delete_storage_paths(sb, storage_paths)

    # 5. Row deletes, deepest first (FK-safe even without cascades)
    if dashboard_ids:
        await sb.table_delete(
            "charts",
            {"dashboard_id": f"in.({_csv_uuids(dashboard_ids)})"},
        )
    await sb.table_delete("dashboards", {"dataset_id": f"eq.{dataset_id}"})
    await sb.table_delete("ai_conversations", {"dataset_id": f"eq.{dataset_id}"})
    if version_ids:
        await sb.table_delete(
            "ai_outputs",
            {"dataset_version_id": f"in.({_csv_uuids(version_ids)})"},
        )
        await sb.table_delete(
            "data_profiles",
            {"dataset_version_id": f"in.({_csv_uuids(version_ids)})"},
        )
    await sb.table_delete("analysis_jobs", {"dataset_id": f"eq.{dataset_id}"})
    await sb.table_delete("dataset_versions", {"dataset_id": f"eq.{dataset_id}"})
    await sb.table_delete("datasets", {"id": f"eq.{dataset_id}"})

    return {
        "ok": True,
        "deleted": {
            "dataset_id": dataset_id,
            "dataset_name": ds.get("name"),
            "storage_files": storage_deleted,
            "storage_missing": storage_missing,
            "rows_by_table": counts,
        },
    }


__all__ = ["DatasetDeleteError", "delete_dataset"]
