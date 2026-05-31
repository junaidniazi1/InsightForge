from __future__ import annotations

import datetime as dt
import io
import logging
import re
from typing import Any

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ..config import Settings, get_settings
from ..deps import CurrentUser, get_current_user
from ..schemas.charts import (
    ChartDataRequest,
    ChartDataResponse,
    ChartSuggestionsResponse,
    FilterOptionsResponse,
)
from ..schemas.clean import (
    AutoPlanResponse,
    AutoPlanStep,
    CleanDiff,
    CleanPreviewRequest,
    CleanPreviewResponse,
    CleanRequest,
    CleanResponse,
    OperationCatalog,
)
from ..schemas.datasets import PreviewResponse
from ..schemas.profile import JobRecord, ProfileEnvelope, ProfileTriggerResponse
from ..services.auto_clean import build_auto_plan, plan_summary
from ..services.dataset_delete import DatasetDeleteError, delete_dataset as svc_delete_dataset
from ..services.chart_data import build_chart_data, build_filter_options
from ..services.chart_recommender import recommend as recommend_charts
from ..services.cleaner import REGISTRY as OP_REGISTRY
from ..services.cleaner import apply_steps, compute_diff, get_catalog
from ..services.data_loader import CLEAN_MAX_ROWS, load_dataframe, paginate, to_json_safe
from ..services.gemini_client import AIUnavailable, GeminiClient
from ..services.profiler import profile_dataframe
from ..supabase_client import SupabaseClient

log = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])


async def _get_client(settings: Settings = Depends(get_settings)) -> SupabaseClient:
    return SupabaseClient(settings)


# =============================================================================
# Helpers
# =============================================================================

