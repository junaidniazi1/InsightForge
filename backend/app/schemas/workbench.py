"""Workbench request / response models.

All endpoints follow the same envelope: { result, charts, interpretation }.
Charts are full Phase-4 payloads so the frontend can pass them directly to the
`<Chart>` router without a second backend round-trip.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared response envelope
# ---------------------------------------------------------------------------

class WorkbenchChart(BaseModel):
    title: str
    spec: dict[str, Any]
    data: dict[str, Any]


class WorkbenchEnvelope(BaseModel):
    result: dict[str, Any]
    charts: list[WorkbenchChart] = Field(default_factory=list)
    interpretation: str = ""


# ---------------------------------------------------------------------------
# Describe
# ---------------------------------------------------------------------------

class DescribeRequest(BaseModel):
    columns: list[str]
    bins: int = Field(default=30, ge=5, le=200)


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------

class CorrelationRequest(BaseModel):
    columns: list[str] = Field(default_factory=list)
    method: Literal["pearson", "spearman", "kendall"] = "pearson"


# ---------------------------------------------------------------------------
# Hypothesis tests
# ---------------------------------------------------------------------------

class HypothesisRequest(BaseModel):
    test: Literal["ttest_one", "ttest_two", "anova", "chi_square", "mann_whitney"]
    value_col: str | None = None
    group_col: str | None = None
    second_col: str | None = None
    popmean: float | None = None


class TestRecommendRequest(BaseModel):
    columns: list[str]


# ---------------------------------------------------------------------------
# Time-series
# ---------------------------------------------------------------------------

Frequency = Literal["D", "W", "ME", "QE", "YE"]
AggKind = Literal["mean", "sum", "min", "max", "median"]


class TimeseriesRequest(BaseModel):
    mode: Literal["resample", "decompose", "acf_pacf", "stationarity"] = "resample"
    x: str
    y: str
    freq: Frequency = "ME"
    agg: AggKind = "mean"
    rolling_window: int | None = None
    period: int | None = None
    model: Literal["additive", "multiplicative"] = "additive"
    nlags: int = 30


# ---------------------------------------------------------------------------
# 7B — ML toolkit
# ---------------------------------------------------------------------------

class ClusteringRequest(BaseModel):
    features: list[str] = Field(default_factory=list)
    k_max: int = Field(default=8, ge=2, le=12)


class PCARequest(BaseModel):
    features: list[str] = Field(default_factory=list)
    n_components: int = Field(default=2, ge=2, le=12)


class AnomalyRequest(BaseModel):
    features: list[str] = Field(default_factory=list)
    contamination: float = Field(default=0.05, gt=0.0, le=0.5)


class FeatureImportanceRequest(BaseModel):
    target: str


class ModelRequest(BaseModel):
    target: str
