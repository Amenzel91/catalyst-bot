# src/catalyst_bot/logging_utils.py
import json
import logging
import logging.handlers
import os
import sys
import time
from typing import Any, Dict

from .config import get_settings

# Keys commonly present on a LogRecord that we don't want to echo as "extra"
_EXCLUDE_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}


def _jsonify(value: Any) -> Any:
    """Return a JSON-serializable representation of `value`."""
    try:
        json.dumps(value)
        return value
    except Exception:
        # Fallback to string to avoid formatter explosions
        return str(value)


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for Catalyst‑Bot.

    When LOG_PLAIN is set to 1 in the environment (see Settings.log_plain), the
    console output will use a human‑readable single‑line format with colourised
    levels.  Regardless of this setting, a JSON log will be written to a
    rotating file in ``data/logs`` for downstream consumption.  If LOG_PLAIN
    is unset (the default), console logs will continue to use the JSON
    formatter.  The log level can be customised via the ``level`` argument or
    via the ``LOG_LEVEL`` environment variable.

    WAVE 2.3: Enhanced logging with rotation and separate error log files.
    Logs are rotated based on LOG_ROTATION_DAYS (default: 7 days).
    """

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            base: Dict[str, Any] = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "level": record.levelname,
                "name": record.name,
                "msg": record.getMessage(),
            }
            # Merge any "extra" attributes that were added to the record
            for k, v in record.__dict__.items():
                if k not in _EXCLUDE_KEYS and k not in base and not k.startswith("_"):
                    base[k] = _jsonify(v)
            if record.exc_info:
                try:
                    base["exc"] = self.formatException(record.exc_info)
                except Exception:
                    base["exc"] = "unavailable"
            return json.dumps(base, ensure_ascii=False)

    class PlainFormatter(logging.Formatter):
        """Human‑readable single‑line log formatter with colourised levels."""

        # ANSI colour codes for different log levels
        LEVEL_COLOURS = {
            "DEBUG": "\033[36m",  # cyan
            "INFO": "\033[32m",  # green
            "WARNING": "\033[33m",  # yellow
            "ERROR": "\033[31m",  # red
            "CRITICAL": "\033[35m",  # magenta
        }
        RESET = "\033[0m"

        def format(self, record: logging.LogRecord) -> str:
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            level = record.levelname
            name = record.name
            msg = record.getMessage()
            # Build extras string from non‑excluded keys
            extras: list[str] = []
            for k, v in record.__dict__.items():
                if k not in _EXCLUDE_KEYS and not k.startswith("_"):
                    extras.append(f"{k}={_jsonify(v)}")
            extra_str = " " + " ".join(extras) if extras else ""
            colour = self.LEVEL_COLOURS.get(level, "")
            reset = self.RESET if colour else ""
            return f"{ts} {colour}{level:<8}{reset} {name}: {msg}{extra_str}"

    settings = get_settings()
    # Determine desired log level (environment overrides function argument)
    env_level = settings.log_level or level
    level_upper = (env_level or level or "INFO").upper()

    # Configure root logger
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level_upper)

    # Ensure logs directory exists for file output
    try:
        log_dir = settings.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Determine rotation settings from environment
        rotation_days = int(os.getenv("LOG_ROTATION_DAYS", "7"))
        max_bytes = 10 * 1024 * 1024  # 10MB per file
        backup_count = rotation_days  # Keep one backup per day

        # Main bot log (all levels)
        file_path = log_dir / "bot.jsonl"
        file_handler = logging.handlers.RotatingFileHandler(
            file_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)

        # Separate error log (WARNING and above)
        error_path = log_dir / "errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(JsonFormatter())
        root.addHandler(error_handler)

        # Health monitoring log (for health_monitor module)
        # This can be analyzed separately for uptime/performance tracking
        health_path = log_dir / "health.log"
        health_handler = logging.handlers.RotatingFileHandler(
            health_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        health_handler.setFormatter(JsonFormatter())
        health_handler.addFilter(lambda record: record.name.startswith("health"))
        root.addHandler(health_handler)

    except Exception:
        # If file handler fails (e.g. unwritable directory), fall back silently
        pass

    # Configure console handler: plain or JSON based on LOG_PLAIN flag
    stream_handler = logging.StreamHandler(sys.stdout)
    if settings.log_plain:
        stream_handler.setFormatter(PlainFormatter())
    else:
        stream_handler.setFormatter(JsonFormatter())
    root.addHandler(stream_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
