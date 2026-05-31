"""Read CSV/Excel bytes into a pandas DataFrame, with safety caps."""

import io
import math
from typing import Any

import numpy as np
import pandas as pd

# Phase-1 cap: we read the first N rows for preview / profiling so the UI stays
# responsive. Cleaning (Phase 3) needs to load the *whole* file — callers pass
# nrows=None for that. Excel is fully loaded by openpyxl regardless.
MAX_PREVIEW_SCAN_ROWS = 100_000
# Safety ceiling so a malicious upload can't OOM us during cleaning.
CLEAN_MAX_ROWS = 2_000_000


def load_dataframe(
    raw: bytes,
    source_type: str,
    *,
    nrows: int | None = MAX_PREVIEW_SCAN_ROWS,
) -> tuple[pd.DataFrame, bool]:
    """Return (df, truncated).

    - `nrows` caps rows read; pass `None` to load everything (cleaning path).
    - `truncated` is True if we hit the cap.
    """
    if source_type == "file_csv":
        if nrows is None:
            df = pd.read_csv(io.BytesIO(raw), low_memory=False)
            return df, False
        df = pd.read_csv(io.BytesIO(raw), nrows=nrows + 1, low_memory=False)
        truncated = len(df) > nrows
        if truncated:
            df = df.head(nrows)
        return df, truncated
    elif source_type == "file_excel":
        df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
        if nrows is not None and len(df) > nrows:
            return df.head(nrows), True
        return df, False
    else:
        raise ValueError(f"unsupported source_type: {source_type}")


def _json_safe(v: Any) -> Any:
    """Make a single cell JSON-serializable (NaN/NaT → None, numpy scalars → py)."""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if v is pd.NaT:
        return None
    return v


def to_json_safe(obj: Any) -> Any:
    """Recursively make a nested structure JSON-safe.

    Used for the profile JSON, which contains dicts of dicts of pandas/numpy
    scalars. Leaves are normalised with `_json_safe`.
    """
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return [to_json_safe(v) for v in obj]
    return _json_safe(obj)


def paginate(df: pd.DataFrame, page: int, page_size: int) -> list[dict[str, Any]]:
    start = (page - 1) * page_size
    end = start + page_size
    chunk = df.iloc[start:end]
    records: list[dict[str, Any]] = []
    for row in chunk.to_dict(orient="records"):
        records.append({k: _json_safe(v) for k, v in row.items()})
    return records
