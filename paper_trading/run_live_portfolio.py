"""
Main trading cycle orchestrator.
Handles RL exits, PQS candidate entries, and portfolio persistence.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from paper_trading.live_candidate_engine import LiveCandidateEngine
from paper_trading.logging_config import get_system_logger
from paper_trading.metrics import record_cycle_error, record_cycle_start, update_cycle_metrics
from paper_trading.portfolio_engine import PortfolioEngine
from paper_trading.retry_utils import retry_call
from paper_trading.rotation_engine import RotationEngine
from paper_trading.state_manager import PORTFOLIO_COLUMNS, StateManager
from paper_trading.supabase_logger import SupabaseLogger

try:
    # Pointing to updated module naming convention
    from paper_trading.rl_exit import RLExitEngine
except ImportError:
    try:
        from paper_trading.rl_exit_engine import RLExitEngine
    except Exception:  # pragma: no cover - protects cloud startup if torch/dependencies are missing
        class RLExitEngine:  # type: ignore[no-redef]
            def evaluate_positions(self, open_positions: pd.DataFrame) -> pd.DataFrame:
                return pd.DataFrame(
                    [
                        {
                            "timestamp": pd.Timestamp.now("UTC").isoformat(),
                            "symbol": str(row["symbol"]),
                            "decision": "HOLD",
                            "reason": "rl_dependency_unavailable",
                        }
                        for _, row in open_positions.iterrows()
                    ],
                    columns=["timestamp", "symbol", "decision", "reason"],
                )


def apply_rl_exits(portfolio_df: pd.DataFrame, decisions_df: pd.DataFrame) -> pd.DataFrame:
    if portfolio_df.empty or decisions_df.empty:
        return portfolio_df
    if "close_reason" not in portfolio_df.columns:
        portfolio_df["close_reason"] = pd.Series(dtype="object")

    sells = set(decisions_df[decisions_df["decision"] == "SELL"]["symbol"].tolist())
    mask = (portfolio_df["status"] == "OPEN") & (portfolio_df["symbol"].isin(sells))

    portfolio_df.loc[mask, "status"] = "CLOSED_RL"
    portfolio_df.loc[mask, "close_reason"] = "rl_exit"
    portfolio_df.loc[mask, "exit_timestamp"] = pd.Timestamp.utcnow()
    return portfolio_df


def build_snapshot(portfolio_df: pd.DataFrame) -> dict:
    now = pd.Timestamp.now("UTC")
    open_positions = portfolio_df[portfolio_df["status"] == "OPEN"].copy() if not portfolio_df.empty else pd.DataFrame()
    invested = float((open_positions["entry_price"] * open_positions["quantity"]).sum()) if not open_positions.empty else 0.0
    return {
        "timestamp": now.isoformat(),
        "cash": 1_000_000.0 - invested,
        "equity": 1_000_000.0,
        "positions": int(len(open_positions)),
        "daily_pnl": 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live paper trading cycle.")
    parser.add_argument("--dry-run", action="store_true", help="Skip Supabase writes.")
    parser.add_argument("--slot", default="CYCLE", help="Cycle identifier.")
    args = parser.parse_args()

    start_time = time.time()
    logger = get_system_logger("paper_trading.live_cycle")
    state_manager = StateManager()
    
    # 1. Start the run heartbeat log
    record_cycle_start()
    logger.info("Cycle start slot=%s dry_run=%s", args.slot, args.dry_run)

    try:
        # Step 1: Generate candidates via PQS ranking matrix
        candidate_engine = LiveCandidateEngine()
        candidates = candidate_engine.generate_candidates()

        if candidates.empty:
            logger.warning("No candidates generated. Skipping cycle.")
            return

        # Step 2: Upload top 100 PQS rankings to Supabase for the frontend layout table
        if not args.dry_run:
            try:
                supabase_logger = SupabaseLogger()
                top_rankings = candidates.sort_values("pqs", ascending=False).head(100)
                ranking_rows = []
                for idx, row in top_rankings.reset_index(drop=True).iterrows():
                    ranking_rows.append({
                        "timestamp": pd.Timestamp.now("UTC").isoformat(),
                        "rank": idx + 1,
                        "symbol": str(row["symbol"]),
                        "pqs": float(row["pqs"]),
                        "last_price": float(row.get("last_price", 0.0)),
                    })
                supabase_logger.log_pqs_rankings(ranking_rows)
            except Exception as e:
                logger.warning("Failed to upload PQS rankings to Supabase: %s", e)

        # Step 3: Update portfolio matrix entries using active slots
        portfolio_engine = PortfolioEngine()
        portfolio = portfolio_engine.update_from_candidates(candidates)
        open_positions = portfolio[portfolio["status"] == "OPEN"].copy() if not portfolio.empty else pd.DataFrame()

        # Step 4: Evaluate DQN neural network configurations for active holding exits
        rl_engine = RLExitEngine()
        exit_decisions = rl_engine.evaluate_positions(open_positions)
        portfolio = apply_rl_exits(portfolio, exit_decisions)

        # Step 5: Check asset swaps (safely bypassed via Option 2 environment variable check)
        rotation_engine = RotationEngine()
        portfolio, rotation_log = rotation_engine.evaluate_and_rotate(portfolio, candidates)

        # Step 6: Core save update loop to local CSV backup file
        state_manager.save_portfolio(portfolio)

        # Step 7: Push active positions data streams to Supabase backend endpoints
        if not args.dry_run:
            try:
                supabase_logger = SupabaseLogger()
                candidate_prices = (
                    candidates[["symbol", "last_price"]]
                    .drop_duplicates(subset=["symbol"])
                    .set_index("symbol")["last_price"]
                    .to_dict()
                )

                open_positions_rows = []
                for _, row in portfolio[portfolio["status"] == "OPEN"].iterrows():
                    symbol = str(row["symbol"])
                    current_price = float(candidate_prices.get(symbol, row["entry_price"]))
                    entry_price = float(row["entry_price"])
                    quantity = int(row["quantity"])
                    cost_basis = entry_price * quantity
                    market_value = current_price * quantity
                    unrealized_pnl = market_value - cost_basis

                    open_positions_rows.append({
                        "timestamp": pd.Timestamp.now("UTC").isoformat(),
                        "symbol": symbol,
                        "entry_timestamp": pd.Timestamp(row["entry_timestamp"]).isoformat(),
                        "entry_price": entry_price,
                        "quantity": quantity,
                        "slot_id": int(row["slot_id"]),
                        "slot_capital": float(row["slot_capital"]),
                        "pqs": float(row["pqs"]),
                        "status": str(row.get("status", "OPEN")),
                        "current_price": current_price,
                        "market_value": market_value,
                        "unrealized_pnl": unrealized_pnl,
                        "unrealized_pnl_pct": (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0,
                    })
                
                if open_positions_rows:
                    supabase_logger.log_open_positions(open_positions_rows)

                # Step 8: Calculate core portfolio valuation snapshot entries
                snapshot = build_snapshot(portfolio)
                supabase_logger.log_portfolio_snapshots([snapshot])

                if not rotation_log.empty:
                    logger.info("Rotations triggered: %d", len(rotation_log))

            except Exception as e:
                logger.warning("Supabase sync pipeline encountered data transfer dropped: %s", e)

        # Step 9: Finalize 2-hour performance telemetry updates
        cycle_duration = round(time.time() - start_time, 3)
        trades_executed = len(exit_decisions) if not exit_decisions.empty else 0
        exits_triggered = int((exit_decisions["decision"] == "SELL").sum()) if not exit_decisions.empty else 0
        rotations_triggered = len(rotation_log) if not rotation_log.empty else 0
        
        update_cycle_metrics(
            portfolio=portfolio,
            trades_executed=trades_executed,
            exits_triggered=exits_triggered,
            rotations_triggered=rotations_triggered,
            cycle_duration_seconds=cycle_duration,
            last_processed_slot=args.slot,
        )

        logger.info(
            "Cycle complete slot=%s candidates=%s exits=%s rotations=%s duration=%ss",
            args.slot, len(candidates), exits_triggered, rotations_triggered, cycle_duration,
        )

    except Exception as exc:
        record_cycle_error(str(exc))
        logger.exception("Cycle failed execution slot=%s", args.slot)
        raise


if __name__ == "__main__":
    main()
