from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FilterClause(BaseModel):
    column: str
    type: Literal["in", "range"] = "in"
    values: list[Any] | None = None
    min: float | str | None = None
    max: float | str | None = None


class ChartSpec(BaseModel):
    chart_type: str
    encoding: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    bins: int | None = None
    top_n: int | None = None
    filters: list[FilterClause] = Field(default_factory=list)


class Suggestion(BaseModel):
    chart_type: str
    engine: str
    title: str
    encoding: dict[str, Any]
    rationale: str
    score: float
    bins: int | None = None
    top_n: int | None = None


class ChartSuggestionsResponse(BaseModel):
    version_id: str
    version_label: str
    kpis: list[Suggestion]
    suggestions: list[Suggestion]


class ChartDataRequest(BaseModel):
    chart_type: str
    encoding: dict[str, Any] = Field(default_factory=dict)
    bins: int | None = None
    top_n: int | None = None
    filters: list[FilterClause] = Field(default_factory=list)


class ChartDataResponse(BaseModel):
    chart_type: str
    engine: str
    data: dict[str, Any]
    meta: dict[str, Any] = Field(default_factory=dict)


class FilterOption(BaseModel):
    column: str
    kind: Literal["categorical", "numeric_range", "datetime_range"]
    values: list[str] | None = None
    min: float | str | None = None
    max: float | str | None = None


class FilterOptionsResponse(BaseModel):
    version_id: str
    filters: list[FilterOption]


# ----------------- Dashboards -----------------

class DashboardChartIn(BaseModel):
    chart_type: str
    config: dict[str, Any]
    position: int = 0


class DashboardCreate(BaseModel):
    dataset_id: str
    name: str
    layout: dict[str, Any] = Field(default_factory=dict)
    charts: list[DashboardChartIn] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    name: str | None = None
    layout: dict[str, Any] | None = None
    charts: list[DashboardChartIn] | None = None


class DashboardChartOut(BaseModel):
    id: str
    dashboard_id: str
    chart_type: str
    config: dict[str, Any]
    position: int


class DashboardOut(BaseModel):
    id: str
    user_id: str
    dataset_id: str
    name: str
    layout: dict[str, Any]
    created_at: str
    charts: list[DashboardChartOut] = Field(default_factory=list)


class DashboardListItem(BaseModel):
    id: str
    name: str
    dataset_id: str
    layout: dict[str, Any]
    created_at: str
    chart_count: int
