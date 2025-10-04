"""Chart caching system to avoid regenerating identical charts.

Caches charts by (ticker, timeframe) with TTL-based expiration. Charts are
stored as files on disk with a lightweight JSON index tracking metadata.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    from .logging_utils import get_logger
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    def get_logger(_):
        return logging.getLogger("chart_cache")

log = get_logger("chart_cache")


class ChartCache:
    """File-based cache for generated chart images.

    Attributes
    ----------
    cache_dir : Path
        Directory where chart images are stored
    index_file : Path
        JSON file tracking cache metadata
    ttl_seconds : int
        Time-to-live for cached charts (default: 5 minutes)
    """

    def __init__(
        self,
        cache_dir: str | Path = "out/charts/cache",
        ttl_seconds: int = 300,  # 5 minutes default
    ):
        """Initialize the chart cache.

        Parameters
        ----------
        cache_dir : str | Path
            Directory to store cached charts
        ttl_seconds : int
            Cache TTL in seconds (default: 300 = 5 minutes)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.index_file = self.cache_dir / "cache_index.json"
        self.ttl_seconds = ttl_seconds

        # Load existing index
        self.index = self._load_index()

    def _load_index(self) -> Dict[str, Dict]:
        """Load the cache index from disk."""
        if not self.index_file.exists():
            return {}

        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8"))
            return data
        except Exception as e:
            log.warning("index_load_failed err=%s", str(e))
            return {}

    def _save_index(self):
        """Save the cache index to disk."""
        try:
            self.index_file.write_text(
                json.dumps(self.index, indent=2, sort_keys=True),
                encoding="utf-8"
            )
        except Exception as e:
            log.warning("index_save_failed err=%s", str(e))

    def _make_key(self, ticker: str, timeframe: str) -> str:
        """Create a cache key from ticker and timeframe."""
        return f"{ticker.upper()}_{timeframe.upper()}"

    def get(
        self,
        ticker: str,
        timeframe: str
    ) -> Optional[Path]:
        """Retrieve a cached chart if it exists and hasn't expired.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        timeframe : str
            Timeframe (1D, 5D, 1M, 3M, 1Y)

        Returns
        -------
        Path or None
            Path to cached chart image, or None if cache miss/expired
        """
        key = self._make_key(ticker, timeframe)

        if key not in self.index:
            log.debug("cache_miss key=%s reason=not_found", key)
            return None

        entry = self.index[key]
        cached_at = entry.get("cached_at", 0)
        file_path = entry.get("file_path")

        # Check if expired
        age = time.time() - cached_at
        if age > self.ttl_seconds:
            log.debug(
                "cache_miss key=%s reason=expired age=%.1fs ttl=%ds",
                key, age, self.ttl_seconds
            )
            # Clean up expired entry
            self._remove(key)
            return None

        # Check if file still exists
        path = Path(file_path)
        if not path.exists():
            log.debug("cache_miss key=%s reason=file_not_found", key)
            self._remove(key)
            return None

        log.info("cache_hit key=%s age=%.1fs", key, age)
        return path

    def put(
        self,
        ticker: str,
        timeframe: str,
        file_path: Path
    ) -> None:
        """Store a chart in the cache.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        timeframe : str
            Timeframe (1D, 5D, 1M, 3M, 1Y)
        file_path : Path
            Path to the chart image file
        """
        if not file_path.exists():
            log.warning("cache_put_failed reason=file_not_found path=%s", file_path)
            return

        key = self._make_key(ticker, timeframe)

        self.index[key] = {
            "ticker": ticker.upper(),
            "timeframe": timeframe.upper(),
            "file_path": str(file_path.absolute()),
            "cached_at": time.time(),
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        self._save_index()

        log.info("cache_put key=%s path=%s", key, file_path)

    def _remove(self, key: str) -> None:
        """Remove an entry from the cache index."""
        if key in self.index:
            entry = self.index.pop(key)
            self._save_index()

            # Optionally delete the file
            try:
                file_path = Path(entry.get("file_path", ""))
                if file_path.exists():
                    file_path.unlink()
                    log.debug("cache_file_deleted path=%s", file_path)
            except Exception as e:
                log.debug("cache_file_delete_failed err=%s", str(e))

    def clear_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns
        -------
        int
            Number of entries removed
        """
        now = time.time()
        expired_keys = []

        for key, entry in self.index.items():
            cached_at = entry.get("cached_at", 0)
            age = now - cached_at

            if age > self.ttl_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            self._remove(key)

        if expired_keys:
            log.info("cache_cleared_expired count=%d", len(expired_keys))

        return len(expired_keys)

    def clear_all(self) -> int:
        """Remove all entries from the cache.

        Returns
        -------
        int
            Number of entries removed
        """
        count = len(self.index)

        for key in list(self.index.keys()):
            self._remove(key)

        log.info("cache_cleared_all count=%d", count)
        return count

    def stats(self) -> Dict:
        """Get cache statistics.

        Returns
        -------
        Dict
            Cache statistics including size, oldest/newest entries
        """
        if not self.index:
            return {
                "size": 0,
                "oldest": None,
                "newest": None,
                "expired": 0,
                "ttl_seconds": self.ttl_seconds,
            }

        now = time.time()
        cached_times = [e.get("cached_at", 0) for e in self.index.values()]

        oldest = min(cached_times) if cached_times else 0
        newest = max(cached_times) if cached_times else 0

        expired_count = sum(
            1 for t in cached_times
            if (now - t) > self.ttl_seconds
        )

        return {
            "size": len(self.index),
            "oldest": datetime.fromtimestamp(oldest).isoformat() if oldest else None,
            "newest": datetime.fromtimestamp(newest).isoformat() if newest else None,
            "expired": expired_count,
            "ttl_seconds": self.ttl_seconds,
        }


# Global cache instance
_CACHE: Optional[ChartCache] = None


def get_cache() -> ChartCache:
    """Get or create the global chart cache instance."""
    global _CACHE

    if _CACHE is None:
        # Read TTL from environment (default 5 minutes)
        try:
            ttl = int(os.getenv("CHART_CACHE_TTL_SECONDS", "300"))
        except Exception:
            ttl = 300

        cache_dir = os.getenv("CHART_CACHE_DIR", "out/charts/cache")

        _CACHE = ChartCache(cache_dir=cache_dir, ttl_seconds=ttl)

    return _CACHE
