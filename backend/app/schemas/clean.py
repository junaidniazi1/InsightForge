from typing import Any

from pydantic import BaseModel, Field


class CleanStep(BaseModel):
    op: str
    columns: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


class OperationCatalogItem(BaseModel):
    id: str
    label: str
    description: str
    applies_to: str
    params: list[dict[str, Any]] = Field(default_factory=list)


class OperationCatalog(BaseModel):
    groups: dict[str, list[OperationCatalogItem]]


class CleanPreviewRequest(BaseModel):
    step: CleanStep
    sample_rows: int = Field(default=2000, ge=10, le=20000)
    show_rows: int = Field(default=5, ge=1, le=50)


class CleanPreviewResponse(BaseModel):
    op: str
    summary: str | None = None
    log: dict[str, Any] | None = None
    columns_before: list[str]
    columns_after: list[str]
    sample_before: list[dict[str, Any]]
    sample_after: list[dict[str, Any]]
    error: str | None = None


class NullCountDiff(BaseModel):
    before: int
    after: int


class ChangedRow(BaseModel):
    index: int
    before: dict[str, Any]
    after: dict[str, Any]


class CleanDiff(BaseModel):
    rows_before: int
    rows_after: int
    columns_before: int
    columns_after: int
    duplicates_before: int
    duplicates_after: int
    columns_added: list[str]
    columns_dropped: list[str]
    null_counts: dict[str, NullCountDiff]
    changed_rows_sample: list[ChangedRow]


class CleanRequest(BaseModel):
    steps: list[CleanStep]


class CleanResponse(BaseModel):
    cleaned_version_id: str
    version_no: int
    storage_path: str
    diff: CleanDiff
    steps_applied: list[dict[str, Any]]
    reprofile_job_id: str | None = None
    quality_score_before: int | None = None


# Phase 6 — auto-clean agent
class AutoPlanStep(BaseModel):
    op: str
    columns: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str


class AutoPlanResponse(BaseModel):
    version_id: str
    version_label: str
    steps: list[AutoPlanStep]
    summary: str
    # Optional friendly LLM explanation. None when Gemini isn't configured or
    # the call failed — the plan itself is always present.
    explanation: str | None = None
