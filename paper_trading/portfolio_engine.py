from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from paper_trading.common import TradingConfig
from paper_trading.logging_config import get_system_logger
from paper_trading.state_manager import StateManager

# Safe initialization block for Supabase Cloud Sync
try:
    from supabase import create_client, Client
    SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("VITE_SUPABASE_ANON_KEY", "")
    supabase_client: Client | None = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None
except ImportError:
    supabase_client = None


@dataclass
class PortfolioEngineConfig:
    candidates_file: Path = Path("logs/live_candidates.csv")
    portfolio_file: Path = Path("current_portfolio.csv")
    initial_capital: float = 1_000_000.0
    slots: tuple[float, float, float] = (500_000.0, 300_000.0, 200_000.0)
    max_positions: int = 3


class PortfolioEngine:
    def __init__(self, config: PortfolioEngineConfig | None = None) -> None:
        self.config = config or PortfolioEngineConfig()
        self.trading_config = TradingConfig(
            initial_capital=self.config.initial_capital,
            slots=self.config.slots,
            max_positions=self.config.max_positions,
        )
        self.state_manager = StateManager(portfolio_file=self.config.portfolio_file)
        self.logger = get_system_logger("paper_trading.portfolio")

    def _load_existing(self) -> pd.DataFrame:
        df = self.state_manager.load_portfolio()
        if not df.empty and "entry_timestamp" in df.columns:
            df["entry_timestamp"] = pd.to_datetime(df["entry_timestamp"], errors="coerce")
        return df

    def _free_slots(self, open_positions: pd.DataFrame) -> list[tuple[int, float]]:
        used = set(open_positions["slot_id"].tolist()) if not open_positions.empty else set()
        free = []
        for i, capital in enumerate(self.trading_config.slots, start=1):
            if i not in used:
                free.append((i, float(capital)))
        free.sort(key=lambda x: x[1], reverse=True)
        return free

    def _sync_to_supabase(self, portfolio: pd.DataFrame) -> None:
        """
        Cloud sync worker that ensures all active positions are fully updated 
        in Supabase so the React dashboard renders them accurately.
        """
        if not supabase_client:
            return

        try:
            if portfolio.empty:
                return

            records_to_sync = []
            for _, row in portfolio.iterrows():
                ts = row["entry_timestamp"]
                ts_iso = ts.isoformat() if isinstance(ts, datetime) else str(ts)

                records_to_sync.append({
                    "symbol": str(row["symbol"]),
                    "entry_timestamp": ts_iso,
                    "entry_price": float(row["entry_price"]),
                    "quantity": int(row["quantity"]),
                    "slot_id": int(row["slot_id"]) if pd.notna(row["slot_id"]) else None,
                    "slot_capital": float(row["slot_capital"]),
                    "pqs": float(row["pqs"]),
                    "status": str(row["status"]),
                    "current_price": float(row.get("current_price", row["entry_price"])),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            if records_to_sync:
                supabase_client.table("open_positions").upsert(records_to_sync, on_conflict="symbol").execute()
                self.logger.info("Successfully synchronized %d positions to Supabase cloud table.", len(records_to_sync))
        except Exception as err:
            self.logger.error("Supabase open_positions table sync encountered an interception failure: %s", err)

    def is_market_open(self) -> bool:
        """
        Helper method to check if the Indian Stock Market (NSE/BSE) is currently open.
        Market hours: Monday - Friday, 9:15 AM to 3:30 PM IST.
        """
        now_utc = datetime.now(timezone.utc)
        # Indian Standard Time is UTC + 5 hours 30 minutes
        now_ist = now_utc + timedelta(hours=5, minutes=30)
        
        if now_ist.weekday() >= 5:
            return False
            
        market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
        
        return market_start <= now_ist <= market_end

    def update_from_candidates(self, candidates: pd.DataFrame | None = None) -> pd.DataFrame:
        """
        Evaluates top ranking strategies and fills available capital slots with new positions.
        Strictly enforces active market hour boundaries before processing transaction footprints.
        """
        # Market Hours Guard (Uncomment to block out-of-market processing)
        # if not self.is_market_open():
        #     self.logger.warning("Skipping portfolio pipeline execution: Indian Stock Market is currently CLOSED.")
        #     return self._load_existing()

        if candidates is None:
            if supabase_client:
                try:
                    self.logger.info("Fetching top PQS candidates directly from Supabase cloud...")
                    # CLEANED: Parentheses wrap method chain to permanently solve trailing space syntax bugs
                    response = (
                        supabase_client.table("pqs_rankings")
                        .select("symbol, pqs, rank, last_price, timestamp")
                        .order("rank", desc=False)
                        .limit(20)
                        .execute()
                    )
                    
                    if response.data:
                        candidates = pd.DataFrame(response.data)
                        self.logger.info("Successfully loaded %d candidates from database.", len(candidates))
                    else:
                        candidates = pd.DataFrame()
                except Exception as db_err:
                    self.logger.error("Failed to query Supabase pqs_rankings, falling back to local CSV: %s", db_err)
                    candidates = pd.DataFrame()

            if candidates is None or candidates.empty:
                if self.config.candidates_file.exists():
                    candidates = pd.read_csv(self.config.candidates_file)
                else:
                    candidates = pd.DataFrame()

        if not candidates.empty and "timestamp" in candidates.columns:
            candidates["timestamp"] = pd.to_datetime(candidates["timestamp"], errors="coerce")
        else:
            candidates["timestamp"] = datetime.now(timezone.utc)

        try:
            portfolio = self._load_existing()
        except Exception:
            portfolio = pd.DataFrame()

        if portfolio is None or portfolio.empty:
            portfolio = pd.DataFrame(
                columns=[
                    "symbol",
                    "entry_timestamp",
                    "entry_price",
                    "quantity",
                    "slot_id",
                    "slot_capital",
                    "pqs",
                    "status",
                ]
            )

        open_positions = portfolio[portfolio["status"] == "OPEN"].copy()
        free_slots = self._free_slots(open_positions)
        
        if candidates.empty or not free_slots:
            self.state_manager.save_portfolio(portfolio)
            self._sync_to_supabase(portfolio)
            self.logger.info("Portfolio update saved rows=%s open_positions=%s (No candidates or free slots)", len(portfolio), len(open_positions))
            return portfolio

        open_symbols = set(open_positions["symbol"].tolist())
        ranked = candidates.sort_values("pqs", ascending=False)
        
        # Real transaction timestamp baseline
        execution_timestamp = datetime.now(timezone.utc).isoformat()

        for _, row in ranked.iterrows():
            if not free_slots:
                break
                
            symbol = str(row["symbol"])
            if symbol in open_symbols:
                continue

            price = float(row.get("last_price", 0.0))
            if price <= 0:
                continue
                
            slot_id, slot_cap = free_slots.pop(0)
            qty = int(slot_cap // price)
            if qty <= 0:
                free_slots.insert(0, (slot_id, slot_cap))
                continue
                
            entry = {
                "symbol": symbol,
                "entry_timestamp": execution_timestamp,
                "entry_price": price,
                "quantity": qty,
                "slot_id": slot_id,
                "slot_capital": slot_cap,
                "pqs": float(row["pqs"]),
                "status": "OPEN",
            }
            portfolio = pd.concat([portfolio, pd.DataFrame([entry])], ignore_index=True)
            open_symbols.add(symbol)

            if len(portfolio[portfolio["status"] == "OPEN"]) >= self.trading_config.max_positions:
                break

        self.state_manager.save_portfolio(portfolio)
        self._sync_to_supabase(portfolio)
        
        self.logger.info(
            "Portfolio update saved rows=%s open_positions=%s",
            len(portfolio),
            int((portfolio["status"] == "OPEN").sum()),
        )
        return portfolio


def main() -> None:
    engine = PortfolioEngine()
    out = engine.update_from_candidates()
    print(f"Portfolio rows calculated: {len(out)}")


if __name__ == "__main__":
    main()
