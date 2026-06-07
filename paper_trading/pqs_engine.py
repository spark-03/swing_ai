"""
PQS (Portfolio Quality Score) Engine
Calculates composite quality scores for stock candidates based on technical indicators.
"""
import numpy as np
import pandas as pd
from paper_trading.logging_config import get_system_logger

logger = get_system_logger("paper_trading.pqs_engine")


def zscore(series):
    """Compute z-scores for a pandas Series, handling zero-std gracefully."""
    std = float(series.std(ddof=0))
    if std == 0 or np.isnan(std):
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - series.mean()) / std


def calculate_pqs(df):
    """
    Calculate PQS (Portfolio Quality Score) for each stock in the universe.

    Scoring weights:
      - ema_spread:        40% (positive = bullish crossover)
      - trend_strength:    25% (positive = above moving average)
      - momentum_score:    20% (positive = upward momentum)
      - compression_score: 10% (inverted: low compression = breakout ready)
      - volatility_score:   5% (inverted: low volatility = stability)
    """
    if df.empty:
        logger.warning("Empty DataFrame provided for PQS calculation.")
        return df

    work = df.copy()

    logger.info("Calculating PQS across %d stocks.", len(work))

    work["pqs"] = (
        0.40 * zscore(work["ema_spread"])
        + 0.25 * zscore(work["trend_strength"])
        + 0.20 * zscore(work["momentum_score"])
        + 0.10 * zscore(-work["compression_score"])
        + 0.05 * zscore(-work["volatility_score"])
    )

    logger.info("PQS calculation complete. Top score: %.4f, Bottom score: %.4f",
                work["pqs"].max(), work["pqs"].min())

    return work


if __name__ == "__main__":
    # Quick test with synthetic data
    test_data = pd.DataFrame({
        "symbol": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"],
        "close": [2500.0, 3800.0, 1600.0, 1700.0, 1200.0],
        "momentum_score": [15.0, 25.0, 10.0, 20.0, 12.0],
        "trend_strength": [50.0, 80.0, 30.0, 60.0, 40.0],
        "ema_spread": [25.0, 40.0, 15.0, 30.0, 20.0],
        "volatility_score": [30.0, 20.0, 45.0, 25.0, 35.0],
        "compression_score": [0.5, 0.8, 0.3, 0.6, 0.4],
    })

    result = calculate_pqs(test_data)
    print("\n=== PQS Test Results ===")
    print(result[["symbol", "pqs"]].sort_values("pqs", ascending=False).to_string(index=False))
