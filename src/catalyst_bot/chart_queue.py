"""
Chart Generation Queue with Worker Pool
========================================

Parallel chart rendering to avoid blocking the main alert loop.

Features:
- Worker pool for concurrent chart generation
- Priority queue (alerts vs on-demand)
- Chart result caching
- Async chart generation for Discord embeds
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import PriorityQueue, Empty
from typing import Any, Dict, List, Optional, Callable

from .logging_utils import get_logger

log = get_logger("chart_queue")


@dataclass
class ChartRequest:
    """Chart generation request."""
    ticker: str
    timeframe: str = "1D"
    priority: int = 5  # 1=highest, 10=lowest
    callback: Optional[Callable[[Optional[str]], None]] = None
    request_id: Optional[str] = None
    chart_type: str = "advanced"  # "advanced" or "basic"

    def __lt__(self, other):
        """Priority queue comparison."""
        return self.priority < other.priority


class ChartGenerationQueue:
    """Process chart generation requests in parallel."""

    def __init__(self, max_workers: int = 4, cache_ttl: int = 300):
        """
        Initialize chart queue.

        Parameters
        ----------
        max_workers : int
            Number of concurrent chart workers (default: 4)
        cache_ttl : int
            Cache TTL in seconds (default: 300 = 5 minutes)
        """
        self.max_workers = max_workers
        self.cache_ttl = cache_ttl

        self.request_queue = PriorityQueue()
        self.workers: List[threading.Thread] = []
        self.running = False

        # Chart cache: {cache_key: (chart_path, timestamp)}
        self.cache: Dict[str, tuple] = {}
        self.cache_lock = threading.Lock()

        # Stats
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'charts_generated': 0,
            'avg_generation_time': 0.0,
        }
        self.stats_lock = threading.Lock()

    def start(self):
        """Start worker threads."""
        if self.running:
            log.warning("chart_queue already running")
            return

        self.running = True

        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"chart_worker_{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        log.info(f"chart_queue_started workers={self.max_workers}")

    def stop(self):
        """Stop worker threads."""
        self.running = False

        for worker in self.workers:
            worker.join(timeout=5)

        self.workers.clear()
        log.info("chart_queue_stopped")

    def submit(
        self,
        ticker: str,
        timeframe: str = "1D",
        priority: int = 5,
        chart_type: str = "advanced",
        callback: Optional[Callable[[Optional[str]], None]] = None,
    ) -> str:
        """
        Submit chart generation request.

        Parameters
        ----------
        ticker : str
            Stock ticker
        timeframe : str
            Chart timeframe (1D, 5D, 1M, 3M, 1Y)
        priority : int
            Priority level (1=highest, 10=lowest)
        chart_type : str
            "advanced" or "basic"
        callback : callable, optional
            Callback to receive chart path

        Returns
        -------
        str
            Request ID
        """
        # Generate request ID
        request_id = hashlib.md5(
            f"{ticker}{timeframe}{chart_type}{time.time()}".encode()
        ).hexdigest()[:12]

        # Check cache
        cache_key = self._cache_key(ticker, timeframe, chart_type)
        cached_path = self._get_cached(cache_key)

        if cached_path is not None:
            with self.stats_lock:
                self.stats['cache_hits'] += 1

            log.debug(f"chart_cache_hit id={request_id} ticker={ticker}")

            if callback:
                callback(cached_path)

            return request_id

        # Cache miss - queue request
        with self.stats_lock:
            self.stats['total_requests'] += 1
            self.stats['cache_misses'] += 1

        request = ChartRequest(
            ticker=ticker,
            timeframe=timeframe,
            priority=priority,
            callback=callback,
            request_id=request_id,
            chart_type=chart_type,
        )

        self.request_queue.put(request)
        log.debug(f"chart_request_queued id={request_id} ticker={ticker} tf={timeframe}")

        return request_id

    def submit_batch(self, requests: List[Dict[str, Any]]) -> List[str]:
        """
        Submit multiple chart requests.

        Parameters
        ----------
        requests : list of dict
            List with keys: ticker, timeframe, priority, chart_type, callback

        Returns
        -------
        list of str
            Request IDs
        """
        request_ids = []

        for req in requests:
            req_id = self.submit(
                ticker=req.get('ticker', ''),
                timeframe=req.get('timeframe', '1D'),
                priority=req.get('priority', 5),
                chart_type=req.get('chart_type', 'advanced'),
                callback=req.get('callback'),
            )
            request_ids.append(req_id)

        log.info(f"chart_batch_submitted count={len(requests)}")
        return request_ids

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        with self.stats_lock:
            stats_copy = self.stats.copy()

        total = stats_copy['cache_hits'] + stats_copy['cache_misses']
        if total > 0:
            stats_copy['cache_hit_rate'] = stats_copy['cache_hits'] / total
        else:
            stats_copy['cache_hit_rate'] = 0.0

        stats_copy['queue_size'] = self.request_queue.qsize()
        stats_copy['cache_size'] = len(self.cache)

        return stats_copy

    def _worker_loop(self):
        """Worker thread main loop."""
        while self.running:
            try:
                request = self.request_queue.get(timeout=1.0)
                self._process_request(request)

            except Empty:
                continue
            except Exception as e:
                log.error(f"chart_worker_error err={e}")

    def _process_request(self, request: ChartRequest):
        """Process a single chart request."""
        start_time = time.time()

        try:
            # Generate chart
            chart_path = self._generate_chart(
                ticker=request.ticker,
                timeframe=request.timeframe,
                chart_type=request.chart_type,
            )

            # Update stats
            elapsed = time.time() - start_time
            with self.stats_lock:
                self.stats['charts_generated'] += 1
                # Exponential moving average
                alpha = 0.2
                self.stats['avg_generation_time'] = (
                    alpha * elapsed + (1 - alpha) * self.stats['avg_generation_time']
                )

            # Cache result
            cache_key = self._cache_key(request.ticker, request.timeframe, request.chart_type)
            self._set_cached(cache_key, chart_path)

            # Invoke callback
            if request.callback:
                request.callback(chart_path)

            log.debug(
                f"chart_generated id={request.request_id} ticker={request.ticker} "
                f"time={elapsed:.2f}s"
            )

        except Exception as e:
            log.error(f"chart_generation_failed id={request.request_id} ticker={request.ticker} err={e}")

            if request.callback:
                request.callback(None)

    def _generate_chart(self, ticker: str, timeframe: str, chart_type: str) -> Optional[str]:
        """
        Generate chart and return path.

        This delegates to the actual chart generation logic.
        """
        try:
            if chart_type == "advanced":
                from .charts_advanced import generate_advanced_chart
                chart_path = generate_advanced_chart(ticker, timeframe)
            else:
                from .charts import generate_chart_url
                chart_path = generate_chart_url(ticker, timeframe)

            return chart_path

        except Exception as e:
            log.error(f"chart_generation_error ticker={ticker} tf={timeframe} err={e}")
            return None

    def _cache_key(self, ticker: str, timeframe: str, chart_type: str) -> str:
        """Generate cache key."""
        return f"{ticker}_{timeframe}_{chart_type}".lower()

    def _get_cached(self, key: str) -> Optional[str]:
        """Get cached chart path if not expired."""
        with self.cache_lock:
            if key not in self.cache:
                return None

            chart_path, timestamp = self.cache[key]

            # Check if expired
            if time.time() - timestamp > self.cache_ttl:
                del self.cache[key]
                return None

            # Check if file still exists
            if not Path(chart_path).exists():
                del self.cache[key]
                return None

            return chart_path

    def _set_cached(self, key: str, chart_path: Optional[str]):
        """Store chart path in cache."""
        if chart_path is None:
            return

        with self.cache_lock:
            self.cache[key] = (chart_path, time.time())

            # Prune if cache is large
            if len(self.cache) > 500:
                self._prune_cache()

    def _prune_cache(self):
        """Remove expired cache entries."""
        now = time.time()
        expired_keys = [
            k for k, (_, ts) in self.cache.items()
            if now - ts > self.cache_ttl
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            log.debug(f"chart_cache_pruned count={len(expired_keys)}")


# Global chart queue instance
_chart_queue: Optional[ChartGenerationQueue] = None


def get_chart_queue() -> ChartGenerationQueue:
    """Get global chart queue instance (lazy initialization)."""
    global _chart_queue

    if _chart_queue is None:
        max_workers = int(os.getenv('CHART_QUEUE_WORKERS', '4'))
        cache_ttl = int(os.getenv('CHART_CACHE_TTL', '300'))

        _chart_queue = ChartGenerationQueue(
            max_workers=max_workers,
            cache_ttl=cache_ttl,
        )
        _chart_queue.start()

    return _chart_queue


def submit_chart_request(
    ticker: str,
    timeframe: str = "1D",
    priority: int = 5,
    chart_type: str = "advanced",
    callback: Optional[Callable[[Optional[str]], None]] = None,
) -> str:
    """
    Submit chart generation request to global queue.

    Parameters
    ----------
    ticker : str
        Stock ticker
    timeframe : str
        Chart timeframe
    priority : int
        Priority level (1=highest, 10=lowest)
    chart_type : str
        "advanced" or "basic"
    callback : callable, optional
        Callback to receive chart path

    Returns
    -------
    str
        Request ID
    """
    queue = get_chart_queue()
    return queue.submit(ticker, timeframe, priority, chart_type, callback)
