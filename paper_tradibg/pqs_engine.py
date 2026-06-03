import pandas as pd
import numpy as np

def zscore(series: pd.Series) -> pd.Series:
    """Computes population mathematical z-scores safely handling flat-lines."""
    std = float(series.std(ddof=0))
    if std == 0 or np.isnan(std):
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - series.mean()) / std

def calculate_pqs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies the weighted PQS score to rank candidate entries:
    40% EMA Spread, 25% Trend, 20% Momentum, 10% Compression, 5% Volatility.
    """
    work = df.copy()
    work["pqs"] = (
        0.40 * zscore(work["ema_spread"]) +
        0.25 * zscore(work["trend_strength"]) +
        0.20 * zscore(work["momentum_score"]) +
        0.10 * zscore(-work["compression_score"]) +
        0.05 * zscore(-work["volatility_score"])
    )
    return work
