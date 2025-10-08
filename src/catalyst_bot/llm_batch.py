"""
LLM Request Batching and Queue Management
==========================================

Batches multiple LLM requests to reduce overhead and improve throughput.

Features:
- Request queuing with priority levels
- Automatic batching of similar requests
- Concurrent processing with thread pool
- Response caching to avoid duplicate queries
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from queue import Empty, PriorityQueue
from typing import Any, Callable, Dict, List, Optional

from .llm_client import query_llm
from .logging_utils import get_logger

log = get_logger("llm_batch")


@dataclass
class LLMRequest:
    """LLM request with priority and metadata."""

    prompt: str
    system: Optional[str] = None
    priority: int = 5  # 1=highest, 10=lowest
    timeout: float = 20.0
    callback: Optional[Callable[[Optional[str]], None]] = None
    request_id: Optional[str] = None

    def __lt__(self, other):
        """Priority queue comparison (lower priority number = higher priority)."""
        return self.priority < other.priority


class LLMBatchProcessor:
    """Process LLM requests in batches with caching and concurrency."""

    def __init__(self, max_workers: int = 3, cache_ttl: int = 3600):
        """
        Initialize batch processor.

        Parameters
        ----------
        max_workers : int
            Number of concurrent LLM workers (default: 3)
        cache_ttl : int
            Cache time-to-live in seconds (default: 3600 = 1 hour)
        """
        self.max_workers = max_workers
        self.cache_ttl = cache_ttl

        self.request_queue = PriorityQueue()
        self.workers: List[threading.Thread] = []
        self.running = False

        # Response cache: {request_hash: (response, timestamp)}
        self.cache: Dict[str, tuple] = {}
        self.cache_lock = threading.Lock()

        # Stats
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "batches_processed": 0,
            "avg_batch_size": 0.0,
        }
        self.stats_lock = threading.Lock()

    def start(self):
        """Start worker threads."""
        if self.running:
            log.warning("llm_batch_processor already running")
            return

        self.running = True

        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop, name=f"llm_worker_{i}", daemon=True
            )
            worker.start()
            self.workers.append(worker)

        log.info(f"llm_batch_processor_started workers={self.max_workers}")

    def stop(self):
        """Stop worker threads."""
        self.running = False

        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=5)

        self.workers.clear()
        log.info("llm_batch_processor_stopped")

    def submit(
        self,
        prompt: str,
        system: Optional[str] = None,
        priority: int = 5,
        timeout: float = 20.0,
        callback: Optional[Callable[[Optional[str]], None]] = None,
    ) -> str:
        """
        Submit LLM request to queue.

        Parameters
        ----------
        prompt : str
            User prompt
        system : str, optional
            System message
        priority : int
            Priority level (1=highest, 10=lowest)
        timeout : float
            Request timeout in seconds
        callback : callable, optional
            Callback function to receive response

        Returns
        -------
        str
            Request ID for tracking
        """
        # Generate request ID
        request_id = hashlib.md5(f"{prompt}{system}{time.time()}".encode()).hexdigest()[
            :12
        ]

        # Check cache first
        cache_key = self._cache_key(prompt, system)
        cached_response = self._get_cached(cache_key)

        if cached_response is not None:
            with self.stats_lock:
                self.stats["cache_hits"] += 1

            log.debug(f"llm_cache_hit id={request_id}")

            # Invoke callback immediately
            if callback:
                callback(cached_response)

            return request_id

        # Cache miss - queue request
        with self.stats_lock:
            self.stats["total_requests"] += 1
            self.stats["cache_misses"] += 1

        request = LLMRequest(
            prompt=prompt,
            system=system,
            priority=priority,
            timeout=timeout,
            callback=callback,
            request_id=request_id,
        )

        self.request_queue.put(request)
        log.debug(f"llm_request_queued id={request_id} priority={priority}")

        return request_id

    def submit_batch(self, requests: List[Dict[str, Any]]) -> List[str]:
        """
        Submit multiple requests at once.

        Parameters
        ----------
        requests : list of dict
            List of request dicts with keys: prompt, system, priority, timeout, callback

        Returns
        -------
        list of str
            Request IDs
        """
        request_ids = []

        for req in requests:
            req_id = self.submit(
                prompt=req.get("prompt", ""),
                system=req.get("system"),
                priority=req.get("priority", 5),
                timeout=req.get("timeout", 20.0),
                callback=req.get("callback"),
            )
            request_ids.append(req_id)

        log.info(f"llm_batch_submitted count={len(requests)}")
        return request_ids

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        with self.stats_lock:
            stats_copy = self.stats.copy()

        # Calculate cache hit rate
        total = stats_copy["cache_hits"] + stats_copy["cache_misses"]
        if total > 0:
            stats_copy["cache_hit_rate"] = stats_copy["cache_hits"] / total
        else:
            stats_copy["cache_hit_rate"] = 0.0

        stats_copy["queue_size"] = self.request_queue.qsize()
        stats_copy["cache_size"] = len(self.cache)

        return stats_copy

    def _worker_loop(self):
        """Worker thread main loop."""
        while self.running:
            try:
                # Get request from queue (block for 1 second)
                request = self.request_queue.get(timeout=1.0)

                # Process request
                self._process_request(request)

            except Empty:
                continue
            except Exception as e:
                log.error(f"llm_worker_error err={e}")

    def _process_request(self, request: LLMRequest):
        """Process a single LLM request."""
        try:
            # Query LLM
            response = query_llm(
                prompt=request.prompt,
                system=request.system,
                timeout=request.timeout,
            )

            # Cache response
            cache_key = self._cache_key(request.prompt, request.system)
            self._set_cached(cache_key, response)

            # Invoke callback
            if request.callback:
                request.callback(response)

            log.debug(f"llm_request_completed id={request.request_id}")

        except Exception as e:
            log.error(f"llm_request_failed id={request.request_id} err={e}")

            # Invoke callback with None on error
            if request.callback:
                request.callback(None)

    def _cache_key(self, prompt: str, system: Optional[str]) -> str:
        """Generate cache key from prompt and system message."""
        content = f"{prompt}|{system or ''}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[str]:
        """Get cached response if not expired."""
        with self.cache_lock:
            if key not in self.cache:
                return None

            response, timestamp = self.cache[key]

            # Check if expired
            if time.time() - timestamp > self.cache_ttl:
                del self.cache[key]
                return None

            return response

    def _set_cached(self, key: str, response: Optional[str]):
        """Store response in cache."""
        if response is None:
            return

        with self.cache_lock:
            self.cache[key] = (response, time.time())

            # Prune expired entries if cache is large
            if len(self.cache) > 1000:
                self._prune_cache()

    def _prune_cache(self):
        """Remove expired cache entries."""
        now = time.time()
        expired_keys = [
            k for k, (_, ts) in self.cache.items() if now - ts > self.cache_ttl
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            log.debug(f"llm_cache_pruned count={len(expired_keys)}")


# Global batch processor instance
_batch_processor: Optional[LLMBatchProcessor] = None


def get_batch_processor() -> LLMBatchProcessor:
    """Get global batch processor instance (lazy initialization)."""
    global _batch_processor

    if _batch_processor is None:
        max_workers = int(os.getenv("LLM_BATCH_WORKERS", "3"))
        cache_ttl = int(os.getenv("LLM_CACHE_TTL", "3600"))

        _batch_processor = LLMBatchProcessor(
            max_workers=max_workers,
            cache_ttl=cache_ttl,
        )
        _batch_processor.start()

    return _batch_processor


def submit_llm_request(
    prompt: str,
    system: Optional[str] = None,
    priority: int = 5,
    callback: Optional[Callable[[Optional[str]], None]] = None,
) -> str:
    """
    Submit LLM request to global batch processor.

    This is the recommended way to make LLM calls in production.

    Parameters
    ----------
    prompt : str
        User prompt
    system : str, optional
        System message
    priority : int
        Priority level (1=highest, 10=lowest)
    callback : callable, optional
        Callback to receive response

    Returns
    -------
    str
        Request ID
    """
    processor = get_batch_processor()
    return processor.submit(prompt, system, priority, callback=callback)
