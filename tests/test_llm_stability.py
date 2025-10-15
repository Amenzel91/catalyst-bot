"""
Tests for LLM Stability Enhancements (Wave 0.2)

Tests cover:
- Rate limiting with sliding windows
- Batch processing with pre-filtering
- Error handling and graceful degradation
- GPU warmup and memory monitoring
- Intelligent throttling
"""

import time

import pytest

from catalyst_bot.llm_stability import (
    BatchProcessor,
    ErrorHandler,
    RateLimitConfig,
    RateLimiter,
    get_batch_processor,
    get_error_handler,
    get_rate_limiter,
)

# Configure pytest-asyncio
pytestmark = pytest.mark.anyio


class TestRateLimiter:
    """Test rate limiting functionality."""

    def test_rate_limiter_creation(self):
        """Test rate limiter can be created with config."""
        config = RateLimitConfig(
            max_requests_per_minute=10,
            max_requests_per_hour=100,
            max_requests_per_day=1000,
            min_interval_sec=1.0,
        )
        limiter = RateLimiter(config=config)
        assert limiter.config.max_requests_per_minute == 10
        assert limiter.consecutive_failures == 0

    def test_rate_limiter_allows_first_request(self):
        """Test rate limiter allows first request."""
        config = RateLimitConfig(max_requests_per_minute=10)
        limiter = RateLimiter(config=config)

        can_proceed, wait_time = limiter.can_make_request()
        assert can_proceed is True
        assert wait_time == 0.0

    def test_rate_limiter_enforces_min_interval(self):
        """Test rate limiter enforces minimum interval between requests."""
        config = RateLimitConfig(min_interval_sec=2.0)
        limiter = RateLimiter(config=config)

        # First request should be allowed
        can_proceed, _ = limiter.can_make_request()
        assert can_proceed is True
        limiter.record_request()

        # Immediate second request should be blocked
        can_proceed, wait_time = limiter.can_make_request()
        assert can_proceed is False
        assert wait_time > 0
        assert wait_time <= 2.0

    def test_rate_limiter_enforces_per_minute_limit(self):
        """Test rate limiter enforces requests per minute limit."""
        config = RateLimitConfig(max_requests_per_minute=5, min_interval_sec=0.0)
        limiter = RateLimiter(config=config)

        # Make 5 requests (should be allowed)
        for i in range(5):
            can_proceed, _ = limiter.can_make_request()
            assert can_proceed is True, f"Request {i+1} should be allowed"
            limiter.record_request()

        # 6th request should be blocked
        can_proceed, wait_time = limiter.can_make_request()
        assert can_proceed is False
        assert wait_time == 60.0

    def test_rate_limiter_exponential_backoff(self):
        """Test exponential backoff increases with consecutive failures."""
        config = RateLimitConfig()
        limiter = RateLimiter(config=config)

        # Record successive failures
        delays = []
        for i in range(5):
            limiter.record_request(success=False)
            delay = limiter.get_backoff_delay()
            delays.append(delay)

        # Verify exponential growth: 2, 4, 8, 16, 32 (capped at 60)
        assert delays[0] == 2.0
        assert delays[1] == 4.0
        assert delays[2] == 8.0
        assert delays[3] == 16.0
        assert delays[4] == 32.0

    def test_rate_limiter_resets_on_success(self):
        """Test consecutive failures reset on successful request."""
        config = RateLimitConfig()
        limiter = RateLimiter(config=config)

        # Record failures
        limiter.record_request(success=False)
        limiter.record_request(success=False)
        assert limiter.consecutive_failures == 2

        # Record success
        limiter.record_request(success=True)
        assert limiter.consecutive_failures == 0
        assert limiter.get_backoff_delay() == 0.0

    def test_rate_limiter_stats(self):
        """Test rate limiter provides accurate statistics."""
        config = RateLimitConfig()
        limiter = RateLimiter(config=config)

        # Make some requests
        for i in range(3):
            limiter.record_request()

        stats = limiter.get_stats()
        assert stats["requests_last_min"] == 3
        assert stats["requests_last_hour"] == 3
        assert stats["requests_last_day"] == 3
        assert stats["consecutive_failures"] == 0

    async def test_rate_limiter_wait_if_needed(self):
        """Test rate limiter waits when necessary."""
        config = RateLimitConfig(min_interval_sec=0.1)
        limiter = RateLimiter(config=config)

        # First request should not wait
        limiter.record_request()

        # Second request should wait briefly
        start = time.time()
        await limiter.wait_if_needed()
        elapsed = time.time() - start

        assert elapsed >= 0.1  # Should have waited at least 0.1s


