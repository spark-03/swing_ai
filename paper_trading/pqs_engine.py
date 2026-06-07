"""
PQS (Portfolio Quality Score) Engine
Calculates composite quality scores for stock candidates based on technical indicators.
"""
import numpy as np
import pandas as pd
from paper_trading.logging_config import get_system_logger

logger = get_system_logger("paper_trading.pqs_engine")

# Feature weights for PQS calculation (higher = more important)
PQS_WEIGHTS = {
    "momentum_score": 0.20,
    "trend_strength": 0.18,
    "ema_spread": 0.15,
    "volatility_score": 0.10,
    "compression_score": 0.10,
    "momentum_persistence": 0.08,
    "higher_low_strength": 0.07,
    "price_position": 0.06,
    "ATR": 0.06,
}

# Features where lower values are better (inverted scoring)
INVERTED_FEATURES = {"volatility_score"}


def _z_score_series(series: pd.Series) -> pd.Series:
    """Compute z-scores for a pandas Series, handling zero-std gracefully."""
    mean = series.mean()
    std = series.std()
    if std == 0 or pd.isna(std):
        return pd.Series(0.0, index=series.index)
    return (series - mean) / std


def _normalize_to_0_100(series: pd.Series) -> pd.Series:
    """Normalize a z-scored series to 0-100 range using sigmoid-like mapping."""
    # Clip extreme z-scores to prevent outlier domination
    clipped = series.clip(-3, 3)
    # Map from [-3, 3] to [0, 100]
    normalized = ((clipped + 3) / 6) * 100
    return normalized


def calculate_pqs(universe_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate PQS (Portfolio Quality Score) for each stock in the universe.
    
    Args:
        universe_df: DataFrame with technical indicator columns from data_ingestion.
                     Must contain at least 'symbol' and the indicator columns.
    
    Returns:
        DataFrame with an added 'pqs' column, sorted by descending PQS.
    """
    if universe_df.empty:
        logger.warning("Empty universe DataFrame provided for PQS calculation.")
        return universe_df

    result = universe_df.copy()
    
    # Ensure all required feature columns exist
    available_features = {f: w for f, w in PQS_WEIGHTS.items() if f in result.columns}
    
    if not available_features:
        logger.error("No PQS feature columns found in universe DataFrame. Available: %s", list(result.columns))
        result["pqs"] = 0.0
        return result

    logger.info("Calculating PQS across %d stocks using %d features.", len(result), len(available_features))

    # Step 1: Z-score each feature across the universe
    z_scored = pd.DataFrame(index=result.index)
    for feature in available_features:
        raw_values = result[feature].fillna(0.0)
        z_scored[feature] = _z_score_series(raw_values)
        
        # Invert features where lower is better
        if feature in INVERTED_FEATURES:
            z_scored[feature] = -z_scored[feature]

    # Step 2: Normalize z-scores to 0-100 range
    normalized = pd.DataFrame(index=result.index)
    for feature in available_features:
        normalized[feature] = _normalize_to_0_100(z_scored[feature])

    # Step 3: Calculate weighted composite score
    total_weight = sum(available_features.values())
    pqs_scores = pd.Series(0.0, index=result.index, dtype=float)
    
    for feature, weight in available_features.items():
        pqs_scores += (normalized[feature] * weight / total_weight)

    # Step 4: Apply confidence penalty for stocks with sparse data
    if "volume" in result.columns:
        # Stocks with very low volume get penalized
        volume_median = result["volume"].median()
        if volume_median > 0:
            volume_factor = (result["volume"] / volume_median).clip(0.3, 1.0)
            pqs_scores = pqs_scores * volume_factor

    result["pqs"] = pqs_scores.round(4)
    
    logger.info("PQS calculation complete. Top score: %.4f, Bottom score: %.4f", 
                result["pqs"].max(), result["pqs"].min())

    return result


def get_top_candidates(scored_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Return the top N candidates by PQS score."""
    if scored_df.empty:
        return scored_df
    return scored_df.nlargest(top_n, "pqs")


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
        "momentum_persistence": [5.0, 8.0, 3.0, 6.0, 4.0],
        "higher_low_strength": [2.0, 4.0, 1.0, 3.0, 2.5],
        "price_position": [0.7, 0.9, 0.5, 0.8, 0.6],
        "ATR": [45.0, 30.0, 55.0, 35.0, 40.0],
        "volume": [100000, 250000, 80000, 200000, 120000],
    })
    
    result = calculate_pqs(test_data)
    print("\n=== PQS Test Results ===")
    print(result[["symbol", "pqs"]].sort_values("pqs", ascending=False).to_string(index=False))