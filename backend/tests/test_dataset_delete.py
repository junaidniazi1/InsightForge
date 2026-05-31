"""Phase 9-PRE tests — owner-only cascading dataset deletion.

The Supabase client is a hand-rolled async stub so we can assert the exact
sequence of storage + table operations without touching the network.
"""

from __future__ import annotations

from typing import Any

import asyncio

import httpx
import pytest

from app.services.dataset_delete import DatasetDeleteError, delete_dataset


# ---------------------------------------------------------------------------
# Stub Supabase client — records every call so tests can assert what happened.
# ---------------------------------------------------------------------------

class _StubResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class StubSupabaseClient:
    """Records every storage and table call. Returns canned data for `table_get`
    keyed by `(table, filter_key, filter_value)`.
    """

    def __init__(
        self,
        *,
        datasets: list[dict[str, Any]],
        versions: list[dict[str, Any]],
        dashboards: list[dict[str, Any]],
        charts: list[dict[str, Any]] | None = None,
        ai_conversations: list[dict[str, Any]] | None = None,
        ai_outputs: list[dict[str, Any]] | None = None,
        data_profiles: list[dict[str, Any]] | None = None,
        analysis_jobs: list[dict[str, Any]] | None = None,
        storage_missing_paths: set[str] | None = None,
    ) -> None:
        self.datasets = datasets
        self.versions = versions
        self.dashboards = dashboards
        self.charts = charts or []
        self.ai_conversations = ai_conversations or []
        self.ai_outputs = ai_outputs or []
        self.data_profiles = data_profiles or []
        self.analysis_jobs = analysis_jobs or []
        self.storage_missing = storage_missing_paths or set()

        # Recorded operations
        self.storage_deletes: list[tuple[str, str]] = []
        self.table_deletes: list[tuple[str, dict[str, str]]] = []
        self.table_gets: list[tuple[str, dict[str, str]]] = []

    # -- Table read --------------------------------------------------------
    async def table_get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        self.table_gets.append((table, dict(params)))
        if table == "datasets":
            return [dict(d) for d in self.datasets]
        if table == "dataset_versions":
            return [dict(v) for v in self.versions]
        if table == "dashboards":
            return [dict(d) for d in self.dashboards]
        if table == "charts":
            return [dict(c) for c in self.charts]
        if table == "ai_conversations":
            return [dict(c) for c in self.ai_conversations]
        if table == "ai_outputs":
            return [dict(o) for o in self.ai_outputs]
        if table == "data_profiles":
            return [dict(p) for p in self.data_profiles]
        if table == "analysis_jobs":
            return [dict(j) for j in self.analysis_jobs]
        return []

    # -- Table delete ------------------------------------------------------
    async def table_delete(self, table: str, params: dict[str, str]) -> None:
        self.table_deletes.append((table, dict(params)))

    # -- Storage delete ----------------------------------------------------
    async def storage_delete(self, bucket: str, path: str) -> None:
        self.storage_deletes.append((bucket, path))
        if path in self.storage_missing:
            # Simulate a Supabase 404.
            req = httpx.Request("DELETE", f"http://test/{bucket}/{path}")
            resp = httpx.Response(404, request=req)
            raise httpx.HTTPStatusError("not found", request=req, response=resp)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

OWNER = "user-owner-1"
INTRUDER = "user-other-2"
DATASET_ID = "ds-aaaaaaaa-1111-2222-3333-444444444444"
RAW_VERSION_ID = "ver-aaaa-1111"
CLEANED_VERSION_ID = "ver-bbbb-2222"
CLEANED_VERSION_ID_2 = "ver-cccc-3333"
DASHBOARD_ID = "dash-1111"


