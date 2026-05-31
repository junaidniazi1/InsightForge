"""Isolation-Forest anomaly detection (Phase 7B, tool 7).

Standalone tool — distinct from the Phase-2 outlier flagging in the profiler.
The user picks `contamination` (default 0.05). Output is the per-row anomaly
score, the boolean flag, the flagged rows (capped), and visualisations.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ._common import chart, envelope
from ._ml import extract_numeric, pca_2d, standardize

MAX_FLAGGED_ROWS = 1000
DEFAULT_CONTAMINATION = 0.05
RANDOM_STATE = 0


def run_anomaly(
    df: pd.DataFrame,
    features: list[str] | None = None,
    *,
    contamination: float = DEFAULT_CONTAMINATION,
) -> dict[str, Any]:
    contamination = float(max(0.001, min(contamination, 0.5)))
    X, meta = extract_numeric(df, features, min_rows=20, what="anomaly detection")
    X_scaled = standardize(X)

    iso = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=RANDOM_STATE,
    )
    iso.fit(X_scaled)
    # Higher score = more anomalous. score_samples returns higher = more normal,
    # so negate.
    raw = iso.score_samples(X_scaled)
    scores = -raw
    preds = iso.predict(X_scaled)
    is_anomaly = preds == -1

    flagged_idx = np.where(is_anomaly)[0]
    flagged_count = int(flagged_idx.size)
    capped_idx = flagged_idx[:MAX_FLAGGED_ROWS]
    truncated = flagged_count > MAX_FLAGGED_ROWS

    # 2D projection coloured by flag.
    proj = pca_2d(X_scaled)

    # Decision threshold ≈ score at the (1 - contamination) quantile of raw.
    threshold = float(np.quantile(scores, 1 - contamination))

    # Build flagged-rows preview table (capped).
    flagged_rows = []
    for i in capped_idx:
        row = {f: float(X.iloc[int(i)][f]) for f in meta["features"]}
        row["__index"] = int(i)
        row["__score"] = float(scores[int(i)])
        flagged_rows.append(row)

    # Histogram of scores with the threshold marked.
    counts, edges = np.histogram(scores, bins=30)
    centers = (edges[:-1] + edges[1:]) / 2
    score_hist = chart(
        title="Anomaly-score histogram",
        chart_type="histogram",
        encoding={"x": "anomaly_score"},
        data={
            "x": [float(v) for v in centers],
            "y": [int(v) for v in counts],
            "edges": [float(v) for v in edges],
            "threshold": threshold,
        },
        presentation={"x_label": "anomaly score"},
    )

    # 2D PCA scatter with anomalies highlighted.
    normal_idx = np.where(~is_anomaly)[0]
    anomaly_idx = np.where(is_anomaly)[0]
    scatter = chart(
        title="PCA projection — anomalies highlighted",
        chart_type="scatter",
        encoding={"x": "PC1", "y": "PC2"},
        data={
            "x": [float(p) for p in proj[:, 0]],
            "y": [float(p) for p in proj[:, 1]],
            "color": ["anomaly" if a else "normal" for a in is_anomaly],
            "n_rows": int(len(X)),
            "shown": int(len(X)),
            "sampled": False,
            "series_by_color": [
                {
                    "name": "normal",
                    "values": [[float(proj[i, 0]), float(proj[i, 1])] for i in normal_idx],
                },
                {
                    "name": "anomaly",
                    "values": [[float(proj[i, 0]), float(proj[i, 1])] for i in anomaly_idx],
                },
            ],
        },
        presentation={"legend": True, "x_label": "PC1", "y_label": "PC2"},
    )

    pct = flagged_count / max(len(X), 1) * 100.0
    parts = [
        f"Flagged {flagged_count} rows (~{pct:.1f}% of data) as anomalous at contamination = {contamination:.3f}.",
    ]
    if flagged_count == 0:
        parts.append("No outliers found at this contamination — try a higher setting.")
    else:
        top = np.argsort(scores)[::-1][:5]
        parts.append(
            "Highest-scoring row indices: "
            + ", ".join(str(int(i)) for i in top)
            + "."
        )
    if meta["rows_dropped"]:
        parts.append(f"({meta['rows_dropped']} rows with NaN dropped.)")

    return envelope(
        result={
            "features": meta["features"],
            "contamination": contamination,
            "threshold": threshold,
            "flagged_count": flagged_count,
            "flagged_pct": round(pct, 2),
            "flagged_rows": flagged_rows,
            "truncated": truncated,
            "max_flagged": MAX_FLAGGED_ROWS,
            "rows_used": meta["rows_after"],
            "rows_dropped": meta["rows_dropped"],
        },
        charts=[score_hist, scatter],
        interpretation=" ".join(parts),
    )


__all__ = ["run_anomaly"]
