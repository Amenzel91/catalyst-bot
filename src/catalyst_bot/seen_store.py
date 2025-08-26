"""
Seen Store v1 (SQLite TTL)

Purpose
-------
Persist IDs we've alerted on so restarts do not re-alert the same item.

Design
------
- Simple SQLite with a single table: seen(id TEXT PRIMARY KEY, ts INTEGER).
- TTL cleanup on init and periodically when `purge_expired()` is called.
- All ops are best-effort; failures should never crash the caller.

Env
---
FEATURE_PERSIST_SEEN   (default: "true")
SEEN_DB_PATH           (default: "data/seen_ids.sqlite")
SEEN_TTL_DAYS          (default: "7")
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from catalyst_bot.logging_utils import get_logger  # type: ignore
except Exception:  # pragma: no cover
    import logging

    def get_logger(name: str):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        return logging.getLogger(name)


log = get_logger("seen_store")


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SeenStoreConfig:
    path: Path
    ttl_days: int


class SeenStore:
    def __init__(self, config: Optional[SeenStoreConfig] = None):
        if config is None:
            path = Path(os.getenv("SEEN_DB_PATH", "data/seen_ids.sqlite"))
            ttl = int(os.getenv("SEEN_TTL_DAYS", "7"))
            config = SeenStoreConfig(path=path, ttl_days=ttl)

        self.cfg = config
        self.cfg.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.cfg.path), check_same_thread=False)
        self._ensure_schema()
        self.purge_expired()

    def _ensure_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                id TEXT PRIMARY KEY,
                ts INTEGER NOT NULL
            )
            """
        )
        self._conn.commit()

    def purge_expired(self) -> None:
        ttl_secs = self.cfg.ttl_days * 86400
        cutoff = int(time.time()) - ttl_secs
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM seen WHERE ts < ?", (cutoff,))
            self._conn.commit()
        except Exception as e:  # pragma: no cover - non-fatal
            log.warning("purge_expired_failed", extra={"error": str(e)})

    def is_seen(self, item_id: str) -> bool:
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT 1 FROM seen WHERE id = ? LIMIT 1", (item_id,))
            row = cur.fetchone()
            return row is not None
        except Exception as e:  # pragma: no cover - non-fatal
            log.warning("is_seen_failed", extra={"error": str(e)})
            return False

    def mark_seen(self, item_id: str, ts: Optional[int] = None) -> None:
        ts = int(time.time()) if ts is None else int(ts)
        try:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO seen(id, ts) VALUES(?, ?)",
                (item_id, ts),
            )
            self._conn.commit()
        except Exception as e:  # pragma: no cover - non-fatal
            log.warning("mark_seen_failed", extra={"error": str(e)})


def should_filter(item_id: str, store: Optional[SeenStore] = None) -> bool:
    """
    Convenience helper: returns True if the item *should be filtered* (already seen),
    respecting FEATURE_PERSIST_SEEN.
    """
    if not _env_flag("FEATURE_PERSIST_SEEN", "true"):
        return False
    if store is None:
        store = SeenStore()
    if store.is_seen(item_id):
        return True
    store.mark_seen(item_id)
    return False
