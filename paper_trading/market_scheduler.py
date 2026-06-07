import argparse
import os
import subprocess
import sys
import threading
import time
import json
import urllib.request
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
import zoneinfo

# Assuming you use a supabase client helper in your project
# If you don't have a shared wrapper, pip install supabase
from supabase import create_client, Client

from paper_trading.logging_config import get_system_logger

# Initialize Supabase Credentials from Environment Variables
SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("VITE_SUPABASE_ANON_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None


# --- Tiny Background Web Server to stop Render Port Scanning Alerts ---
class HealthCheckHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Spark Engine Core Scheduler is online and active.")

def run_health_server(logger) -> None: # type: ignore
    try:
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info("Internal Render health ping server started on port %s", port)
        server.serve_forever()
    except Exception as e:
        logger.error("Failed to start health ping web server: %s", e)


# --- Live API Status Checker & Dashboard Updater ---
def update_market_status_cache(logger) -> str:
    """Queries Upstox API for live status and updates the Supabase state table.
    Returns 'OPEN', 'CLOSED', or 'UNKNOWN' if the API check fails.
    """
    url = "https://api.upstox.com/v2/market/status/nse"
    status_result = "OPEN" # Default fallback assuming market is open
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=7) as response:
            if response.status == 200:
                raw_data = json.loads(response.read().decode())
                api_status = raw_data.get("data", {}).get("status", "OPEN")
                
                # Upstox explicitly sends 'CLOSED' on official trading holidays
                if api_status == "CLOSED":
                    status_result = "CLOSED"
    except Exception as e:
        logger.warning("Upstox API unreachable. Defaulting status check to OPEN. Error: %s", e)
        status_result = "UNKNOWN"

    # Push status directly to Supabase so the dashboard can render it live
    if supabase:
        try:
            supabase.table("system_state").upsert({
                "key": "market_status",
                "value": status_result,
                "updated_at": datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).isoformat()
            }).execute()
            logger.info("Supabase dashboard flag synchronized: market_status -> %s", status_result)
        except Exception as e:
            logger.error("Failed to push system state matrix to Supabase: %s", e)
            
    return status_result


# --- Core Trading Pipeline Executor ---
def run_trading_pipeline(slot_name: str) -> None:
    """Executes the ingestion step followed by the live portfolio tracker step."""
    logger = get_system_logger("market_scheduler.pipeline")
    logger.info("=== ALERT: Starting scheduled execution cycle for slot [%s] ===", slot_name)

    # 1. Step One: Trigger Data Ingestion to fetch fresh broker candles
    logger.info("Executing data ingestion routines...")
    try:
        ingest_proc = subprocess.run(
            [sys.executable, "-m", "paper_trading.data_ingestion"],
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout
        )
    except subprocess.TimeoutExpired:
        logger.error("Data Ingestion timed out after 600 seconds! Skipping this cycle.")
        return

    if ingest_proc.returncode != 0:
        error_details = ingest_proc.stderr or ingest_proc.stdout or "No console output captured."
        logger.error("Data Ingestion crashed! Skipping execution portfolio logic. Error:\n%s", error_details)
        return
    logger.info("Data Ingestion completed successfully.")

    # 2. Step Two: Trigger Portfolio Core Engine to process DQN Exits & PQS Entries
    logger.info("Executing portfolio matrix engine allocation processes...")
    try:
        portfolio_proc = subprocess.run(
            [sys.executable, "-m", "paper_trading.run_live_portfolio", "--slot", slot_name],
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout
        )
    except subprocess.TimeoutExpired:
        logger.error("Portfolio Engine timed out after 300 seconds!")
        return

    if portfolio_proc.returncode != 0:
        error_details = portfolio_proc.stderr or portfolio_proc.stdout or "No console output captured."
        logger.error("Portfolio Engine crashed! Error Log output:\n%s", error_details)
        return

    logger.info("=== SUCCESS: Scheduled pipeline loop finalized for slot [%s] ===", slot_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Spark-03 market scheduler.")
    parser.add_argument("--once", action="store_true", help="Run one pipeline cycle and exit.")
    parser.add_argument(
        "--allow-late-minutes",
        type=int,
        default=10,
        help="Accepted for GitHub Actions compatibility.",
    )
    args = parser.parse_args()

    logger = get_system_logger("market_scheduler.main")
    logger.info("Spark-03 Background Daemon Cloud Scheduler initialized and running.")

    if args.once:
        timestamp_str = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d_%H:%M")
        run_trading_pipeline(slot_name=f"MANUAL_ONCE_{timestamp_str}")
        return

    # Fire up the health server on a background thread to silence Render warnings
    server_thread = threading.Thread(target=run_health_server, args=(logger,), daemon=True)
    server_thread.start()

    # Enforce Indian Standard Time handling matching exchange clocks
    ist_zone = zoneinfo.ZoneInfo("Asia/Kolkata")

    # Target execution time windows (Hours, Minutes)
    TARGET_SLOTS = [
        (11, 15),  # Slot 1
        (13, 15),  # Slot 2
        (15, 15),  # Slot 3 (Pre-market close check)
    ]

    triggered_today = set()
    last_day = -1
    market_status_today = "UNKNOWN"

    while True:
        try:
            # Get current time in India
            now_ist = datetime.now(ist_zone)
            current_day = now_ist.day
            current_hour = now_ist.hour
            current_minute = now_ist.minute
            weekday = now_ist.weekday()  # Monday=0, Friday=4

            # Reset trigger locks on a new day transition
            if current_day != last_day:
                triggered_today.clear()
                last_day = current_day
                # Force an immediate API update check for the new day
                market_status_today = update_market_status_cache(logger)
                logger.info("New market day registered: %s. Market Status initialized as [%s]", 
                            now_ist.strftime("%Y-%m-%d"), market_status_today)

            # 1. Skip tracking algorithms on weekends entirely
            if weekday >= 5:
                logger.debug("Market closed (Weekend). Sleeping tracker loop.")
                time.sleep(300)
                continue

            # 2. Daily morning status check (Runs at 08:45 AM to refresh the state)
            if current_hour == 8 and 45 <= current_minute <= 50 and "MORNING_CHECK" not in triggered_today:
                market_status_today = update_market_status_cache(logger)
                triggered_today.add("MORNING_CHECK")
                logger.info("Morning verification execution completed. Today's session status: [%s]", market_status_today)

            # 3. If the day is verified as a CLOSED holiday, halt engine operations completely
            if market_status_today == "CLOSED":
                logger.debug("Market session is CLOSED today via Upstox API. Standing down tracking engine.")
                time.sleep(600)  # Check every 10 minutes, staying idle safely
                continue

            # Check if current time matches any of our target calculation slots
            for hr, mnt in TARGET_SLOTS:
                slot_id = f"{hr:02d}:{mnt:02d}"

                if current_hour == hr and mnt <= current_minute <= (mnt + args.allow_late_minutes):
                    if slot_id not in triggered_today:
                        timestamp_str = now_ist.strftime("%Y-%m-%d_%H:%M")
                        run_trading_pipeline(slot_name=f"SLOT_{slot_id}_{timestamp_str}")
                        triggered_today.add(slot_id)

            # Performance management sleeping thresholds
            if 9 <= current_hour <= 16:
                time.sleep(30)  # Active checking window
            else:
                time.sleep(600) # Quiet night state sleep

        except KeyboardInterrupt:
            logger.info("Scheduler daemon manually shutdown by termination signal request.")
            break
        except Exception as e:
            logger.error("Unexpected failure across main scheduler daemon framework loop: %s", e)
            time.sleep(60)


if __name__ == "__main__":
    main()
