"""
Quick script to seed Supabase with mock data for dashboard testing.
Run: python -m paper_trading.seed_supabase
"""
import os
import random
from datetime import datetime, timedelta
import zoneinfo
from paper_trading.supabase_client import get_supabase_client
from paper_trading.logging_config import get_system_logger

logger = get_system_logger("paper_trading.seed_supabase")

MOCK_POSITIONS = [
    {"symbol": "RELIANCE", "entry_price": 2485.50, "pqs": 87.3421},
    {"symbol": "TCS", "entry_price": 3812.00, "pqs": 91.2156},
    {"symbol": "HDFCBANK", "entry_price": 1724.30, "pqs": 84.9873},
    {"symbol": "INFY", "entry_price": 1598.75, "pqs": 82.4531},
    {"symbol": "ICICIBANK", "entry_price": 1245.60, "pqs": 79.8712},
    {"symbol": "SBIN", "entry_price": 812.40, "pqs": 76.5432},
    {"symbol": "BHARTIARTL", "entry_price": 1654.20, "pqs": 85.1234},
    {"symbol": "ITC", "entry_price": 467.80, "pqs": 78.6543},
]


def seed_data():
    client = get_supabase_client()
    if not client.health_check():
        logger.error("Supabase connection failed. Check SUPABASE_URL and SUPABASE_KEY.")
        return

    logger.info("Connected to Supabase. Seeding mock data...")

    # 1. Seed current_portfolio (3 open positions)
    ist = zoneinfo.ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    
    open_positions = []
    for i, stock in enumerate(MOCK_POSITIONS[:3]):
        entry_time = now - timedelta(hours=random.randint(4, 48))
        
        open_positions.append({
            "symbol": stock["symbol"],
            "entry_timestamp": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
            "entry_price": stock["entry_price"],
            "quantity": random.randint(50, 200),
            "slot_capital": 50000.0,
            "pqs": stock["pqs"],
            "status": "OPEN",
        })

    # Clear existing and insert new
    try:
        client.delete("current_portfolio", {"status": "OPEN"})
    except Exception:
        pass
    
    client.insert("current_portfolio", open_positions)
    logger.info("Seeded %d open positions.", len(open_positions))

    # 2. Upsert dashboard_metrics (table has primary key, so use upsert)
    metrics = {
        "id": 1,
        "portfolio_value": round(sum(p["entry_price"] * p["quantity"] for p in open_positions), 2),
        "trades_executed": random.randint(15, 45),
        "exits_triggered": random.randint(3, 12),
        "last_processed_slot": f"SLOT_11:15_{now.strftime('%Y-%m-%d_%H:%M')}",
    }

    try:
        client.upsert("dashboard_metrics", metrics)
        logger.info("Seeded dashboard metrics: %s", metrics)
    except Exception as e:
        logger.warning("Could not upsert dashboard_metrics (may not have all columns): %s", e)

    logger.info("✅ Supabase seeded successfully! Refresh your Netlify dashboard to see data.")


if __name__ == "__main__":
    seed_data()