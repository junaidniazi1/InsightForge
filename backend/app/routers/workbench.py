"""Phase 7 — Analyst Workbench endpoints.

Every tool resolves to the same dashboard version (latest cleaned else raw),
loads the full DataFrame (capped), runs the tool, and returns
{ result, charts, interpretation }.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ..config import Settings, get_settings
from ..deps import CurrentUser, get_current_user
from ..schemas.workbench import (
    AnomalyRequest,
    ClusteringRequest,
    CorrelationRequest,
    DescribeRequest,
    FeatureImportanceRequest,
    HypothesisRequest,
    ModelRequest,
    PCARequest,
    TestRecommendRequest,
    TimeseriesRequest,
    WorkbenchEnvelope,
)
from ..services.data_loader import load_dataframe
from ..services.workbench._common import WORKBENCH_MAX_ROWS, WorkbenchError
from ..services.workbench.anomaly import run_anomaly
from ..services.workbench.clustering import run_clustering
from ..services.workbench.correlation import run_correlation
from ..services.workbench.describe import run_describe
from ..services.workbench.feature_importance import run_feature_importance
from ..services.workbench.hypothesis import recommend_test, run_hypothesis_test
from ..services.workbench.modeling import (
    get_cached_predictions,
    predictions_csv_bytes,
    run_model,
)
from ..services.workbench.pca import run_pca
from ..services.workbench.timeseries import (
    run_acf_pacf,
    run_decompose,
    run_resample,
    run_stationarity,
)
from ..supabase_client import SupabaseClient
from .datasets import (
    _fetch_or_build_profile,
    _fetch_owned_dataset,
    _resolve_dashboard_version,
    _version_source_type,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["workbench"])


async def _get_client(settings: Settings = Depends(get_settings)) -> SupabaseClient:
    return SupabaseClient(settings)


async def _load_df(
    sb: SupabaseClient,
    dataset_id: str,
    user_id: str,
    version_id: str | None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    ds = await _fetch_owned_dataset(sb, dataset_id, user_id)
    version = await _resolve_dashboard_version(sb, dataset_id, version_id)
    source_type = _version_source_type(version, ds)
    raw = await sb.storage_download("datasets", version["storage_path"])
    df, _ = load_dataframe(raw, source_type, nrows=WORKBENCH_MAX_ROWS)
    return df, ds, version


def _to_400(exc: WorkbenchError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"reason": exc.reason, "message": str(exc)},
    )


# ---------------------------------------------------------------------------
# 1. Describe
# ---------------------------------------------------------------------------

@router.post("/{dataset_id}/workbench/describe", response_model=WorkbenchEnvelope)
async def workbench_describe(
    dataset_id: str,
    req: DescribeRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> WorkbenchEnvelope:
    try:
        df, _, _ = await _load_df(sb, dataset_id, user.id, version_id)
        try:
            out = run_describe(df, req.columns, bins=req.bins)
        except WorkbenchError as exc:
            raise _to_400(exc) from exc
        return WorkbenchEnvelope.model_validate(out)
    finally:
        await sb.close()


# ---------------------------------------------------------------------------
# 2. Correlation
# ---------------------------------------------------------------------------

@router.post("/{dataset_id}/workbench/correlation", response_model=WorkbenchEnvelope)
async def workbench_correlation(
    dataset_id: str,
    req: CorrelationRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> WorkbenchEnvelope:
    try:
        df, _, _ = await _load_df(sb, dataset_id, user.id, version_id)
        try:
            out = run_correlation(df, req.columns, method=req.method)
        except WorkbenchError as exc:
            raise _to_400(exc) from exc
        return WorkbenchEnvelope.model_validate(out)
    finally:
        await sb.close()


# ---------------------------------------------------------------------------
# 3. Hypothesis tests + recommender
# ---------------------------------------------------------------------------

@router.post("/{dataset_id}/workbench/hypothesis", response_model=WorkbenchEnvelope)
async def workbench_hypothesis(
    dataset_id: str,
    req: HypothesisRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> WorkbenchEnvelope:
    try:
        df, _, _ = await _load_df(sb, dataset_id, user.id, version_id)
        try:
            out = run_hypothesis_test(
                df,
                req.test,
                value_col=req.value_col,
                group_col=req.group_col,
                second_col=req.second_col,
                popmean=req.popmean,
            )
        except WorkbenchError as exc:
            raise _to_400(exc) from exc
        return WorkbenchEnvelope.model_validate(out)
    finally:
        await sb.close()


@router.post("/{dataset_id}/workbench/hypothesis/recommend")
async def workbench_hypothesis_recommend(
    dataset_id: str,
    req: TestRecommendRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> dict[str, Any]:
    """Suggest a test from the chosen columns' semantic types."""
    try:
        ds = await _fetch_owned_dataset(sb, dataset_id, user.id)
        version = await _resolve_dashboard_version(sb, dataset_id, version_id)
        source_type = _version_source_type(version, ds)
        profile = await _fetch_or_build_profile(sb, version, source_type)
        return recommend_test(profile.get("columns") or [], req.columns)
    finally:
        await sb.close()


