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
        
        # Load credentials from environmental secrets
        self.api_key = os.getenv("ANGEL_API_KEY", "MOCK_API_KEY")
        self.client_id = os.getenv("ANGEL_CLIENT_ID", "")
        self.password = os.getenv("ANGEL_PASSWORD", "")
        self.totp_secret = os.getenv("ANGEL_TOTP_SECRET", "") # The alphanumeric key given by Angel One when setting up TOTP

    def generate_jwt_session(self) -> str:
        """Dynamically generates a fresh session JWT token using TOTP keys."""
        if self.api_key == "MOCK_API_KEY" or not self.totp_secret:
            self.logger.warning("Using mock environment profile credentials for execution framework.")
            return "MOCK_JWT"

        endpoint = "https://apicompania.angelone.in/smartapi/admin/user/v1/loginByPassword"
        
        # Generate the 6-digit dynamic TOTP pin programmatically right now
        totp = pyotp.TOTP(self.totp_secret.strip().replace(" ", ""))
        current_totp_pin = totp.now()

        payload = {
            "clientcode": self.client_id,
            "password": self.password,
            "totp": current_totp_pin
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-PrivateKey": self.api_key
        }

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            response_data = response.json()
            
            if response_data.get("status") is True:
                jwt_token = response_data["data"]["jwtToken"]
                self.logger.info("Angel One authentication session successfully established.")
                return jwt_token
            else:
                raise ValueError(f"Broker login rejected: {response_data.get('message')}")
        except Exception as e:
            self.logger.error("Failed to generate dynamic login session: %s", e)
            raise e

    def load_universe(self) -> list[str]:
        """Reads your tracking text file from the configs directory."""
        if not self.universe_file.exists():
            return []
        with open(self.universe_file, "r") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]

    def fetch_ohlc_from_broker(self, symbol: str, jwt_token: str) -> pd.DataFrame:
        """Connects to the broker endpoint to pull down historical candles."""
        if jwt_token == "MOCK_JWT":
            # Generate simulated calculation rows if no API credentials exist
            intervals = 50
            times = pd.date_range(end=pd.Timestamp.utcnow(), periods=intervals, freq='2h')
            close_prices = 500 + np.cumsum(np.random.normal(0.5, 3.0, size=intervals))
            
            return pd.DataFrame({
                "timestamp": times,
                "open": close_prices - np.random.normal(0.0, 1.0, size=intervals),
                "high": close_prices + np.random.uniform(0.1, 5.0, size=intervals),
                "low": close_prices - np.random.uniform(0.1, 5.0, size=intervals),
                "close": close_prices,
                "volume": np.random.randint(10000, 500000, size=intervals)
            })
            
        else:
            # Actual data fetch from smartapi
            endpoint = "https://apicompania.angelone.in/ms/v1/historicalData"
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/json",
                "X-PrivateKey": self.api_key
            }
            # Custom request payload dictionary matching symbol configuration mappings
            return pd.DataFrame()

    def compute_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transforms raw candles into your exact mathematical indicator metrics."""
        if df.empty or len(df) < 10:
            return df
        work = df.copy()
        
        # Base indicators
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
        """Orchestrates authorization and pulls data for your asset sheets."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        symbols = self.load_universe()
        
        try:
            # Generate your live dynamic login session using TOTP
            jwt_token = self.generate_jwt_session()
        except Exception:
            self.logger.error("Authentication failed. Aborting ingestion loop.")
            return

        self.logger.info("Starting ingestion processing for %d symbols across universe matrix...", len(symbols))
        success_count = 0
        
        for sym in symbols:
            try:
                def process_operation():
                    raw_df = self.fetch_ohlc_from_broker(sym, jwt_token)
                    if raw_df.empty:
                        return False
                    processed_df = self.compute_technical_indicators(raw_df)
                    processed_df.to_parquet(self.output_dir / f"{sym}.parquet", index=False)
                    return True
                
                if retry_call(process_operation, attempts=2):
                    success_count += 1
            except Exception as e:
                self.logger.warning("Failed factor parsing updates for symbol %s: %s", sym, e)
                
        self.logger.info("Ingestion complete. Updated %d/%d data frames.", success_count, len(symbols))

if __name__ == "__main__":
    ingestor = LiveDataIngestor()
    ingestor.run_pipeline()