def _base_client(**overrides: Any) -> StubSupabaseClient:
    defaults: dict[str, Any] = dict(
        datasets=[{
            "id": DATASET_ID,
            "user_id": OWNER,
            "name": "Q4 sales",
            "storage_path": f"{OWNER}/abc-q4.csv",
        }],
        versions=[
            {"id": RAW_VERSION_ID, "storage_path": f"{OWNER}/abc-q4.csv"},
            {"id": CLEANED_VERSION_ID, "storage_path": f"{OWNER}/cleaned/{DATASET_ID}-v2.csv"},
        ],
        dashboards=[{"id": DASHBOARD_ID}],
        charts=[{"id": "ch1"}, {"id": "ch2"}, {"id": "ch3"}],
        ai_conversations=[{"id": f"conv{i}"} for i in range(14)],
        ai_outputs=[{"id": "out1"}, {"id": "out2"}],
        data_profiles=[{"id": "p1"}, {"id": "p2"}],
        analysis_jobs=[{"id": "job1"}],
    )
    defaults.update(overrides)
    return StubSupabaseClient(**defaults)


# ===========================================================================
# Happy path
# ===========================================================================

def test_owner_delete_removes_all_storage_and_rows() -> None:
    sb = _base_client()
    out = asyncio.run(delete_dataset(sb, DATASET_ID, OWNER))

    # Both storage paths got DELETE calls.
    deleted_paths = {p for _, p in sb.storage_deletes}
    assert deleted_paths == {
        f"{OWNER}/abc-q4.csv",
        f"{OWNER}/cleaned/{DATASET_ID}-v2.csv",
    }

    # Every expected table_delete fired, in dependency order.
    deleted_tables = [t for t, _ in sb.table_deletes]
    assert deleted_tables == [
        "charts",
        "dashboards",
        "ai_conversations",
        "ai_outputs",
        "data_profiles",
        "analysis_jobs",
        "dataset_versions",
        "datasets",
    ]

    # Response shape is what the FE expects.
    assert out["ok"] is True
    counts = out["deleted"]["rows_by_table"]
    assert counts["dataset_versions"] == 2
    assert counts["dashboards"] == 1
    assert counts["charts"] == 3
    assert counts["ai_conversations"] == 14
    assert counts["ai_outputs"] == 2
    assert counts["data_profiles"] == 2
    assert counts["analysis_jobs"] == 1
    assert counts["datasets"] == 1
    assert out["deleted"]["storage_files"] == 2
    assert out["deleted"]["storage_missing"] == 0


# ===========================================================================
# Ownership / not-found
# ===========================================================================

def test_non_owner_gets_404_and_nothing_is_deleted() -> None:
    sb = _base_client()
    with pytest.raises(DatasetDeleteError) as ei:
        asyncio.run(delete_dataset(sb, DATASET_ID, INTRUDER))
    # We use 404 (not 403) to avoid leaking the existence of other users'
    # datasets, but the reason is precise enough for tests.
    assert ei.value.status == 404
    assert ei.value.reason == "not_owner"
    # And critically: no storage or row deletes happened.
    assert sb.storage_deletes == []
    assert sb.table_deletes == []


def test_missing_dataset_returns_404() -> None:
    sb = _base_client(datasets=[])
    with pytest.raises(DatasetDeleteError) as ei:
        asyncio.run(delete_dataset(sb, DATASET_ID, OWNER))
    assert ei.value.status == 404
    assert ei.value.reason == "not_found"
    assert sb.storage_deletes == []
    assert sb.table_deletes == []


# ===========================================================================
# Storage best-effort behaviour
# ===========================================================================

def test_missing_storage_file_is_logged_not_raised() -> None:
    """If a storage file is already missing, the row deletes still run."""
    missing = f"{OWNER}/abc-q4.csv"
    sb = _base_client(storage_missing_paths={missing})
    out = asyncio.run(delete_dataset(sb, DATASET_ID, OWNER))

    # All row deletes still fired.
    deleted_tables = [t for t, _ in sb.table_deletes]
    assert "datasets" in deleted_tables
    assert "dataset_versions" in deleted_tables

    # And the response reports the miss.
    assert out["deleted"]["storage_files"] == 1     # the cleaned file
    assert out["deleted"]["storage_missing"] == 1   # the missing raw file


