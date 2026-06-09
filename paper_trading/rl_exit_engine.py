from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from stable_baselines3 import DQN

from paper_trading.logging_config import get_system_logger

# Safe initialization block for Supabase Cloud Sync
try:
    from supabase import create_client, Client
    SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("VITE_SUPABASE_ANON_KEY", "")
    supabase_client: Client | None = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None
except ImportError:
    supabase_client = None

RL_OBSERVATION_FEATURES = [
    "bars_since_entry", "pnl_pct", "peak_pnl_so_far", "drawdown_from_peak",
    "momentum_score", "trend_strength", "volatility_score", "compression_score",
    "momentum_persistence", "higher_low_strength", "price_position", "ATR",
    "ema_spread", "delta_momentum_1", "delta_trend_1", "delta_ema_spread_1",
    "delta_price_position_1", "delta_momentum_3", "delta_trend_3", "delta_ema_spread_3"
]


@dataclass
class RLExitConfig:
    model_path: Path = Path("models/rl_trade_exit_agent_tqs25.zip")
    hourly_data_dir: Path = Path("data/2h")


class RLExitEngine:
    def __init__(self, config: RLExitConfig | None = None) -> None:
        self.config = config or RLExitConfig()
        self.logger = get_system_logger("paper_trading.rl_exit")
        self.model = self._load_model()

    def _load_model(self) -> DQN:
        if not self.config.model_path.exists():
            raise FileNotFoundError(f"Missing DQN model weights archive file at: {self.config.model_path}")
        self.logger.info("DQN Exit Agent successfully verified and loaded into execution space.")
        return DQN.load(str(self.config.model_path))

    def _sync_decisions_to_supabase(self, decisions_df: pd.DataFrame) -> None:
        """
        NEW: Pushes RL model output decisions straight to your Supabase log network 
        so your React dashboard can trigger live UI exit flags and telemetry alerts.
        """
        if not supabase_client or decisions_df.empty:
            return

        try:
            records = []
            for _, row in decisions_df.iterrows():
                ts = row["timestamp"]
                ts_iso = ts.isoformat() if isinstance(ts, datetime) else str(ts)
                
                records.append({
                    "symbol": str(row["symbol"]),
                    "decision": str(row["decision"]),
                    "reason": str(row["reason"]),
                    "updated_at": ts_iso
                })
            
            if records:
                # Upsert updates matching symbol keys instantly
                supabase_client.table("exit_decisions").upsert(records, on_conflict="symbol").execute()
                self.logger.info("Synchronized %d execution decisions to Supabase exit_decisions table.", len(records))
        except Exception as err:
            self.logger.error("Supabase exit_decisions upload loop intercept error: %s", err)

    def evaluate_positions(self, open_positions: pd.DataFrame | None = None) -> pd.DataFrame:
        """
        Processes each position through the DQN model matrix to output HOLD or SELL decisions.
        
        Pulls down active tracking parameters from Supabase if no dataframe is supplied.
        """
        # CHANGED: Pull active tracking stats straight from Supabase if none are passed in
        if open_positions is None:
            if supabase_client:
                try:
                    self.logger.info("Pulling raw position telemetry states from cloud table...")
                    response = supabase_client.table("open_positions").select("*").eq("status", "OPEN").execute()
                    if response.data:
                        open_positions = pd.DataFrame(response.data)
                    else:
                        open_positions = pd.DataFrame()
                except Exception as e:
                    self.logger.error("Failed to extract active cloud status states: %s", e)
                    open_positions = pd.DataFrame()
            
            # Local fallback step
            if open_positions is None:
                open_positions = pd.DataFrame()

        if open_positions.empty:
            return pd.DataFrame(columns=["timestamp", "symbol", "decision", "reason"])

        decisions = []

        for _, row in open_positions.iterrows():
            symbol = str(row["symbol"])
            parquet_path = self.config.hourly_data_dir / f"{symbol}.parquet"
            
            current_time_iso = datetime.now(timezone.utc).isoformat()
            
            if not parquet_path.exists():
                decisions.append({"timestamp": current_time_iso, "symbol": symbol, "decision": "HOLD", "reason": "data_absent"})
                continue
                
            df_file = pd.read_parquet(parquet_path)
            if df_file.empty:
                decisions.append({"timestamp": current_time_iso, "symbol": symbol, "decision": "HOLD", "reason": "empty_frame"})
                continue

            latest_bar = df_file.iloc[-1]
            
            # Extract historical structural states calculated from running metrics updates
            try:
                state_dict = {f: float(latest_bar[f]) for f in RL_OBSERVATION_FEATURES if f not in ["bars_since_entry", "pnl_pct", "peak_pnl_so_far", "drawdown_from_peak"]}
                
                # CHANGED: Safely parse calculated parameters, fallback to 0.0 if column field is absent
                state_dict["bars_since_entry"] = float(row.get("bars_since_entry", 0.0))
                state_dict["pnl_pct"] = float(row.get("pnl_pct", 0.0))
                state_dict["peak_pnl_so_far"] = float(row.get("peak_pnl_so_far", 0.0))
                state_dict["drawdown_from_peak"] = float(row.get("drawdown_from_peak", 0.0))

                obs_vector = np.array([state_dict[f] for f in RL_OBSERVATION_FEATURES], dtype=np.float32)
                action, _ = self.model.predict(obs_vector, deterministic=True)
                
                decision = "SELL" if int(action) == 1 else "HOLD"
                reason = "rl_model_dqn_inference"
            except Exception as e:
                decision = "HOLD"
                reason = f"error_{str(e)}"

            decisions.append({
                "timestamp": current_time_iso,
                "symbol": symbol,
                "decision": decision,
                "reason": reason
            })

        decisions_df = pd.DataFrame(decisions)
        
        # CHANGED: Save the decision outputs to your cloud database table automatically
        self._sync_decisions_to_supabase(decisions_df)
        
        return decisions_df


def main() -> None:
    engine = RLExitEngine()
    out = engine.evaluate_positions()
    print(f"Decisions calculated through DQN matrix rows: {len(out)}")


if __name__ == "__main__":
    main()
