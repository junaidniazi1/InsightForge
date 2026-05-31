"""KMeans with auto-k (Phase 7B, tool 5).

Sweeps k = 2..k_max, picks the k with the highest silhouette (ties broken
toward the smaller k), then fits and reports cluster sizes, per-cluster
feature means, and a 2D PCA projection coloured by cluster.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from ._common import WorkbenchError, chart, envelope
from ._ml import extract_numeric, pca_2d, standardize

K_MAX_CAP = 12
DEFAULT_K_MAX = 8
WEAK_STRUCTURE_THRESHOLD = 0.25
RANDOM_STATE = 0


def _silhouette(X_scaled: np.ndarray, labels: np.ndarray) -> float:
    if len(np.unique(labels)) < 2:
        return 0.0
    return float(silhouette_score(X_scaled, labels))


def run_clustering(
    df: pd.DataFrame,
    features: list[str] | None = None,
    *,
    k_max: int = DEFAULT_K_MAX,
) -> dict[str, Any]:
    k_max = max(2, min(int(k_max), K_MAX_CAP))
    X, meta = extract_numeric(df, features, min_rows=max(20, k_max + 1), what="clustering")
    X_scaled = standardize(X)

    inertias: list[float] = []
    silhouettes: list[float] = []
    ks = list(range(2, k_max + 1))
    labels_by_k: dict[int, np.ndarray] = {}
    for k in ks:
        km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE)
        labels = km.fit_predict(X_scaled)
        inertias.append(float(km.inertia_))
        silhouettes.append(_silhouette(X_scaled, labels))
        labels_by_k[k] = labels

    best_idx = int(np.argmax(silhouettes))  # argmax returns the first max → smaller-k tie-break
    best_k = ks[best_idx]
    best_labels = labels_by_k[best_k]
    best_silhouette = silhouettes[best_idx]

    # Cluster sizes + per-cluster feature means (the cluster profile table).
    cluster_sizes: dict[int, int] = {}
    profiles: list[dict[str, Any]] = []
    X_named = X.copy()
    X_named["__cluster"] = best_labels
    overall_means = X.mean()
    for c in range(best_k):
        mask = best_labels == c
        size = int(mask.sum())
        cluster_sizes[c] = size
        means = X_named.loc[mask, meta["features"]].mean()
        # Deltas vs overall mean — surfaces what each cluster is "about".
        deltas = (means - overall_means).abs()
        top_features = (
            deltas.sort_values(ascending=False).head(3).index.tolist()
        )
        profiles.append({
            "cluster": c,
            "size": size,
            "size_pct": round(size / len(X) * 100.0, 2),
            "means": {f: float(means[f]) for f in meta["features"]},
            "top_distinguishing_features": top_features,
        })

    # 2D PCA projection for the scatter.
    proj = pca_2d(X_scaled)

    # Charts ----------------------------------------------------------------
    # 1. Elbow + silhouette line (two y-series on shared x = k).
    scores_chart = chart(
        title="Elbow + silhouette by k",
        chart_type="line",
        encoding={"x": "k"},
        data={
            "x": [str(k) for k in ks],
            "series": [
                {"name": "inertia", "values": inertias},
                {"name": "silhouette", "values": silhouettes},
            ],
        },
        presentation={"legend": True, "x_label": "k"},
    )

    # 2. PCA scatter coloured by cluster.
    # Build a series per cluster so ECharts uses the palette.
    scatter_series = []
    for c in range(best_k):
        mask = best_labels == c
        scatter_series.append({
            "name": f"cluster {c}",
            "values": [[float(proj[i, 0]), float(proj[i, 1])] for i in np.where(mask)[0]],
        })
    pca_chart = chart(
        title=f"PCA projection (k={best_k})",
        chart_type="scatter",
        encoding={"x": "PC1", "y": "PC2"},
        data={
            # The ECharts scatter renderer reads x/y arrays; we provide a flat
            # one for compatibility plus the per-cluster grouping in `series`.
            "x": [float(p[0]) for p in proj],
            "y": [float(p[1]) for p in proj],
            "color": [str(int(c)) for c in best_labels],
            "n_rows": int(len(X)),
            "shown": int(len(X)),
            "sampled": False,
            "series_by_color": scatter_series,
        },
        presentation={"legend": True, "x_label": "PC1", "y_label": "PC2"},
    )

    # Interpretation --------------------------------------------------------
    interp_parts = [
        f"Best k = {best_k} (silhouette = {best_silhouette:.3f}).",
        f"Cluster sizes: " + ", ".join(
            f"cluster {c}: {cluster_sizes[c]} ({profiles[c]['size_pct']:.1f}%)"
            for c in range(best_k)
        ) + ".",
    ]
    if best_silhouette < WEAK_STRUCTURE_THRESHOLD:
        interp_parts.append(
            "Silhouette is below 0.25 — clusters are weak; consider whether the data is naturally clustered."
        )
    # Highlight the feature with the largest spread of cluster means.
    feature_spreads = {}
    for f in meta["features"]:
        per_cluster = [profiles[c]["means"][f] for c in range(best_k)]
        feature_spreads[f] = float(np.std(per_cluster))
    top_separator = max(feature_spreads.items(), key=lambda kv: kv[1])[0] if feature_spreads else None
    if top_separator:
        interp_parts.append(f"Largest between-cluster separation is on feature `{top_separator}`.")
    if meta["rows_dropped"]:
        interp_parts.append(f"({meta['rows_dropped']} rows with NaN in selected features were dropped.)")

    return envelope(
        result={
            "best_k": best_k,
            "ks": ks,
            "inertias": inertias,
            "silhouettes": silhouettes,
            "best_silhouette": best_silhouette,
            "cluster_sizes": cluster_sizes,
            "cluster_profiles": profiles,
            "features": meta["features"],
            "rows_used": meta["rows_after"],
            "rows_dropped": meta["rows_dropped"],
        },
        charts=[scores_chart, pca_chart],
        interpretation=" ".join(interp_parts),
    )


__all__ = ["run_clustering"]
