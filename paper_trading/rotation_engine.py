from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from paper_trading.common import ensure_parent

# Safe initialization block for Supabase Cloud Sync
try:
    from supabase import create_client, Client
    SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("VITE_SUPABASE_ANON_KEY", "")
    supabase_client: Client | None = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None
except ImportError:
    supabase_client = None


@dataclass
class RotationConfig:
    gap: float = 0.25
    rotation_log_file: Path = Path("logs/rotation_log.csv")


class RotationEngine:
    def __init__(self, config: RotationConfig | None = None) -> None:
        self.config = config or RotationConfig()

    def _sync_rotation_to_supabase(self, log_df: pd.DataFrame) -> None:
        """
        Pushes rotation swap histories directly into your Supabase log table
        so your React dashboard can render a live activity stream of asset handoffs.
        """
        if not supabase_client or log_df.empty:
            return

        try:
            records = []
            for _, row in log_df.iterrows():
                ts = row["timestamp"]
                ts_iso = ts.isoformat() if isinstance(ts, datetime) else str(ts)
                
                records.append({
                    "timestamp": ts_iso,
                    "old_symbol": str(row["old_symbol"]),
                    "new_symbol": str(row["new_symbol"]),
                    "old_tqs": float(row["old_tqs"]),
                    "new_tqs": float(row["new_tqs"])
                })
            
            if records:
                supabase_client.table("rotation_logs").insert(records).execute()
        except Exception as err:
            print(f"Supabase rotation logging sync encountered an interception failure: {err}")

    def evaluate_and_rotate(
        self,
        portfolio_df: pd.DataFrame,
        candidates_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:

        # --- OPTION 2 TOGGLE SWITCH ---
        # The rotation logic will stay paused by default unless explicitly flipped on.
        if os.environ.get("ENABLE_ROTATION", "false").lower() != "true":
            return portfolio_df, pd.DataFrame(
                columns=[
                    "timestamp",
                    "old_symbol",
                    "new_symbol",
                    "old_tqs",
                    "new_tqs",
                ]
            )

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
        open_symbols = set(open_positions["symbol"].tolist())
        ranked_candidates = candidates_df.sort_values("pqs", ascending=False)

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
        current_time = pd.Timestamp.now(tz=timezone.utc)

        if new_symbol != old_symbol and new_tqs > old_tqs + self.config.gap:
            idx = holding.name

            portfolio_df.loc[idx, "status"] = "CLOSED_ROTATION"
            portfolio_df.loc[idx, "close_reason"] = "rotation"
            portfolio_df.loc[idx, "exit_timestamp"] = current_time

            entry = {
                "symbol": new_symbol,
                "entry_timestamp": current_time,
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
                    "timestamp": current_time,
                    "old_symbol": old_symbol,
                    "new_symbol": new_symbol,
                    "old_tqs": old_tqs,
                    "new_tqs": new_tqs,
                }
            )

        log_df = pd.DataFrame(logs)

        if not log_df.empty:
            self._append_logs(log_df)
            self._sync_rotation_to_supabase(log_df)

        return portfolio_df, log_df

    def _append_logs(self, new_logs: pd.DataFrame) -> None:
        ensure_parent(self.config.rotation_log_file)

        if self.config.rotation_log_file.exists():
            try:
                old = pd.read_csv(self.config.rotation_log_file)
                out = pd.concat([old, new_logs], ignore_index=True)
            except Exception:
                out = new_logs
        else:
            out = new_logs

        out.to_csv(self.config.rotation_log_file, index=False)
