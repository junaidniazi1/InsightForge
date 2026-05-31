"""Shared ML prep helpers for clustering, PCA, anomaly, feature importance, modelling.

Two surfaces:
  - `extract_numeric` — for unsupervised tools that need a clean numeric matrix
    after dropping NaN rows; reports how many rows were dropped so the caller
    can warn the user.
  - `prep_features_for_ml` — for supervised tools that have to live with mixed
    dtypes: median-impute numeric, mode-impute + one-hot low-cardinality
    categoricals, drop high-cardinality / datetime columns.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from ._common import WorkbenchError, require_columns, require_min_rows

# Tunables
DEFAULT_MIN_ROWS = 20
DEFAULT_MIN_FEATURES = 2
MAX_CAT_CARDINALITY = 20      # one-hot cap; anything more is dropped
TARGET_CLASS_CARDINALITY = 20  # classification heuristic threshold


def extract_numeric(
    df: pd.DataFrame,
    features: list[str] | None,
    *,
    min_rows: int = DEFAULT_MIN_ROWS,
    min_features: int = DEFAULT_MIN_FEATURES,
    what: str = "this tool",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return (X, meta) where X is a NaN-free numeric DataFrame.

    `meta` carries `{features, rows_before, rows_after, rows_dropped}` so the
    caller can mention it in the interpretation.
    """
    if not features:
        features = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    require_columns(df, features)
    X = df[features].apply(pd.to_numeric, errors="coerce")
    # Drop columns that became all-NaN after coercion.
    X = X.dropna(axis=1, how="all")
    if X.shape[1] < min_features:
        raise WorkbenchError(
            f"{what} needs at least {min_features} numeric feature columns; got {X.shape[1]}.",
            reason="too_few_features",
        )
    rows_before = int(len(X))
    X = X.dropna(axis=0, how="any")
    rows_after = int(len(X))
    if rows_after < min_rows:
        raise WorkbenchError(
            f"{what} needs at least {min_rows} rows after dropping NaN; got {rows_after}.",
            reason="too_few_rows",
        )
    return X.reset_index(drop=True), {
        "features": list(X.columns),
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_dropped": rows_before - rows_after,
    }


def standardize(X: pd.DataFrame) -> np.ndarray:
    """Fit-transform with StandardScaler. Pure helper so callers stay legible."""
    return StandardScaler().fit_transform(X.values)


def pca_2d(X_scaled: np.ndarray) -> np.ndarray:
    """Reduce to 2 components for visualization."""
    n_comp = min(2, X_scaled.shape[1])
    return PCA(n_components=n_comp, random_state=0).fit_transform(X_scaled)


def prep_features_for_ml(
    df: pd.DataFrame,
    target: str,
) -> tuple[pd.DataFrame, list[str]]:
    """Encode + impute for supervised tools. Returns (X, dropped_columns).

    Rules:
      - target column is excluded.
      - numeric columns → median impute.
      - low-cardinality (≤ MAX_CAT_CARDINALITY) categorical / boolean → mode
        impute, then one-hot.
      - high-cardinality categorical, datetime, free-text, id-like → dropped
        with their names appearing in `dropped_columns` so the interpretation
        can mention them.
      - resulting frame is purely numeric (bools cast to int).
    """
    parts: list[pd.DataFrame] = []
    dropped: list[str] = []
    for c in df.columns:
        if c == target:
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            median = s.median()
            if pd.isna(median):
                dropped.append(c)
                continue
            parts.append(s.fillna(median).astype(float).to_frame(c))
        elif pd.api.types.is_datetime64_any_dtype(s):
            dropped.append(c)
        else:
            non_null = s.dropna()
            if non_null.empty:
                dropped.append(c)
                continue
            if non_null.nunique() > MAX_CAT_CARDINALITY:
                dropped.append(c)
                continue
            mode_vals = non_null.mode()
            if mode_vals.empty:
                dropped.append(c)
                continue
            mode = mode_vals.iloc[0]
            s_filled = s.fillna(mode)
            dummies = pd.get_dummies(s_filled, prefix=c, drop_first=False)
            # Convert bools to int.
            dummies = dummies.astype(int)
            parts.append(dummies)
    if not parts:
        raise WorkbenchError(
            "No usable features after encoding — every column is high-cardinality, datetime, or empty.",
            reason="no_features",
        )
    X = pd.concat(parts, axis=1)
    # Drop columns that ended up all-zero (e.g. dummy of single category after mode-fill).
    return X.reset_index(drop=True), dropped


def detect_problem_type(y: pd.Series) -> str:
    """Pick 'regression' or 'classification' from a target series."""
    non_null = y.dropna()
    if non_null.empty:
        raise WorkbenchError("Target column is all null.", reason="empty_target")
    # If the target is numeric AND has high cardinality, treat as regression.
    if pd.api.types.is_numeric_dtype(non_null) and not pd.api.types.is_bool_dtype(non_null):
        if non_null.nunique() > TARGET_CLASS_CARDINALITY:
            return "regression"
    return "classification"


def prepare_supervised(
    df: pd.DataFrame,
    target: str,
    *,
    min_rows: int,
) -> tuple[pd.DataFrame, pd.Series, str, list[str]]:
    """Common path for feature-importance and modeling.

    Returns (X, y, problem_type, dropped_feature_cols).
    """
    if target not in df.columns:
        raise WorkbenchError(
            f"Target column '{target}' not in dataset.",
            reason="missing_target",
        )
    if df[target].notna().sum() == 0:
        raise WorkbenchError(
            f"Target column '{target}' is entirely null.",
            reason="empty_target",
        )
    sub = df[df[target].notna()].reset_index(drop=True)
    require_min_rows(len(sub), minimum=min_rows, what="supervised modelling")
    y = sub[target]
    problem_type = detect_problem_type(y)
    X, dropped = prep_features_for_ml(sub, target)
    # Final alignment (concat may reorder index).
    X = X.reset_index(drop=True)
    return X, y.reset_index(drop=True), problem_type, dropped


__all__ = [
    "DEFAULT_MIN_ROWS",
    "DEFAULT_MIN_FEATURES",
    "MAX_CAT_CARDINALITY",
    "TARGET_CLASS_CARDINALITY",
    "extract_numeric",
    "standardize",
    "pca_2d",
    "prep_features_for_ml",
    "detect_problem_type",
    "prepare_supervised",
]
