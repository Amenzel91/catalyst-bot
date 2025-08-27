# src/catalyst_bot/logging_utils.py
import json
import logging
import sys
import time
from typing import Any, Dict

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

            # Keep logs compact and machine friendly
            return json.dumps(base, ensure_ascii=False)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel((level or "INFO").upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
