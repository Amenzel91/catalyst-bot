"""
Tests for market_regime.py - VIX/Market Regime Classification

Test coverage:
- VIX classification logic (all thresholds)
- SPY trend analysis (all thresholds)
- Combined confidence scoring
- Caching behavior and TTL
- Fallback behavior on API failures
- Config overrides for multipliers
- Singleton pattern
- Convenience functions
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from catalyst_bot import market_regime
from catalyst_bot.market_regime import (
    REGIME_BEAR_MARKET,
    REGIME_BULL_MARKET,
    REGIME_CRASH,
    REGIME_HIGH_VOLATILITY,
    REGIME_NEUTRAL,
    TREND_DOWNTREND,
    TREND_SIDEWAYS,
    TREND_UPTREND,
    MarketRegimeManager,
    get_current_regime,
    get_regime_manager,
    get_regime_multiplier,
    is_high_volatility_regime,
)


class TestVIXClassification:
    """Test VIX-based regime classification logic."""

    def test_bull_market_vix_low(self):
        """Test BULL_MARKET classification for VIX < 15."""
        manager = MarketRegimeManager()

        # Test VIX at 10 (clearly bull market)
        regime = manager._classify_vix_regime(10.0)
        assert regime == REGIME_BULL_MARKET

        # Test VIX at 14.9 (just below threshold)
        regime = manager._classify_vix_regime(14.9)
        assert regime == REGIME_BULL_MARKET

    def test_neutral_vix_moderate(self):
        """Test NEUTRAL classification for VIX 15-20."""
        manager = MarketRegimeManager()

        # Test VIX at 15.0 (at threshold)
        regime = manager._classify_vix_regime(15.0)
        assert regime == REGIME_NEUTRAL

        # Test VIX at 17.5 (mid-range)
        regime = manager._classify_vix_regime(17.5)
        assert regime == REGIME_NEUTRAL

        # Test VIX at 19.9 (just below threshold)
        regime = manager._classify_vix_regime(19.9)
        assert regime == REGIME_NEUTRAL

    def test_high_volatility_vix_elevated(self):
        """Test HIGH_VOLATILITY classification for VIX 20-30."""
        manager = MarketRegimeManager()

        # Test VIX at 20.0 (at threshold)
        regime = manager._classify_vix_regime(20.0)
        assert regime == REGIME_HIGH_VOLATILITY

        # Test VIX at 25.0 (mid-range)
        regime = manager._classify_vix_regime(25.0)
        assert regime == REGIME_HIGH_VOLATILITY

        # Test VIX at 29.9 (just below threshold)
        regime = manager._classify_vix_regime(29.9)
        assert regime == REGIME_HIGH_VOLATILITY

    def test_bear_market_vix_high(self):
        """Test BEAR_MARKET classification for VIX 30-40."""
        manager = MarketRegimeManager()

        # Test VIX at 30.0 (at threshold)
        regime = manager._classify_vix_regime(30.0)
        assert regime == REGIME_BEAR_MARKET

        # Test VIX at 35.0 (mid-range)
        regime = manager._classify_vix_regime(35.0)
        assert regime == REGIME_BEAR_MARKET

        # Test VIX at 39.9 (just below threshold)
        regime = manager._classify_vix_regime(39.9)
        assert regime == REGIME_BEAR_MARKET

    def test_crash_vix_extreme(self):
        """Test CRASH classification for VIX >= 40."""
        manager = MarketRegimeManager()

        # Test VIX at 40.0 (at threshold)
        regime = manager._classify_vix_regime(40.0)
        assert regime == REGIME_CRASH

        # Test VIX at 50.0 (well above threshold)
        regime = manager._classify_vix_regime(50.0)
        assert regime == REGIME_CRASH

        # Test VIX at 80.0 (extreme panic like March 2020)
        regime = manager._classify_vix_regime(80.0)
        assert regime == REGIME_CRASH

    def test_vix_none_returns_neutral(self):
        """Test that None VIX returns NEUTRAL (safe default)."""
        manager = MarketRegimeManager()
        regime = manager._classify_vix_regime(None)
        assert regime == REGIME_NEUTRAL


class TestSPYTrendClassification:
    """Test SPY trend classification logic."""

    def test_uptrend_positive_return(self):
        """Test UPTREND classification for return > 2%."""
        manager = MarketRegimeManager()

        # Test 2.1% return (just above threshold)
        trend = manager._classify_spy_trend(2.1)
        assert trend == TREND_UPTREND

        # Test 5% return (clear uptrend)
        trend = manager._classify_spy_trend(5.0)
        assert trend == TREND_UPTREND

        # Test 10% return (strong uptrend)
        trend = manager._classify_spy_trend(10.0)
        assert trend == TREND_UPTREND

    def test_downtrend_negative_return(self):
        """Test DOWNTREND classification for return < -2%."""
        manager = MarketRegimeManager()

        # Test -2.1% return (just below threshold)
        trend = manager._classify_spy_trend(-2.1)
        assert trend == TREND_DOWNTREND

        # Test -5% return (clear downtrend)
        trend = manager._classify_spy_trend(-5.0)
        assert trend == TREND_DOWNTREND

        # Test -10% return (strong downtrend)
        trend = manager._classify_spy_trend(-10.0)
        assert trend == TREND_DOWNTREND

    def test_sideways_neutral_return(self):
        """Test SIDEWAYS classification for return -2% to 2%."""
        manager = MarketRegimeManager()

        # Test 0% return (flat)
        trend = manager._classify_spy_trend(0.0)
        assert trend == TREND_SIDEWAYS

        # Test 1% return (mild upside)
        trend = manager._classify_spy_trend(1.0)
        assert trend == TREND_SIDEWAYS

        # Test -1% return (mild downside)
        trend = manager._classify_spy_trend(-1.0)
        assert trend == TREND_SIDEWAYS

        # Test 2.0% return (at threshold)
        trend = manager._classify_spy_trend(2.0)
        assert trend == TREND_SIDEWAYS

        # Test -2.0% return (at threshold)
        trend = manager._classify_spy_trend(-2.0)
        assert trend == TREND_SIDEWAYS

    def test_spy_return_none_returns_sideways(self):
        """Test that None SPY return returns SIDEWAYS (safe default)."""
        manager = MarketRegimeManager()
        trend = manager._classify_spy_trend(None)
        assert trend == TREND_SIDEWAYS


class TestConfidenceCalculation:
    """Test combined confidence scoring logic."""

    def test_confidence_with_all_data(self):
        """Test confidence calculation with both VIX and SPY data."""
        manager = MarketRegimeManager()

        # Test with both data points available
        confidence = manager._calculate_confidence(
            vix_value=12.0,
            spy_return=5.0,
            regime=REGIME_BULL_MARKET,
            spy_trend=TREND_UPTREND,
        )

        # Should have 0.5 + 0.5 base + 0.2 alignment bonus = 1.0
        assert confidence == 1.0

    def test_confidence_with_aligned_bull_uptrend(self):
        """Test confidence boost for aligned bull market + uptrend."""
        manager = MarketRegimeManager()

        confidence = manager._calculate_confidence(
            vix_value=12.0,
            spy_return=5.0,
            regime=REGIME_BULL_MARKET,
            spy_trend=TREND_UPTREND,
        )

        assert confidence == 1.0  # Max confidence with alignment

    def test_confidence_with_aligned_bear_downtrend(self):
        """Test confidence boost for aligned bear market + downtrend."""
        manager = MarketRegimeManager()

        confidence = manager._calculate_confidence(
            vix_value=35.0,
            spy_return=-5.0,
            regime=REGIME_BEAR_MARKET,
            spy_trend=TREND_DOWNTREND,
        )

        assert confidence == 1.0  # Max confidence with alignment

    def test_confidence_with_conflicted_bull_downtrend(self):
        """Test confidence reduction for conflicted bull + downtrend."""
        manager = MarketRegimeManager()

        confidence = manager._calculate_confidence(
            vix_value=12.0,
            spy_return=-5.0,
            regime=REGIME_BULL_MARKET,
            spy_trend=TREND_DOWNTREND,
        )

        # Should have 0.5 + 0.5 base - 0.2 conflict penalty = 0.8
        assert confidence == 0.8

    def test_confidence_with_conflicted_bear_uptrend(self):
        """Test confidence reduction for conflicted bear + uptrend."""
        manager = MarketRegimeManager()

        confidence = manager._calculate_confidence(
            vix_value=35.0,
            spy_return=5.0,
            regime=REGIME_BEAR_MARKET,
            spy_trend=TREND_UPTREND,
        )

        # Should have 0.5 + 0.5 base - 0.2 conflict penalty = 0.8
        assert confidence == 0.8

    def test_confidence_with_vix_only(self):
        """Test confidence calculation with only VIX data."""
        manager = MarketRegimeManager()

        confidence = manager._calculate_confidence(
            vix_value=15.0,
            spy_return=None,
            regime=REGIME_NEUTRAL,
            spy_trend=TREND_SIDEWAYS,
        )

        # Should have only VIX base: 0.5
        assert confidence == 0.5

    def test_confidence_with_spy_only(self):
        """Test confidence calculation with only SPY data."""
        manager = MarketRegimeManager()

        confidence = manager._calculate_confidence(
            vix_value=None,
            spy_return=1.0,
            regime=REGIME_NEUTRAL,
            spy_trend=TREND_SIDEWAYS,
        )

        # Should have only SPY base: 0.5
        assert confidence == 0.5

    def test_confidence_with_no_data(self):
        """Test confidence calculation with no data."""
        manager = MarketRegimeManager()

        confidence = manager._calculate_confidence(
            vix_value=None,
            spy_return=None,
            regime=REGIME_NEUTRAL,
            spy_trend=TREND_SIDEWAYS,
        )

        # Should have no confidence: 0.0
        assert confidence == 0.0


class TestMultiplierLogic:
    """Test multiplier calculation and config overrides."""

    def test_default_multipliers(self):
        """Test default multipliers for each regime."""
        manager = MarketRegimeManager()

        # Test default multipliers
        assert manager._get_multiplier(REGIME_BULL_MARKET) == 1.2
        assert manager._get_multiplier(REGIME_NEUTRAL) == 1.0
        assert manager._get_multiplier(REGIME_HIGH_VOLATILITY) == 0.8
        assert manager._get_multiplier(REGIME_BEAR_MARKET) == 0.7
        assert manager._get_multiplier(REGIME_CRASH) == 0.5

    def test_config_override_multipliers(self):
        """Test multiplier overrides from config."""
        manager = MarketRegimeManager()

        # Mock config with overrides
        with patch("catalyst_bot.market_regime.get_settings") as mock_settings:
            mock_config = Mock()
            mock_config.regime_multiplier_bull = 1.5
            mock_config.regime_multiplier_neutral = 0.9
            mock_config.regime_multiplier_high_vol = 0.6
            mock_config.regime_multiplier_bear = 0.5
            mock_config.regime_multiplier_crash = 0.3
            mock_settings.return_value = mock_config

            # Test overridden multipliers
            assert manager._get_multiplier(REGIME_BULL_MARKET) == 1.5
            assert manager._get_multiplier(REGIME_NEUTRAL) == 0.9
            assert manager._get_multiplier(REGIME_HIGH_VOLATILITY) == 0.6
            assert manager._get_multiplier(REGIME_BEAR_MARKET) == 0.5
            assert manager._get_multiplier(REGIME_CRASH) == 0.3

    def test_partial_config_overrides(self):
        """Test that unset config values fall back to defaults."""
        manager = MarketRegimeManager()

        # Mock config with some overrides, some None
        with patch("catalyst_bot.market_regime.get_settings") as mock_settings:
            mock_config = Mock()
            mock_config.regime_multiplier_bull = 1.3
            mock_config.regime_multiplier_neutral = None  # Should use default
            mock_config.regime_multiplier_high_vol = None  # Should use default
            mock_config.regime_multiplier_bear = 0.6
            mock_config.regime_multiplier_crash = None  # Should use default
            mock_settings.return_value = mock_config

            # Test mixed overrides and defaults
            assert manager._get_multiplier(REGIME_BULL_MARKET) == 1.3
            assert manager._get_multiplier(REGIME_NEUTRAL) == 1.0  # Default
            assert manager._get_multiplier(REGIME_HIGH_VOLATILITY) == 0.8  # Default
            assert manager._get_multiplier(REGIME_BEAR_MARKET) == 0.6
            assert manager._get_multiplier(REGIME_CRASH) == 0.5  # Default


class TestCaching:
    """Test caching behavior and TTL."""

    def test_cache_hit_within_ttl(self):
        """Test that cache returns data within TTL."""
        import time as time_module

        manager = MarketRegimeManager()

        # Get current time
        current_time = time_module.time()

        # Populate cache
        test_data = {
            "regime": REGIME_BULL_MARKET,
            "vix": 12.0,
            "multiplier": 1.2,
            "spy_trend": TREND_UPTREND,
            "spy_20d_return": 5.0,
            "confidence": 1.0,
            "cached_at": datetime.now(timezone.utc),
        }

        manager._cache = test_data
        manager._cache_time = current_time  # Set to current time (fresh cache)

        # Mock time.time to return value within TTL (1 second later)
        with patch("time.time", return_value=current_time + 1):
            # Should get cache hit
            cached = manager._get_from_cache()
            assert cached is not None
            assert cached == test_data

    def test_cache_miss_expired(self):
        """Test that cache returns None when expired."""
        manager = MarketRegimeManager()

        # Populate cache with old timestamp
        test_data = {
            "regime": REGIME_BULL_MARKET,
            "vix": 12.0,
            "multiplier": 1.2,
            "spy_trend": TREND_UPTREND,
            "spy_20d_return": 5.0,
            "confidence": 1.0,
            "cached_at": datetime.now(timezone.utc),
        }

        manager._cache = test_data
        manager._cache_time = 0.0  # Old timestamp (expired)

        # Should get cache miss
        cached = manager._get_from_cache()
        assert cached is None

    def test_cache_updates_on_fetch(self):
        """Test that cache is updated after successful fetch."""
        manager = MarketRegimeManager()

        # Mock VIX and SPY fetches
        with patch.object(manager, "_fetch_vix", return_value=12.0):
            with patch.object(manager, "_fetch_spy_return", return_value=5.0):
                # Fetch regime data
                result = manager.get_current_regime()

                # Cache should be populated
                assert manager._cache is not None
                assert manager._cache["regime"] == REGIME_BULL_MARKET
                assert manager._cache["vix"] == 12.0
                assert manager._cache_time > 0

    def test_multiple_calls_use_cache(self):
        """Test that multiple calls within TTL use cache."""
        manager = MarketRegimeManager()

        # Mock VIX and SPY fetches
        with patch.object(manager, "_fetch_vix", return_value=12.0) as mock_vix:
            with patch.object(manager, "_fetch_spy_return", return_value=5.0) as mock_spy:
                # First call should fetch
                result1 = manager.get_current_regime()
                assert mock_vix.call_count == 1
                assert mock_spy.call_count == 1

                # Second call should use cache
                result2 = manager.get_current_regime()
                assert mock_vix.call_count == 1  # No additional call
                assert mock_spy.call_count == 1  # No additional call

                # Results should be identical
                assert result1 == result2


class TestFallbackBehavior:
    """Test fallback behavior on API failures."""

    def test_fallback_on_vix_fetch_failure(self):
        """Test that VIX fetch failure returns default regime."""
        manager = MarketRegimeManager()

        # Mock VIX fetch failure
        with patch.object(manager, "_fetch_vix", side_effect=Exception("API error")):
            with patch.object(manager, "_fetch_spy_return", return_value=None):
                result = manager.get_current_regime()

                # Should return safe default
                assert result["regime"] == REGIME_NEUTRAL
                assert result["multiplier"] == 1.0
                assert result["confidence"] == 0.0

    def test_fallback_on_spy_fetch_failure(self):
        """Test that SPY fetch failure still works with VIX data."""
        manager = MarketRegimeManager()

        # Mock SPY fetch failure but VIX success
        with patch.object(manager, "_fetch_vix", return_value=12.0):
            with patch.object(manager, "_fetch_spy_return", return_value=None):
                result = manager.get_current_regime()

                # Should have VIX data but default SPY trend
                assert result["regime"] == REGIME_BULL_MARKET
                assert result["spy_trend"] == TREND_SIDEWAYS
                assert result["spy_20d_return"] is None
                assert result["confidence"] == 0.5  # Only VIX confidence

    def test_default_regime_structure(self):
        """Test that default regime has correct structure."""
        manager = MarketRegimeManager()
        default = manager._get_default_regime()

        # Verify structure
        assert "regime" in default
        assert "vix" in default
        assert "multiplier" in default
        assert "spy_trend" in default
        assert "spy_20d_return" in default
        assert "confidence" in default
        assert "cached_at" in default

        # Verify safe defaults
        assert default["regime"] == REGIME_NEUTRAL
        assert default["multiplier"] == 1.0
        assert default["confidence"] == 0.0


class TestSingletonPattern:
    """Test singleton pattern for regime manager."""

    def test_singleton_returns_same_instance(self):
        """Test that get_regime_manager() returns the same instance."""
        manager1 = get_regime_manager()
        manager2 = get_regime_manager()

        assert manager1 is manager2

    def test_singleton_instance_is_manager(self):
        """Test that singleton instance is MarketRegimeManager."""
        manager = get_regime_manager()
        assert isinstance(manager, MarketRegimeManager)


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_get_current_regime(self):
        """Test get_current_regime() convenience function."""
        with patch.object(MarketRegimeManager, "get_current_regime") as mock_method:
            mock_method.return_value = {
                "regime": REGIME_BULL_MARKET,
                "vix": 12.0,
                "multiplier": 1.2,
                "spy_trend": TREND_UPTREND,
                "spy_20d_return": 5.0,
                "confidence": 1.0,
                "cached_at": datetime.now(timezone.utc),
            }

            result = get_current_regime()

            assert result["regime"] == REGIME_BULL_MARKET
            assert result["multiplier"] == 1.2
            mock_method.assert_called_once()

    def test_get_regime_multiplier(self):
        """Test get_regime_multiplier() convenience function."""
        with patch("catalyst_bot.market_regime.get_current_regime") as mock_func:
            mock_func.return_value = {"multiplier": 1.2}

            multiplier = get_regime_multiplier()

            assert multiplier == 1.2
            mock_func.assert_called_once()

    def test_is_high_volatility_regime_true(self):
        """Test is_high_volatility_regime() returns True for volatile regimes."""
        # Test HIGH_VOLATILITY
        with patch("catalyst_bot.market_regime.get_current_regime") as mock_func:
            mock_func.return_value = {"regime": REGIME_HIGH_VOLATILITY}
            assert is_high_volatility_regime() is True

        # Test BEAR_MARKET
        with patch("catalyst_bot.market_regime.get_current_regime") as mock_func:
            mock_func.return_value = {"regime": REGIME_BEAR_MARKET}
            assert is_high_volatility_regime() is True

        # Test CRASH
        with patch("catalyst_bot.market_regime.get_current_regime") as mock_func:
            mock_func.return_value = {"regime": REGIME_CRASH}
            assert is_high_volatility_regime() is True

    def test_is_high_volatility_regime_false(self):
        """Test is_high_volatility_regime() returns False for calm regimes."""
        # Test BULL_MARKET
        with patch("catalyst_bot.market_regime.get_current_regime") as mock_func:
            mock_func.return_value = {"regime": REGIME_BULL_MARKET}
            assert is_high_volatility_regime() is False

        # Test NEUTRAL
        with patch("catalyst_bot.market_regime.get_current_regime") as mock_func:
            mock_func.return_value = {"regime": REGIME_NEUTRAL}
            assert is_high_volatility_regime() is False


class TestCacheStats:
    """Test cache statistics tracking."""

    def test_cache_stats_initial_state(self):
        """Test cache stats in initial state."""
        manager = MarketRegimeManager()
        stats = manager.get_cache_stats()

        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["api_errors"] == 0
        assert stats["total_requests"] == 0

    def test_cache_stats_after_hits(self):
        """Test cache stats after cache hits."""
        import time as time_module

        manager = MarketRegimeManager()

        # Mock current time to be within TTL
        current_time = time_module.time()

        # Populate cache with current time
        manager._cache = {
            "regime": REGIME_BULL_MARKET,
            "vix": 12.0,
            "multiplier": 1.2,
            "spy_trend": TREND_UPTREND,
            "spy_20d_return": 5.0,
            "confidence": 1.0,
            "cached_at": datetime.now(timezone.utc),
        }
        manager._cache_time = current_time  # Current time (fresh)

        # Make multiple calls (should hit cache)
        with patch.object(manager, "_fetch_vix", return_value=12.0):
            with patch.object(manager, "_fetch_spy_return", return_value=5.0):
                # Patch time.time to return consistent value during cache checks
                with patch("time.time", return_value=current_time + 1):
                    manager.get_current_regime()
                    manager.get_current_regime()
                    manager.get_current_regime()

        stats = manager.get_cache_stats()
        assert stats["cache_hits"] == 3
        assert stats["cache_misses"] == 0

    def test_cache_stats_after_misses(self):
        """Test cache stats after cache misses."""
        manager = MarketRegimeManager()

        # Make calls with expired cache (should miss)
        manager._cache_time = 0.0  # Expired

        with patch.object(manager, "_fetch_vix", return_value=12.0):
            with patch.object(manager, "_fetch_spy_return", return_value=5.0):
                manager.get_current_regime()
                manager._cache_time = 0.0  # Reset to force miss
                manager.get_current_regime()

        stats = manager.get_cache_stats()
        assert stats["cache_misses"] >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
