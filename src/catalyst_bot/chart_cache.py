"""SQLite-based chart caching system to avoid regenerating identical charts.

Caches chart URLs by (ticker, timeframe) with TTL-based expiration. Charts are
stored in a SQLite database with automatic cleanup of expired entries.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("chart_cache")


log = get_logger("chart_cache")


class ChartCache:
    """SQLite-based cache for chart URLs with TTL expiration.

    Attributes
    ----------
    db_path : Path
        Path to SQLite database file
    ttl_map : dict
        Mapping of timeframe -> TTL in seconds
    """

    # TTL strategy (in seconds)
    TTL_MAP = {
        "1D": 60,  # 1 minute (intraday, volatile)
        "5D": 300,  # 5 minutes
        "1M": 900,  # 15 minutes
        "3M": 3600,  # 1 hour
        "1Y": 3600,  # 1 hour
    }

    def __init__(
        self,
        db_path: str | Path = "data/chart_cache.db",
        ttl_map: Optional[dict] = None,
    ):
        """Initialize the chart cache.

        Parameters
        ----------
        db_path : str | Path
            Path to SQLite database file
        ttl_map : Optional[dict]
            Custom TTL mapping (timeframe -> seconds)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Allow custom TTL map or use defaults
        self.ttl_map = ttl_map or self.TTL_MAP.copy()

        # Override from environment variables if provided
        env_ttls = {
            "1D": os.getenv("CHART_CACHE_1D_TTL"),
            "5D": os.getenv("CHART_CACHE_5D_TTL"),
            "1M": os.getenv("CHART_CACHE_1M_TTL"),
            "3M": os.getenv("CHART_CACHE_3M_TTL"),
        }
        for tf, val in env_ttls.items():
            if val:
                try:
                    self.ttl_map[tf] = int(val)
                except ValueError:
                    log.warning("invalid_ttl_env tf=%s val=%s", tf, val)

        # Initialize database schema
        self._init_db()

        # Auto-cleanup on startup
        self._cleanup_old_entries()

    def _init_db(self):
        """Create the chart_cache table if it doesn't exist."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chart_cache (
                    ticker TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    url TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    ttl INTEGER NOT NULL,
                    PRIMARY KEY (ticker, timeframe)
                )
                """
            )
            # Create index for efficient cleanup queries
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON chart_cache(created_at)
                """
            )
            conn.commit()

        log.info("chart_cache_initialized db=%s", self.db_path)

    def _cleanup_old_entries(self):
        """Delete entries older than 24 hours on startup."""
        cutoff = int(time.time()) - (24 * 60 * 60)  # 24 hours ago

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM chart_cache WHERE created_at < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
            conn.commit()

        if deleted > 0:
            log.info("chart_cache_cleanup deleted=%d", deleted)

    def _get_ttl(self, timeframe: str) -> int:
        """Get TTL for a timeframe (default: 300 seconds)."""
        return self.ttl_map.get(timeframe.upper(), 300)

    def get_cached_chart(self, ticker: str, timeframe: str) -> Optional[Path]:
        """Retrieve a cached chart URL if not expired.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        timeframe : str
            Timeframe (1D, 5D, 1M, 3M, 1Y)

        Returns
        -------
        Optional[Path]
            Cached chart path or None if cache miss/expired
        """
        ticker = ticker.upper()
        timeframe = timeframe.upper()

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                """
                SELECT url, created_at, ttl
                FROM chart_cache
                WHERE ticker = ? AND timeframe = ?
                """,
                (ticker, timeframe),
            )
            row = cursor.fetchone()

        if not row:
            log.debug("cache_miss ticker=%s tf=%s reason=not_found", ticker, timeframe)
            return None

        url, created_at, ttl = row
        age = int(time.time()) - created_at

        # Check if expired
        if age > ttl:
            log.debug(
                "cache_miss ticker=%s tf=%s reason=expired age=%ds ttl=%ds",
                ticker,
                timeframe,
                age,
                ttl,
            )
            return None

        log.info("cache_hit ticker=%s tf=%s age=%ds", ticker, timeframe, age)
        # Convert string path to Path object for compatibility
        return Path(url) if isinstance(url, str) else url

    def cache_chart(
        self,
        ticker: str,
        timeframe: str,
        url: str | Path,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Store a chart URL in the cache.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        timeframe : str
            Timeframe (1D, 5D, 1M, 3M, 1Y)
        url : str
            Chart image URL
        ttl_seconds : Optional[int]
            Custom TTL in seconds (defaults to timeframe-based TTL)
        """
        ticker = ticker.upper()
        timeframe = timeframe.upper()

        # Convert Path to string if needed
        url_str = str(url) if isinstance(url, Path) else url

        # Use custom TTL or default based on timeframe
        ttl = ttl_seconds if ttl_seconds is not None else self._get_ttl(timeframe)
        created_at = int(time.time())

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO chart_cache
                (ticker, timeframe, url, created_at, ttl)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ticker, timeframe, url_str, created_at, ttl),
            )
            conn.commit()

        log.info(
            "cache_put ticker=%s tf=%s ttl=%ds url=%s",
            ticker,
            timeframe,
            ttl,
            url_str[:60],
        )

    def clear_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns
        -------
        int
            Number of entries removed
        """
        now = int(time.time())

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                """
                DELETE FROM chart_cache
                WHERE (created_at + ttl) < ?
                """,
                (now,),
            )
            deleted = cursor.rowcount
            conn.commit()

        if deleted > 0:
            log.info("cache_cleared_expired count=%d", deleted)

        return deleted

    def clear_all(self) -> int:
        """Remove all entries from the cache.

        Returns
        -------
        int
            Number of entries removed
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("DELETE FROM chart_cache")
            deleted = cursor.rowcount
            conn.commit()

        log.info("cache_cleared_all count=%d", deleted)
        return deleted

    def stats(self) -> dict:
        """Get cache statistics.

        Returns
        -------
        dict
            Cache statistics including size, oldest/newest entries
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            # Get total count
            cursor = conn.execute("SELECT COUNT(*) FROM chart_cache")
            total = cursor.fetchone()[0]

            if total == 0:
                return {
                    "size": 0,
                    "oldest": None,
                    "newest": None,
                    "expired": 0,
                }

            # Get oldest and newest timestamps
            cursor = conn.execute(
                "SELECT MIN(created_at), MAX(created_at) FROM chart_cache"
            )
            oldest, newest = cursor.fetchone()

            # Count expired entries
            now = int(time.time())
            cursor = conn.execute(
                "SELECT COUNT(*) FROM chart_cache WHERE (created_at + ttl) < ?",
                (now,),
            )
            expired = cursor.fetchone()[0]

        return {
            "size": total,
            "oldest": oldest,
            "newest": newest,
            "expired": expired,
        }


# Global cache instance
_CACHE: Optional[ChartCache] = None


def get_cache() -> ChartCache:
    """Get or create the global chart cache instance."""
    global _CACHE

    if _CACHE is None:
        # Read cache settings from environment
        db_path = os.getenv("CHART_CACHE_DB_PATH", "data/chart_cache.db")

        # Check if caching is enabled
        cache_enabled = os.getenv("CHART_CACHE_ENABLED", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        if not cache_enabled:
            log.warning("chart_cache_disabled using_in_memory_cache")
            # Return a cache instance anyway but with very short TTLs
            _CACHE = ChartCache(db_path=":memory:")
        else:
            _CACHE = ChartCache(db_path=db_path)

    return _CACHE
