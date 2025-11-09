"""
SEC LLM Cache Module (Agent 2)
================================

Caches SEC filing LLM analysis results to avoid duplicate API calls.

Features:
- 72-hour cache TTL for SEC filing analysis
- SQLite-based persistence
- Automatic cache invalidation for amended filings
- Cache hit/miss statistics
- Thread-safe operations

Environment Variables:
* ``FEATURE_SEC_LLM_CACHE`` – Enable SEC LLM caching (default: 1)
* ``SEC_LLM_CACHE_TTL_HOURS`` – Cache TTL in hours (default: 72)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .storage import init_optimized_connection

_logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry for SEC filing analysis."""

    cache_key: str
    filing_id: str
    ticker: str
    filing_type: str
    analysis_result: Dict[str, Any]
    created_at: float  # Unix timestamp
    expires_at: float  # Unix timestamp
    hit_count: int = 0


class SECLLMCache:
    """
    Cache for SEC filing LLM analysis results.

    Stores analysis results in SQLite database with TTL expiration.
    Automatically invalidates caches when amended filings are detected.
    """

    def __init__(self, db_path: Optional[Path] = None, ttl_hours: int = 72):
        """
        Initialize SEC LLM cache.

        Parameters
        ----------
        db_path : Path, optional
            Path to SQLite database file. If None, uses data/sec_llm_cache.db
        ttl_hours : int
            Cache time-to-live in hours (default: 72)
        """
        # Determine database path
        if db_path is None:
            from .config import get_settings
            settings = get_settings()
            self.db_path = settings.data_dir / "sec_llm_cache.db"
        else:
            self.db_path = Path(db_path)

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.ttl_hours = ttl_hours
        self.ttl_seconds = ttl_hours * 3600

        # Thread-safe lock for database operations
        self._lock = threading.Lock()

        # Cache statistics
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "invalidations": 0,
        }

        # Initialize database
        self._init_db()

        _logger.info(
            "sec_llm_cache_initialized db_path=%s ttl_hours=%d",
            self.db_path,
            ttl_hours,
        )

    def _init_db(self):
        """Initialize SQLite database schema with WAL mode and optimized pragmas."""
        with init_optimized_connection(str(self.db_path), timeout=30) as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")

            cursor = conn.cursor()

            # Create cache table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sec_llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    filing_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    filing_type TEXT NOT NULL,
                    analysis_result TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)

            # Create indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ticker_filing_type
                ON sec_llm_cache(ticker, filing_type)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at
                ON sec_llm_cache(expires_at)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_filing_id
                ON sec_llm_cache(filing_id)
            """)

            conn.commit()

        _logger.debug("sec_llm_cache_schema_initialized wal_mode=enabled")

    def close(self):
        """Close any open database connections (for cleanup in tests)."""
        # SQLite connections are created per-operation, so no persistent connection
        # This method is here for API compatibility
        pass

    def _generate_cache_key(
        self,
        filing_id: str,
        ticker: str,
        filing_type: str,
        document_hash: Optional[str] = None,
    ) -> str:
        """
        Generate cache key from filing metadata.

        Parameters
        ----------
        filing_id : str
            Unique filing identifier (e.g., accession number)
        ticker : str
            Stock ticker
        filing_type : str
            Type of filing (e.g., '8-K', '424B5')
        document_hash : str, optional
            Hash of document content (for additional uniqueness)

        Returns
        -------
        str
            Cache key (MD5 hash)
        """
        # Combine all identifiers
        key_content = f"{filing_id}|{ticker}|{filing_type}"
        if document_hash:
            key_content += f"|{document_hash}"

        # Generate MD5 hash
        return hashlib.md5(key_content.encode()).hexdigest()

    def get_cached_sec_analysis(
        self,
        filing_id: str,
        ticker: str,
        filing_type: str,
        document_hash: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached SEC analysis result (thread-safe).

        Parameters
        ----------
        filing_id : str
            Unique filing identifier
        ticker : str
            Stock ticker
        filing_type : str
            Type of filing
        document_hash : str, optional
            Hash of document content

        Returns
        -------
        dict or None
            Cached analysis result, or None if not found/expired
        """
        # Check if caching is enabled
        if not os.getenv("FEATURE_SEC_LLM_CACHE", "1") in ("1", "true", "yes", "on"):
            return None

        cache_key = self._generate_cache_key(filing_id, ticker, filing_type, document_hash)

        with self._lock:  # Thread-safe access
            self.stats["total_requests"] += 1

            try:
                with init_optimized_connection(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()

                    # Query cache
                    cursor.execute(
                        """
                        SELECT analysis_result, expires_at, hit_count
                        FROM sec_llm_cache
                        WHERE cache_key = ?
                        """,
                        (cache_key,),
                    )

                    row = cursor.fetchone()

                    if row is None:
                        # Cache miss
                        self.stats["cache_misses"] += 1
                        _logger.debug(
                            "sec_llm_cache_miss filing_id=%s ticker=%s filing_type=%s",
                            filing_id,
                            ticker,
                            filing_type,
                        )
                        return None

                    analysis_json, expires_at, hit_count = row

                    # Check if expired
                    now = time.time()
                    if now >= expires_at:
                        # Expired - delete and return None
                        cursor.execute("DELETE FROM sec_llm_cache WHERE cache_key = ?", (cache_key,))
                        conn.commit()

                        self.stats["cache_misses"] += 1
                        _logger.debug(
                            "sec_llm_cache_expired filing_id=%s ticker=%s",
                            filing_id,
                            ticker,
                        )
                        return None

                    # Cache hit - update hit count
                    cursor.execute(
                        "UPDATE sec_llm_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                        (cache_key,),
                    )
                    conn.commit()

                    self.stats["cache_hits"] += 1
                    _logger.info(
                        "sec_llm_cache_hit filing_id=%s ticker=%s hit_count=%d ttl_remaining=%.1fh",
                        filing_id,
                        ticker,
                        hit_count + 1,
                        (expires_at - now) / 3600,
                    )

                    # Deserialize and return
                    return json.loads(analysis_json)

            except Exception as e:
                _logger.error(
                    "sec_llm_cache_get_error filing_id=%s err=%s",
                    filing_id,
                    str(e),
                    exc_info=True
                )
                return None  # Treat errors as cache miss

    def cache_sec_analysis(
        self,
        filing_id: str,
        ticker: str,
        filing_type: str,
        analysis_result: Dict[str, Any],
        document_hash: Optional[str] = None,
    ) -> bool:
        """
        Cache SEC analysis result (thread-safe).

        Parameters
        ----------
        filing_id : str
            Unique filing identifier
        ticker : str
            Stock ticker
        filing_type : str
            Type of filing
        analysis_result : dict
            Analysis result to cache
        document_hash : str, optional
            Hash of document content

        Returns
        -------
        bool
            True if cached successfully
        """
        # Check if caching is enabled
        if not os.getenv("FEATURE_SEC_LLM_CACHE", "1") in ("1", "true", "yes", "on"):
            return False

        cache_key = self._generate_cache_key(filing_id, ticker, filing_type, document_hash)

        with self._lock:  # Thread-safe access
            try:
                now = time.time()
                expires_at = now + self.ttl_seconds

                with init_optimized_connection(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()

                    # Serialize analysis result
                    analysis_json = json.dumps(analysis_result)

                    # Insert or replace
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO sec_llm_cache
                        (cache_key, filing_id, ticker, filing_type, analysis_result, created_at, expires_at, hit_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (cache_key, filing_id, ticker, filing_type, analysis_json, now, expires_at),
                    )

                    conn.commit()

                _logger.info(
                    "sec_llm_cache_set filing_id=%s ticker=%s filing_type=%s ttl_hours=%d",
                    filing_id,
                    ticker,
                    filing_type,
                    self.ttl_hours,
                )

                return True

            except Exception as e:
                _logger.error(
                    "sec_llm_cache_store_error filing_id=%s err=%s",
                    filing_id,
                    str(e),
                    exc_info=True
                )
                return False

    def invalidate_amendment_caches(self, ticker: str, filing_type: str) -> int:
        """
        Invalidate all caches for a ticker/filing_type when amendment is detected.

        Parameters
        ----------
        ticker : str
            Stock ticker
        filing_type : str
            Type of filing (e.g., '8-K/A' indicates amendment)

        Returns
        -------
        int
            Number of cache entries invalidated
        """
        with self._lock:
            try:
                with init_optimized_connection(str(self.db_path)) as conn:
                    cursor = conn.cursor()

                    # Delete all cache entries for this ticker/filing type
                    cursor.execute(
                        """
                        DELETE FROM sec_llm_cache
                        WHERE ticker = ? AND filing_type LIKE ?
                        """,
                        (ticker, f"{filing_type}%"),
                    )

                    deleted_count = cursor.rowcount
                    conn.commit()

                    if deleted_count > 0:
                        self.stats["invalidations"] += deleted_count
                        _logger.info(
                            "sec_llm_cache_invalidated ticker=%s filing_type=%s count=%d",
                            ticker,
                            filing_type,
                            deleted_count,
                        )

                    return deleted_count

            except Exception as e:
                _logger.warning("sec_llm_cache_invalidate_failed err=%s", str(e))
                return 0

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.

        Returns
        -------
        int
            Number of entries removed
        """
        with self._lock:
            try:
                now = time.time()

                with init_optimized_connection(str(self.db_path)) as conn:
                    cursor = conn.cursor()

                    cursor.execute(
                        "DELETE FROM sec_llm_cache WHERE expires_at < ?",
                        (now,),
                    )

                    deleted_count = cursor.rowcount
                    conn.commit()

                    if deleted_count > 0:
                        _logger.info("sec_llm_cache_cleanup count=%d", deleted_count)

                    return deleted_count

            except Exception as e:
                _logger.warning("sec_llm_cache_cleanup_failed err=%s", str(e))
                return 0

    def log_cache_stats(self) -> Dict[str, Any]:
        """
        Log and return cache statistics.

        Returns
        -------
        dict
            Cache statistics
        """
        with self._lock:
            stats = self.stats.copy()

            # Calculate hit rate
            total = stats["cache_hits"] + stats["cache_misses"]
            if total > 0:
                stats["hit_rate"] = stats["cache_hits"] / total
            else:
                stats["hit_rate"] = 0.0

            # Get cache size
            try:
                with init_optimized_connection(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM sec_llm_cache")
                    stats["cache_size"] = cursor.fetchone()[0]
            except Exception:
                stats["cache_size"] = 0

            _logger.info(
                "sec_llm_cache_stats requests=%d hits=%d misses=%d hit_rate=%.1f%% size=%d invalidations=%d",
                stats["total_requests"],
                stats["cache_hits"],
                stats["cache_misses"],
                stats["hit_rate"] * 100,
                stats["cache_size"],
                stats["invalidations"],
            )

            return stats


# Global cache instance (lazy initialization)
_cache: Optional[SECLLMCache] = None


def get_sec_llm_cache() -> SECLLMCache:
    """Get or create the global SEC LLM cache instance."""
    global _cache
    if _cache is None:
        from .config import get_settings
        settings = get_settings()
        ttl_hours = getattr(settings, "sec_llm_cache_ttl_hours", 72)
        _cache = SECLLMCache(ttl_hours=ttl_hours)
    return _cache
