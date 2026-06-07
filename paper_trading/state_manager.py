from __future__ import annotations

import os
from dataclasses import dataclass
import pandas as pd
from paper_trading.logging_config import get_system_logger
from paper_trading.supabase_client import get_supabase_client

PORTFOLIO_COLUMNS = [
    "symbol", "entry_timestamp", "entry_price", "quantity", 
    "slot_id", "slot_capital", "pqs", "status", 
    "bars_since_entry", "pnl_pct", "peak_pnl_so_far", "drawdown_from_peak"
]

@dataclass
class CloudStateManager:
    """Manages system state parameters via Supabase with retry logic and connection pooling."""
    
    def __post_init__(self) -> None:
        self.logger = get_system_logger("paper_trading.cloud_state")
        self.url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.key = os.getenv("SUPABASE_KEY", "").strip()
        
        if not self.url or not self.key:
            self.logger.warning("SUPABASE credentials missing. Using local fallback mode.")
            self._client = None
        else:
            self._client = get_supabase_client()

    def load_portfolio(self) -> pd.DataFrame:
        """Fetches active and historical portfolio listings from the live Supabase database."""
        if not self._client:
            return pd.DataFrame(columns=PORTFOLIO_COLUMNS)

        try:
            data = self._client.select("current_portfolio")
            if not data:
                return pd.DataFrame(columns=PORTFOLIO_COLUMNS)
            return pd.DataFrame(data)
        except Exception as e:
            self.logger.error("Failed to sync portfolio state from Supabase: %s", e)
            return pd.DataFrame(columns=PORTFOLIO_COLUMNS)

    def save_portfolio_row(self, row_dict: dict) -> None:
        """Upserts a single position tracking row into Supabase based on the symbol key."""
        if not self._client:
            self.logger.info("Local Sim-Mode Save: Row updated for %s", row_dict.get("symbol"))
            return

        # Clean data types for database compliance
        clean_row = {k: (int(v) if isinstance(v, (int, round)) else float(v) if isinstance(v, float) else str(v)) 
                     for k, v in row_dict.items() if not pd.isna(v)}

        try:
            self._client.upsert("current_portfolio", clean_row, on_conflict="symbol")
            self.logger.info("Successfully updated cloud database entry for %s", clean_row.get("symbol"))
        except Exception as e:
            self.logger.error("Failed to push row state to Supabase: %s", e)

    def save_portfolio(self, portfolio_df: pd.DataFrame) -> None:
        """Upserts the entire portfolio DataFrame into Supabase."""
        if not self._client:
            self.logger.info("Local Sim-Mode Save: Portfolio with %d rows", len(portfolio_df))
            return

        if portfolio_df.empty:
            self.logger.warning("Empty portfolio DataFrame provided. Skipping save.")
            return

        try:
            # Convert DataFrame to list of dicts, cleaning NaN values
            records = []
            for _, row in portfolio_df.iterrows():
                clean_row = {}
                for col in portfolio_df.columns:
                    val = row[col]
                    if pd.isna(val):
                        continue
                    if isinstance(val, (int, round)):
                        clean_row[col] = int(val)
                    elif isinstance(val, float):
                        clean_row[col] = float(val)
                    else:
                        clean_row[col] = str(val)
                records.append(clean_row)

            if records:
                self._client.upsert("current_portfolio", records, on_conflict="symbol")
                self.logger.info("Successfully saved %d portfolio rows to Supabase.", len(records))
        except Exception as e:
            self.logger.error("Failed to batch save portfolio to Supabase: %s", e)
