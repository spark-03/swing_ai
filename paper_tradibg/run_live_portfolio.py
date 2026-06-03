from __future__ import annotations

import argparse
import time
import pandas as pd

from paper_trading.live_candidate_engine import LiveCandidateEngine
from paper_trading.logging_config import get_system_logger
from paper_trading.metrics import record_cycle_error, record_cycle_start, update_cycle_metrics
from paper_trading.portfolio_engine import PortfolioEngine
from paper_trading.rl_exit_engine import RLExitEngine
from paper_trading.state_manager import CloudStateManager
from paper_trading.supabase_logger import SupabaseLogger

def main() -> int:
    parser = argparse.ArgumentParser(description="PQS Entry + DQN Exit Production Engine Loop.")
    parser.add_argument("--slot", required=True, help="Current time slot ID string (e.g., 2026-06-03 11:15)")
    args = parser.parse_args()

    logger = get_system_logger("paper_trading.orchestrator")
    logger.info("Initializing trading cycle execution for slot=%s", args.slot)
    cycle_started = time.monotonic()
    
    record_cycle_start()
    supabase_logger = SupabaseLogger()
    state_manager = CloudStateManager()

    try:
        candidate_engine = LiveCandidateEngine()
        candidates = candidate_engine.generate_candidates()
        if candidates.empty:
            logger.warning("No fresh market candidates computed for this cycle context.")
            return 0

        portfolio_df = state_manager.load_portfolio()
        if portfolio_df.empty:
            open_positions = pd.DataFrame()
            historical_closed = pd.DataFrame()
        else:
            open_mask = portfolio_df["status"] == "OPEN"
            open_positions = portfolio_df[open_mask].copy()
            historical_closed = portfolio_df[~open_mask].copy()

        rl_engine = RLExitEngine()
        updated_open, exit_decisions = rl_engine.evaluate_and_update_states(open_positions)

        active_remaining = []
        supabase_exit_rows = []
        
        if not exit_decisions.empty:
            for _, row in updated_open.iterrows():
                symbol = row["symbol"]
                signal = exit_decisions[exit_decisions["symbol"] == symbol].iloc[0]["decision"]
                
                if signal == "SELL":
                    row["status"] = "CLOSED"
                    row["exit_timestamp"] = str(pd.Timestamp.utcnow())
                    row["close_reason"] = "rl_model"
                    historical_closed = pd.concat([historical_closed, pd.DataFrame([row])], ignore_index=True)
                    
                    supabase_exit_rows.append({
                        "symbol": symbol,
                        "action": "SELL",
                        "price": float(row["entry_price"]),
                        "reason": "rl_model_dqn",
                        "timestamp": str(pd.Timestamp.utcnow())
                    })
                    state_manager.save_portfolio_row(row.to_dict())
                    logger.info("DQN Signal: Executing exit liquidation for %s", symbol)
                else:
                    active_remaining.append(row)
                    state_manager.save_portfolio_row(row.to_dict())

        current_open_df = pd.DataFrame(active_remaining) if active_remaining else pd.DataFrame()

        free_slots = 3 - len(current_open_df)
        
        if free_slots > 0:
            portfolio_engine = PortfolioEngine()
            updated_portfolio = portfolio_engine.update_from_candidates(candidates)
            
            if not updated_portfolio.empty:
                if current_open_df.empty:
                    new_open_mask = updated_portfolio["status"] == "OPEN"
                else:
                    new_open_mask = (updated_portfolio["status"] == "OPEN") & (~updated_portfolio["symbol"].isin(current_open_df["symbol"]))
                
                newly_bought = updated_portfolio[new_open_mask].copy()
                
                if not newly_bought.empty:
                    newly_bought["bars_since_entry"] = 0
                    newly_bought["peak_pnl_so_far"] = 0.0
                    
                    current_open_df = pd.concat([current_open_df, newly_bought], ignore_index=True)
                    
                    buy_rows = []
                    for _, b_row in newly_bought.iterrows():
                        b_dict = b_row.to_dict()
                        state_manager.save_portfolio_row(b_dict)
                        buy_rows.append({
                            "symbol": b_dict["symbol"],
                            "action": "BUY",
                            "price": float(b_dict["entry_price"]),
                            "reason": "ranked_candidate_pqs",
                            "timestamp": str(pd.Timestamp.utcnow())
                        })
                    supabase_logger.log_paper_trades(buy_rows)

        if supabase_exit_rows:
            supabase_logger.log_paper_trades(supabase_exit_rows)

        duration = time.monotonic() - cycle_started
        
        final_portfolio_state = pd.concat([current_open_df, historical_closed], ignore_index=True) if not current_open_df.empty or not historical_closed.empty else pd.DataFrame()
        
        update_cycle_metrics(
            portfolio=final_portfolio_state,
            trades_executed=len(supabase_exit_rows) + (len(current_open_df) - len(active_remaining) if not current_open_df.empty else 0),
            exits_triggered=len(supabase_exit_rows),
            rotations_triggered=0,
            cycle_duration_seconds=duration,
            last_processed_slot=args.slot
        )
        
        logger.info("Execution complete for cycle %s.", args.slot)

    except Exception as exc:
        record_cycle_error(str(exc))
        logger.exception("Trading pipeline execution sequence tracking crashed for slot=%s", args.slot)
        return 1

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
