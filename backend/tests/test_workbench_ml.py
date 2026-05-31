"""Phase 7B — ML toolkit tests."""

from __future__ import annotations

import csv
import io
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app.services.workbench._common import WorkbenchError
from app.services.workbench.anomaly import run_anomaly
from app.services.workbench.clustering import run_clustering
from app.services.workbench.feature_importance import run_feature_importance
from app.services.workbench.modeling import (
    cache_predictions,
    get_cached_predictions,
    predictions_csv_bytes,
    run_model,
)
from app.services.workbench.pca import run_pca


# ===========================================================================
# Clustering
# ===========================================================================

def _three_blobs(n_per: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    blobs = []
    for cx, cy in [(0, 0), (10, 10), (0, 10)]:
        blobs.append(np.column_stack([
            rng.normal(cx, 0.4, n_per),
            rng.normal(cy, 0.4, n_per),
        ]))
    data = np.vstack(blobs)
    return pd.DataFrame(data, columns=["x", "y"])


def test_clustering_recovers_three_well_separated_blobs() -> None:
    df = _three_blobs()
    out = run_clustering(df, ["x", "y"], k_max=8)
    # Auto-k should land on ~3.
    assert 2 <= out["result"]["best_k"] <= 4
    # Silhouette is strong on well-separated blobs.
    assert out["result"]["best_silhouette"] > 0.5
    # Elbow curve length matches the k-range.
    assert len(out["result"]["inertias"]) == len(out["result"]["ks"])


def test_clustering_emits_scores_and_pca_charts() -> None:
    df = _three_blobs()
    out = run_clustering(df, ["x", "y"], k_max=6)
    types = [c["spec"]["chart_type"] for c in out["charts"]]
    assert "line" in types        # elbow + silhouette
    assert "scatter" in types     # PCA projection


def test_clustering_rejects_too_few_features() -> None:
    df = pd.DataFrame({"only_one": list(range(50))})
    with pytest.raises(WorkbenchError) as ei:
        run_clustering(df, ["only_one"])
    assert ei.value.reason in ("too_few_features", "missing_columns")


# ===========================================================================
# PCA
# ===========================================================================

def test_pca_pc1_captures_almost_all_variance_for_correlated_features() -> None:
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1, 300)
    noise = lambda: rng.normal(0, 0.02, 300)
    df = pd.DataFrame({
        "a": base + noise(),
        "b": 2 * base + noise(),
        "c": -base + noise(),
    })
    out = run_pca(df, ["a", "b", "c"], n_components=3)
    evr = out["result"]["explained_variance_ratio"]
    assert evr[0] > 0.95
    # PC1's top loadings should include the correlated set.
    top_features = [l["feature"] for l in out["result"]["components"][0]["loadings"]]
    assert {"a", "b", "c"} & set(top_features)


def test_pca_reports_n_components_for_90pct() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        f"c_{i}": rng.normal(0, 1, 200) for i in range(5)
    })
    out = run_pca(df, list(df.columns), n_components=5)
    assert 1 <= out["result"]["n_for_90pct"] <= 5


def test_pca_rejects_too_few_numeric_features() -> None:
    df = pd.DataFrame({"text": ["a", "b", "c"] * 20})
    with pytest.raises(WorkbenchError) as ei:
        run_pca(df, ["text"])
    assert ei.value.reason in ("too_few_features", "missing_columns")


def test_pca_emits_scree_and_projection_charts() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({f"x{i}": rng.normal(0, 1, 100) for i in range(4)})
    out = run_pca(df, list(df.columns))
    types = [c["spec"]["chart_type"] for c in out["charts"]]
    assert "bar" in types        # scree
    assert "scatter" in types    # projection


# ===========================================================================
# Anomaly detection
# ===========================================================================

def test_anomaly_flags_injected_outliers() -> None:
    rng = np.random.default_rng(0)
    cloud = rng.normal(0, 1, (300, 2))
    outliers = np.array([[20.0, 20.0], [-20.0, 20.0], [20.0, -20.0]])
    df = pd.DataFrame(np.vstack([cloud, outliers]), columns=["x", "y"])
    out = run_anomaly(df, ["x", "y"], contamination=0.02)
    flagged = {r["__index"] for r in out["result"]["flagged_rows"]}
    # Injected points live at the end of the frame.
    injected_indices = {300, 301, 302}
    assert injected_indices.issubset(flagged)


def test_anomaly_count_is_close_to_contamination_times_n() -> None:
    rng = np.random.default_rng(0)
    n = 500
    df = pd.DataFrame({"x": rng.normal(0, 1, n), "y": rng.normal(0, 1, n)})
    out = run_anomaly(df, ["x", "y"], contamination=0.1)
    flagged = out["result"]["flagged_count"]
    # Allow some slack — IsolationForest is approximate.
    assert 0.5 * 0.1 * n <= flagged <= 1.6 * 0.1 * n


def test_anomaly_emits_histogram_and_scatter() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"x": rng.normal(0, 1, 200), "y": rng.normal(0, 1, 200)})
    out = run_anomaly(df, ["x", "y"])
    types = [c["spec"]["chart_type"] for c in out["charts"]]
    assert "histogram" in types
    assert "scatter" in types


# ===========================================================================
# Feature importance
# ===========================================================================

