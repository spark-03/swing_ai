import logging
import logging.handlers
import sys
import os
from pathlib import Path

_LOG_DIR = Path("logs")
_LOG_FORMAT = '[%(asctime)s] %(levelname)s [%(name)s]: %(message)s'
_LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

_config_initialized = False


def _setup_root_logging() -> None:
    """Configure root logging with console + rotating file handlers."""
    global _config_initialized
    if _config_initialized:
        return
    _config_initialized = True

    # Create logs directory
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # Rotating file handler (10MB per file, keep 5 backups)
    log_file = _LOG_DIR / "system.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Error-only file handler
    error_file = _LOG_DIR / "errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)


def get_system_logger(name: str) -> logging.Logger:
    """Returns a standardized logger with console + file output."""
    _setup_root_logging()
    logger = logging.getLogger(name)
    return logger
