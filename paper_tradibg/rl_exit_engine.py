from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from stable_baselines3 import DQN
from paper_trading.logging_config import get_system_logger

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
    hourly_data_dir: Path = Path("data/live/2h")

class RLExitEngine:
    def __init__(self, config: RLExitConfig | None = None) -> None:
        self.config = config or RLExitConfig()
        self.logger = get_system_logger("paper_trading.rl_exit")
        self.model = self._load_model()
        self.expected_dim = len(RL_OBSERVATION_FEATURES)

    def _load_model(self) -> DQN:
        if not self.config.model_path.exists():
            raise FileNotFoundError(f"Production DQN Model weights absent at: {self.config.model_path}")
        self.logger.info("Loading Production DQN Exit Agent: %s", self.config.model_path)
        return DQN.load(str(self.config.model_path))

    def evaluate_and_update_states(self, open_positions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Processes open positions, reads their 2H data, updates state counters,
        and generates exit decisions using the DQN model.
        """
        decisions = []
        if open_positions.empty:
            return open_positions, pd.DataFrame(columns=["timestamp", "symbol", "decision", "reason"])

        updated_rows = []

        for _, row in open_positions.iterrows():
            symbol = str(row["symbol"])
            parquet_path = self.config.hourly_data_dir / f"{symbol}.parquet"
            
            if not parquet_path.exists():
                self.logger.warning("Parquet data missing for active asset %s, skipping exit checks.", symbol)
                updated_rows.append(row)
                continue
                
            df_file = pd.read_parquet(parquet_path)
            if df_file.empty:
                updated_rows.append(row)
                continue

            latest_bar = df_file.iloc[-1]
            latest_close = float(latest_bar["close"])
            latest_high = float(latest_bar["high"])
            entry_price = float(row["entry_price"])

            # Update State Variables
            current_bars = int(row["bars_since_entry"]) + 1
            current_pnl_pct = ((latest_close - entry_price) / entry_price) * 100.0
            high_pnl_pct = ((latest_high - entry_price) / entry_price) * 100.0
            
            previous_peak = float(row["peak_pnl_so_far"]) if not pd.isna(row["peak_pnl_so_far"]) else -999.0
            updated_peak = max(previous_peak, high_pnl_pct)
            current_drawdown = updated_peak - current_pnl_pct

            row["bars_since_entry"] = current_bars
            row["peak_pnl_so_far"] = updated_peak

            try:
                state_dict = {
                    "bars_since_entry": current_bars,
                    "pnl_pct": current_pnl_pct,
                    "peak_pnl_so_far": updated_peak,
                    "drawdown_from_peak": current_drawdown,
                    "momentum_score": float(latest_bar["momentum_score"]),
                    "trend_strength": float(latest_bar["trend_strength"]),
                    "volatility_score": float(latest_bar["volatility_score"]),
                    "compression_score": float(latest_bar["compression_score"]),
                    "momentum_persistence": float(latest_bar["momentum_persistence"]),
                    "higher_low_strength": float(latest_bar["higher_low_strength"]),
                    "price_position": float(latest_bar["price_position"]),
                    "ATR": float(latest_bar["ATR"]),
                    "ema_spread": float(latest_bar["ema_spread"]),
                    "delta_momentum_1": float(latest_bar["delta_momentum_1"]),
                    "delta_trend_1": float(latest_bar["delta_trend_1"]),
                    "delta_ema_spread_1": float(latest_bar["delta_ema_spread_1"]),
                    "delta_price_position_1": float(latest_bar["delta_price_position_1"]),
                    "delta_momentum_3": float(latest_bar["delta_momentum_3"]),
                    "delta_trend_3": float(latest_bar["delta_trend_3"]),
                    "delta_ema_spread_3": float(latest_bar["delta_ema_spread_3"])
                }
                
                obs_vector = np.array([state_dict[f] for f in RL_OBSERVATION_FEATURES], dtype=np.float32)
                action, _states = self.model.predict(obs_vector, deterministic=True)
                decision = "SELL" if int(action) == 1 else "HOLD"
                
            except KeyError as e:
                self.logger.error("Feature calculation failed for %s due to missing technical factor: %s", symbol, e)
                decision = "HOLD"

            decisions.append({
                "timestamp": pd.Timestamp.utcnow(),
                "symbol": symbol,
                "decision": decision,
                "reason": "rl_model_dqn"
            })
            updated_rows.append(row)

        return pd.DataFrame(updated_rows), pd.DataFrame(decisions)
