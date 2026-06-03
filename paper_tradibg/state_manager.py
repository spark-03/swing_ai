from __future__ import annotations

import os
from dataclasses import dataclass
import pandas as pd
import requests
from paper_trading.logging_config import get_system_logger
from paper_trading.retry_utils import retry_call

PORTFOLIO_COLUMNS = [
    "symbol", "entry_timestamp", "entry_price", "quantity", 
    "slot_id", "slot_capital", "pqs", "status", 
    "bars_since_entry", "pnl_pct", "peak_pnl_so_far", "drawdown_from_peak"
]

@dataclass
class CloudStateManager:
    """Manages system state parameters via Supabase REST endpoints instead of local disk CSV files."""
    
    def __post_init__(self) -> None:
        self.logger = get_system_logger("paper_trading.cloud_state")
        self.url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.key = os.getenv("SUPABASE_KEY", "").strip()
        
        # When running locally, it defaults to a safe mock check; when online, Render forces the error if missing
        if not self.url or not self.key:
            self.logger.warning("SUPABASE credentials missing from environment. Using local fallback schemas for protection.")
            
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def load_portfolio(self) -> pd.DataFrame:
        """Fetches active and historical portfolio listings from the live Supabase database."""
        if not self.url or not self.key:
            return pd.DataFrame(columns=PORTFOLIO_COLUMNS)

        endpoint = f"{self.url}/rest/v1/current_portfolio?select=*"
        
        def fetch_op():
            resp = requests.get(endpoint, headers=self.headers, timeout=15)
            resp.raise_for_status()
            return resp.json()
            
        try:
            data = retry_call(fetch_op, attempts=3)
            if not data:
                return pd.DataFrame(columns=PORTFOLIO_COLUMNS)
            return pd.DataFrame(data)
        except Exception as e:
            self.logger.error("Failed to sync portfolio state from Supabase cluster: %s", e)
            return pd.DataFrame(columns=PORTFOLIO_COLUMNS)

    def save_portfolio_row(self, row_dict: dict) -> None:
        """Upserts a modified position tracking row back into cloud tables based on the symbol key."""
        if not self.url or not self.key:
            self.logger.info("Local Sim-Mode Save: Row updated for %s", row_dict.get("symbol"))
            return

        endpoint = f"{self.url}/rest/v1/current_portfolio"
        # The 'resolution=merge-duplicates' header tells Supabase to overwrite the row if the symbol already exists
        headers = {**self.headers, "Prefer": "resolution=merge-duplicates"}
        
        # Clean data types to ensure standard database parser compliance
        clean_row = {k: (int(v) if isinstance(v, (int, round)) else float(v) if isinstance(v, float) else str(v)) 
                     for k, v in row_dict.items() if not pd.isna(v)}

        def upsert_op():
            resp = requests.post(endpoint, headers=headers, json=clean_row, timeout=15)
            resp.raise_for_status()
            
        try:
            retry_call(upsert_op, attempts=3)
            self.logger.info("Successfully updated cloud database matrix entry for %s", clean_row.get("symbol"))
        except Exception as e:
            self.logger.error("Failed to push row state to Supabase: %s", e)
