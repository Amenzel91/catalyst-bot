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
import threading
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
        self._lock = threading.Lock()  # Thread-safe access protection
        self._thread_local = threading.local()  # Thread-local storage for connections
        self._init_schema()
        self.purge_expired()

    def _get_connection(self):
        """
        Get a thread-local SQLite connection.

        Creates a new connection for each thread on first access, ensuring
        SQLite's "same-thread" requirement is always satisfied.
        """
        if not hasattr(self._thread_local, "conn") or self._thread_local.conn is None:
            from catalyst_bot.storage import init_optimized_connection

            self._thread_local.conn = init_optimized_connection(
                str(self.cfg.path), timeout=30
            )
            log.debug(
                "seen_store_thread_connection_created thread_id=%s",
                threading.current_thread().ident,
            )

        return self._thread_local.conn

    def _init_schema(self) -> None:
        """Initialize database schema in the main thread."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS seen (
                    id TEXT PRIMARY KEY,
                    ts INTEGER NOT NULL
                )
                """
            )
            conn.commit()
            log.info("seen_store_initialized path=%s wal_mode=enabled", self.cfg.path)
        except Exception as e:
            log.error("seen_store_schema_init_failed err=%s", str(e), exc_info=True)
            raise

    def close(self) -> None:
        """Close all thread-local connections and truncate WAL files."""
        try:
            if hasattr(self._thread_local, "conn") and self._thread_local.conn:
                conn = self._thread_local.conn
                try:
                    # CRITICAL: Force WAL checkpoint and truncate to prevent WAL bloat
                    # Without this, WAL can grow to 70x database size, causing 4x slowdown
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    conn.close()
                    log.debug("seen_store_connection_closed wal_truncated=true")
                except Exception as e:
                    log.warning("seen_store_close_error err=%s", str(e))
                finally:
                    self._thread_local.conn = None
        except Exception as e:
            log.warning("seen_store_close_cleanup_error err=%s", str(e))

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False  # Don't suppress exceptions

    def purge_expired(self) -> None:
        """Remove expired entries (thread-safe)."""
        ttl_secs = self.cfg.ttl_days * 86400
        cutoff = int(time.time()) - ttl_secs
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.cursor()
                cur.execute("DELETE FROM seen WHERE ts < ?", (cutoff,))
                conn.commit()
                log.debug("purge_expired_success cutoff=%d", cutoff)
            except Exception as e:  # pragma: no cover - non-fatal
                log.warning("purge_expired_failed", extra={"error": str(e)})

    def is_seen(self, item_id: str) -> bool:
        """Check if item is seen (thread-safe across async and sync contexts)."""
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM seen WHERE id = ? LIMIT 1", (item_id,))
                row = cur.fetchone()
                return row is not None
            except Exception as e:  # pragma: no cover - non-fatal
                log.error(
                    "is_seen_error item_id=%s err=%s thread_id=%s",
                    item_id,
                    str(e),
                    threading.current_thread().ident,
                    exc_info=True,
                )
                return False  # Assume not seen on error (safer)

    def mark_seen(self, item_id: str, ts: Optional[int] = None) -> None:
        """Mark item as seen (thread-safe across async and sync contexts)."""
        ts = int(time.time()) if ts is None else int(ts)

        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.cursor()
                cur.execute(
                    "INSERT OR REPLACE INTO seen(id, ts) VALUES(?, ?)",
                    (item_id, ts),
                )
                conn.commit()
                log.debug("marked_seen item_id=%s", item_id[:80])
            except Exception as e:  # pragma: no cover - non-fatal
                log.error(
                    "mark_seen_error item_id=%s err=%s thread_id=%s",
                    item_id,
                    str(e),
                    threading.current_thread().ident,
                    exc_info=True,
                )
                raise  # Re-raise for caller to handle

    def cleanup_old_entries(self, days_old: int = 30) -> int:
        """
        Remove entries older than N days (thread-safe).

        Args:
            days_old: Number of days to keep. Entries older than this are deleted.

        Returns:
            Number of entries deleted.
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cutoff = int(time.time()) - (days_old * 86400)
                cursor = conn.execute("DELETE FROM seen WHERE ts < ?", (cutoff,))
                deleted = cursor.rowcount
                conn.commit()
                log.info(
                    "seen_store_cleanup deleted=%d cutoff_days=%d", deleted, days_old
                )
                return deleted
            except Exception as e:
                log.error("cleanup_error err=%s", str(e), exc_info=True)
                return 0


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
