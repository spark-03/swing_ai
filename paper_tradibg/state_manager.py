import os
import pandas as pd
from pathlib import Path
from paper_trading.logging_config import get_system_logger

PORTFOLIO_COLUMNS = [
    "symbol", "entry_timestamp", "entry_price", "quantity", 
    "slot_id", "slot_capital", "pqs", "status", 
    "bars_since_entry", "pnl_pct", "peak_pnl_so_far", "drawdown_from_peak"
]

class LocalStateManager:
    def __init__(self, portfolio_file: str = "current_portfolio.csv"):
        self.portfolio_file = Path(portfolio_file)
        self.logger = get_system_logger("paper_trading.state_manager")
        self._ensure_portfolio_exists()

    def _ensure_portfolio_exists(self):
        if not self.portfolio_file.exists():
            df = pd.DataFrame(columns=PORTFOLIO_COLUMNS)
            df.to_csv(self.portfolio_file, index=False)
            self.logger.info("Initialized fresh local ledger: %s", self.portfolio_file)

    def load_portfolio(self) -> pd.DataFrame:
        """Reads the tracking registry sheet into memory safely."""
        try:
            return pd.read_csv(self.portfolio_file)
        except Exception as e:
            self.logger.error("Error loading portfolio file, returning blank layout structure: %s", e)
            return pd.DataFrame(columns=PORTFOLIO_COLUMNS)

    def save_portfolio(self, df: pd.DataFrame):
        """Atomically saves tracking frames over the active ledger spreadsheet."""
        temp_file = self.portfolio_file.with_suffix(".tmp")
        df.to_csv(temp_file, index=False)
        os.replace(temp_file, self.portfolio_file)
        self.logger.info("Local position ledger state synced smoothly.")
