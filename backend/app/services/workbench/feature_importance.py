"""Random-Forest feature importance (Phase 7B, tool 8).

Auto-selects regressor vs classifier from the target's semantic type. Encodes
and imputes features via `_ml.prepare_supervised`. Reports OOB score so the
user knows whether to trust the ranking.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import LabelEncoder

from ._common import chart, envelope, require_min_rows
from ._ml import prepare_supervised

TOP_IMPORTANCES = 20
RANDOM_STATE = 0
MIN_ROWS = 30


def _oob_verdict(oob: float, problem_type: str) -> str:
    if problem_type == "regression":
        if oob >= 0.7:
            return "Strong signal — the importance ranking is reliable."
        if oob >= 0.3:
            return "Reasonable signal — the ranking is usable but not definitive."
        return "Weak signal — the ranking is suggestive at best."
    # Classification thresholds (oob score = accuracy).
    if oob >= 0.85:
        return "Strong signal — the importance ranking is reliable."
    if oob >= 0.65:
        return "Reasonable signal — the ranking is usable but not definitive."
    return "Weak signal — the ranking is suggestive at best."


def run_feature_importance(
    df: pd.DataFrame,
    *,
    target: str,
) -> dict[str, Any]:
    X, y, problem_type, dropped = prepare_supervised(df, target, min_rows=MIN_ROWS)
    require_min_rows(len(X), minimum=MIN_ROWS, what="feature importance")

    if problem_type == "classification":
        # Encode non-numeric targets to ints.
        if not pd.api.types.is_numeric_dtype(y):
            y_enc = LabelEncoder().fit_transform(y.astype(str))
        else:
            y_enc = y.astype(int).to_numpy()
        model = RandomForestClassifier(
            n_estimators=200,
            random_state=RANDOM_STATE,
            oob_score=True,
            bootstrap=True,
            n_jobs=-1,
        )
        model.fit(X, y_enc)
    else:
        y_enc = pd.to_numeric(y, errors="coerce").to_numpy()
        model = RandomForestRegressor(
            n_estimators=200,
            random_state=RANDOM_STATE,
            oob_score=True,
            bootstrap=True,
            n_jobs=-1,
        )
        model.fit(X, y_enc)

    oob = float(getattr(model, "oob_score_", float("nan")))
    importances = list(zip(X.columns.tolist(), model.feature_importances_.tolist()))
    importances.sort(key=lambda kv: kv[1], reverse=True)
    top = importances[:TOP_IMPORTANCES]

    bar = chart(
        title=f"Top features driving `{target}`",
        chart_type="bar",
        encoding={"x": "feature", "y": "importance"},
        data={
            "categories": [k for k, _ in top],
            "series": [{"name": "importance", "values": [float(v) for k, v in top]}],
        },
        presentation={"x_label": "feature", "y_label": "importance"},
    )

    interp = (
        f"Top drivers of `{target}` are "
        + ", ".join(f"`{k}` ({v:.3f})" for k, v in top[:3])
        + f". Model OOB score: {oob:.3f} — {_oob_verdict(oob, problem_type)}"
    )
    if dropped:
        interp += f" {len(dropped)} column(s) were dropped from features (high-cardinality / datetime / empty)."

    return envelope(
        result={
            "target": target,
            "problem_type": problem_type,
            "oob_score": oob,
            "feature_importances": [{"feature": k, "importance": float(v)} for k, v in importances],
            "top_n": TOP_IMPORTANCES,
            "dropped_features": dropped,
            "n_rows_used": int(len(X)),
            "n_features_used": int(X.shape[1]),
        },
        charts=[bar],
        interpretation=interp,
    )


__all__ = ["run_feature_importance"]
