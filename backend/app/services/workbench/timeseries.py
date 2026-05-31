"""Time-series workbench (Phase 7A, tool 4).

Resampling + rolling, seasonal decomposition, ACF/PACF, Augmented Dickey-Fuller
stationarity. Enabled when a datetime column exists.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import acf, adfuller, pacf
from statsmodels.tsa.seasonal import seasonal_decompose

from ._common import WorkbenchError, chart, envelope, require_columns, require_min_rows


Frequency = Literal["D", "W", "ME", "QE", "YE"]
AggKind = Literal["mean", "sum", "min", "max", "median"]

_DEFAULT_LAGS = 30
_MAX_LAGS = 100
_DECOMPOSE_MAX_LEN = 5000   # statsmodels is slow on big series; cap.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_series(df: pd.DataFrame, x: str, y: str) -> pd.Series:
    require_columns(df, [x, y])
    s = pd.to_datetime(df[x], errors="coerce")
    v = pd.to_numeric(df[y], errors="coerce")
    sub = pd.DataFrame({"_t": s, "_y": v}).dropna()
    if sub.empty:
        raise WorkbenchError(
            f"`{x}` × `{y}` has no parseable datetime/numeric pairs.",
            reason="empty_series",
        )
    sub = sub.set_index("_t").sort_index()
    return sub["_y"]


def _resample_one(series: pd.Series, freq: Frequency, agg: AggKind) -> pd.Series:
    return series.resample(freq).agg(agg).dropna()


def _interpretation_for_adf(
    adf_stat: float, p: float, crit: dict[str, float]
) -> str:
    if p < 0.05:
        return (
            f"The series is **stationary** (ADF statistic = {adf_stat:.3f}, "
            f"p = {p:.4g}). Trends and seasonality can be modelled directly."
        )
    return (
        f"The series is **non-stationary** (ADF statistic = {adf_stat:.3f}, "
        f"p = {p:.4g}; 5%% critical = {crit.get('5%', float('nan')):.3f}). "
        "Consider differencing or detrending before modelling."
    )


# ---------------------------------------------------------------------------
# Public runners
# ---------------------------------------------------------------------------

def run_resample(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    freq: Frequency = "ME",
    agg: AggKind = "mean",
    rolling_window: int | None = None,
) -> dict[str, Any]:
    series = _to_series(df, x, y)
    resampled = _resample_one(series, freq, agg)
    require_min_rows(len(resampled), minimum=3, what=f"resample by {freq}")

    series_list = [
        {"name": f"{agg}({y})", "values": [float(v) for v in resampled.values]}
    ]
    if rolling_window and rolling_window >= 2:
        rolling = resampled.rolling(window=int(rolling_window)).mean()
        series_list.append({
            "name": f"{rolling_window}-period rolling mean",
            "values": [float(v) if not np.isnan(v) else None for v in rolling.values],  # type: ignore[misc]
        })

    interp = (
        f"`{y}` over `{x}`, resampled at frequency `{freq}` using `{agg}` "
        f"({len(resampled)} points)."
    )
    return envelope(
        result={
            "x": [t.isoformat() for t in resampled.index],
            "y": [float(v) for v in resampled.values],
            "freq": freq,
            "agg": agg,
            "rolling_window": rolling_window,
        },
        charts=[chart(
            title=f"{agg}({y}) by {freq}",
            chart_type="line",
            encoding={"x": x, "y": y, "agg": agg},
            data={
                "x": [t.isoformat() for t in resampled.index],
                "series": series_list,
            },
        )],
        interpretation=interp,
    )


def run_decompose(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    freq: Frequency = "ME",
    period: int | None = None,
    model: Literal["additive", "multiplicative"] = "additive",
) -> dict[str, Any]:
    series = _to_series(df, x, y)
    resampled = _resample_one(series, freq, "mean")
    if len(resampled) > _DECOMPOSE_MAX_LEN:
        resampled = resampled.iloc[: _DECOMPOSE_MAX_LEN]
    # Default period from frequency.
    default_period = {"D": 7, "W": 52, "ME": 12, "QE": 4, "YE": 1}[freq]
    p = int(period) if period else default_period
    require_min_rows(len(resampled), minimum=p * 2 + 1, what=f"decomposition with period={p}")

    decomp = seasonal_decompose(resampled, model=model, period=p, extrapolate_trend="freq")
    x_iso = [t.isoformat() for t in resampled.index]
    return envelope(
        result={
            "x": x_iso,
            "observed": [float(v) for v in decomp.observed.values],
            "trend": [float(v) if not np.isnan(v) else None for v in decomp.trend.values],
            "seasonal": [float(v) for v in decomp.seasonal.values],
            "residual": [float(v) if not np.isnan(v) else None for v in decomp.resid.values],
            "model": model,
            "period": p,
        },
        charts=[chart(
            title=f"Decomposition of {y} ({model}, period={p})",
            chart_type="line",
            encoding={"x": x, "y": y},
            data={
                "x": x_iso,
                "series": [
                    {"name": "observed", "values": [float(v) for v in decomp.observed.values]},
                    {"name": "trend", "values": [None if np.isnan(v) else float(v) for v in decomp.trend.values]},
                    {"name": "seasonal", "values": [float(v) for v in decomp.seasonal.values]},
                    {"name": "residual", "values": [None if np.isnan(v) else float(v) for v in decomp.resid.values]},
                ],
            },
            presentation={"legend": True},
        )],
        interpretation=(
            f"Decomposed `{y}` into trend + seasonal (period {p}) + residual using "
            f"the {model} model."
        ),
    )


def run_acf_pacf(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    freq: Frequency = "ME",
    nlags: int = _DEFAULT_LAGS,
) -> dict[str, Any]:
    nlags = max(5, min(int(nlags), _MAX_LAGS))
    series = _resample_one(_to_series(df, x, y), freq, "mean")
    require_min_rows(len(series), minimum=nlags + 3, what=f"ACF/PACF with {nlags} lags")
    acf_vals = acf(series.values, nlags=nlags, fft=True)
    pacf_vals = pacf(series.values, nlags=nlags, method="ols")
    lags = list(range(0, nlags + 1))
    return envelope(
        result={
            "lags": lags,
            "acf": [float(v) for v in acf_vals],
            "pacf": [float(v) for v in pacf_vals],
            "nlags": nlags,
        },
        charts=[
            chart(
                title=f"ACF of {y}",
                chart_type="bar",
                encoding={"x": "lag", "y": "acf"},
                data={
                    "categories": [str(l) for l in lags],
                    "series": [{"name": "acf", "values": [float(v) for v in acf_vals]}],
                },
            ),
            chart(
                title=f"PACF of {y}",
                chart_type="bar",
                encoding={"x": "lag", "y": "pacf"},
                data={
                    "categories": [str(l) for l in lags],
                    "series": [{"name": "pacf", "values": [float(v) for v in pacf_vals]}],
                },
            ),
        ],
        interpretation=(
            f"ACF/PACF up to lag {nlags} for `{y}` resampled at `{freq}`. "
            "Significant non-zero lags indicate autocorrelation worth modelling."
        ),
    )


def run_stationarity(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    freq: Frequency = "ME",
) -> dict[str, Any]:
    series = _resample_one(_to_series(df, x, y), freq, "mean")
    require_min_rows(len(series), minimum=10, what="ADF test")
    stat, p, used_lag, n_obs, crit, _icbest = adfuller(series.values, autolag="AIC")
    crit_dict = {k: float(v) for k, v in (crit or {}).items()}
    return envelope(
        result={
            "adf_statistic": float(stat),
            "p_value": float(p),
            "used_lag": int(used_lag),
            "n_observations": int(n_obs),
            "critical_values": crit_dict,
            "is_stationary": bool(p < 0.05),
        },
        charts=[chart(
            title=f"{y} over {x}",
            chart_type="line",
            encoding={"x": x, "y": y, "agg": "mean"},
            data={
                "x": [t.isoformat() for t in series.index],
                "series": [{"name": y, "values": [float(v) for v in series.values]}],
            },
        )],
        interpretation=_interpretation_for_adf(float(stat), float(p), crit_dict),
    )


__all__ = [
    "run_resample",
    "run_decompose",
    "run_acf_pacf",
    "run_stationarity",
]
