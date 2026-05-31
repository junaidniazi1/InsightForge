from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SummaryResponse(BaseModel):
    version_id: str
    version_label: str
    text: str
    created_at: str | None = None
    cached: bool = False


class StoryResponse(SummaryResponse):
    pass


class Finding(BaseModel):
    title: str
    detail: str
    severity: Literal["info", "notable", "concern"] = "info"
    columns: list[str] | None = None


class SuggestedAnalysis(BaseModel):
    label: str
    question: str | None = None


class InsightsResponse(BaseModel):
    version_id: str
    version_label: str
    findings: list[Finding]
    suggested_analyses: list[SuggestedAnalysis]
    created_at: str | None = None
    cached: bool = False


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    version_id: str | None = None


class ResultTable(BaseModel):
    name: str | None = None
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool = False
    row_count: int = 0


class AskResponse(BaseModel):
    version_id: str
    version_label: str
    question: str
    answer: str
    analysis_spec: dict[str, Any]
    result_table: ResultTable
    suggested_chart: dict[str, Any] | None = None


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str
    # Optional structured payload assistants persist alongside their answer.
    payload: dict[str, Any] | None = None


class ConversationResponse(BaseModel):
    dataset_id: str
    turns: list[ConversationTurn]
