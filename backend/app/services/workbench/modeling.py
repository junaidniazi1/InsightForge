"""Baseline predictive modelling (Phase 7B, tool 9).

Auto-detects regression vs classification. Trains two baselines side-by-side
(linear + RF for regression, logistic + RF for classification), reports
metrics, and caches the test-set predictions in memory so the user can
download them via the GET .../predictions.csv endpoint.
"""

from __future__ import annotations

import io
import threading
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from ._common import WorkbenchError, chart, envelope
from ._ml import prepare_supervised

MIN_ROWS_FOR_MODELING = 30
SMALL_DATASET_WARN = 100
RANDOM_STATE = 0
TEST_SIZE = 0.2
MAX_PREDICTION_ROWS = 2000


# ---------------------------------------------------------------------------
# Predictions cache — module-level dict keyed by (user_id, dataset_id).
# Locked so concurrent runs don't race.
# ---------------------------------------------------------------------------

_PREDICTIONS_LOCK = threading.Lock()
_PREDICTIONS: dict[tuple[str, str], dict[str, Any]] = {}


def cache_predictions(user_id: str, dataset_id: str, table: pd.DataFrame, *, target: str, problem: str) -> None:
    with _PREDICTIONS_LOCK:
        _PREDICTIONS[(user_id, dataset_id)] = {
            "table": table,
            "target": target,
            "problem": problem,
        }


def get_cached_predictions(user_id: str, dataset_id: str) -> dict[str, Any] | None:
    with _PREDICTIONS_LOCK:
        return _PREDICTIONS.get((user_id, dataset_id))


def predictions_csv_bytes(rec: dict[str, Any]) -> tuple[bytes, str]:
    buf = io.BytesIO()
    rec["table"].to_csv(buf, index=False)
    return buf.getvalue(), f"predictions-{rec['target']}.csv"


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_model(
    df: pd.DataFrame,
    *,
    target: str,
    user_id: str,
    dataset_id: str,
) -> dict[str, Any]:
    X, y, problem, dropped = prepare_supervised(df, target, min_rows=MIN_ROWS_FOR_MODELING)

    if problem == "classification":
        return _run_classification(X, y, target, dropped, user_id, dataset_id)
    return _run_regression(X, y, target, dropped, user_id, dataset_id)


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------

