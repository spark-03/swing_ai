from __future__ import annotations

import os
from dataclasses import dataclass
import pandas as pd
import requests
from paper_trading.logging_config import get_system_logger
from paper_trading.retry_utils import retry_call

@dataclass
class CloudStateManager:
    """Manages system state parameters via cloud endpoints instead of local CSV/TXT files."""
    
    def __post_init__(self) -> None:
        self.logger = get_system_logger("paper_trading.cloud_state")
        self.url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.key = os.getenv("SUPABASE_KEY", "").strip()
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be configured for Cloud Execution.")
            
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def load_portfolio(self) -> pd.DataFrame:
        """Fetches active and historical portfolio listings from Supabase tables."""
        endpoint = f"{self.url}/rest/v1/current_portfolio?select=*"
        
        def fetch_op():
            resp = requests.get(endpoint, headers=self.headers, timeout=15)
            resp.raise_for_status()
            return resp.json()
            
        try:
            data = retry_call(fetch_op, attempts=3)
            if not data:
                return pd.DataFrame()
            return pd.DataFrame(data)
        except Exception as e:
            self.logger.error("Failed to sync portfolio state from Supabase cluster: %s", e)
            return pd.DataFrame()

    def save_portfolio_row(self, row_dict: dict) -> None:
        """Upserts a modified position tracking row back into cloud tables based on symbol key."""
        endpoint = f"{self.url}/rest/v1/current_portfolio"
        headers = {**self.headers, "Prefer": "resolution=merge-duplicates"}
        
        def upsert_op():
            resp = requests.post(endpoint, headers=headers, json=row_dict, timeout=15)
            resp.raise_for_status()
            
        retry_call(upsert_op, attempts=3)
        self.logger.info("Successfully updated cloud database matrix entry for %s", row_dict.get("symbol"))
