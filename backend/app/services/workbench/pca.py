"""PCA workbench tool (Phase 7B, tool 6).

Explained variance per component + cumulative, top loadings per component
(top-5 by |loading|), and the 2D projection.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from ._common import chart, envelope
from ._ml import extract_numeric, standardize

DEFAULT_COMPONENTS = 2
MAX_COMPONENTS = 12
TOP_LOADINGS_PER_COMP = 5
RANDOM_STATE = 0


def run_pca(
    df: pd.DataFrame,
    features: list[str] | None = None,
    *,
    n_components: int = DEFAULT_COMPONENTS,
) -> dict[str, Any]:
    X, meta = extract_numeric(df, features, min_rows=10, what="PCA")
    X_scaled = standardize(X)
    max_comp = min(MAX_COMPONENTS, X.shape[1], X_scaled.shape[0])
    n_components = max(2, min(int(n_components), max_comp))

    pca = PCA(n_components=n_components, random_state=RANDOM_STATE)
    proj = pca.fit_transform(X_scaled)

    evr = pca.explained_variance_ratio_
    cumulative = np.cumsum(evr)

    # n_components for ≥90% variance.
    n_for_90 = int(np.argmax(cumulative >= 0.9) + 1) if (cumulative >= 0.9).any() else int(n_components)

    # Top loadings per component (signed; ranked by |loading|).
    components_loadings: list[dict[str, Any]] = []
    for i, row in enumerate(pca.components_):
        ranked = sorted(
            zip(meta["features"], row),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )[:TOP_LOADINGS_PER_COMP]
        components_loadings.append({
            "component": f"PC{i + 1}",
            "explained_variance": float(evr[i]),
            "cumulative": float(cumulative[i]),
            "loadings": [
                {"feature": f, "loading": float(v)} for f, v in ranked
            ],
        })

    # ---- Charts -----------------------------------------------------------
    # 1. Scree: bar of per-component variance.
    scree = chart(
        title="Scree — explained variance",
        chart_type="bar",
        encoding={"x": "component", "y": "explained_variance"},
        data={
            "categories": [f"PC{i + 1}" for i in range(n_components)],
            "series": [
                {"name": "explained variance", "values": [float(v) for v in evr]},
                {"name": "cumulative", "values": [float(v) for v in cumulative]},
            ],
        },
        presentation={"legend": True, "y_label": "share of variance"},
    )

    # 2. 2D projection scatter.
    proj_2d = proj[:, :2]
    projection = chart(
        title="PC1 vs PC2 projection",
        chart_type="scatter",
        encoding={"x": "PC1", "y": "PC2"},
        data={
            "x": [float(v) for v in proj_2d[:, 0]],
            "y": [float(v) for v in proj_2d[:, 1]],
            "n_rows": int(len(X)),
            "shown": int(len(X)),
            "sampled": False,
        },
        presentation={"x_label": "PC1", "y_label": "PC2"},
    )

    # ---- Interpretation ---------------------------------------------------
    drivers = [
        f"`{components_loadings[0]['loadings'][0]['feature']}`"
        + (
            f" (loading {components_loadings[0]['loadings'][0]['loading']:+.2f})"
            if components_loadings else ""
        )
    ] if components_loadings else []
    if n_components >= 2 and components_loadings[1]["loadings"]:
        drivers.append(
            f"`{components_loadings[1]['loadings'][0]['feature']}`"
            f" (loading {components_loadings[1]['loadings'][0]['loading']:+.2f})"
        )
    parts = [
        f"{n_for_90} component(s) capture ~90% of variance"
        f" (cumulative {float(cumulative[n_for_90 - 1]) * 100:.1f}%).",
    ]
    if components_loadings:
        parts.append(
            f"PC1 is driven mostly by {drivers[0]}"
            + (f"; PC2 by {drivers[1]}." if len(drivers) > 1 else ".")
        )
    if meta["rows_dropped"]:
        parts.append(f"({meta['rows_dropped']} rows with NaN dropped.)")

    return envelope(
        result={
            "features": meta["features"],
            "n_components": n_components,
            "explained_variance_ratio": [float(v) for v in evr],
            "cumulative_variance": [float(v) for v in cumulative],
            "components": components_loadings,
            "n_for_90pct": n_for_90,
            "rows_used": meta["rows_after"],
            "rows_dropped": meta["rows_dropped"],
        },
        charts=[scree, projection],
        interpretation=" ".join(parts),
    )


__all__ = ["run_pca"]
