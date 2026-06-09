import numpy as np
import pandas as pd


def zscore(series: pd.Series) -> pd.Series:
    """Computes population mathematical z-scores safely handling flat-lines."""
    std = float(series.std(ddof=0))
    if std == 0 or np.isnan(std):
        return pd.Series(np.zeros(len(series), dtype=float), index=series.index)
    return (series - float(series.mean())) / std


def calculate_pqs(df: pd.DataFrame) -> pd.DataFrame:
    """Applies the weighted PQS score to rank candidate entries:

    40% EMA Spread, 25% Trend, 20% Momentum, 10% Compression, 5% Volatility.
    Handles calculations per asset dynamically if a 'symbol' column is present.
    """
    work = df.copy()

    # If the dataframe contains multiple stocks, apply z-score within each stock group
    if "symbol" in work.columns:
        ema_z = work.groupby("symbol")["ema_spread"].transform(zscore)
        trend_z = work.groupby("symbol")["trend_strength"].transform(zscore)
        momentum_z = work.groupby("symbol")["momentum_score"].transform(zscore)
        compression_z = work.groupby("symbol")["compression_score"].transform(lambda x: zscore(-x))
        volatility_z = work.groupby("symbol")["volatility_score"].transform(lambda x: zscore(-x))
    else:
        # Fallback for single-asset dataframes
        ema_z = zscore(work["ema_spread"])
        trend_z = zscore(work["trend_strength"])
        momentum_z = zscore(work["momentum_score"])
        compression_z = zscore(-work["compression_score"])
        volatility_z = zscore(-work["volatility_score"])

    work["pqs"] = (
        0.40 * ema_z +
        0.25 * trend_z +
        0.20 * momentum_z +
        0.10 * compression_z +
        0.05 * volatility_z
    )
    return work