async def _fetch_owned_dataset(sb: SupabaseClient, dataset_id: str, user_id: str) -> dict[str, Any]:
    rows = await sb.table_get(
        "datasets",
        {
            "id": f"eq.{dataset_id}",
            "user_id": f"eq.{user_id}",
            "select": "id,name,source_type,storage_path,row_count,column_count,status",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    return rows[0]


async def _fetch_raw_version(sb: SupabaseClient, dataset_id: str) -> dict[str, Any]:
    rows = await sb.table_get(
        "dataset_versions",
        {
            "dataset_id": f"eq.{dataset_id}",
            "label": "eq.raw",
            "select": "id,storage_path,version_no,label,cleaning_steps",
            "order": "version_no.asc",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status.HTTP_409_CONFLICT, "dataset has no raw version yet")
    return rows[0]


async def _fetch_latest_cleaned(sb: SupabaseClient, dataset_id: str) -> dict[str, Any] | None:
    rows = await sb.table_get(
        "dataset_versions",
        {
            "dataset_id": f"eq.{dataset_id}",
            "label": "eq.cleaned",
            "select": "id,storage_path,version_no,label,cleaning_steps",
            "order": "version_no.desc",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


async def _fetch_version(
    sb: SupabaseClient, dataset_id: str, version_id: str | None
) -> dict[str, Any]:
    """Return the requested version, or the raw version if `version_id` is None."""
    if version_id is None:
        return await _fetch_raw_version(sb, dataset_id)
    rows = await sb.table_get(
        "dataset_versions",
        {
            "id": f"eq.{version_id}",
            "dataset_id": f"eq.{dataset_id}",
            "select": "id,storage_path,version_no,label,cleaning_steps",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
    return rows[0]


async def _resolve_dashboard_version(
    sb: SupabaseClient, dataset_id: str, version_id: str | None
) -> dict[str, Any]:
    """For dashboard endpoints: explicit version_id wins; else latest cleaned; else raw."""
    if version_id:
        return await _fetch_version(sb, dataset_id, version_id)
    cleaned = await _fetch_latest_cleaned(sb, dataset_id)
    if cleaned:
        return cleaned
    return await _fetch_raw_version(sb, dataset_id)


async def _fetch_or_build_profile(
    sb: SupabaseClient, version: dict[str, Any], source_type: str
) -> dict[str, Any]:
    """Return the latest stored profile for `version`, building one inline if missing.

    Dashboards must run on a profile so the recommender knows column types. Most
    of the time the Phase-2 worker has already produced one (cleaning auto-
    triggers a re-profile). If not, we generate one synchronously — slower on
    first dashboard open but reliable.
    """
    rows = await sb.table_get(
        "data_profiles",
        {
            "dataset_version_id": f"eq.{version['id']}",
            "select": "profile_json",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    if rows:
        return rows[0]["profile_json"]
    raw = await sb.storage_download("datasets", version["storage_path"])
    df, truncated = load_dataframe(raw, source_type)
    profile = profile_dataframe(df, truncated=truncated)
    await sb.table_insert(
        "data_profiles",
        {"dataset_version_id": version["id"], "profile_json": profile},
        returning="minimal",
    )
    return profile


async def _max_version_no(sb: SupabaseClient, dataset_id: str) -> int:
    rows = await sb.table_get(
        "dataset_versions",
        {
            "dataset_id": f"eq.{dataset_id}",
            "select": "version_no",
            "order": "version_no.desc",
            "limit": "1",
        },
    )
    return int(rows[0]["version_no"]) if rows else 0


async def _latest_running_job(
    sb: SupabaseClient, *, user_id: str, dataset_id: str, job_type: str
) -> dict[str, Any] | None:
    rows = await sb.table_get(
        "analysis_jobs",
        {
            "user_id": f"eq.{user_id}",
            "dataset_id": f"eq.{dataset_id}",
            "job_type": f"eq.{job_type}",
            "status": "in.(queued,running)",
            "select": "id,status,created_at,updated_at,error,result_json",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


async def _latest_job(
    sb: SupabaseClient, *, user_id: str, dataset_id: str, job_type: str
) -> dict[str, Any] | None:
    rows = await sb.table_get(
        "analysis_jobs",
        {
            "user_id": f"eq.{user_id}",
            "dataset_id": f"eq.{dataset_id}",
            "job_type": f"eq.{job_type}",
            "select": "id,status,created_at,updated_at,error,result_json",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def _job_record(row: dict[str, Any]) -> JobRecord:
    return JobRecord(
        id=row["id"],
        status=row["status"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        error=row.get("error"),
    )


def _version_source_type(version: dict[str, Any], dataset: dict[str, Any]) -> str:
    """Raw → dataset's source_type; cleaned → always CSV (we save them that way)."""
    return "file_csv" if version.get("label") == "cleaned" else dataset["source_type"]


# =============================================================================
# Preview (Phase 1)
# =============================================================================

# =============================================================================
# Delete (Phase 9-PRE) — cascading delete of dataset + everything it owns.
# =============================================================================

@router.delete("/{dataset_id}")
async def delete_dataset_endpoint(
    dataset_id: str,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> dict[str, Any]:
    """Owner-only cascading delete. Removes the storage files, every version,
    every dashboard/chart, profile, AI cache, and conversation row.
    """
    try:
        try:
            return await svc_delete_dataset(sb, dataset_id, user.id)
        except DatasetDeleteError as exc:
            raise HTTPException(
                status_code=exc.status,
                detail={"reason": exc.reason, "message": str(exc)},
            ) from exc
        except Exception as exc:  # noqa: BLE001
            log.exception("dataset delete failed for %s", dataset_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "reason": "partial_failure",
                    "message": f"delete failed mid-way: {exc}. Re-run to clean up remaining rows.",
                },
            ) from exc
    finally:
        await sb.close()


@router.get("/{dataset_id}/preview", response_model=PreviewResponse)
async def preview_dataset(
    dataset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> PreviewResponse:
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        if ds["source_type"] not in ("file_csv", "file_excel"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "preview only supports file_csv / file_excel in Phase 1",
            )
        if not ds["storage_path"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "dataset has no storage_path")

        raw = await sb.storage_download("datasets", ds["storage_path"])
        df, truncated = load_dataframe(raw, ds["source_type"])
        rows_out = paginate(df, page, page_size)

        return PreviewResponse(
            dataset_id=ds["id"],
            name=ds["name"],
            source_type=ds["source_type"],
            columns=[str(c) for c in df.columns],
            rows=rows_out,
            page=page,
            page_size=page_size,
            total_rows=None if truncated else int(len(df)),
            truncated=truncated,
        )
    finally:
        await sb.close()


# =============================================================================
# Profile (Phase 2) — optional ?version_id= for Phase 3's cleaned version
# =============================================================================

@router.post("/{dataset_id}/profile", response_model=ProfileTriggerResponse)
async def trigger_profile(
    dataset_id: str,
    background_tasks: BackgroundTasks,
    version_id: str | None = Query(default=None, description="version to profile; defaults to raw"),
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    sb: SupabaseClient = Depends(_get_client),
) -> ProfileTriggerResponse:
    """Kick off (or no-op if already running) a profiling job."""
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        if ds["source_type"] not in ("file_csv", "file_excel"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "profiling only supports file_csv / file_excel right now",
            )
        version = await _fetch_version(sb, dataset_id, version_id)

        existing = await _latest_running_job(
            sb, user_id=user.id, dataset_id=dataset_id, job_type="profile"
        )
        if existing:
            return ProfileTriggerResponse(job=_job_record(existing), already_running=True)

        created = await sb.table_insert(
            "analysis_jobs",
            {
                "user_id": user.id,
                "dataset_id": dataset_id,
                "job_type": "profile",
                "status": "queued",
                "result_json": {"version_id": version["id"]},
            },
        )
        job_row = created[0]
        job_id = job_row["id"]

        background_tasks.add_task(
            _run_profile_job,
            settings=settings,
            job_id=job_id,
            dataset_id=dataset_id,
            version_id=version["id"],
            storage_path=version["storage_path"] or ds["storage_path"],
            source_type=_version_source_type(version, ds),
            update_dataset_summary=(version["label"] == "raw"),
        )
        return ProfileTriggerResponse(job=_job_record(job_row))
    finally:
        await sb.close()


@router.get("/{dataset_id}/profile", response_model=ProfileEnvelope)
async def get_profile(
    dataset_id: str,
    version_id: str | None = Query(default=None, description="version to fetch; defaults to raw"),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> ProfileEnvelope:
    """Return the latest profile, the running job state, or 'needs_profiling'."""
    try:
        await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _fetch_version(sb, dataset_id, version_id)

        profile_rows = await sb.table_get(
            "data_profiles",
            {
                "dataset_version_id": f"eq.{version['id']}",
                "select": "profile_json,created_at",
                "order": "created_at.desc",
                "limit": "1",
            },
        )

        running = await _latest_running_job(
            sb, user_id=user.id, dataset_id=dataset_id, job_type="profile"
        )
        if running:
            # Only report "running" if this version is the one being profiled.
            running_version_id = (running.get("result_json") or {}).get("version_id")
            if running_version_id is None or running_version_id == version["id"]:
                return ProfileEnvelope(status="running", job=_job_record(running))

        if profile_rows:
            return ProfileEnvelope(
                status="ready",
                profile=profile_rows[0]["profile_json"],
                profiled_at=profile_rows[0]["created_at"],
            )

        last = await _latest_job(sb, user_id=user.id, dataset_id=dataset_id, job_type="profile")
        if last and last["status"] == "failed":
            return ProfileEnvelope(
                status="failed", job=_job_record(last), error=last.get("error")
            )
        return ProfileEnvelope(status="needs_profiling")
    finally:
        await sb.close()


# =============================================================================
# Cleaning (Phase 3)
# =============================================================================

@router.get("/{dataset_id}/operations", response_model=OperationCatalog)
async def list_operations(
    dataset_id: str,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> OperationCatalog:
    """Return the operations catalog so the toolbox UI can render dynamic forms."""
    try:
        # Verify ownership (so unauthenticated requests can't even probe the catalog).
        await _fetch_owned_dataset(sb, dataset_id, user.id)
        return OperationCatalog(groups=get_catalog())  # type: ignore[arg-type]
    finally:
        await sb.close()


@router.post("/{dataset_id}/clean/preview", response_model=CleanPreviewResponse)
async def clean_preview(
    dataset_id: str,
    req: CleanPreviewRequest,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> CleanPreviewResponse:
    """Dry-run a single step on a sample. Nothing is persisted."""
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _fetch_raw_version(sb, dataset_id)
        if req.step.op not in OP_REGISTRY:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown op: {req.step.op}")

        raw = await sb.storage_download("datasets", version["storage_path"] or ds["storage_path"])
        df_sample, _ = load_dataframe(raw, _version_source_type(version, ds), nrows=req.sample_rows)
        before_sample = df_sample.head(req.show_rows).copy()
        cols_before = [str(c) for c in df_sample.columns]

        try:
            after_df, log_entries = apply_steps(df_sample, [req.step.model_dump()])
        except Exception as exc:  # noqa: BLE001
            return CleanPreviewResponse(
                op=req.step.op,
                columns_before=cols_before,
                columns_after=cols_before,
                sample_before=to_json_safe(before_sample.to_dict(orient="records")),
                sample_after=[],
                error=str(exc),
            )

        # Show the same row indices before & after where possible (so the user
        # can compare cells in place); fall back to head if rows were dropped.
        show_idx = before_sample.index.intersection(after_df.index)[: req.show_rows]
        if len(show_idx) == 0:
            after_show = after_df.head(req.show_rows)
            before_show = before_sample.head(req.show_rows)
        else:
            before_show = before_sample.loc[show_idx]
            after_show = after_df.loc[show_idx]

        return CleanPreviewResponse(
            op=req.step.op,
            summary=log_entries[0].get("summary") if log_entries else None,
            log=log_entries[0] if log_entries else None,
            columns_before=cols_before,
            columns_after=[str(c) for c in after_df.columns],
            sample_before=to_json_safe(before_show.to_dict(orient="records")),
            sample_after=to_json_safe(after_show.to_dict(orient="records")),
        )
    finally:
        await sb.close()


@router.post("/{dataset_id}/clean", response_model=CleanResponse)
async def clean_dataset(
    dataset_id: str,
    req: CleanRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    sb: SupabaseClient = Depends(_get_client),
) -> CleanResponse:
    """Apply the full pipeline, save as a new version, return the diff."""
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _fetch_raw_version(sb, dataset_id)
        if not req.steps:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "no steps to apply")

        # Validate up front so we abort before downloading on bad input.
        unknown = [s.op for s in req.steps if s.op not in OP_REGISTRY]
        if unknown:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"unknown op(s): {sorted(set(unknown))}"
            )

        raw = await sb.storage_download("datasets", version["storage_path"] or ds["storage_path"])
        # Load the WHOLE file for cleaning, bounded by a safety ceiling.
        before_df, truncated = load_dataframe(
            raw, _version_source_type(version, ds), nrows=CLEAN_MAX_ROWS
        )
        if truncated:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"cleaning is capped at {CLEAN_MAX_ROWS} rows; file is larger",
            )

        # Apply steps. If any step raises, we never write anything.
        try:
            after_df, log_entries = apply_steps(before_df, [s.model_dump() for s in req.steps])
        except Exception as exc:  # noqa: BLE001
            log.exception("clean failed for dataset %s", dataset_id)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

        # Compute diff against the *original* (untouched) DataFrame.
        diff = compute_diff(before_df, after_df)

        # Serialize cleaned df to CSV bytes and upload.
        csv_buf = io.BytesIO()
        after_df.to_csv(csv_buf, index=False)
        csv_bytes = csv_buf.getvalue()

        next_no = await _max_version_no(sb, dataset_id) + 1
        storage_path = f"{user.id}/cleaned/{dataset_id}-v{next_no}.csv"
        await sb.storage_upload("datasets", storage_path, csv_bytes, content_type="text/csv")

        # Insert new version row with the full step log.
        created = await sb.table_insert(
            "dataset_versions",
            {
                "dataset_id": dataset_id,
                "version_no": next_no,
                "label": "cleaned",
                "storage_path": storage_path,
                "cleaning_steps": log_entries,
            },
        )
        new_version = created[0]

        # Look up the prior quality score for the FE before/after badge.
        prior_profile = await sb.table_get(
            "data_profiles",
            {
                "dataset_version_id": f"eq.{version['id']}",
                "select": "profile_json",
                "order": "created_at.desc",
                "limit": "1",
            },
        )
        prior_score = None
        if prior_profile:
            prior_score = int(
                ((prior_profile[0]["profile_json"] or {}).get("summary") or {})
                .get("quality_score", 0)
            ) or None

        # Schedule a re-profile of the cleaned version (Phase-2 worker).
        job = await sb.table_insert(
            "analysis_jobs",
            {
                "user_id": user.id,
                "dataset_id": dataset_id,
                "job_type": "profile",
                "status": "queued",
                "result_json": {"version_id": new_version["id"], "reason": "post-clean"},
            },
        )
        reprofile_job_id = job[0]["id"]
        background_tasks.add_task(
            _run_profile_job,
            settings=settings,
            job_id=reprofile_job_id,
            dataset_id=dataset_id,
            version_id=new_version["id"],
            storage_path=storage_path,
            source_type="file_csv",
            update_dataset_summary=False,
        )

        return CleanResponse(
            cleaned_version_id=new_version["id"],
            version_no=next_no,
            storage_path=storage_path,
            diff=CleanDiff.model_validate(diff),
            steps_applied=log_entries,
            reprofile_job_id=reprofile_job_id,
            quality_score_before=prior_score,
        )
    finally:
        await sb.close()


# =============================================================================
# Background worker (Phase 2, with `update_dataset_summary` flag)
# =============================================================================

async def _run_profile_job(
    *,
    settings: Settings,
    job_id: str,
    dataset_id: str,
    version_id: str,
    storage_path: str,
    source_type: str,
    update_dataset_summary: bool = True,
) -> None:
    """Top-level background task. Logs and updates analysis_jobs on every step."""
    sb = SupabaseClient(settings)
    now = lambda: dt.datetime.now(dt.timezone.utc).isoformat()  # noqa: E731
    try:
        await sb.table_update(
            "analysis_jobs",
            {"id": f"eq.{job_id}"},
            {"status": "running", "updated_at": now()},
        )
        raw = await sb.storage_download("datasets", storage_path)
        df, truncated = load_dataframe(raw, source_type)
        profile = profile_dataframe(df, truncated=truncated)

        await sb.table_insert(
            "data_profiles",
            {"dataset_version_id": version_id, "profile_json": profile},
            returning="minimal",
        )
        if update_dataset_summary:
            await sb.table_update(
                "datasets",
                {"id": f"eq.{dataset_id}"},
                {
                    "row_count": int(profile["summary"]["row_count"]),
                    "column_count": int(profile["summary"]["column_count"]),
                    "status": "profiled",
                },
            )
        await sb.table_update(
            "analysis_jobs",
            {"id": f"eq.{job_id}"},
            {
                "status": "succeeded",
                "updated_at": now(),
                "result_json": {
                    "version_id": version_id,
                    "summary": profile["summary"],
                },
            },
        )
        log.info("profile job %s succeeded for dataset %s", job_id, dataset_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("profile job %s failed", job_id)
        try:
            await sb.table_update(
                "analysis_jobs",
                {"id": f"eq.{job_id}"},
                {"status": "failed", "updated_at": now(), "error": str(exc)[:1000]},
            )
            if update_dataset_summary:
                await sb.table_update(
                    "datasets",
                    {"id": f"eq.{dataset_id}"},
                    {"status": "error"},
                )
        except Exception:  # noqa: BLE001
            log.exception("failed to mark profile job %s as failed", job_id)
    finally:
        await sb.close()


# =============================================================================
# Auto-clean (Phase 6 / Part B)
# =============================================================================

_AUTO_CLEAN_EXPLAIN_SYSTEM = (
    "You are a data-cleaning assistant. Given a JSON list of preprocessing "
    "steps with one-line rationales, write a short friendly explanation (2–3 "
    "sentences, plain English) of what the pipeline will do and why. Mention "
    "any notable trade-offs. Don't list every step."
)


@router.post("/{dataset_id}/clean/auto-plan", response_model=AutoPlanResponse)
async def auto_plan(
    dataset_id: str,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    sb: SupabaseClient = Depends(_get_client),
) -> AutoPlanResponse:
    """Propose an ordered cleaning pipeline derived from the profile.

    The plan is deterministic — it never depends on Gemini. We *optionally*
    pass the plan through Gemini for a friendly explanation, but a missing /
    rate-limited model only nulls `explanation`; the plan ships either way.
    """
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _resolve_dashboard_version(sb, dataset_id, version_id)
        profile = await _fetch_or_build_profile(sb, version, _version_source_type(version, ds))

        plan = build_auto_plan(profile)
        summary = plan_summary(plan)

        explanation: str | None = None
        if settings.gemini_api_key and plan:
            try:
                explanation = GeminiClient(settings).generate_text(
                    _AUTO_CLEAN_EXPLAIN_SYSTEM,
                    "Plan steps:\n" + "\n".join(
                        f"- {s['op']} on {s['columns'] or 'all rows'}: {s['rationale']}"
                        for s in plan
                    ),
                )
            except AIUnavailable:
                explanation = None  # Plan still ships fine without it.

        return AutoPlanResponse(
            version_id=version["id"],
            version_label=version["label"],
            steps=[AutoPlanStep(**s) for s in plan],
            summary=summary,
            explanation=explanation,
        )
    finally:
        await sb.close()


# =============================================================================
# Download (Phase 6 / Part A)
# =============================================================================

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str, version_label: str, fmt: str) -> str:
    stem = _SAFE_NAME_RE.sub("_", name.rsplit(".", 1)[0]).strip("_") or "dataset"
    suffix = "cleaned" if version_label == "cleaned" else "raw"
    return f"{stem}-{suffix}.{fmt}"


@router.get("/{dataset_id}/download")
async def download_dataset(
    dataset_id: str,
    version_id: str | None = Query(default=None),
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> StreamingResponse:
    """Stream a dataset version as CSV or XLSX.

    Defaults to the latest cleaned version (raw if no cleaned exists), so a
    cleaning-only user can upload → clean → download without touching the rest
    of the app.
    """
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _resolve_dashboard_version(sb, dataset_id, version_id)
        source_type = _version_source_type(version, ds)

        raw_bytes = await sb.storage_download("datasets", version["storage_path"])
        filename = _safe_filename(ds["name"], version["label"], format)

        if format == "csv":
            if source_type == "file_csv":
                content = raw_bytes  # pass through; matches original encoding
            else:
                df, _ = load_dataframe(raw_bytes, source_type, nrows=None)
                buf = io.BytesIO()
                df.to_csv(buf, index=False)
                content = buf.getvalue()
            media_type = "text/csv; charset=utf-8"
        else:  # xlsx
            df, _ = load_dataframe(raw_bytes, source_type, nrows=None)
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="data", index=False)
            content = buf.getvalue()
            media_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        return StreamingResponse(
            io.BytesIO(content),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(content)),
                "Cache-Control": "no-store",
            },
        )
    finally:
        await sb.close()


# =============================================================================
# Dashboard data (Phase 4)
# =============================================================================

@router.get("/{dataset_id}/chart-suggestions", response_model=ChartSuggestionsResponse)
async def chart_suggestions(
    dataset_id: str,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> ChartSuggestionsResponse:
    """Ranked chart + KPI suggestions for the chosen version (defaults to latest cleaned)."""
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _resolve_dashboard_version(sb, dataset_id, version_id)
        source_type = _version_source_type(version, ds)
        profile = await _fetch_or_build_profile(sb, version, source_type)
        rec = recommend_charts(profile)
        return ChartSuggestionsResponse(
            version_id=version["id"],
            version_label=version["label"],
            kpis=rec["kpis"],
            suggestions=rec["suggestions"],
        )
    finally:
        await sb.close()


@router.post("/{dataset_id}/chart-data", response_model=ChartDataResponse)
async def chart_data(
    dataset_id: str,
    req: ChartDataRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> ChartDataResponse:
    """Compute chart-ready data server-side. Body carries the chart spec (and filters)."""
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _resolve_dashboard_version(sb, dataset_id, version_id)
        source_type = _version_source_type(version, ds)

        raw = await sb.storage_download("datasets", version["storage_path"])
        df, _ = load_dataframe(raw, source_type)
        spec = req.model_dump()
        try:
            payload = build_chart_data(df, spec)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        return ChartDataResponse.model_validate(payload)
    finally:
        await sb.close()


@router.get("/{dataset_id}/filter-options", response_model=FilterOptionsResponse)
async def filter_options(
    dataset_id: str,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> FilterOptionsResponse:
    """Distinct values / min-max ranges for filter controls."""
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _resolve_dashboard_version(sb, dataset_id, version_id)
        source_type = _version_source_type(version, ds)
        raw = await sb.storage_download("datasets", version["storage_path"])
        df, _ = load_dataframe(raw, source_type)
        profile = await _fetch_or_build_profile(sb, version, source_type)
        opts = build_filter_options(df, profile.get("columns"))
        return FilterOptionsResponse(version_id=version["id"], filters=opts["filters"])
    finally:
        await sb.close()
