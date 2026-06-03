import argparse
import time
import pandas as pd
from paper_trading.state_manager import CloudStateManager, PORTFOLIO_COLUMNS
from paper_trading.live_candidate_engine import LiveCandidateEngine
from paper_trading.rl_exit_engine import RLExitEngine
from paper_trading.logging_config import get_system_logger

def main():
    parser = argparse.ArgumentParser(description="Spark-03 Local Core Matrix Engine Workflow Loop.")
    parser.add_argument("--slot", required=True, help="Processing cycle timeframe context ID string.")
    args = parser.parse_args()

    logger = get_system_logger("paper_trading.orchestrator")
    logger.info("Initializing trading matrix tick execution sequence for slot=%s", args.slot)

    state_mgr =CloudStateManager()
    portfolio_df = state_mgr.load_portfolio()

    # Split open records from historic archive blocks
    if not portfolio_df.empty:
        open_positions = portfolio_df[portfolio_df["status"] == "OPEN"].copy()
        closed_archive = portfolio_df[portfolio_df["status"] != "OPEN"].copy()
    else:
        open_positions = pd.DataFrame(columns=PORTFOLIO_COLUMNS)
        closed_archive = pd.DataFrame(columns=PORTFOLIO_COLUMNS)

    # ==========================================================================
    # STEP 1: PROCESSING CURRENT OPEN REINFORCEMENT ALGORITHM EXITS
    # ==========================================================================
    active_remaining = []
    
    if not open_positions.empty:
        logger.info("Syncing indicators and tracking vectors across %d open positions...", len(open_positions))
        rl_engine = RLExitEngine()
        
        # Step through every position to calculate live peak high prices before inference loops
        for _, row in open_positions.iterrows():
            sym = row["symbol"]
            parquet_path = Path(f"data/live/2h/{sym}.parquet")
            
            if not parquet_path.exists():
                active_remaining.append(row)
                continue
                
            df_file = pd.read_parquet(parquet_path)
            if df_file.empty:
                active_remaining.append(row)
                continue

            latest_bar = df_file.iloc[-1]
            latest_close = float(latest_bar["close"])
            latest_high = float(latest_bar["high"])
            entry_price = float(row["entry_price"])

            # Increment candle bars indicator counter
            row["bars_since_entry"] = int(row["bars_since_entry"]) + 1
            
            # Formulate peak calculations matching DQN reward expectations
            current_pnl = ((latest_close - entry_price) / entry_price) * 100.0
            high_pnl = ((latest_high - entry_price) / entry_price) * 100.0
            
            previous_peak = float(row["peak_pnl_so_far"]) if not pd.isna(row["peak_pnl_so_far"]) else -999.0
            updated_peak = max(previous_peak, high_pnl)
            
            row["pnl_pct"] = current_pnl
            row["peak_pnl_so_far"] = updated_peak
            row["drawdown_from_peak"] = updated_peak - current_pnl

        updated_open_df = pd.DataFrame(open_positions)
        # Evaluate states directly via model load matrix
        exit_decisions = rl_engine.evaluate_positions(updated_open_df)

        for _, row in updated_open_df.iterrows():
            sym = row["symbol"]
            decision_row = exit_decisions[exit_decisions["symbol"] == sym]
            
            if not decision_row.empty and decision_row.iloc[0]["decision"] == "SELL":
                logger.info("DQN SIGNAL: Liquidating allocation model slot position for: %s", sym)
                row["status"] = "CLOSED"
                closed_archive = pd.concat([closed_archive, pd.DataFrame([row])], ignore_index=True)
            else:
                active_remaining.append(row)

    current_open_df = pd.DataFrame(active_remaining) if active_remaining else pd.DataFrame(columns=PORTFOLIO_COLUMNS)

    # ==========================================================================
    # STEP 2: PROCESSING STRATEGIC POSITION VACANCY ENTRYS (MAX 3)
    # ==========================================================================
    vacant_slots = 3 - len(current_open_df)
    logger.info("Current portfolio state allocation counts: %d Open. Vacancies remaining: %d", len(current_open_df), vacant_slots)

    if vacant_slots > 0:
        candidate_eng = LiveCandidateEngine()
        ranked_candidates = candidate_eng.generate_candidates()

        if not ranked_candidates.empty:
            for _, candidate in ranked_candidates.iterrows():
                if vacant_slots <= 0:
                    break
                    
                sym = candidate["symbol"]
                # Duplicate Protection check
                if not current_open_df.empty and sym in current_open_df["symbol"].values:
                    continue

                logger.info("PQS ALPHA TRACER: Executing trade entry buy allocation order for %s", sym)
                
                new_position = {
                    "symbol": sym,
                    "entry_timestamp": str(pd.Timestamp.utcnow()),
                    "entry_price": float(candidate["close"]),
                    "quantity": 100,  # Default testing baseline assignment metric
                    "slot_id": 3 - vacant_slots,
                    "slot_capital": 50000.0,
                    "pqs": float(candidate["pqs"]),
                    "status": "OPEN",
                    "bars_since_entry": 0,
                    "pnl_pct": 0.0,
                    "peak_pnl_so_far": 0.0,
                    "drawdown_from_peak": 0.0
                }
                
                current_open_df = pd.concat([current_open_df, pd.DataFrame([new_position])], ignore_index=True)
                vacant_slots -= 1

    # Save running structures atomically back onto disk tracking sheets
    final_state_ledger = pd.concat([current_open_df, closed_archive], ignore_index=True)
    state_mgr.save_portfolio(final_state_ledger)
    logger.info("Pipeline processing tick successfully updated for sequence %s.", args.slot)

if __name__ == "__main__":
    main()