# ---------------------------------------------------------------------------
# 4. Time-series
# ---------------------------------------------------------------------------

@router.post("/{dataset_id}/workbench/timeseries", response_model=WorkbenchEnvelope)
async def workbench_timeseries(
    dataset_id: str,
    req: TimeseriesRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> WorkbenchEnvelope:
    try:
        df, _, _ = await _load_df(sb, dataset_id, user.id, version_id)
        try:
            if req.mode == "resample":
                out = run_resample(
                    df, x=req.x, y=req.y, freq=req.freq, agg=req.agg,
                    rolling_window=req.rolling_window,
                )
            elif req.mode == "decompose":
                out = run_decompose(
                    df, x=req.x, y=req.y, freq=req.freq,
                    period=req.period, model=req.model,
                )
            elif req.mode == "acf_pacf":
                out = run_acf_pacf(df, x=req.x, y=req.y, freq=req.freq, nlags=req.nlags)
            elif req.mode == "stationarity":
                out = run_stationarity(df, x=req.x, y=req.y, freq=req.freq)
            else:  # pragma: no cover - pydantic validates
                raise WorkbenchError(f"unknown timeseries mode: {req.mode}", reason="bad_mode")
        except WorkbenchError as exc:
            raise _to_400(exc) from exc
        return WorkbenchEnvelope.model_validate(out)
    finally:
        await sb.close()


# ---------------------------------------------------------------------------
# 7B — ML toolkit
# ---------------------------------------------------------------------------

@router.post("/{dataset_id}/workbench/clustering", response_model=WorkbenchEnvelope)
async def workbench_clustering(
    dataset_id: str,
    req: ClusteringRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> WorkbenchEnvelope:
    try:
        df, _, _ = await _load_df(sb, dataset_id, user.id, version_id)
        try:
            out = run_clustering(df, req.features, k_max=req.k_max)
        except WorkbenchError as exc:
            raise _to_400(exc) from exc
        return WorkbenchEnvelope.model_validate(out)
    finally:
        await sb.close()


@router.post("/{dataset_id}/workbench/pca", response_model=WorkbenchEnvelope)
async def workbench_pca(
    dataset_id: str,
    req: PCARequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> WorkbenchEnvelope:
    try:
        df, _, _ = await _load_df(sb, dataset_id, user.id, version_id)
        try:
            out = run_pca(df, req.features, n_components=req.n_components)
        except WorkbenchError as exc:
            raise _to_400(exc) from exc
        return WorkbenchEnvelope.model_validate(out)
    finally:
        await sb.close()


@router.post("/{dataset_id}/workbench/anomaly", response_model=WorkbenchEnvelope)
async def workbench_anomaly(
    dataset_id: str,
    req: AnomalyRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> WorkbenchEnvelope:
    try:
        df, _, _ = await _load_df(sb, dataset_id, user.id, version_id)
        try:
            out = run_anomaly(df, req.features, contamination=req.contamination)
        except WorkbenchError as exc:
            raise _to_400(exc) from exc
        return WorkbenchEnvelope.model_validate(out)
    finally:
        await sb.close()


@router.post("/{dataset_id}/workbench/feature-importance", response_model=WorkbenchEnvelope)
async def workbench_feature_importance(
    dataset_id: str,
    req: FeatureImportanceRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> WorkbenchEnvelope:
    try:
        df, _, _ = await _load_df(sb, dataset_id, user.id, version_id)
        try:
            out = run_feature_importance(df, target=req.target)
        except WorkbenchError as exc:
            raise _to_400(exc) from exc
        return WorkbenchEnvelope.model_validate(out)
    finally:
        await sb.close()


@router.post("/{dataset_id}/workbench/model", response_model=WorkbenchEnvelope)
async def workbench_model(
    dataset_id: str,
    req: ModelRequest,
    version_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> WorkbenchEnvelope:
    try:
        df, _, _ = await _load_df(sb, dataset_id, user.id, version_id)
        try:
            out = run_model(df, target=req.target, user_id=user.id, dataset_id=dataset_id)
        except WorkbenchError as exc:
            raise _to_400(exc) from exc
        return WorkbenchEnvelope.model_validate(out)
    finally:
        await sb.close()


@router.get("/{dataset_id}/workbench/model/predictions.csv")
async def workbench_model_predictions(
    dataset_id: str,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
) -> StreamingResponse:
    """Stream the most recent model run's test predictions for this user/dataset."""
    try:
        # Ownership check (also catches typos in dataset_id) but the cache is
        # the source of truth for the bytes.
        await _fetch_owned_dataset(sb, dataset_id, user.id)
        rec = get_cached_predictions(user.id, dataset_id)
        if rec is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"reason": "no_predictions", "message": "Run a model first to download predictions."},
            )
        content, filename = predictions_csv_bytes(rec)
        return StreamingResponse(
            io.BytesIO(content),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(content)),
                "Cache-Control": "no-store",
            },
        )
    finally:
        await sb.close()
