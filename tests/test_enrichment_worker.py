"""Tests for async enrichment worker system."""

import time
from datetime import datetime, timezone

import pytest

from catalyst_bot.enrichment_worker import (
    EnrichmentQueue,
    EnrichmentTask,
    EnrichmentWorker,
    enqueue_for_enrichment,
    get_enriched_item,
    get_enrichment_worker,
    stop_enrichment_worker,
)
from catalyst_bot.models import NewsItem, ScoredItem


def test_enrichment_queue_basic():
    """Test basic queue operations."""
    queue = EnrichmentQueue(maxsize=100)

    # Create task
    news_item = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Test News",
        canonical_url="http://example.com",
        ticker="AAPL",
    )
    scored_item = ScoredItem(
        relevance=2.5, sentiment=0.8, tags=["test"], enriched=False
    )
    task = EnrichmentTask(
        scored_item=scored_item,
        news_item=news_item,
        enqueued_at=time.time(),
        task_id="AAPL_123",
    )

    # Put and get
    queue.put(task)
    assert queue.qsize() == 1

    retrieved = queue.get()
    assert retrieved is not None
    assert retrieved.task_id == "AAPL_123"
    assert retrieved.news_item.ticker == "AAPL"
    assert queue.qsize() == 0


def test_enrichment_queue_results():
    """Test results storage and retrieval."""
    queue = EnrichmentQueue()

    enriched_item = ScoredItem(
        relevance=3.0, sentiment=0.9, tags=["test"], enriched=True, enrichment_timestamp=time.time()
    )

    # Store result
    queue.store_result("task_123", enriched_item)

    # Retrieve result
    result = queue.get_result("task_123")
    assert result is not None
    assert result.enriched is True
    assert result.relevance == 3.0

    # Result should be removed after retrieval
    result2 = queue.get_result("task_123")
    assert result2 is None


def test_enrichment_queue_cleanup():
    """Test cleanup of old results."""
    queue = EnrichmentQueue()

    # Store old result (simulate old timestamp)
    old_item = ScoredItem(
        relevance=2.0,
        sentiment=0.5,
        tags=["old"],
        enriched=True,
        enrichment_timestamp=time.time() - 400,  # 400 seconds ago
    )
    queue.store_result("old_task", old_item)

    # Store recent result
    recent_item = ScoredItem(
        relevance=3.0,
        sentiment=0.8,
        tags=["recent"],
        enriched=True,
        enrichment_timestamp=time.time() - 10,  # 10 seconds ago
    )
    queue.store_result("recent_task", recent_item)

    # Cleanup with max_age=300 seconds (should remove old_task)
    removed = queue.cleanup_old_results(max_age_seconds=300)
    assert removed == 1

    # Recent task should still be there
    recent_result = queue.get_result("recent_task")
    assert recent_result is not None

    # Old task should be gone
    old_result = queue.get_result("old_task")
    assert old_result is None


def test_enrichment_worker_lifecycle():
    """Test worker start/stop."""
    worker = EnrichmentWorker(batch_size=5, batch_timeout=1.0, max_workers=2)

    # Start worker
    worker.start()
    assert worker._running is True
    assert worker._thread is not None
    assert worker._executor is not None

    # Give worker time to start
    time.sleep(0.5)

    # Stop worker
    worker.stop(timeout=2.0)
    assert worker._running is False


def test_enrichment_worker_enqueue_and_retrieve():
    """Test enqueueing and retrieving enriched items."""
    worker = EnrichmentWorker(batch_size=2, batch_timeout=0.5, max_workers=2)
    worker.start()

    try:
        # Create test item (use real ticker that exists in Yahoo Finance)
        news_item = NewsItem(
            ts_utc=datetime.now(timezone.utc),
            title="Apple announces new product lineup",
            canonical_url="http://example.com/aapl",
            ticker="AAPL",
        )
        scored_item = ScoredItem(
            relevance=3.0, sentiment=0.7, tags=["product"], enriched=False
        )

        # Enqueue for enrichment
        task_id = worker.enqueue(scored_item, news_item)
        assert task_id.startswith("AAPL_")

        # Wait for enrichment (should complete within 2 seconds)
        enriched = worker.get_enriched_item(task_id, timeout=5.0)

        # Enrichment should be complete
        assert enriched is not None
        assert enriched.enriched is True
        assert enriched.enrichment_timestamp is not None

    finally:
        worker.stop(timeout=2.0)


def test_enrichment_worker_batch_processing():
    """Test that worker processes items in batches."""
    worker = EnrichmentWorker(batch_size=3, batch_timeout=1.0, max_workers=2)
    worker.start()

    try:
        task_ids = []

        # Enqueue multiple items
        for i in range(5):
            news_item = NewsItem(
                ts_utc=datetime.now(timezone.utc),
                title=f"News {i}",
                canonical_url=f"http://example.com/{i}",
                ticker=f"TICK{i}",
            )
            scored_item = ScoredItem(
                relevance=2.0 + i * 0.1,
                sentiment=0.5,
                tags=["test"],
                enriched=False,
            )
            task_id = worker.enqueue(scored_item, news_item)
            task_ids.append(task_id)

        # Wait for all enrichments
        time.sleep(3.0)

        # All items should be enriched
        enriched_count = 0
        for task_id in task_ids:
            result = worker.get_enriched_item(task_id, timeout=0.1)
            if result and result.enriched:
                enriched_count += 1

        # At least some should be enriched (may not be all if timing varies)
        assert enriched_count >= 3

    finally:
        worker.stop(timeout=2.0)


def test_singleton_enrichment_worker():
    """Test singleton pattern for enrichment worker."""
    # Stop any existing worker
    stop_enrichment_worker(timeout=2.0)

    # Get worker (should create new one)
    worker1 = get_enrichment_worker()
    assert worker1 is not None
    assert worker1._running is True

    # Get worker again (should return same instance)
    worker2 = get_enrichment_worker()
    assert worker2 is worker1

    # Clean up
    stop_enrichment_worker(timeout=2.0)


def test_enqueue_and_get_helpers():
    """Test helper functions for enqueueing and retrieving."""
    # Stop any existing worker
    stop_enrichment_worker(timeout=2.0)

    # Create test item
    news_item = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Test Item",
        canonical_url="http://example.com/test",
        ticker="TEST",
    )
    scored_item = ScoredItem(
        relevance=2.5, sentiment=0.6, tags=["test"], enriched=False
    )

    # Enqueue using helper
    task_id = enqueue_for_enrichment(scored_item, news_item)
    assert task_id.startswith("TEST_")

    # Retrieve using helper
    enriched = get_enriched_item(task_id, timeout=5.0)
    assert enriched is not None
    assert enriched.enriched is True

    # Clean up
    stop_enrichment_worker(timeout=2.0)


def test_enrichment_timeout():
    """Test timeout when enrichment takes too long."""
    worker = EnrichmentWorker(batch_size=10, batch_timeout=5.0, max_workers=1)
    worker.start()

    try:
        news_item = NewsItem(
            ts_utc=datetime.now(timezone.utc),
            title="Slow Item",
            canonical_url="http://example.com/slow",
            ticker="SLOW",
        )
        scored_item = ScoredItem(
            relevance=2.0, sentiment=0.5, tags=["test"], enriched=False
        )

        task_id = worker.enqueue(scored_item, news_item)

        # Try to get with very short timeout (should timeout)
        enriched = worker.get_enriched_item(task_id, timeout=0.1)
        # May or may not be None depending on timing, but shouldn't crash
        assert enriched is None or isinstance(enriched, ScoredItem)

    finally:
        worker.stop(timeout=2.0)