# ===========================================================================
# Multi-version coverage
# ===========================================================================

def test_multiple_cleaned_versions_all_files_deleted() -> None:
    sb = _base_client(
        versions=[
            {"id": RAW_VERSION_ID, "storage_path": f"{OWNER}/raw.csv"},
            {"id": CLEANED_VERSION_ID, "storage_path": f"{OWNER}/cleaned/v2.csv"},
            {"id": CLEANED_VERSION_ID_2, "storage_path": f"{OWNER}/cleaned/v3.csv"},
        ],
        datasets=[{
            "id": DATASET_ID,
            "user_id": OWNER,
            "name": "multi-version dataset",
            "storage_path": f"{OWNER}/raw.csv",
        }],
    )
    out = asyncio.run(delete_dataset(sb, DATASET_ID, OWNER))
    deleted_paths = {p for _, p in sb.storage_deletes}
    assert deleted_paths == {
        f"{OWNER}/raw.csv",
        f"{OWNER}/cleaned/v2.csv",
        f"{OWNER}/cleaned/v3.csv",
    }
    assert out["deleted"]["rows_by_table"]["dataset_versions"] == 3


def test_raw_path_not_double_deleted_when_version_repeats_it() -> None:
    """The raw file path is listed both on `datasets.storage_path` and on the
    raw `dataset_versions.storage_path`. Don't try to delete it twice."""
    sb = _base_client(
        versions=[
            {"id": RAW_VERSION_ID, "storage_path": f"{OWNER}/abc-q4.csv"},
        ],
    )
    asyncio.run(delete_dataset(sb, DATASET_ID, OWNER))
    raw_path_count = sum(
        1 for _, p in sb.storage_deletes if p == f"{OWNER}/abc-q4.csv"
    )
    assert raw_path_count == 1


# ===========================================================================
# Dashboard + chart cleanup
# ===========================================================================

def test_dataset_with_dashboard_removes_dashboards_and_charts() -> None:
    sb = _base_client()
    asyncio.run(delete_dataset(sb, DATASET_ID, OWNER))
    deleted_tables = [t for t, _ in sb.table_deletes]
    assert "charts" in deleted_tables
    assert "dashboards" in deleted_tables
    # charts deleted by `in.(dashboard_ids)` filter
    chart_filter = next(p for t, p in sb.table_deletes if t == "charts")
    assert f"in.({DASHBOARD_ID})" in chart_filter["dashboard_id"]


def test_dataset_without_dashboards_skips_chart_delete() -> None:
    sb = _base_client(dashboards=[], charts=[])
    asyncio.run(delete_dataset(sb, DATASET_ID, OWNER))
    deleted_tables = [t for t, _ in sb.table_deletes]
    # No charts query / delete should happen if there are no dashboards.
    assert "charts" not in deleted_tables
    # Dashboards delete still fires (no-op at DB level, but harmless).
    assert "dashboards" in deleted_tables


# ===========================================================================
# Sanity: dataset with no versions still works
# ===========================================================================

def test_dataset_without_versions_still_deletes() -> None:
    sb = _base_client(
        versions=[],
        ai_outputs=[],
        data_profiles=[],
    )
    out = asyncio.run(delete_dataset(sb, DATASET_ID, OWNER))
    # The raw storage path from `datasets` row is still cleaned up; the
    # "datasets" here is the storage *bucket* name, not the table.
    assert sb.storage_deletes == [("datasets", f"{OWNER}/abc-q4.csv")]
    # ai_outputs / data_profiles deletes are skipped since there are no
    # version ids to scope the in.() filter.
    deleted_tables = [t for t, _ in sb.table_deletes]
    assert "ai_outputs" not in deleted_tables
    assert "data_profiles" not in deleted_tables
    assert out["deleted"]["rows_by_table"]["dataset_versions"] == 0
