"""
Logging setup: console + rotating file handler.

Render free instances have limited disk, so we cap the log file at
2 MB with one backup to prevent unbounded growth.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import LOGS_DIR, LOG_LEVEL

LOG_FILE: str = str(LOGS_DIR / "bot.log")


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger with both stream and file handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    if logger.hasHandlers():
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Rotating file handler: 2 MB per file, 1 backup
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
