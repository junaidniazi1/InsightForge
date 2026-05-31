from typing import Any

from pydantic import BaseModel


class PreviewResponse(BaseModel):
    dataset_id: str
    name: str
    source_type: str
    columns: list[str]
    rows: list[dict[str, Any]]
    page: int
    page_size: int
    total_rows: int | None  # None for very large files we didn't fully count
    truncated: bool         # True if we capped row scanning
