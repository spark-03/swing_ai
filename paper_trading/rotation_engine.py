from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from paper_trading.common import ensure_parent


@dataclass
class RotationConfig:
    gap: float = 0.25
    rotation_log_file: Path = Path("logs/rotation_log.csv")


class RotationEngine:
    def __init__(self, config: RotationConfig | None = None) -> None:
        self.config = config or RotationConfig()

    def evaluate_and_rotate(
        self,
        portfolio_df: pd.DataFrame,
        candidates_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:

        if portfolio_df.empty or candidates_df.empty:
            return portfolio_df, pd.DataFrame(
                columns=[
                    "timestamp",
                    "old_symbol",
                    "new_symbol",
                    "old_tqs",
                    "new_tqs",
                ]
            )

        open_mask = portfolio_df["status"] == "OPEN"
        open_positions = portfolio_df[open_mask].copy()

        if open_positions.empty:
            return portfolio_df, pd.DataFrame(
                columns=[
                    "timestamp",
                    "old_symbol",
                    "new_symbol",
                    "old_tqs",
                    "new_tqs",
                ]
            )

        holding = open_positions.sort_values("pqs", ascending=True).iloc[0]

        open_symbols = set(
            open_positions["symbol"].tolist()
        )

        ranked_candidates = candidates_df.sort_values(
            "pqs",
            ascending=False
        )

        best_candidate = None

        for _, candidate in ranked_candidates.iterrows():

            candidate_symbol = str(candidate["symbol"])

            if candidate_symbol in open_symbols:
                continue

            best_candidate = candidate
            break

        if best_candidate is None:
            return portfolio_df, pd.DataFrame(
                columns=[
                    "timestamp",
                    "old_symbol",
                    "new_symbol",
                    "old_tqs",
                    "new_tqs",
                ]
            )

        old_tqs = float(holding["pqs"])
        new_tqs = float(best_candidate["pqs"])
        old_symbol = str(holding["symbol"])
        new_symbol = str(best_candidate["symbol"])

        logs = []

        if new_symbol != old_symbol and new_tqs > old_tqs + self.config.gap:

            idx = holding.name

            portfolio_df.loc[idx, "status"] = "CLOSED_ROTATION"
            portfolio_df.loc[idx, "close_reason"] = "rotation"
            portfolio_df.loc[idx, "exit_timestamp"] = pd.Timestamp.utcnow()

            entry = {
                "symbol": new_symbol,
                "entry_timestamp": pd.Timestamp.utcnow(),
                "entry_price": float(best_candidate.get("last_price", 0.0)),
                "quantity": int(holding["quantity"]),
                "slot_id": int(holding["slot_id"]),
                "slot_capital": float(holding["slot_capital"]),
                "pqs": new_tqs,
                "status": "OPEN",
            }

            portfolio_df = pd.concat(
                [portfolio_df, pd.DataFrame([entry])],
                ignore_index=True,
            )

            logs.append(
                {
                    "timestamp": pd.Timestamp.utcnow(),
                    "old_symbol": old_symbol,
                    "new_symbol": new_symbol,
                    "old_tqs": old_tqs,
                    "new_tqs": new_tqs,
                }
            )

        log_df = pd.DataFrame(logs)

        if not log_df.empty:
            self._append_logs(log_df)

        return portfolio_df, log_df

    def _append_logs(self, new_logs: pd.DataFrame) -> None:
        ensure_parent(self.config.rotation_log_file)

        if self.config.rotation_log_file.exists():
            old = pd.read_csv(self.config.rotation_log_file)
            out = pd.concat([old, new_logs], ignore_index=True)
        else:
            out = new_logs

        out.to_csv(self.config.rotation_log_file, index=False)