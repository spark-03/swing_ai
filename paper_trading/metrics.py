from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from paper_trading.retry_utils import retry_call


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
    def write_once() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.tmp")
        tmp_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)
    retry_call(write_once, attempts=3, retry_exceptions=(OSError,))


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