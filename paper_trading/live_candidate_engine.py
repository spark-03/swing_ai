from pathlib import Path

import pandas as pd

from paper_trading.logging_config import get_system_logger
from paper_trading.pqs_engine import calculate_pqs


class LiveCandidateEngine:

    def __init__(self, universe_file: str = "ind_nifty500list.csv", data_dir: str = "data/2h") -> None:
        self.universe_file = Path(universe_file)
        self.data_dir = Path(data_dir)
        self.logger = get_system_logger("paper_trading.candidate_engine")

    def _load_symbols(self) -> list[str]:
        """Load symbols from the NIFTY CSV or the legacy text universe."""
        if self.universe_file.suffix.lower() == ".csv":
            df = pd.read_csv(self.universe_file)
            if "Symbol" not in df.columns:
                self.logger.error("Universe CSV missing Symbol column: %s", self.universe_file)
                return []
            return df["Symbol"].dropna().astype(str).str.strip().tolist()

        with open(self.universe_file, encoding="utf-8") as f:
            return [
                line.strip().removesuffix("-EQ")
                for line in f
                if line.strip() and not line.startswith("#")
            ]

    def generate_candidates(self) -> pd.DataFrame:
        """Assembles and scores technical indicators across the stock universe."""
        if not self.universe_file.exists():
            self.logger.error("Universe tracking profile empty at %s", self.universe_file)
            return pd.DataFrame()

        symbols = self._load_symbols()
        latest_scored_records = []

        for sym in symbols:
            file_path = self.data_dir / f"{sym}.parquet"
            if not file_path.exists():
                continue

            try:
                # 1. Load the rolling buffer (e.g., last 60 candles)
                df = pd.read_parquet(file_path)
                if df.empty or len(df) < 2:
                    continue

                # 2. Add the symbol identifier needed for grouping
                df = df.copy()
                df["symbol"] = sym

                # 3. Calculate PQS immediately using this asset's historical window context
                scored_df = calculate_pqs(df)

                # 4. NOW capture the absolute latest scored row snapshot
                latest_bar = scored_df.iloc[-1].copy()
                latest_scored_records.append(latest_bar)

            except Exception as e:
                self.logger.warning("Error reading parquet snapshot map for %s: %s", sym, e)

        if not latest_scored_records:
            return pd.DataFrame()

        # 5. Combine the latest snapshot from each stock into a cross-sectional ranking table
        final_universe_df = pd.DataFrame(latest_scored_records)
        
        return final_universe_df.sort_values(by="pqs", ascending=False).reset_index(drop=True)
