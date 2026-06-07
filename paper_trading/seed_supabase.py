"""
Quick script to seed Supabase with mock data for dashboard testing.
Populates: open_positions, pqs_rankings, current_portfolio, dashboard_metrics

Run: python -m paper_trading.seed_supabase
"""
import os
import random
from datetime import datetime, timedelta
import zoneinfo
from paper_trading.supabase_client import get_supabase_client
from paper_trading.logging_config import get_system_logger

logger = get_system_logger("paper_trading.seed_supabase")

# Stocks with realistic Indian market data
# (symbol, entry_price, base_pqs, current_price_variation)
STOCKS = [
    ("RELIANCE",    2485.50, 87.34, 0.04),
    ("TCS",         3812.00, 91.22, 0.03),
    ("HDFCBANK",    1724.30, 84.99, 0.05),
    ("INFY",        1598.75, 82.45, 0.02),
    ("ICICIBANK",   1245.60, 79.87, 0.04),
    ("SBIN",         812.40, 76.54, 0.06),
    ("BHARTIARTL",  1654.20, 85.12, 0.03),
    ("ITC",          467.80, 78.65, 0.02),
    ("WIPRO",        532.60, 73.21, 0.04),
    ("NTPC",         365.40, 71.98, 0.03),
    ("POWERGRID",    298.75, 69.45, 0.02),
    ("AXISBANK",    1123.40, 77.56, 0.05),
    ("MARUTI",      9824.50, 72.34, 0.03),
    ("SUNPHARMA",   1523.40, 74.12, 0.04),
    ("BAJFINANCE",  6689.20, 81.67, 0.06),
]


def seed_data():
    client = get_supabase_client()
    if not client.health_check():
        logger.error("Supabase connection failed. Check SUPABASE_URL and SUPABASE_KEY.")
        return

    logger.info("Connected to Supabase. Seeding all dashboard tables...")

    ist = zoneinfo.ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    now_iso = now.isoformat()

    # ============================
    # 1. Seed open_positions (3 stocks)
    # ============================
    selected = random.sample(STOCKS, 3)
    open_positions = []

    for i, (symbol, entry_price, base_pqs, var) in enumerate(selected):
        entry_time = now - timedelta(hours=random.randint(4, 48))
        qty = random.randint(50, 200)
        # Simulate current price fluctuating around entry price
        current_price = round(entry_price * (1 + random.uniform(-0.03, 0.05)), 2)
        market_value = round(current_price * qty, 2)
        cost_basis = entry_price * qty
        unrealized_pnl = round(market_value - cost_basis, 2)
        unrealized_pnl_pct = round((unrealized_pnl / cost_basis) * 100, 2) if cost_basis > 0 else 0.0

        open_positions.append({
            "symbol": symbol,
            "entry_timestamp": entry_time.isoformat(),
            "entry_price": entry_price,
            "quantity": qty,
            "slot_id": i + 1,
            "slot_capital": 50000.0,
            "pqs": round(base_pqs + random.uniform(-2, 2), 4),
            "status": "OPEN",
            "current_price": current_price,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "timestamp": entry_time.isoformat(),
        })

    # Clear and insert
    try:
        client.delete("open_positions", {})
    except Exception:
        pass

    client.insert("open_positions", open_positions)
    logger.info("Seeded %d open positions to open_positions table.", len(open_positions))

    # Also seed current_portfolio with its supported columns (fewer columns)
    current_portfolio_rows = [
        {
            "symbol": p["symbol"],
            "entry_timestamp": p["entry_timestamp"],
            "entry_price": p["entry_price"],
            "quantity": p["quantity"],
            "slot_id": p["slot_id"],
            "slot_capital": p["slot_capital"],
            "pqs": p["pqs"],
            "status": p["status"],
        }
        for p in open_positions
    ]
    try:
        client.delete("current_portfolio", {})
    except Exception:
        pass
    try:
        client.insert("current_portfolio", current_portfolio_rows)
        logger.info("Also seeded %d rows to current_portfolio.", len(current_portfolio_rows))
    except Exception as e:
        logger.warning("current_portfolio insert failed (expected if table has RLS): %s", e)

    # ============================
    # 2. Seed pqs_rankings (15 stocks)
    # ============================
    # Sort STOCKS by PQS descending for realistic rankings
    ranked_stocks = sorted(STOCKS, key=lambda x: x[2], reverse=True)
    ranking_rows = []
    for idx, (symbol, entry_price, base_pqs, var) in enumerate(ranked_stocks):
        # Vary PQS dynamically for realistic live dashboard
        dynamic_pqs = round(base_pqs + random.uniform(-3, 3), 4)
        last_price = round(entry_price * (1 + random.uniform(-0.02, 0.02)), 2)
        ranking_rows.append({
            "timestamp": now_iso,
            "rank": idx + 1,
            "symbol": symbol,
            "pqs": dynamic_pqs,
            "last_price": last_price,
        })

    try:
        client.delete("pqs_rankings", {})
    except Exception:
        pass
    client.insert("pqs_rankings", ranking_rows)
    logger.info("Seeded %d PQS rankings.", len(ranking_rows))

    # ============================
    # 3. Seed dashboard_metrics
    # ============================
    total_value = sum(p["current_price"] * p["quantity"] for p in open_positions) + 500000  # cash buffer
    metrics = {
        "id": 1,
        "portfolio_value": round(total_value, 2),
        "trades_executed": random.randint(20, 50),
        "exits_triggered": random.randint(5, 15),
        "active_positions": len(open_positions),
        "last_processed_slot": f"SLOT_11:15_{now.strftime('%Y-%m-%d_%H:%M')}",
    }

    try:
        client.upsert("dashboard_metrics", metrics)
        logger.info("Seeded dashboard metrics: %s", metrics)
    except Exception as e:
        logger.warning("Could not upsert dashboard_metrics: %s", e)

    logger.info("✅ Supabase seeded successfully! Refresh your Netlify dashboard.")
    logger.info("   Dashboard will show: %d positions, %d PQS rankings, dynamic P&L", len(open_positions), len(ranking_rows))


if __name__ == "__main__":
    seed_data()