"""
Comprehensive Test Suite for Cost Optimization Patch (4 Agents)
================================================================

Tests all four cost optimization features:
1. Flash-Lite Integration
2. SEC LLM Caching
3. Batch Classification
4. Cost Monitoring Alerts

Run with: pytest tests/test_cost_optimization_patch.py -v
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Agent 1: Flash-Lite Integration Tests
def test_flash_lite_model_in_costs():
    """Test that Flash-Lite model is defined in GEMINI_COSTS."""
    from src.catalyst_bot.llm_hybrid import GEMINI_COSTS

    assert "gemini-2.0-flash-lite" in GEMINI_COSTS
    assert GEMINI_COSTS["gemini-2.0-flash-lite"]["input"] == 0.02 / 1_000_000
    assert GEMINI_COSTS["gemini-2.0-flash-lite"]["output"] == 0.10 / 1_000_000


def test_is_simple_operation():
    """Test simple operation detection for Flash-Lite routing."""
    from src.catalyst_bot.llm_hybrid import is_simple_operation

    # Short text is always simple
    assert is_simple_operation("sentiment", text_length=200) is True

    # Medium text depends on operation
    assert is_simple_operation("sentiment", text_length=1000) is True
    assert is_simple_operation("sec_analysis", text_length=1000) is False

    # Long text is always complex
    assert is_simple_operation("sentiment", text_length=3000) is False


def test_select_model_tier_flash_lite():
    """Test model selection includes Flash-Lite for simple operations."""
    from src.catalyst_bot.llm_hybrid import select_model_tier

    with patch.dict(os.environ, {"FEATURE_FLASH_LITE": "1", "LLM_FLASH_LITE_THRESHOLD": "0.3"}):
        # Simple operation should use Flash-Lite
        model = select_model_tier(
            complexity=0.2,
            strategy="auto",
            text_length=200,
            operation="sentiment"
        )
        assert model == "gemini-2.0-flash-lite"

        # Complex operation should use Flash
        model = select_model_tier(
            complexity=0.5,
            strategy="auto",
            text_length=2000,
            operation="sec_analysis"
        )
        assert model == "gemini-2.5-flash"


def test_flash_lite_config_flags():
    """Test Flash-Lite configuration flags in settings."""
    from src.catalyst_bot.config import Settings

    settings = Settings()

    # Check default values
    assert hasattr(settings, "feature_flash_lite")
    assert hasattr(settings, "flash_lite_complexity_threshold")
    assert settings.flash_lite_complexity_threshold == 0.3


# Agent 2: SEC LLM Cache Tests
def test_sec_llm_cache_initialization():
    """Test SEC LLM cache initialization."""
    from src.catalyst_bot.sec_llm_cache import SECLLMCache
    import gc
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SECLLMCache(db_path=db_path, ttl_hours=72)

        assert cache.db_path.exists()
        assert cache.ttl_hours == 72
        assert cache.stats["total_requests"] == 0

        # Explicit cleanup for Windows
        cache.close()
        del cache
        gc.collect()
        time.sleep(0.1)


def test_sec_llm_cache_get_set():
    """Test caching and retrieving SEC analysis results."""
    from src.catalyst_bot.sec_llm_cache import SECLLMCache
    import gc
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SECLLMCache(db_path=db_path, ttl_hours=72)

        # Cache miss (no data)
        result = cache.get_cached_sec_analysis(
            filing_id="test_123",
            ticker="AAPL",
            filing_type="8-K"
        )
        assert result is None

        # Cache set
        analysis_data = {
            "keywords": ["earnings", "revenue"],
            "sentiment": 0.5,
            "confidence": 0.8
        }
        success = cache.cache_sec_analysis(
            filing_id="test_123",
            ticker="AAPL",
            filing_type="8-K",
            analysis_result=analysis_data
        )
        assert success is True

        # Cache hit
        cached_result = cache.get_cached_sec_analysis(
            filing_id="test_123",
            ticker="AAPL",
            filing_type="8-K"
        )
        assert cached_result is not None
        assert cached_result["keywords"] == ["earnings", "revenue"]
        assert cache.stats["cache_hits"] == 1

        # Explicit cleanup for Windows
        cache.close()
        del cache
        gc.collect()
        time.sleep(0.1)


def test_sec_llm_cache_invalidation():
    """Test cache invalidation for amended filings."""
    from src.catalyst_bot.sec_llm_cache import SECLLMCache
    import gc
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SECLLMCache(db_path=db_path, ttl_hours=72)

        # Cache two filings for same ticker
        cache.cache_sec_analysis(
            filing_id="test_1",
            ticker="TSLA",
            filing_type="8-K",
            analysis_result={"data": "original"}
        )
        cache.cache_sec_analysis(
            filing_id="test_2",
            ticker="TSLA",
            filing_type="8-K",
            analysis_result={"data": "second"}
        )

        # Invalidate all 8-K filings for TSLA
        count = cache.invalidate_amendment_caches("TSLA", "8-K")
        assert count == 2

        # Verify both are gone
        assert cache.get_cached_sec_analysis("test_1", "TSLA", "8-K") is None
        assert cache.get_cached_sec_analysis("test_2", "TSLA", "8-K") is None

        # Explicit cleanup for Windows
        cache.close()
        del cache
        gc.collect()
        time.sleep(0.1)


def test_sec_llm_cache_config():
    """Test SEC cache configuration flags."""
    from src.catalyst_bot.config import Settings

    settings = Settings()

    assert hasattr(settings, "feature_sec_llm_cache")
    assert hasattr(settings, "sec_llm_cache_ttl_hours")
    assert settings.sec_llm_cache_ttl_hours == 72


# Agent 3: Batch Classification Tests
def test_batch_classification_manager():
    """Test batch classification manager."""
    from src.catalyst_bot.llm_batch import BatchClassificationManager

    manager = BatchClassificationManager(batch_size=3, batch_timeout=1.0)

    # Add items one by one
    item1 = {"title": "News 1"}
    item2 = {"title": "News 2"}
    item3 = {"title": "News 3"}

    # First two items don't fill batch
    assert manager.add_item(item1) is None
    assert manager.add_item(item2) is None

    # Third item fills batch
    batch = manager.add_item(item3)
    assert batch is not None
    assert len(batch) == 3


def test_group_items_for_batch():
    """Test item grouping function."""
    from src.catalyst_bot.llm_batch import group_items_for_batch

    items = [{"title": f"News {i}"} for i in range(12)]
    batches = group_items_for_batch(items, batch_size=5)

    assert len(batches) == 3
    assert len(batches[0]) == 5
    assert len(batches[1]) == 5
    assert len(batches[2]) == 2


def test_create_batch_classification_prompt():
    """Test batch classification prompt creation."""
    from src.catalyst_bot.llm_batch import create_batch_classification_prompt

    items = [
        {"title": "Apple beats earnings", "description": "Q4 results exceed estimates"},
        {"title": "Tesla announces recall", "description": "Safety issue with brakes"},
    ]

    prompt = create_batch_classification_prompt(items)

    assert "Apple beats earnings" in prompt
    assert "Tesla announces recall" in prompt
    assert "sentiment" in prompt
    assert "relevance" in prompt


def test_batch_classification_config():
    """Test batch classification configuration."""
    from src.catalyst_bot.config import Settings

    settings = Settings()

    assert hasattr(settings, "feature_llm_batch")
    assert hasattr(settings, "llm_batch_size")
    assert hasattr(settings, "llm_batch_timeout")
    assert settings.llm_batch_size == 5
    assert settings.llm_batch_timeout == 2.0


# Agent 4: Cost Monitoring Tests
def test_cost_monitoring_initialization():
    """Test cost monitoring initialization."""
    from src.catalyst_bot.llm_usage_monitor import LLMUsageMonitor

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "usage.jsonl"
        monitor = LLMUsageMonitor(log_path=log_path)

        assert monitor.realtime_cost_today == 0.0
        assert "gemini-2.0-flash-lite" in monitor.model_availability
        assert "gemini-2.5-pro" in monitor.model_availability
        assert monitor.model_availability["gemini-2.5-pro"] is True


def test_cost_threshold_check():
    """Test cost threshold checking."""
    from src.catalyst_bot.llm_usage_monitor import LLMUsageMonitor

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "usage.jsonl"
        monitor = LLMUsageMonitor(log_path=log_path)

        # Initially below threshold
        assert monitor.check_cost_threshold("warn") is False

        # Simulate some costs
        monitor._update_realtime_cost(3.0)
        assert monitor.realtime_cost_today == 3.0

        # Still below warn threshold (5.0)
        assert monitor.check_cost_threshold("warn") is False

        # Add more cost to exceed warn threshold
        monitor._update_realtime_cost(3.0)
        assert monitor.realtime_cost_today == 6.0
        assert monitor.check_cost_threshold("warn") is True


def test_model_disable_enable():
    """Test model disabling and enabling."""
    from src.catalyst_bot.llm_usage_monitor import LLMUsageMonitor

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "usage.jsonl"
        monitor = LLMUsageMonitor(log_path=log_path)

        # Initially available
        assert monitor.is_model_available("gemini-2.5-pro") is True

        # Disable model
        monitor.disable_model("gemini-2.5-pro")
        assert monitor.is_model_available("gemini-2.5-pro") is False

        # Re-enable model
        monitor.enable_model("gemini-2.5-pro")
        assert monitor.is_model_available("gemini-2.5-pro") is True


def test_cost_monitoring_config():
    """Test cost monitoring configuration."""
    from src.catalyst_bot.config import Settings

    settings = Settings()

    assert hasattr(settings, "llm_cost_alert_warn")
    assert hasattr(settings, "llm_cost_alert_crit")
    assert hasattr(settings, "llm_cost_alert_emergency")
    assert settings.llm_cost_alert_warn == 5.0
    assert settings.llm_cost_alert_crit == 10.0
    assert settings.llm_cost_alert_emergency == 20.0


# Integration Tests
def test_all_features_enabled_by_default():
    """Test that all four features are enabled by default."""
    from src.catalyst_bot.config import Settings

    settings = Settings()

    # Agent 1
    assert settings.feature_flash_lite is True

    # Agent 2
    assert settings.feature_sec_llm_cache is True

    # Agent 3
    assert settings.feature_llm_batch is True

    # Agent 4 (implicitly enabled via thresholds)
    assert settings.llm_cost_alert_warn > 0
    assert settings.llm_cost_alert_crit > 0
    assert settings.llm_cost_alert_emergency > 0


def test_flash_lite_pricing_advantage():
    """Test that Flash-Lite is significantly cheaper than Flash."""
    from src.catalyst_bot.llm_hybrid import GEMINI_COSTS

    flash_input = GEMINI_COSTS["gemini-2.5-flash"]["input"]
    flash_lite_input = GEMINI_COSTS["gemini-2.0-flash-lite"]["input"]

    # Flash-Lite should be at least 70% cheaper
    savings = (flash_input - flash_lite_input) / flash_input
    assert savings >= 0.70, f"Flash-Lite savings: {savings*100:.1f}%"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