class TestBatchProcessor:
    """Test batch processing functionality."""

    def test_batch_processor_creation(self):
        """Test batch processor can be created."""
        processor = BatchProcessor(
            batch_size=5, batch_delay_sec=1.0, min_prescale_score=0.2
        )
        assert processor.batch_size == 5
        assert processor.batch_delay_sec == 1.0
        assert processor.min_prescale_score == 0.2

    def test_batch_processor_pre_filter(self):
        """Test batch processor filters items by prescale score."""
        processor = BatchProcessor(min_prescale_score=0.3)

        items = [
            {"id": 1, "prescale_score": 0.1},  # Below threshold
            {"id": 2, "prescale_score": 0.4},  # Above threshold
            {"id": 3, "prescale_score": 0.5},  # Above threshold
            {"id": 4, "prescale_score": 0.2},  # Below threshold
        ]

        filtered = processor.pre_filter(items)
        assert len(filtered) == 2
        assert filtered[0]["id"] == 2
        assert filtered[1]["id"] == 3

    def test_batch_processor_no_filter_when_threshold_zero(self):
        """Test batch processor doesn't filter when threshold is 0."""
        processor = BatchProcessor(min_prescale_score=0.0)

        items = [
            {"id": 1, "prescale_score": 0.1},
            {"id": 2, "prescale_score": 0.4},
        ]

        filtered = processor.pre_filter(items)
        assert len(filtered) == 2

    async def test_batch_processor_processes_in_batches(self):
        """Test batch processor splits items into batches."""
        processor = BatchProcessor(batch_size=2, batch_delay_sec=0.1)

        items = [{"id": i, "prescale_score": 0.5} for i in range(5)]

        processed_count = 0

        async def process_fn(item):
            nonlocal processed_count
            processed_count += 1
            return item

        start = time.time()
        results = await processor.process_batch(items, process_fn, filter_items=False)
        elapsed = time.time() - start

        # Should have processed all 5 items
        assert len(results) == 5
        assert processed_count == 5

        # Should have taken at least 2 batch delays (3 batches: 2+2+1)
        # Batches: [0,1] delay [2,3] delay [4]
        assert elapsed >= 0.2

    async def test_batch_processor_handles_errors_gracefully(self):
        """Test batch processor continues after individual item failures."""
        processor = BatchProcessor(batch_size=2, batch_delay_sec=0.0)

        items = [{"id": i, "prescale_score": 0.5} for i in range(4)]

        async def process_fn(item):
            if item["id"] == 1:
                raise Exception("Simulated error")
            return item

        results = await processor.process_batch(items, process_fn, filter_items=False)

        # Should still process all items (failed item returned unprocessed)
        assert len(results) == 4


class TestErrorHandler:
    """Test error handling functionality."""

    def test_error_handler_creation(self):
        """Test error handler can be created."""
        handler = ErrorHandler()
        assert isinstance(handler.error_counts, dict)
        assert len(handler.last_errors) == 0

    def test_error_handler_records_errors(self):
        """Test error handler records errors."""
        handler = ErrorHandler()

        handler.record_error("timeout", "Request timeout")
        handler.record_error("timeout", "Another timeout")
        handler.record_error("rate_limit", "Rate limit exceeded")

        assert handler.error_counts["timeout"] == 2
        assert handler.error_counts["rate_limit"] == 1
        assert len(handler.last_errors) == 3

    def test_error_handler_should_retry(self):
        """Test error handler retry logic."""
        handler = ErrorHandler()

        # Record some failures
        handler.record_error("timeout", "Request timeout")
        assert handler.should_retry("timeout", max_retries=3) is True

        handler.record_error("timeout", "Request timeout")
        assert handler.should_retry("timeout", max_retries=3) is True

        handler.record_error("timeout", "Request timeout")
        assert handler.should_retry("timeout", max_retries=3) is False

    def test_error_handler_stats(self):
        """Test error handler provides statistics."""
        handler = ErrorHandler()

        handler.record_error("timeout", "Request timeout")
        handler.record_error("rate_limit", "Rate limit exceeded")

        stats = handler.get_error_stats()
        assert stats["total_errors"] == 2
        assert "timeout" in stats["error_types"]
        assert "rate_limit" in stats["error_types"]


class TestGlobalInstances:
    """Test global instance management."""

    def test_get_rate_limiter_creates_instance(self):
        """Test get_rate_limiter creates instances on demand."""
        limiter = get_rate_limiter("test_provider")
        assert isinstance(limiter, RateLimiter)

        # Should return same instance on second call
        limiter2 = get_rate_limiter("test_provider")
        assert limiter is limiter2

    def test_get_error_handler_returns_singleton(self):
        """Test get_error_handler returns global singleton."""
        handler1 = get_error_handler()
        handler2 = get_error_handler()
        assert handler1 is handler2

    def test_get_batch_processor_creates_configured_instance(self):
        """Test get_batch_processor creates properly configured instance."""
        processor = get_batch_processor()
        assert isinstance(processor, BatchProcessor)
        assert processor.batch_size > 0
        assert processor.batch_delay_sec >= 0
        assert processor.min_prescale_score >= 0


class TestIntegration:
    """Integration tests combining multiple components."""

    async def test_batch_processing_with_rate_limiting(self):
        """Test batch processing respects rate limits."""
        config = RateLimitConfig(min_interval_sec=0.05)
        limiter = RateLimiter(config=config)
        processor = BatchProcessor(
            batch_size=2, batch_delay_sec=0.0, rate_limiter=limiter
        )

        items = [{"id": i, "prescale_score": 0.5} for i in range(4)]

        async def process_fn(item):
            return item

        start = time.time()
        results = await processor.process_batch(items, process_fn, filter_items=False)
        elapsed = time.time() - start

        # Should process all items
        assert len(results) == 4

        # Should take time due to rate limiting (4 items * 0.05s = 0.2s minimum)
        assert elapsed >= 0.15  # Allow some margin

    async def test_batch_processing_with_error_recovery(self):
        """Test batch processing with error handler tracks failures."""
        error_handler = ErrorHandler()
        processor = BatchProcessor(batch_size=2, batch_delay_sec=0.0)

        items = [{"id": i, "prescale_score": 0.5} for i in range(4)]

        call_count = 0

        async def process_fn(item):
            nonlocal call_count
            call_count += 1
            if item["id"] in [1, 2]:
                error_handler.record_error(
                    "processing_error", f"Error on item {item['id']}"
                )
                raise Exception("Simulated error")
            return item

        results = await processor.process_batch(items, process_fn, filter_items=False)

        # All items processed (failed items returned as-is)
        assert len(results) == 4
        assert call_count == 4

        # Error handler should have recorded failures
        assert error_handler.error_counts.get("processing_error", 0) == 2