def _run_regression(
    X: pd.DataFrame,
    y: pd.Series,
    target: str,
    dropped: list[str],
    user_id: str,
    dataset_id: str,
) -> dict[str, Any]:
    y_vals = pd.to_numeric(y, errors="coerce")
    mask = y_vals.notna()
    X = X.loc[mask].reset_index(drop=True)
    y_vals = y_vals.loc[mask].reset_index(drop=True)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_vals, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )

    lin = LinearRegression()
    lin.fit(X_train, y_train)
    lin_pred = lin.predict(X_test)

    rf = RandomForestRegressor(n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1)
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)

    def _metrics(name: str, pred: np.ndarray) -> dict[str, Any]:
        rmse = float(np.sqrt(mean_squared_error(y_test, pred)))
        return {
            "model": name,
            "r2": float(r2_score(y_test, pred)),
            "rmse": rmse,
            "mae": float(mean_absolute_error(y_test, pred)),
        }

    metrics = [_metrics("LinearRegression", lin_pred), _metrics("RandomForestRegressor", rf_pred)]
    best = max(metrics, key=lambda m: m["r2"])
    best_pred = rf_pred if best["model"].startswith("Random") else lin_pred

    # Predictions table (capped) for CSV download.
    preds_table = pd.DataFrame({
        "row_index": X_test.index.to_numpy(),
        "y_true": y_test.values,
        "y_pred": best_pred,
        "model": best["model"],
    }).head(MAX_PREDICTION_ROWS).reset_index(drop=True)
    cache_predictions(user_id, dataset_id, preds_table, target=target, problem="regression")

    # Predicted-vs-actual scatter for the best model (sample if huge).
    n = len(y_test)
    idx = np.arange(n)
    if n > 5000:
        idx = np.random.default_rng(0).choice(n, 5000, replace=False)
    diag = chart(
        title=f"Predicted vs Actual ({best['model']})",
        chart_type="scatter",
        encoding={"x": "actual", "y": "predicted"},
        data={
            "x": [float(y_test.iloc[int(i)]) for i in idx],
            "y": [float(best_pred[int(i)]) for i in idx],
            "n_rows": int(n),
            "shown": int(len(idx)),
            "sampled": bool(n > 5000),
        },
        presentation={"x_label": f"actual {target}", "y_label": f"predicted {target}"},
    )

    importances = sorted(
        zip(X.columns.tolist(), rf.feature_importances_.tolist()),
        key=lambda kv: kv[1], reverse=True,
    )[:20]
    importances_chart = chart(
        title=f"Top features (RandomForest)",
        chart_type="bar",
        encoding={"x": "feature", "y": "importance"},
        data={
            "categories": [k for k, _ in importances],
            "series": [{"name": "importance", "values": [float(v) for _, v in importances]}],
        },
    )

    warnings: list[str] = []
    if len(X) < SMALL_DATASET_WARN:
        warnings.append(f"Small dataset ({len(X)} rows) — metrics may be unstable.")
    interp = (
        f"Best model: **{best['model']}** "
        f"(R² = {best['r2']:.3f}, RMSE = {best['rmse']:.3g}, MAE = {best['mae']:.3g}). "
        + (
            "Excellent fit." if best["r2"] >= 0.9 else
            "Good fit." if best["r2"] >= 0.7 else
            "Moderate fit — consider feature engineering." if best["r2"] >= 0.3 else
            "Poor fit — the chosen features don't explain `" + target + "` well."
        )
    )
    if warnings:
        interp += " " + " ".join(warnings)
    if dropped:
        interp += f" {len(dropped)} feature column(s) were dropped (high-cardinality / datetime / empty)."

    return envelope(
        result={
            "target": target,
            "problem_type": "regression",
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
            "metrics": metrics,
            "best_model": best["model"],
            "feature_importances": [
                {"feature": k, "importance": float(v)} for k, v in importances
            ],
            "predictions_count": int(len(preds_table)),
            "dropped_features": dropped,
            "warnings": warnings,
        },
        charts=[diag, importances_chart],
        interpretation=interp,
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _run_classification(
    X: pd.DataFrame,
    y: pd.Series,
    target: str,
    dropped: list[str],
    user_id: str,
    dataset_id: str,
) -> dict[str, Any]:
    # Encode target to ints.
    raw_classes = y.astype(str)
    encoder = LabelEncoder()
    y_enc = encoder.fit_transform(raw_classes)
    classes = encoder.classes_.tolist()
    n_classes = len(classes)
    if n_classes < 2:
        raise WorkbenchError(
            f"Classification needs at least 2 distinct target classes; got {n_classes}.",
            reason="too_few_classes",
        )

    # Stratify only if every class has ≥ 2 members.
    counts = pd.Series(y_enc).value_counts()
    stratify = y_enc if (counts >= 2).all() and len(X) * TEST_SIZE >= n_classes else None

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=stratify
    )

    logreg = LogisticRegression(max_iter=2000, n_jobs=-1, random_state=RANDOM_STATE)
    logreg.fit(X_train, y_train)
    log_pred = logreg.predict(X_test)

    rf = RandomForestClassifier(
        n_estimators=200,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        class_weight="balanced" if (counts.min() / counts.max() < 0.5) else None,
    )
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)

    def _metrics(name: str, pred: np.ndarray) -> dict[str, Any]:
        return {
            "model": name,
            "accuracy": float(accuracy_score(y_test, pred)),
            "precision_macro": float(precision_score(y_test, pred, average="macro", zero_division=0)),
            "recall_macro": float(recall_score(y_test, pred, average="macro", zero_division=0)),
            "f1_macro": float(f1_score(y_test, pred, average="macro", zero_division=0)),
        }

    metrics = [_metrics("LogisticRegression", log_pred), _metrics("RandomForestClassifier", rf_pred)]
    best = max(metrics, key=lambda m: m["f1_macro"])
    best_pred = rf_pred if best["model"].startswith("Random") else log_pred
    best_pred_labels = encoder.inverse_transform(best_pred)
    cm = confusion_matrix(y_test, best_pred, labels=list(range(n_classes)))

    # Predictions cache.
    preds_table = pd.DataFrame({
        "row_index": X_test.index.to_numpy(),
        "y_true": encoder.inverse_transform(y_test),
        "y_pred": best_pred_labels,
        "model": best["model"],
    }).head(MAX_PREDICTION_ROWS).reset_index(drop=True)
    cache_predictions(user_id, dataset_id, preds_table, target=target, problem="classification")

    # Confusion-matrix heatmap.
    cm_chart = chart(
        title=f"Confusion matrix ({best['model']})",
        chart_type="heatmap",
        encoding={"columns": [str(c) for c in classes]},
        data={
            "columns": [str(c) for c in classes],
            "values": [[int(v) for v in row] for row in cm.tolist()],
        },
    )

    importances = sorted(
        zip(X.columns.tolist(), rf.feature_importances_.tolist()),
        key=lambda kv: kv[1], reverse=True,
    )[:20]
    importances_chart = chart(
        title="Top features (RandomForest)",
        chart_type="bar",
        encoding={"x": "feature", "y": "importance"},
        data={
            "categories": [k for k, _ in importances],
            "series": [{"name": "importance", "values": [float(v) for _, v in importances]}],
        },
    )

    warnings: list[str] = []
    if len(X) < SMALL_DATASET_WARN:
        warnings.append(f"Small dataset ({len(X)} rows) — metrics may be unstable.")
    if counts.min() / counts.max() < 0.2:
        warnings.append(
            f"Severe class imbalance (min/max class ratio = {counts.min() / counts.max():.2f})."
        )

    interp = (
        f"Best model: **{best['model']}** "
        f"(accuracy = {best['accuracy']:.3f}, macro-F1 = {best['f1_macro']:.3f} "
        f"across {n_classes} classes). "
        + (
            "Excellent separability." if best["accuracy"] >= 0.9 else
            "Good separability." if best["accuracy"] >= 0.75 else
            "Moderate — consider more features or a stronger model." if best["accuracy"] >= 0.55 else
            "Weak — the chosen features don't separate the classes well."
        )
    )
    if warnings:
        interp += " " + " ".join(warnings)
    if dropped:
        interp += f" {len(dropped)} feature column(s) were dropped (high-cardinality / datetime / empty)."

    return envelope(
        result={
            "target": target,
            "problem_type": "classification",
            "classes": [str(c) for c in classes],
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
            "metrics": metrics,
            "best_model": best["model"],
            "confusion_matrix": [[int(v) for v in row] for row in cm.tolist()],
            "feature_importances": [
                {"feature": k, "importance": float(v)} for k, v in importances
            ],
            "predictions_count": int(len(preds_table)),
            "dropped_features": dropped,
            "warnings": warnings,
        },
        charts=[cm_chart, importances_chart],
        interpretation=interp,
    )


__all__ = ["run_model", "cache_predictions", "get_cached_predictions", "predictions_csv_bytes"]
