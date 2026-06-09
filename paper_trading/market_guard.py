import os
import sys
from datetime import datetime, timezone, timedelta

# Ensure parent directory is in path for easy execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from supabase import create_client, Client
    SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("VITE_SUPABASE_ANON_KEY", "")
    supabase_client: Client | None = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None
except ImportError:
    supabase_client = None

def check_market_status() -> tuple[str, str]:
    """
    Checks if the Indian Stock Market is currently open.
    Returns a tuple: (market_state, reason_message)
    """
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    
    # Check for weekends (5 = Saturday, 6 = Sunday)
    if now_ist.weekday() >= 5:
        return "CLOSED", f"Market is closed today (Weekend: {now_ist.strftime('%A')})."
        
    # Define standard market operational boundaries in IST
    market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if market_start <= now_ist <= market_end:
        return "OPEN", f"Market is live. Checked at {now_ist.strftime('%I:%M %p')} IST."
    else:
        return "CLOSED", f"Market is outside normal hours. Current time: {now_ist.strftime('%I:%M %p')} IST."

def sync_status_to_supabase():
    print("--- Running Morning Market Guard Check ---")
    if not supabase_client:
        print("CRITICAL ERROR: Supabase client is not initialized. Check your environment variables.")
        return

    state, message = check_market_status()
    timestamp_iso = datetime.now(timezone.utc).isoformat()

    # Fixed single record array payload to overwrite row id 1 every single time
    status_record = {
        "id": 1,
        "market_state": state,
        "last_checked": timestamp_iso,
        "message": message
    }

    try:
        response = (
            supabase_client.table("system_status")
            .upsert(status_record, on_conflict="id")
            .execute()
        )
        print(f"Successfully pushed status to Supabase!")
        print(f"Current State: {state}")
        print(f"Details: {message}")
    except Exception as err:
        print(f"Failed to sync status to cloud database: {err}")

if __name__ == "__main__":
    sync_status_to_supabase()
