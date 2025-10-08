"""
test_indicators.py
==================

Test suite for WAVE 3.1 Advanced Chart Indicators.

This module provides comprehensive tests for all indicator calculations
to ensure mathematical correctness and proper integration.

Run with: python test_indicators.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.catalyst_bot.indicators import (  # noqa: E402
    analyze_multiple_timeframes,
    calculate_bandwidth,
    calculate_bollinger_bands,
    calculate_fibonacci_levels,
    calculate_value_area,
    calculate_volume_profile,
    detect_support_resistance,
    detect_trend,
    find_point_of_control,
    find_swing_points,
    get_bollinger_position,
)


def test_bollinger_bands():
    """Test Bollinger Bands calculation."""
    print("Testing Bollinger Bands...")

    # Test with simple data
    prices = [
        100,
        102,
        101,
        103,
        105,
        104,
        106,
        108,
        107,
        109,
        110,
        108,
        109,
        111,
        110,
        112,
        114,
        113,
        115,
        116,
    ]

    upper, middle, lower = calculate_bollinger_bands(prices, period=5, std_dev=2.0)

    # Basic validation
    assert len(upper) == len(prices), "Upper band length mismatch"
    assert len(middle) == len(prices), "Middle band length mismatch"
    assert len(lower) == len(prices), "Lower band length mismatch"

    # Check ordering (upper >= middle >= lower)
    import math

    for i in range(5, len(prices)):
        if (
            not math.isnan(upper[i])
            and not math.isnan(middle[i])
            and not math.isnan(lower[i])
        ):
            assert upper[i] >= middle[i], f"Upper < Middle at index {i}"
            assert middle[i] >= lower[i], f"Middle < Lower at index {i}"

    # Test position detection
    current_price = 117  # Above upper band
    position = get_bollinger_position(current_price, upper[-1], middle[-1], lower[-1])
    assert position in [
        "Above Upper Band",
        "Near Upper Band",
    ], f"Position detection failed: {position}"

    # Test bandwidth calculation
    bandwidth = calculate_bandwidth(upper[-1], middle[-1], lower[-1])
    assert bandwidth is not None and bandwidth > 0, "Bandwidth calculation failed"

    print("  ✓ Bollinger Bands tests passed")


def test_fibonacci_levels():
    """Test Fibonacci retracement levels."""
    print("Testing Fibonacci Levels...")

    # Calculate Fib levels from swing high/low
    high = 150.0
    low = 100.0

    levels = calculate_fibonacci_levels(high, low)

    # Check all standard levels exist
    expected_levels = ["0%", "23.6%", "38.2%", "50%", "61.8%", "78.6%", "100%"]
    for level_name in expected_levels:
        assert level_name in levels, f"Missing Fibonacci level: {level_name}"

    # Verify calculations
    assert levels["0%"] == 100.0, "0% level should equal low"
    assert levels["100%"] == 150.0, "100% level should equal high"
    assert levels["50%"] == 125.0, "50% level should be midpoint"

    # Golden ratio (61.8%) should be between 50% and 100%
    assert 125.0 < levels["61.8%"] < 150.0, "61.8% level out of range"

    print("  ✓ Fibonacci levels tests passed")


def test_swing_points():
    """Test swing point detection."""
    print("Testing Swing Point Detection...")

    # Create data with clear swing high and low
    prices = [
        100,
        105,
        110,
        108,
        106,
        104,
        107,
        112,
        115,
        113,
        110,
        108,
        106,
        109,
        112,
        114,
        116,
        114,
        112,
        110,
    ]

    high, low, h_idx, l_idx = find_swing_points(prices, lookback=20, min_bars=2)

    assert high is not None, "Swing high not found"
    assert low is not None, "Swing low not found"
    assert high > low, "Swing high should be greater than swing low"
    assert h_idx is not None and l_idx is not None, "Swing indices not found"

    print(f"  Found swing high: {high:.2f} at index {h_idx}")
    print(f"  Found swing low: {low:.2f} at index {l_idx}")
    print("  ✓ Swing point detection tests passed")


def test_support_resistance():
    """Test support and resistance detection."""
    print("Testing Support/Resistance Detection...")

    # Create price data with clear levels
    prices = [
        100,
        102,
        100,
        103,
        100,
        105,
        102,
        107,
        105,
        110,
        108,
        112,
        110,
        115,
        112,
        110,
        108,
        105,
        107,
        105,
    ]
    volumes = [1000] * len(prices)

    support, resistance = detect_support_resistance(
        prices, volumes, sensitivity=0.03, min_touches=2, max_levels=5
    )

    assert len(support) > 0 or len(resistance) > 0, "No S/R levels detected"

    # Verify level structure
    if support:
        level = support[0]
        assert "price" in level, "Support level missing price"
        assert "strength" in level, "Support level missing strength"
        assert "touches" in level, "Support level missing touches"
        print(
            f"  Found support at ${level['price']:.2f} (strength: {level['strength']:.2f})"
        )

    if resistance:
        level = resistance[0]
        assert "price" in level, "Resistance level missing price"
        assert "strength" in level, "Resistance level missing strength"
        assert "touches" in level, "Resistance level missing touches"
        print(
            f"  Found resistance at ${level['price']:.2f} (strength: {level['strength']:.2f})"
        )

    print("  ✓ Support/Resistance detection tests passed")


def test_volume_profile():
    """Test volume profile calculation."""
    print("Testing Volume Profile...")

    prices = [
        100,
        101,
        102,
        101,
        100,
        99,
        100,
        101,
        102,
        103,
        102,
        101,
        100,
        101,
        102,
        103,
        104,
        103,
        102,
        101,
    ]
    volumes = [
        1000,
        1500,
        2000,
        1800,
        1200,
        900,
        1100,
        1600,
        2100,
        1700,
        1900,
        1400,
        1300,
        1700,
        2200,
        2400,
        2000,
        1800,
        1500,
        1200,
    ]

    price_levels, vol_at_price = calculate_volume_profile(prices, volumes, bins=5)

    assert len(price_levels) == 5, "Wrong number of price levels"
    assert len(vol_at_price) == 5, "Wrong number of volume bins"
    assert sum(vol_at_price) > 0, "Total volume should be > 0"

    # Find POC
    poc = find_point_of_control(price_levels, vol_at_price)
    assert poc is not None, "POC not found"
    assert min(prices) <= poc <= max(prices), "POC out of price range"

    # Calculate value area
    vah, poc_va, val = calculate_value_area(
        price_levels, vol_at_price, value_area_pct=0.70
    )
    assert vah is not None and val is not None, "Value area not calculated"
    assert vah > val, "VAH should be greater than VAL"
    assert val <= poc_va <= vah, "POC should be within value area"

    print(f"  POC: ${poc:.2f}")
    print(f"  Value Area: ${val:.2f} - ${vah:.2f}")
    print("  ✓ Volume Profile tests passed")


def test_mtf_analysis():
    """Test multiple timeframe analysis."""
    print("Testing Multiple Timeframe Analysis...")

    # Create trending data for different timeframes
    data = {
        "1D": [100, 102, 104, 106, 108, 110],  # Bullish
        "1W": [95, 100, 105, 110, 115, 120],  # Bullish
        "1M": [80, 90, 100, 110, 120, 130],  # Bullish
    }

    result = analyze_multiple_timeframes(data, timeframe_order=["1D", "1W", "1M"])

    assert "trends" in result, "Trends not in result"
    assert "alignment" in result, "Alignment not in result"
    assert "strength" in result, "Strength not in result"

    # All should be bullish
    assert (
        result["alignment"] == "all_bullish"
    ), f"Expected all_bullish, got {result['alignment']}"
    assert result["strength"] == 100, f"Expected strength 100, got {result['strength']}"

    print(f"  Trends: {result['trends']}")
    print(f"  Alignment: {result['alignment']}")
    print(f"  Strength: {result['strength']}")
    print("  ✓ MTF Analysis tests passed")


def test_trend_detection():
    """Test trend detection."""
    print("Testing Trend Detection...")

    # Uptrend
    up_prices = [100, 102, 104, 106, 108, 110]
    trend = detect_trend(up_prices, method="ma")
    assert trend == "bullish", f"Expected bullish, got {trend}"

    # Downtrend
    down_prices = [110, 108, 106, 104, 102, 100]
    trend = detect_trend(down_prices, method="ma")
    assert trend == "bearish", f"Expected bearish, got {trend}"

    # Neutral/sideways
    neutral_prices = [100, 101, 100, 101, 100, 101]
    trend = detect_trend(neutral_prices, method="ma")
    assert trend == "neutral", f"Expected neutral, got {trend}"

    print("  ✓ Trend detection tests passed")


def run_all_tests():
    """Run all indicator tests."""
    print("=" * 60)
    print("WAVE 3.1: Advanced Chart Indicators - Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_bollinger_bands,
        test_fibonacci_levels,
        test_swing_points,
        test_support_resistance,
        test_volume_profile,
        test_mtf_analysis,
        test_trend_detection,
    ]

    failed = []

    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  ✗ {test.__name__} FAILED: {e}")
            failed.append((test.__name__, e))

    print()
    print("=" * 60)

    if failed:
        print(f"FAILED: {len(failed)}/{len(tests)} tests failed")
        print()
        for name, error in failed:
            print(f"  - {name}: {error}")
    else:
        print(f"SUCCESS: All {len(tests)} tests passed!")

    print("=" * 60)

    return len(failed) == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
