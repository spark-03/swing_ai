import os
import pandas as pd
from pathlib import Path
from paper_trading.pqs_engine import calculate_pqs
from paper_trading.logging_config import get_system_logger

class LiveCandidateEngine:
    def __init__(self, universe_file: str = "configs/nifty500_symbols.txt", data_dir: str = "data/2h"):
        self.universe_file = Path(universe_file)
        self.data_dir = Path(data_dir)
        self.logger = get_system_logger("paper_trading.candidate_engine")

    def generate_candidates(self) -> pd.DataFrame:
        """Assembles and scores technical indicators across the stock universe."""
        if not self.universe_file.exists():
            self.logger.error("Universe tracking profile empty at %s", self.universe_file)
            return pd.DataFrame()

        with open(self.universe_file, "r") as f:
            symbols = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        collected_records = []
        for sym in symbols:
            file_path = self.data_dir / f"{sym}.parquet"
            if not file_path.exists():
                continue
            
            try:
                df = pd.read_parquet(file_path)
                if df.empty:
                    continue
                
                # Capture the absolute latest state vector bar row snapshot
                latest_bar = df.iloc[-1].copy()
                latest_bar["symbol"] = sym
                collected_records.append(latest_bar)
            except Exception as e:
                self.logger.warning("Error reading parquet snapshot map for %s: %s", sym, e)

        if not collected_records:
            return pd.DataFrame()

        raw_universe_df = pd.DataFrame(collected_records)
        # Apply factor z-scoring models to rank alpha candidates
        scored_universe_df = calculate_pqs(raw_universe_df)
        
        return scored_universe_df.sort_values(by="pqs", ascending=False)
