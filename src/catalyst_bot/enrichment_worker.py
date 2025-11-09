"""Async enrichment worker system for parallel market data enrichment.

This module provides a threaded worker system that enriches ScoredItems with
market data (RVOL, float, VWAP, divergence) in parallel after fast classification.

Architecture:
- EnrichmentQueue: Thread-safe queue for items awaiting enrichment
- EnrichmentWorker: Background thread that processes enrichment in batches
- Batch functions: Parallel API calls using ThreadPoolExecutor

Usage:
    from enrichment_worker import get_enrichment_worker, enqueue_for_enrichment

    # Start worker (once at app startup)
    worker = get_enrichment_worker()

    # Enqueue items for enrichment
    enqueue_for_enrichment(scored_item, news_item)

    # Get enriched result later
    enriched_item = worker.get_enriched_item(scored_item.id, timeout=5.0)
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .models import NewsItem, ScoredItem

log = logging.getLogger(__name__)

# Singleton worker instance
_enrichment_worker: Optional[EnrichmentWorker] = None
_worker_lock = threading.Lock()


@dataclass
class EnrichmentTask:
    """Task for enriching a scored item with market data."""

    scored_item: ScoredItem
    news_item: NewsItem
    enqueued_at: float
    task_id: str  # Unique identifier (ticker + timestamp)


class EnrichmentQueue:
    """Thread-safe queue for enrichment tasks."""

    def __init__(self, maxsize: int = 1000):
        self._queue: queue.Queue[EnrichmentTask] = queue.Queue(maxsize=maxsize)
        self._results: Dict[str, ScoredItem] = {}
        self._results_lock = threading.Lock()

    def put(self, task: EnrichmentTask, block: bool = True, timeout: Optional[float] = None) -> None:
        """Add task to enrichment queue."""
        try:
            self._queue.put(task, block=block, timeout=timeout)
            log.debug(
                "enrichment_task_queued task_id=%s ticker=%s queue_size=%d",
                task.task_id,
                task.news_item.ticker,
                self._queue.qsize(),
            )
        except queue.Full:
            log.warning(
                "enrichment_queue_full task_id=%s ticker=%s queue_size=%d",
                task.task_id,
                task.news_item.ticker,
                self._queue.qsize(),
            )

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[EnrichmentTask]:
        """Get next task from queue."""
        try:
            return self._queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def qsize(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    def store_result(self, task_id: str, enriched_item: ScoredItem) -> None:
        """Store enriched result for later retrieval."""
        with self._results_lock:
            self._results[task_id] = enriched_item
            log.debug(
                "enrichment_result_stored task_id=%s results_cache_size=%d",
                task_id,
                len(self._results),
            )

    def get_result(self, task_id: str) -> Optional[ScoredItem]:
        """Retrieve enriched result if available."""
        with self._results_lock:
            return self._results.pop(task_id, None)

    def cleanup_old_results(self, max_age_seconds: float = 300) -> int:
        """Remove results older than max_age_seconds. Returns count removed."""
        current_time = time.time()
        removed = 0
        with self._results_lock:
            task_ids = list(self._results.keys())
            for task_id in task_ids:
                item = self._results.get(task_id)
                if item and item.enrichment_timestamp:
                    age = current_time - item.enrichment_timestamp
                    if age > max_age_seconds:
                        self._results.pop(task_id, None)
                        removed += 1
        if removed > 0:
            log.debug("enrichment_results_cleanup removed=%d", removed)
        return removed


class EnrichmentWorker:
    """Background worker thread for parallel enrichment."""

    def __init__(
        self,
        batch_size: int = 10,
        batch_timeout: float = 2.0,
        max_workers: int = 5,
    ):
        """
        Initialize enrichment worker.

        Args:
            batch_size: Maximum items to process in one batch
            batch_timeout: Maximum time to wait for batch to fill (seconds)
            max_workers: ThreadPoolExecutor worker threads for parallel API calls
        """
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.max_workers = max_workers

        self.queue = EnrichmentQueue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._executor: Optional[ThreadPoolExecutor] = None

    def start(self) -> None:
        """Start background worker thread."""
        if self._running:
            log.warning("enrichment_worker_already_running")
            return

        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="enrichment")
        self._thread = threading.Thread(target=self._worker_loop, name="enrichment-worker", daemon=True)
        self._thread.start()
        log.info(
            "enrichment_worker_started batch_size=%d batch_timeout=%.1fs max_workers=%d",
            self.batch_size,
            self.batch_timeout,
            self.max_workers,
        )

    def stop(self, timeout: float = 10.0) -> None:
        """Stop background worker thread."""
        if not self._running:
            return

        log.info("enrichment_worker_stopping")
        self._running = False

        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                log.warning("enrichment_worker_did_not_stop_in_time timeout=%.1fs", timeout)

        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=False)
            self._executor = None

        log.info("enrichment_worker_stopped")

    def enqueue(self, scored_item: ScoredItem, news_item: NewsItem) -> str:
        """
        Add item to enrichment queue.

        Returns:
            task_id for retrieving enriched result later
        """
        task_id = f"{news_item.ticker}_{int(time.time() * 1000)}"
        task = EnrichmentTask(
            scored_item=scored_item,
            news_item=news_item,
            enqueued_at=time.time(),
            task_id=task_id,
        )
        self.queue.put(task)
        return task_id

    def get_enriched_item(self, task_id: str, timeout: float = 5.0) -> Optional[ScoredItem]:
        """
        Retrieve enriched item by task_id.

        Args:
            task_id: Task identifier from enqueue()
            timeout: Maximum time to wait for enrichment (seconds)

        Returns:
            Enriched ScoredItem or None if not ready/timed out
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.queue.get_result(task_id)
            if result:
                return result
            time.sleep(0.1)  # Poll every 100ms

        log.debug("enrichment_result_timeout task_id=%s timeout=%.1fs", task_id, timeout)
        return None

    def _worker_loop(self) -> None:
        """Main worker loop: collect batches and process them."""
        log.info("enrichment_worker_loop_started")

        while self._running:
            try:
                # Collect batch of tasks
                batch = self._collect_batch()
                if not batch:
                    continue

                # Process batch in parallel
                self._process_batch(batch)

                # Periodic cleanup of old results
                if int(time.time()) % 60 == 0:  # Every minute
                    self.queue.cleanup_old_results(max_age_seconds=300)

            except Exception as e:
                log.error("enrichment_worker_loop_error err=%s", str(e), exc_info=True)
                time.sleep(1.0)  # Backoff on error

        log.info("enrichment_worker_loop_stopped")

    def _collect_batch(self) -> List[EnrichmentTask]:
        """Collect batch of tasks from queue."""
        batch: List[EnrichmentTask] = []
        deadline = time.time() + self.batch_timeout

        while len(batch) < self.batch_size and time.time() < deadline:
            remaining_time = deadline - time.time()
            if remaining_time <= 0:
                break

            task = self.queue.get(block=True, timeout=min(remaining_time, 0.5))
            if task:
                batch.append(task)

        if batch:
            log.debug("enrichment_batch_collected count=%d", len(batch))

        return batch

    def _process_batch(self, batch: List[EnrichmentTask]) -> None:
        """Process batch of enrichment tasks in parallel."""
        start_time = time.time()

        if not self._executor:
            log.error("enrichment_executor_not_initialized")
            return

        # Group tasks by ticker (same ticker can share API calls)
        ticker_tasks: Dict[str, List[EnrichmentTask]] = {}
        for task in batch:
            ticker = task.news_item.ticker
            if ticker not in ticker_tasks:
                ticker_tasks[ticker] = []
            ticker_tasks[ticker].append(task)

        # Submit enrichment jobs for each ticker
        futures = {}
        for ticker, tasks in ticker_tasks.items():
            future = self._executor.submit(self._enrich_ticker_batch, ticker, tasks)
            futures[future] = ticker

        # Wait for all enrichment jobs to complete
        completed = 0
        failed = 0
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                enriched_count = future.result()
                completed += enriched_count
            except Exception as e:
                log.error("enrichment_batch_failed ticker=%s err=%s", ticker, str(e))
                failed += 1

        elapsed = time.time() - start_time
        log.info(
            "enrichment_batch_processed total=%d completed=%d failed=%d elapsed=%.2fs",
            len(batch),
            completed,
            failed,
            elapsed,
        )

    def _enrich_ticker_batch(self, ticker: str, tasks: List[EnrichmentTask]) -> int:
        """Enrich all tasks for a specific ticker (can share API calls)."""
        from .classify import enrich_scored_item

        enriched_count = 0

        for task in tasks:
            try:
                # Enrich the scored item with market data
                enriched_item = enrich_scored_item(task.scored_item, task.news_item)

                # Store result for retrieval
                self.queue.store_result(task.task_id, enriched_item)
                enriched_count += 1

            except Exception as e:
                log.error(
                    "enrichment_task_failed task_id=%s ticker=%s err=%s",
                    task.task_id,
                    ticker,
                    str(e),
                )

        return enriched_count


