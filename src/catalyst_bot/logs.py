"""Logging utilities for the catalyst bot.

This module provides a standardized way to configure logging across
components. It also offers helper functions to record structured
events to JSONL files for later analysis. All logs are written into
the ``data/logs`` directory defined by the runtime configuration.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .config import get_settings


def setup_logging() -> logging.Logger:
    """Configure and return a logger for the catalyst bot.

    The logger writes to a rotating file in the ``data/logs`` directory.
    Rotation occurs at approximately 5 MB with 5 backups retained.
    """
    settings = get_settings()
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "bot.log"

    logger = logging.getLogger("catalyst_bot")
    if logger.handlers:
        # Avoid adding multiple handlers if setup_logging is called more than once
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def log_event(event: Dict[str, Any], file_name: str = "events.jsonl") -> None:
    """Append a structured event to a JSONL log file.

    Parameters
    ----------
    event : Dict[str, Any]
        The event data to record. Non‑serializable values will be
        converted to strings.
    file_name : str, optional
        The filename (under ``data/logs``) to which the event should be
        appended. Defaults to ``events.jsonl``.
    """
    settings = get_settings()
    path = settings.data_dir / "logs" / file_name
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
    except Exception as exc:
        # Logging should never raise; fall back to stderr
        try:
            print(f"Failed to write log event: {exc}")
        except Exception:
            pass