def test_feature_importance_ranks_true_driver_first_regression() -> None:
    rng = np.random.default_rng(0)
    n = 400
    a = rng.normal(0, 1, n)
    df = pd.DataFrame({
        "a": a,
        "b": rng.normal(0, 1, n),    # noise
        "c": rng.normal(0, 1, n),    # noise
        "y": 3 * a + rng.normal(0, 0.1, n),
    })
    out = run_feature_importance(df, target="y")
    ranked = out["result"]["feature_importances"]
    assert ranked[0]["feature"] == "a"
    assert out["result"]["problem_type"] == "regression"
    # OOB should be high since `y` is almost-perfectly `3*a`.
    assert out["result"]["oob_score"] > 0.85


def test_feature_importance_classification_ranks_true_driver() -> None:
    rng = np.random.default_rng(0)
    n = 400
    a = rng.normal(0, 1, n)
    df = pd.DataFrame({
        "a": a,
        "b": rng.normal(0, 1, n),
        "c": rng.normal(0, 1, n),
        "label": (a > 0).astype(int),  # only depends on `a`
    })
    out = run_feature_importance(df, target="label")
    assert out["result"]["feature_importances"][0]["feature"] == "a"
    assert out["result"]["problem_type"] == "classification"


def test_feature_importance_rejects_missing_target() -> None:
    df = pd.DataFrame({"a": list(range(60))})
    with pytest.raises(WorkbenchError) as ei:
        run_feature_importance(df, target="missing")
    assert ei.value.reason == "missing_target"


# ===========================================================================
# Modeling — regression
# ===========================================================================

def test_modeling_regression_high_r2_on_linear_relationship() -> None:
    rng = np.random.default_rng(0)
    n = 300
    a = rng.normal(0, 1, n)
    b = rng.normal(0, 1, n)
    df = pd.DataFrame({
        "a": a,
        "b": b,
        "y": 2 * a + 3 * b + rng.normal(0, 0.05, n),
    })
    out = run_model(df, target="y", user_id="u1", dataset_id="d1")
    assert out["result"]["problem_type"] == "regression"
    metrics = {m["model"]: m for m in out["result"]["metrics"]}
    assert metrics["LinearRegression"]["r2"] > 0.9
    # Predicted-vs-actual scatter is emitted.
    chart_types = [c["spec"]["chart_type"] for c in out["charts"]]
    assert "scatter" in chart_types


def test_modeling_classification_high_accuracy_on_separable_classes() -> None:
    rng = np.random.default_rng(0)
    n = 400
    a = np.concatenate([rng.normal(-3, 0.5, n), rng.normal(3, 0.5, n)])
    b = np.concatenate([rng.normal(-3, 0.5, n), rng.normal(3, 0.5, n)])
    label = np.array(["A"] * n + ["B"] * n)
    df = pd.DataFrame({"a": a, "b": b, "label": label})
    out = run_model(df, target="label", user_id="u1", dataset_id="d2")
    assert out["result"]["problem_type"] == "classification"
    best = next(m for m in out["result"]["metrics"] if m["model"] == out["result"]["best_model"])
    assert best["accuracy"] > 0.9
    # Confusion matrix is diagonal-heavy.
    cm = out["result"]["confusion_matrix"]
    diag = sum(cm[i][i] for i in range(len(cm)))
    total = sum(sum(row) for row in cm)
    assert diag / total > 0.9
    # Heatmap chart present.
    types = [c["spec"]["chart_type"] for c in out["charts"]]
    assert "heatmap" in types


def test_modeling_caches_predictions_and_csv_is_non_empty() -> None:
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({
        "a": rng.normal(0, 1, n),
        "y": rng.normal(0, 1, n),
    })
    run_model(df, target="y", user_id="user-csv", dataset_id="ds-csv")
    rec = get_cached_predictions("user-csv", "ds-csv")
    assert rec is not None
    assert not rec["table"].empty
    content, filename = predictions_csv_bytes(rec)
    assert content.startswith(b"row_index")
    assert filename.endswith(".csv")
    # Parses as CSV.
    rows = list(csv.reader(io.StringIO(content.decode())))
    assert len(rows) >= 2  # header + at least one data row


def test_modeling_rejects_tiny_dataset() -> None:
    df = pd.DataFrame({"a": [1, 2, 3, 4], "y": [1, 2, 3, 4]})
    with pytest.raises(WorkbenchError) as ei:
        run_model(df, target="y", user_id="u", dataset_id="d")
    assert ei.value.reason == "too_few_rows"


def test_modeling_rejects_missing_target() -> None:
    df = pd.DataFrame({"a": list(range(60))})
    with pytest.raises(WorkbenchError) as ei:
        run_model(df, target="missing", user_id="u", dataset_id="d")
    assert ei.value.reason == "missing_target"


# ===========================================================================
# Cache plumbing
# ===========================================================================

def test_cache_predictions_round_trips() -> None:
    table = pd.DataFrame({"row_index": [0, 1], "y_true": [1.0, 2.0], "y_pred": [1.1, 1.9], "model": ["m", "m"]})
    cache_predictions("ua", "da", table, target="t", problem="regression")
    rec = get_cached_predictions("ua", "da")
    assert rec is not None
    assert list(rec["table"].columns) == ["row_index", "y_true", "y_pred", "model"]
    assert rec["target"] == "t"
