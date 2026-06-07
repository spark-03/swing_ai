import os
import sys
import time
import subprocess
import threading
from datetime import datetime
import zoneinfo
from http.server import SimpleHTTPRequestHandler, HTTPServer
from paper_trading.logging_config import get_system_logger

# --- Tiny Background Web Server to stop Render Port Scanning Alerts ---
class HealthCheckHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Spark Engine Core Scheduler is online and active.")

def run_health_server(logger):
    try:
        port = int(os.environ.get("PORT", 10000)) 
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info("Internal Render health ping server started on port %s", port)
        server.serve_forever()
    except Exception as e:
        logger.error("Failed to start health ping web server: %s", e)

# --- Core Trading Pipeline Executor ---
def run_trading_pipeline(slot_name: str):
    """Executes the ingestion step followed by the live portfolio tracker step."""
    logger = get_system_logger("market_scheduler.pipeline")
    logger.info("=== ALERT: Starting scheduled execution cycle for slot [%s] ===", slot_name)
    
    # 1. Step One: Trigger Data Ingestion to fetch fresh broker candles
    logger.info("Executing data ingestion routines...")
    try:
        ingest_proc = subprocess.run(
            [sys.executable, "-m", "paper_trading.data_ingestion"], 
            capture_output=True, text=True, timeout=600  # 10 min timeout
        )
    except subprocess.TimeoutExpired:
        logger.error("Data Ingestion timed out after 600 seconds! Skipping this cycle.")
        return
    
    if ingest_proc.returncode != 0:
        logger.error("Data Ingestion crashed! Skipping execution portfolio logic. Error:\n%s", ingest_proc.stderr)
        return
    logger.info("Data Ingestion completed successfully.")

    # 2. Step Two: Trigger Portfolio Core Engine to process DQN Exits & PQS Entries
    logger.info("Executing portfolio matrix engine allocation processes...")
    try:
        portfolio_proc = subprocess.run([
            sys.executable, "-m", "paper_trading.run_live_portfolio", "--slot", slot_name
        ], capture_output=True, text=True, timeout=300)  # 5 min timeout
    except subprocess.TimeoutExpired:
        logger.error("Portfolio Engine timed out after 300 seconds!")
        return
    
    if portfolio_proc.returncode != 0:
        logger.error("Portfolio Engine crashed! Error Log output:\n%s", portfolio_proc.stderr)
        return
    
    logger.info("=== SUCCESS: Scheduled pipeline loop finalized for slot [%s] ===", slot_name)

def main():
    logger = get_system_logger("market_scheduler.main")
    logger.info("Spark-03 Background Daemon Cloud Scheduler initialized and running.")
    
    # Fire up the health server on a background thread to silence Render warnings
    server_thread = threading.Thread(target=run_health_server, args=(logger,), daemon=True)
    server_thread.start()
    
    # Enforce Indian Standard Time handling matching exchange clocks
    ist_zone = zoneinfo.ZoneInfo("Asia/Kolkata")
    
    # Target execution time windows (Hours, Minutes)
    TARGET_SLOTS = [
        (11, 15),  # Slot 1
        (13, 15),  # Slot 2
        (15, 15)   # Slot 3 (Pre-market close check)
    ]
    
    triggered_today = set()
    last_day = -1

    while True:
        try:
            # Get current time in India
            now_ist = datetime.now(ist_zone)
            current_day = now_ist.day
            current_hour = now_ist.hour
            current_minute = now_ist.minute
            weekday = now_ist.weekday()  # Monday=0, Friday=4, Saturday=5, Sunday=6

            # Reset trigger locks at midnight or on a new day
            if current_day != last_day:
                triggered_today.clear()
                last_day = current_day
                logger.info("New market day registered: %s. Trigger matrix reset clean.", now_ist.strftime('%Y-%m-%d'))

            # Skip tracking algorithms on weekends entirely
            if weekday >= 5:
                logger.debug("Market closed (Weekend). Sleeping tracker loop.")
                time.sleep(300)  # Check every 5 minutes on weekends
                continue

            # Check if current time matches any of our target calculation hours
            for hr, mnt in TARGET_SLOTS:
                slot_id = f"{hr:02d}:{mnt:02d}"
                
                # If we hit the hour/minute mark and haven't run it yet today
                if current_hour == hr and current_minute >= mnt and slot_id not in triggered_today:
                    # Double check we don't fire too late past the window
                    if current_minute <= mnt + 10: 
                        timestamp_str = now_ist.strftime('%Y-%m-%d_%H:%M')
                        run_trading_pipeline(slot_name=f"SLOT_{slot_id}_{timestamp_str}")
                        triggered_today.add(slot_id)
            
            # High-precision sleep during market hours to prevent missing execution seconds
            if 9 <= current_hour <= 16:
                time.sleep(30)  # Check every 30 seconds during active market windows
            else:
                time.sleep(600) # Check every 10 minutes at night to conserve compute assets

        except KeyboardInterrupt:
            logger.info("Scheduler daemon manually shutdown by termination signal request.")
            break
        except Exception as e:
            logger.error("Unexpected failure across main scheduler daemon framework loop: %s", e)
            time.sleep(60)

if __name__ == "__main__":
    main()
