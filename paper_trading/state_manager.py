from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from paper_trading.retry_utils import retry_call


PORTFOLIO_COLUMNS = [
    "symbol",
    "entry_timestamp",
    "entry_price",
    "quantity",
    "slot_id",
    "slot_capital",
    "pqs",
    "status",
]


@dataclass
class StateManager:
    portfolio_file: Path = Path("current_portfolio.csv")
    last_processed_slot_file: Path = Path("logs/last_processed_slot.txt")
    backup_dir: Path = Path("logs/state_backups")
    retry_attempts: int = 3

    def __post_init__(self) -> None:
        self.portfolio_file = Path(self.portfolio_file)
        self.last_processed_slot_file = Path(self.last_processed_slot_file)
        self.backup_dir = Path(self.backup_dir)
        self.portfolio_file.parent.mkdir(parents=True, exist_ok=True)
        self.last_processed_slot_file.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_files()

    def _ensure_files(self) -> None:
        if not self.portfolio_file.exists():
            self.save_portfolio(pd.DataFrame(columns=PORTFOLIO_COLUMNS), create_backup=False)
        if not self.last_processed_slot_file.exists():
            self.save_last_processed_slot("", create_backup=False)

    def _timestamp_suffix(self) -> str:
        return datetime.utcnow().strftime("%Y%m%d%H%M%S%f")

    def _backup_file(self, path: Path, reason: str = "bak") -> Path | None:
        if not path.exists() or path.stat().st_size == 0:
            return None
        backup_path = self.backup_dir / f"{path.name}.{reason}.{self._timestamp_suffix()}"
        shutil.copy2(path, backup_path)
        return backup_path

    def _atomic_write_text(self, path: Path, text: str) -> None:
        def write_once() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name(f".{path.name}.{self._timestamp_suffix()}.tmp")
            tmp_path.write_text(text, encoding="utf-8")
            tmp_path.replace(path)
        retry_call(write_once, attempts=self.retry_attempts, retry_exceptions=(OSError,))

    def _atomic_write_dataframe(self, path: Path, df: pd.DataFrame) -> None:
        def write_once() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name(f".{path.name}.{self._timestamp_suffix()}.tmp")
            df.to_csv(tmp_path, index=False)
            tmp_path.replace(path)
        retry_call(write_once, attempts=self.retry_attempts, retry_exceptions=(OSError,))

    def load_portfolio(self) -> pd.DataFrame:
        try:
            if not self.portfolio_file.exists() or self.portfolio_file.stat().st_size == 0:
                portfolio = pd.DataFrame(columns=PORTFOLIO_COLUMNS)
                self.save_portfolio(portfolio, create_backup=False)
                return portfolio
            portfolio = pd.read_csv(self.portfolio_file)
            for column in PORTFOLIO_COLUMNS:
                if column not in portfolio.columns:
                    portfolio[column] = pd.NA
            return portfolio
        except Exception:
            self._backup_file(self.portfolio_file, reason="corrupt")
            portfolio = pd.DataFrame(columns=PORTFOLIO_COLUMNS)
            self.save_portfolio(portfolio, create_backup=False)
            return portfolio

    def save_portfolio(self, portfolio: pd.DataFrame, *, create_backup: bool = True) -> None:
        if create_backup:
            self._backup_file(self.portfolio_file)
        self._atomic_write_dataframe(self.portfolio_file, portfolio)

    def load_last_processed_slot(self) -> str | None:
        try:
            if not self.last_processed_slot_file.exists():
                self.save_last_processed_slot("", create_backup=False)
                return None
            slot = self.last_processed_slot_file.read_text(encoding="utf-8").strip()
            return slot or None
        except Exception:
            self._backup_file(self.last_processed_slot_file, reason="corrupt")
            self.save_last_processed_slot("", create_backup=False)
            return None

    def save_last_processed_slot(self, slot: str, *, create_backup: bool = True) -> None:
        if create_backup:
            self._backup_file(self.last_processed_slot_file)
        body = f"{slot.strip()}\n" if slot.strip() else ""
        self._atomic_write_text(self.last_processed_slot_file, body)