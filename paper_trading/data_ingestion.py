import os
from datetime import datetime, timedelta
from pathlib import Path
import zoneinfo

import numpy as np
import pandas as pd
import pyotp
import requests

from paper_trading.logging_config import get_system_logger


class LiveDataIngestor:
    def __init__(self, universe_csv: str = "ind_nifty500list.csv", output_dir: str = "data/2h"):
        # Anchor paths dynamically relative to the script's root workspace
        self.base_dir = Path(__file__).resolve().parent.parent
        self.universe_file = self.base_dir / universe_csv
        self.output_dir = self.base_dir / output_dir

        self.logger = get_system_logger("paper_trading.data_ingestion")

        # SmartAPI Credentials pulled directly from your cloud Environment variables
        self.api_key = os.getenv("ANGEL_API_KEY", "MOCK_API_KEY")
        self.client_id = os.getenv("ANGEL_CLIENT_ID", "")
        self.password = os.getenv("ANGEL_PASSWORD", "")
        self.totp_secret = os.getenv("ANGEL_TOTP_SECRET", "")

        # Enforce strict maximum tracking depth for FIFO memory buffers
        self.max_history_window = 60

    def generate_jwt_session(self) -> str:
        """Dynamically generates a fresh session token using TOTP authentication."""
        if self.api_key == "MOCK_API_KEY" or not self.totp_secret:
            self.logger.warning("Missing API configuration credentials. Launching mock simulation pipeline.")
            return "MOCK_JWT"

        endpoint = "https://apicompania.angelone.in/smartapi/admin/user/v1/loginByPassword"
        totp = pyotp.TOTP(self.totp_secret.strip().replace(" ", ""))

        payload = {
            "clientcode": self.client_id,
            "password": self.password,
            "totp": totp.now()
        }
        headers = {"Content-Type": "application/json", "X-PrivateKey": self.api_key}

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            res_json = response.json()
            if res_json.get("status") is True:
                return res_json["data"]["jwtToken"]
            else:
                raise ValueError(f"Login Rejected by Angel One: {res_json.get('message')}")
        except Exception as e:
            self.logger.error("Session authorization crash: %s", e)
            raise e

    def load_universe(self) -> list[str]:
        """Parses your uploaded ind_nifty500list.csv file to extract current symbols."""
        if not self.universe_file.exists():
            self.logger.error(f"Critical Error: Universe mapping file missing at {self.universe_file}")
            return []

        try:
            df = pd.read_csv(self.universe_file)
            if 'Symbol' in df.columns:
                symbols = df['Symbol'].dropna().astype(str).str.strip().tolist()
                self.logger.info(f"Loaded {len(symbols)} tracking targets from {self.universe_file.name}")
                return symbols
            else:
                self.logger.error("CSV structure anomaly: Missing mandatory 'Symbol' column layout.")
                return []
        except Exception as e:
            self.logger.error(f"Failed parsing universe tracking layout list: {e}")
            return []

    def fetch_candles(self, symbol: str, jwt_token: str, fetch_count: int) -> pd.DataFrame:
        """Fetches candle intervals (60 rows for cold start, 1 row for rolling live sweeps)."""
        if jwt_token == "MOCK_JWT":
            # High-fidelity simulation matrix generator targeting 2-hour transaction slots
            ist_zone = zoneinfo.ZoneInfo("Asia/Kolkata")
            now = datetime.now(ist_zone)
            timestamps = []
            current_time = now

            while len(timestamps) < fetch_count:
                if 9 <= current_time.hour <= 15:
                    if current_time.weekday() < 5:  # Monday to Friday
                        timestamps.append(current_time.strftime("%Y-%m-%d %H:%M:%S"))
                current_time -= timedelta(hours=2)

            timestamps.reverse()

            close_prices = 1200.0 + np.cumsum(np.random.normal(0.1, 4.0, size=fetch_count))
            return pd.DataFrame({
                "timestamp": timestamps,
                "open": close_prices - np.random.normal(0.0, 2.0, size=fetch_count),
                "high": close_prices + np.random.uniform(0.5, 8.0, size=fetch_count),
                "low": close_prices - np.random.uniform(0.5, 8.0, size=fetch_count),
                "close": close_prices,
                "volume": np.random.randint(10000, 500000, size=fetch_count)
            })
        else:
            # SmartAPI active routing parameters placeholder (cleaned unused vars)
            return pd.DataFrame()

    def compute_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Computes technical indicator fields over the rolling data frames."""
        if df.empty or len(df) < 25:
            return df

        work = df.copy().reset_index(drop=True)

        # Exponential moving averages
        ema_short = work["close"].ewm(span=9, adjust=False).mean()
        ema_long = work["close"].ewm(span=21, adjust=False).mean()
        work["ema_spread"] = ema_short - ema_long

        # Momentum calculations
        work["momentum_score"] = work["close"].diff(periods=5).fillna(0.0)
        work["trend_strength"] = (work["close"] - work["close"].rolling(window=14).mean()).fillna(0.0)

        # Volatility metric sets
        rolling_std = work["close"].rolling(window=10).std().fillna(0.0)
        work["volatility_score"] = rolling_std
        high_low_range = work["high"].rolling(window=14).max() - work["low"].rolling(window=14).min()
        work["compression_score"] = (rolling_std / (high_low_range + 0.0001)).fillna(0.0)

        # Velocity metrics
        work["momentum_persistence"] = work["momentum_score"].rolling(window=3).mean().fillna(0.0)
        work["higher_low_strength"] = (work["low"] - work["low"].shift(1)).fillna(0.0)
        work["price_position"] = ((work["close"] - work["low"]) / ((work["high"] - work["low"]) + 0.0001))

        # Average True Range (ATR)
        tr = np.maximum(work["high"] - work["low"],
                        np.maximum(abs(work["high"] - work["close"].shift(1)),
                                   abs(work["low"] - work["close"].shift(1)))).fillna(0.0)
        work["ATR"] = tr.rolling(window=14).mean().fillna(0.1)

        # Delta vectors
        for feature in ["momentum_score", "trend_strength", "ema_spread", "price_position"]:
            work[f"delta_{feature}_1"] = work[feature].diff(periods=1).fillna(0.0)
            work[f"delta_{feature}_3"] = work[feature].diff(periods=3).fillna(0.0)

        return work

    def run_pipeline(self):
        """Processes rolling FIFO layers across your active NIFTY500 symbols list."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        symbols = self.load_universe()

        if not symbols:
            self.logger.error("No valid trading assets located. Ingestion process terminated.")
            return

        try:
            jwt_token = self.generate_jwt_session()
        except Exception:
            self.logger.error("Authorization handshake dropped. Ingestion loop killed.")
            return

        self.logger.info(f"Syncing FIFO layers for {len(symbols)} stocks inside {self.output_dir.relative_to(self.base_dir)}...")
        success_count = 0

        for idx, sym in enumerate(symbols, start=1):
            try:
                sym_clean = sym.strip()
                parquet_target = self.output_dir / f"{sym_clean}.parquet"

                # Check for historical data to distinguish cold starts from live updates
                if parquet_target.exists():
                    existing_df = pd.read_parquet(parquet_target)

                    # Fetch single newest 2-hour processing slice
                    new_candle_df = self.fetch_candles(sym_clean, jwt_token, fetch_count=1)
                    if new_candle_df.empty:
                        continue

                    raw_columns = ["timestamp", "open", "high", "low", "close", "volume"]
                    cleaned_hist = existing_df[raw_columns]

                    # Append new candle and apply FIFO slice to drop the oldest record
                    merged_raw_df = pd.concat([cleaned_hist, new_candle_df], ignore_index=True)
                    final_raw_df = merged_raw_df.tail(self.max_history_window)
                else:
                    # Cold Start: Seed the full historical lookback window (60 intervals)
                    if idx % 100 == 1 or idx == len(symbols):
                        self.logger.info(f"Cold Start sequence active for asset array index [{idx}/{len(symbols)}]: Seeding lookback window for {sym_clean}")
                    final_raw_df = self.fetch_candles(sym_clean, jwt_token, fetch_count=self.max_history_window)

                if final_raw_df.empty:
                    continue

                # Refresh technical feature layers across current data slices
                processed_df = self.compute_technical_indicators(final_raw_df)
                processed_df.to_parquet(parquet_target, index=False)
                success_count += 1

            except Exception as e:
                self.logger.warning(f"Failed processing execution buffers for asset {sym}: {e}")

        self.logger.info(f"=== FIFO UPDATE MATRIX SUCCESSFUL: Maintained {success_count}/{len(symbols)} stock logs ===")


if __name__ == "__main__":
    ingestor = LiveDataIngestor()
    ingestor.run_pipeline()
