from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from paper_trading.retry_utils import retry_call

# Safe initialization block for Supabase Python SDK client module
try:
    from supabase import create_client, Client
    SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("VITE_SUPABASE_ANON_KEY", "")
    supabase_client: Client | None = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None
except ImportError:
    supabase_client = None


METRICS_FILE = Path("logs/dashboard_metrics.json")


def _default_metrics() -> dict[str, Any]:
    return {
        "cycle_count": 0,
        "trades_executed": 0,
        "exits_triggered": 0,
        "rotations_triggered": 0,
        "active_positions": 0,
        "portfolio_value": 1_000_000.0,
        "last_cycle_started_at": None,
        "last_cycle_completed_at": None,
        "last_cycle_duration_seconds": None,
        "last_processed_slot": None,
        "last_error": None,
    }


def load_metrics(path: Path = METRICS_FILE) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return _default_metrics()
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_metrics()
    metrics = _default_metrics()
    metrics.update(current)
    return metrics


def save_metrics(metrics: dict[str, Any], path: Path = METRICS_FILE) -> None:
    # 1. Local Fallback Backup Strategy (Atomic write logic)
    def write_once() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.tmp")
        tmp_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)
    
    try:
        retry_call(write_once, attempts=3, retry_exceptions=(OSError,))
    except Exception as e:
        print(f"Local metrics file-write failed: {e}")

    # 2. Synchronous Push to Supabase Cloud Instance (Overwriting record row id: 1)
    if supabase_client:
        try:
            payload = {
                "id": 1,  # Matches INT PRIMARY KEY layout safely
                "cycle_count": int(metrics.get("cycle_count", 0)),
                "trades_executed": int(metrics.get("trades_executed", 0)),
                "exits_triggered": int(metrics.get("exits_triggered", 0)),
                "rotations_triggered": int(metrics.get("rotations_triggered", 0)),
                "active_positions": int(metrics.get("active_positions", 0)),
                "portfolio_value": float(metrics.get("portfolio_value", 1000000.0)),
                "last_cycle_started_at": metrics.get("last_cycle_started_at"),
                "last_cycle_completed_at": metrics.get("last_cycle_completed_at"),
                "last_cycle_duration_seconds": metrics.get("last_cycle_duration_seconds"),
                "last_processed_slot": metrics.get("last_processed_slot"),
                "last_error": metrics.get("last_error"),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            supabase_client.table("dashboard_metrics").upsert(payload).execute()
        except Exception as err:
            print(f"Supabase metrics table synchronizer loop encountered an intercept failure: {err}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_portfolio_value(portfolio: pd.DataFrame) -> float:
    if portfolio.empty or "status" not in portfolio.columns:
        return 1_000_000.0
    open_positions = portfolio[portfolio["status"] == "OPEN"].copy()
    if open_positions.empty:
        return 1_000_000.0
    entry_value = pd.to_numeric(open_positions["entry_price"], errors="coerce").fillna(0) * pd.to_numeric(
        open_positions["quantity"], errors="coerce"
    ).fillna(0)
    invested = float(entry_value.sum())
    return max(0.0, 1_000_000.0 - invested) + invested


def update_cycle_metrics(
    *,
    portfolio: pd.DataFrame,
    trades_executed: int,
    exits_triggered: int,
    rotations_triggered: int,
    cycle_duration_seconds: float,
    last_processed_slot: str | None = None,
    path: Path = METRICS_FILE,
) -> dict[str, Any]:
    metrics = load_metrics(path)
    metrics["cycle_count"] = int(metrics.get("cycle_count", 0)) + 1
    metrics["trades_executed"] = int(metrics.get("trades_executed", 0)) + int(trades_executed)
    metrics["exits_triggered"] = int(metrics.get("exits_triggered", 0)) + int(exits_triggered)
    metrics["rotations_triggered"] = int(metrics.get("rotations_triggered", 0)) + int(rotations_triggered)
    metrics["active_positions"] = (
        int((portfolio["status"] == "OPEN").sum()) if not portfolio.empty and "status" in portfolio.columns else 0
    )
    metrics["portfolio_value"] = estimate_portfolio_value(portfolio)
    metrics["last_cycle_completed_at"] = utc_now_iso()
    metrics["last_cycle_duration_seconds"] = round(float(cycle_duration_seconds), 3)
    metrics["last_processed_slot"] = last_processed_slot
    metrics["last_error"] = None
    save_metrics(metrics, path)
    return metrics


def record_cycle_start(path: Path = METRICS_FILE) -> dict[str, Any]:
    metrics = load_metrics(path)
    metrics["last_cycle_started_at"] = utc_now_iso()
    save_metrics(metrics, path)
    return metrics


def record_cycle_error(error: str, path: Path = METRICS_FILE) -> dict[str, Any]:
    metrics = load_metrics(path)
    metrics["last_error"] = error
    save_metrics(metrics, path)
    return metrics
