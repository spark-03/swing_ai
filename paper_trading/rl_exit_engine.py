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

    def evaluate_positions(self, open_positions: pd.DataFrame) -> pd.DataFrame:
        """Processes each position through the DQN model matrix to output HOLD or SELL decisions."""
        decisions = []
        if open_positions.empty:
            return pd.DataFrame(columns=["timestamp", "symbol", "decision", "reason"])

        for _, row in open_positions.iterrows():
            symbol = str(row["symbol"])
            parquet_path = self.config.hourly_data_dir / f"{symbol}.parquet"
            
            if not parquet_path.exists():
                decisions.append({"timestamp": pd.Timestamp.utcnow(), "symbol": symbol, "decision": "HOLD", "reason": "data_absent"})
                continue
                
            df_file = pd.read_parquet(parquet_path)
            if df_file.empty:
                decisions.append({"timestamp": pd.Timestamp.utcnow(), "symbol": symbol, "decision": "HOLD", "reason": "empty_frame"})
                continue

            latest_bar = df_file.iloc[-1]
            
            # Extract historical structural states calculated from live_portfolio updates
            try:
                state_dict = {f: float(latest_bar[f]) for f in RL_OBSERVATION_FEATURES if f not in ["bars_since_entry", "pnl_pct", "peak_pnl_so_far", "drawdown_from_peak"]}
                state_dict["bars_since_entry"] = float(row["bars_since_entry"])
                state_dict["pnl_pct"] = float(row["pnl_pct"])
                state_dict["peak_pnl_so_far"] = float(row["peak_pnl_so_far"])
                state_dict["drawdown_from_peak"] = float(row["drawdown_from_peak"])

                obs_vector = np.array([state_dict[f] for f in RL_OBSERVATION_FEATURES], dtype=np.float32)
                action, _ = self.model.predict(obs_vector, deterministic=True)
                decision = "SELL" if int(action) == 1 else "HOLD"
                reason = "rl_model_dqn_inference"
            except Exception as e:
                decision = "HOLD"
                reason = f"error_{str(e)}"

            decisions.append({
                "timestamp": pd.Timestamp.utcnow(),
                "symbol": symbol,
                "decision": decision,
                "reason": reason
            })

        return pd.DataFrame(decisions)
