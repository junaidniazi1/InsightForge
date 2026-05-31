import io
import math

import pandas as pd

from app.services.data_loader import load_dataframe, paginate


def _csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def test_load_csv_basic() -> None:
    df_in = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    df_out, truncated = load_dataframe(_csv_bytes(df_in), "file_csv")
    assert list(df_out.columns) == ["a", "b"]
    assert len(df_out) == 3
    assert truncated is False


def test_paginate_handles_nan() -> None:
    df = pd.DataFrame({"a": [1.0, float("nan"), 3.0], "b": ["x", "y", None]})
    rows = paginate(df, page=1, page_size=10)
    assert rows[0] == {"a": 1.0, "b": "x"}
    # NaN must serialize to None so the JSON response stays valid
    assert rows[1]["a"] is None
    assert rows[2]["b"] is None


def test_paginate_pages() -> None:
    df = pd.DataFrame({"a": list(range(25))})
    page1 = paginate(df, page=1, page_size=10)
    page3 = paginate(df, page=3, page_size=10)
    assert len(page1) == 10 and page1[0]["a"] == 0
    assert len(page3) == 5 and page3[-1]["a"] == 24


def test_no_inf_or_nan_in_output() -> None:
    df = pd.DataFrame({"a": [float("inf"), -float("inf"), float("nan"), 1.5]})
    rows = paginate(df, page=1, page_size=10)
    for r in rows[:3]:
        assert r["a"] is None
    assert rows[3]["a"] == 1.5
    # Sanity: no NaN/inf leaked through
    for r in rows:
        v = r["a"]
        assert v is None or (isinstance(v, float) and not math.isnan(v) and not math.isinf(v))
