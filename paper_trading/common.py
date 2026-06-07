from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass
class TradingConfig:
    initial_capital: float = 1_000_000.0
    slots: tuple[float, float, float] = (
        500_000.0,
        300_000.0,
        200_000.0,
    )
    max_positions: int = 3


def load_hourly_symbol_file(
    path: Path
) -> pd.DataFrame:

    df = pd.read_parquet(path)

    if isinstance(
        df.index,
        pd.DatetimeIndex
    ):

        df = df.reset_index()

        if (
            "index" in df.columns
            and
            "datetime" not in df.columns
        ):
            df = df.rename(
                columns={
                    "index":
                    "datetime"
                }
            )

    if "datetime" not in df.columns:
        raise ValueError(
            f"Missing datetime in {path}"
        )

    for col in (
        "open",
        "high",
        "low",
        "close",
        "volume"
    ):

        if col not in df.columns:
            raise ValueError(
                f"Missing {col} in {path}"
            )

    df["datetime"] = pd.to_datetime(
        df["datetime"],
        errors="coerce"
    )

    df = (
        df
        .dropna(subset=["datetime"])
        .sort_values("datetime")
        .reset_index(drop=True)
    )

    return df


def build_2h_bars(
    symbol_df: pd.DataFrame
) -> pd.DataFrame:

    sdf = symbol_df.copy()

    sdf = (
        sdf
        .set_index("datetime")
        .between_time(
            "09:15",
            "15:30"
        )
    )

    if sdf.empty:
        return pd.DataFrame()

    sdf["date"] = sdf.index.date

    sessions = [

        ("09:15", "11:15"),

        ("11:15", "13:15"),

        ("13:15", "15:30"),

    ]

    rows = []

    for _, day_df in sdf.groupby("date"):

        for start, end in sessions:

            chunk = day_df.between_time(
                start,
                end
            )

            if chunk.empty:
                continue

            rows.append({

                "datetime":
                    chunk.index[0],

                "open":
                    float(
                        chunk["open"].iloc[0]
                    ),

                "high":
                    float(
                        chunk["high"].max()
                    ),

                "low":
                    float(
                        chunk["low"].min()
                    ),

                "close":
                    float(
                        chunk["close"].iloc[-1]
                    ),

                "volume":
                    float(
                        chunk["volume"].sum()
                    ),

            })

    out = pd.DataFrame(rows)

    if out.empty:
        return out

    return (
        out
        .sort_values("datetime")
        .reset_index(drop=True)
    )


def add_state_features(
    df_2h: pd.DataFrame
) -> pd.DataFrame:

    df = df_2h.copy()

    # ==========================
    # RETURNS
    # ==========================

    df["returns"] = (
        df["close"]
        .pct_change()
    )

    # ==========================
    # EMA
    # ==========================

    df["ema_10"] = (
        df["close"]
        .ewm(span=10)
        .mean()
    )

    df["ema_20"] = (
        df["close"]
        .ewm(span=20)
        .mean()
    )

    # ==========================
    # NORMALIZED EMA SPREAD
    # FIXES PAGEIND BIAS
    # ==========================

    df["ema_spread"] = (

        (
            df["ema_10"]
            -
            df["ema_20"]
        )

        /

        df["close"]

    )

    # ==========================
    # VOLATILITY
    # ==========================

    df["volatility_score"] = (

        df["returns"]
        .rolling(10)
        .std()

    )

    # ==========================
    # MOMENTUM
    # ==========================

    df["momentum_score"] = (

        df["close"]
        .pct_change(5)

    )

    # ==========================
    # TREND STRENGTH
    # ==========================

    df["trend_strength"] = (
        df["ema_spread"]
    )

    # ==========================
    # COMPRESSION
    # ==========================

    rolling_range = (

        df["high"]
        .rolling(10)
        .max()

        -

        df["low"]
        .rolling(10)
        .min()

    )

    df["compression_score"] = (

        rolling_range

        /

        df["close"]

    )

    df = (

        df
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
        .dropna()
        .reset_index(drop=True)

    )

    return df


def zscore(
    series: pd.Series
) -> pd.Series:

    std = float(
        series.std(ddof=0)
    )

    if (
        std == 0
        or
        np.isnan(std)
    ):

        return pd.Series(
            np.zeros(
                len(series),
                dtype=float
            ),
            index=series.index
        )

    return (

        series
        -
        float(series.mean())

    ) / std


def ensure_parent(
    path: Path
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )


def latest_prices_from_hourly(
    files: Iterable[Path]
) -> dict[str, float]:

    prices = {}

    for path in files:

        symbol = path.stem

        try:

            df = (
                load_hourly_symbol_file(
                    path
                )
            )

        except Exception:
            continue

        if df.empty:
            continue

        prices[symbol] = float(
            df["close"].iloc[-1]
        )

    return prices
