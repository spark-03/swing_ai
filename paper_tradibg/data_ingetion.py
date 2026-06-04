import os
import sys
import time
import pandas as pd
import numpy as np
import requests
import pyotp
from pathlib import Path
from paper_trading.logging_config import get_system_logger
from paper_trading.retry_utils import retry_call

class LiveDataIngestor:
    def __init__(self, universe_file: str = "configs/nifty500_symbols.txt", output_dir: str = "data/live/2h"):
        self.universe_file = Path(universe_file)
        self.output_dir = Path(output_dir)
        self.logger = get_system_logger("paper_trading.data_ingestion")
        
        self.api_key = os.getenv("ANGEL_API_KEY", "MOCK_API_KEY")
        self.client_id = os.getenv("ANGEL_CLIENT_ID", "")
        self.password = os.getenv("ANGEL_PASSWORD", "")
        self.totp_secret = os.getenv("ANGEL_TOTP_SECRET", "")
        
        # Enforce strict maximum tracking depth for FIFO
        self.max_history_window = 60 

    def generate_jwt_session(self) -> str:
        """Dynamically generates a fresh session token using TOTP verification."""
        if self.api_key == "MOCK_API_KEY" or not self.totp_secret:
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
                raise ValueError(f"Login Rejected: {res_json.get('message')}")
        except Exception as e:
            self.logger.error("Session authorization crash: %s", e)
            raise e

    def load_universe(self) -> list[str]:
        if not self.universe_file.exists():
            return []
        with open(self.universe_file, "r") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]

    def fetch_candles(self, symbol: str, jwt_token: str, fetch_count: int) -> pd.DataFrame:
        """Fetches a specific number of candles (60 for initial boot, 1 for live adjustments)."""
        if jwt_token == "MOCK_JWT":
            # Simulation Generator: Outputs exactly the requested size
            times = pd.date_range(end=pd.Timestamp.utcnow(), periods=fetch_count, freq='2h')
            close_prices = 500 + np.cumsum(np.random.normal(0.2, 2.0, size=fetch_count))
            return pd.DataFrame({
                "timestamp": times,
                "open": close_prices - np.random.normal(0.0, 1.0, size=fetch_count),
                "high": close_prices + np.random.uniform(0.1, 4.0, size=fetch_count),
                "low": close_prices - np.random.uniform(0.1, 4.0, size=fetch_count),
                "close": close_prices,
                "volume": np.random.randint(5000, 200000, size=fetch_count)
            })
        else:
            # SmartAPI connection endpoint mapping logic using fetch_count configuration parameters
            endpoint = "https://apicompania.angelone.in/ms/v1/historicalData"
            # Actual live HTTP requests payloads go here...
            return pd.DataFrame()

    def compute_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Computes technical spreads over the standardized rolling dataframe."""
        if df.empty or len(df) < 25:  # Ensure basic sizing thresholds to avoid NaN calculations
            return df
            
        work = df.copy().reset_index(drop=True)
        
        ema_short = work["close"].ewm(span=9, adjust=False).mean()
        ema_long = work["close"].ewm(span=21, adjust=False).mean()
        work["ema_spread"] = ema_short - ema_long
        work["momentum_score"] = work["close"].diff(periods=5).fillna(0.0)
        work["trend_strength"] = (work["close"] - work["close"].rolling(window=14).mean()).fillna(0.0)
        
        rolling_std = work["close"].rolling(window=10).std().fillna(0.0)
        work["volatility_score"] = rolling_std
        high_low_range = work["high"].rolling(window=14).max() - work["low"].rolling(window=14).min()
        work["compression_score"] = (rolling_std / (high_low_range + 0.0001)).fillna(0.0)
        
        work["momentum_persistence"] = work["momentum_score"].rolling(window=3).mean().fillna(0.0)
        work["higher_low_strength"] = (work["low"] - work["low"].shift(1)).fillna(0.0)
        work["price_position"] = ((work["close"] - work["low"]) / ((work["high"] - work["low"]) + 0.0001))
        
        tr = np.maximum(work["high"] - work["low"], 
                        np.maximum(abs(work["high"] - work["close"].shift(1)), 
                                   abs(work["low"] - work["close"].shift(1)))).fillna(0.0)
        work["ATR"] = tr.rolling(window=14).mean().fillna(0.1)

        for feature in ["momentum_score", "trend_strength", "ema_spread", "price_position"]:
            work[f"delta_{feature}_1"] = work[feature].diff(periods=1).fillna(0.0)
            work[f"delta_{feature}_3"] = work[feature].diff(periods=3).fillna(0.0)
            
        return work

    def run_pipeline(self):
        """Processes rolling FIFO buffers seamlessly for the ticker array lists."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        symbols = self.load_universe()
        
        try:
            jwt_token = self.generate_jwt_session()
        except Exception:
            self.logger.error("Authorization dropped. Ingestion loop killed.")
            return

        self.logger.info("Syncing FIFO data layers across %d asset arrays...", len(symbols))
        success_count = 0
        
        for sym in symbols:
            try:
                parquet_target = self.output_dir / f"{sym}.parquet"
                
                # Check if file exists to distinguish between Cold Start and Live Run
                if parquet_target.exists():
                    # --- LIVE RUN: ROLLING FIFO STEP ---
                    existing_df = pd.read_parquet(parquet_target)
                    
                    # Fetch just 1 single fresh candle
                    new_candle_df = self.fetch_candles(sym, jwt_token, fetch_count=1)
                    
                    if new_candle_df.empty:
                        continue
                        
                    # Drop computed feature columns from history before appending raw data
                    raw_columns = ["timestamp", "open", "high", "low", "close", "volume"]
                    cleaned_hist = existing_df[raw_columns]
                    
                    # FIFO Queue Merge: Append latest, slice tail to protect memory limits
                    merged_raw_df = pd.concat([cleaned_hist, new_candle_df], ignore_index=True)
                    final_raw_df = merged_raw_df.tail(self.max_history_window)
                    
                else:
                    # --- COLD START: SEED THE WINDOW ---
                    self.logger.info("Cold Start tracking triggered for asset %s. Seeding 60 rows.", sym)
                    final_raw_df = self.fetch_candles(sym, jwt_token, fetch_count=self.max_history_window)

                if final_raw_df.empty:
                    continue

                # Recalculate indicators across the strict rolling array windows
                processed_df = self.compute_technical_indicators(final_raw_df)
                processed_df.to_parquet(parquet_target, index=False)
                success_count += 1
                
            except Exception as e:
                self.logger.warning("Failed processing updates for ticker %s: %s", sym, e)
                
        self.logger.info("FIFO Sync sequence finalized. Maintained %d execution matrix logs.", success_count)

if __name__ == "__main__":
    ingestor = LiveDataIngestor()
    ingestor.run_pipeline()
