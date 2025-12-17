"""
Integration tests for classify.py simulation mode support.

Tests that classify uses simulation time for enrichment timestamps
when running in simulation mode.
"""

import os
from datetime import datetime, timezone

from catalyst_bot.simulation import init_clock
from catalyst_bot.simulation import reset as reset_clock
from catalyst_bot.time_utils import time as sim_time


class TestClassifySimulationTime:
    """Tests for classify.py simulation time integration."""

    def setup_method(self):
        """Set up simulation environment."""
        os.environ["SIMULATION_MODE"] = "1"
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,
        )

    def teardown_method(self):
        """Clean up."""
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)

    def test_sim_time_returns_simulation_timestamp(self):
        """Verify sim_time() returns simulation timestamp."""
        expected_ts = self.start_time.timestamp()
        actual_ts = sim_time()

        # Should be close to simulation start time
        assert abs(actual_ts - expected_ts) < 1.0

    def test_enrichment_timestamp_uses_simulation_time(self):
        """Verify enrichment uses simulation time, not real time."""
        from catalyst_bot.classify import enrich_scored_item
        from catalyst_bot.models import NewsItem, ScoredItem

        # Create test item with no ticker to skip heavy operations
        item = NewsItem(
            id="test_001",
            title="Test News",
            link="https://example.com/test",
            ts=self.start_time.isoformat(),
            source="test",
            ticker="",  # Empty ticker skips slow enrichment
        )

        scored = ScoredItem(
            relevance=0.5,
            sentiment=0.3,
            tags=["test"],
            source_weight=1.0,
            keyword_hits=[],
        )

        # Enrich the item (fast path since no ticker)
        enriched = enrich_scored_item(scored, item)

        # Get the enrichment timestamp
        ts = getattr(enriched, "enrichment_timestamp", None)

        assert ts is not None, "enrichment_timestamp should be set"
        # Should be simulation time (2024), not real time (2025)
        ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        assert ts_dt.year == 2024, f"Expected 2024, got {ts_dt.year}"
        assert ts_dt.month == 11, f"Expected November, got {ts_dt.month}"


class TestClassifyBatchDelay:
    """Tests for batch delay using simulation sleep."""

    def setup_method(self):
        """Set up simulation environment."""
        os.environ["SIMULATION_MODE"] = "1"
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,  # Instant mode
        )

    def teardown_method(self):
        """Clean up."""
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)

    def test_batch_delay_uses_sim_sleep(self):
        """Verify batch delay advances simulation time, not real time."""
        import time

        from catalyst_bot.time_utils import now as sim_now
        from catalyst_bot.time_utils import sleep as sim_sleep

        # Record real start time
        real_start = time.time()

        # Record simulation start time
        sim_start = sim_now()

        # Simulate what classify_batch_with_llm does between batches
        sim_sleep(2.0)  # batch_delay

        # Check simulation time advanced
        sim_end = sim_now()
        sim_elapsed = (sim_end - sim_start).total_seconds()
        assert sim_elapsed == 2.0, f"Expected 2s sim time, got {sim_elapsed}s"

        # Check real time didn't advance much (instant mode)
        real_elapsed = time.time() - real_start
        assert real_elapsed < 0.5, f"Real time should be instant, got {real_elapsed}s"


class TestClassifyProductionMode:
    """Tests for classify in production mode."""

    def test_enrichment_timestamp_uses_real_time_in_production(self):
        """Verify enrichment uses real time when not in simulation."""
        # Ensure not in simulation mode
        os.environ.pop("SIMULATION_MODE", None)
        reset_clock()

        import time

        from catalyst_bot.classify import enrich_scored_item
        from catalyst_bot.models import NewsItem, ScoredItem

        # Get current real time
        real_now = time.time()

        # Create test item with no ticker to skip heavy operations
        item = NewsItem(
            id="test_002",
            title="Production Test",
            link="https://example.com/test2",
            ts=datetime.now(timezone.utc).isoformat(),
            source="test",
            ticker="",  # Empty ticker skips slow enrichment
        )

        scored = ScoredItem(
            relevance=0.5,
            sentiment=0.3,
            tags=["test"],
            source_weight=1.0,
            keyword_hits=[],
        )

        # Enrich the item (fast path since no ticker)
        enriched = enrich_scored_item(scored, item)

        # Get the enrichment timestamp
        ts = getattr(enriched, "enrichment_timestamp", None)

        assert ts is not None, "enrichment_timestamp should be set"
        # Should be close to real time (within 5 seconds)
        assert abs(ts - real_now) < 5.0, f"Expected real time ~{real_now}, got {ts}"