def get_enrichment_worker() -> EnrichmentWorker:
    """Get singleton enrichment worker instance (creates and starts if needed)."""
    global _enrichment_worker
    with _worker_lock:
        if _enrichment_worker is None:
            import os

            batch_size = int(os.getenv("ENRICHMENT_BATCH_SIZE", "10"))
            batch_timeout = float(os.getenv("ENRICHMENT_BATCH_TIMEOUT", "2.0"))
            max_workers = int(os.getenv("ENRICHMENT_WORKER_THREADS", "5"))

            _enrichment_worker = EnrichmentWorker(
                batch_size=batch_size,
                batch_timeout=batch_timeout,
                max_workers=max_workers,
            )
            _enrichment_worker.start()

        return _enrichment_worker


def enqueue_for_enrichment(scored_item: ScoredItem, news_item: NewsItem) -> str:
    """
    Enqueue item for async enrichment.

    Returns:
        task_id for retrieving enriched result later
    """
    worker = get_enrichment_worker()
    return worker.enqueue(scored_item, news_item)


def get_enriched_item(task_id: str, timeout: float = 5.0) -> Optional[ScoredItem]:
    """
    Retrieve enriched item by task_id (blocks up to timeout seconds).

    Returns:
        Enriched ScoredItem or None if not ready
    """
    worker = get_enrichment_worker()
    return worker.get_enriched_item(task_id, timeout=timeout)


def stop_enrichment_worker(timeout: float = 10.0) -> None:
    """Stop enrichment worker (for graceful shutdown)."""
    global _enrichment_worker
    with _worker_lock:
        if _enrichment_worker:
            _enrichment_worker.stop(timeout=timeout)
            _enrichment_worker = None
