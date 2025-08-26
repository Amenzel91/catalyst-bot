import json
import logging
import sys
import time
from typing import Any, Dict


def setup_logging(level: str = "INFO") -> None:
    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            base: Dict[str, Any] = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "level": record.levelname,
                "name": record.name,
                "msg": record.getMessage(),
            }
            if record.exc_info:
                base["exc"] = self.formatException(record.exc_info)
            return json.dumps(base)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
