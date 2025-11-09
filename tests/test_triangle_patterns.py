"""
Test script for triangle pattern detection overlay.

Tests the integration of triangle pattern detection from
src/catalyst_bot/indicators/patterns.py into the chart rendering
system in src/catalyst_bot/charts.py.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_bot.charts import render_multipanel_chart
from catalyst_bot.logging_utils import get_logger

log = get_logger("test_triangle_patterns")

def test_triangle_patterns_aapl():
    """Test triangle pattern detection with AAPL."""
    log.info("=== Testing Triangle Pattern Detection ===")
    log.info("Ticker: AAPL")
    log.info("Indicators: vwap, triangles, rsi")

    chart_path = render_multipanel_chart(
        ticker="AAPL",
        indicators=["vwap", "triangles", "rsi"],
        timeframe="1D",
        out_dir="out/charts/test"
    )

    if chart_path:
        log.info("✓ Chart generated successfully")
        log.info(f"  Path: {chart_path}")
        log.info(f"  Size: {chart_path.stat().st_size} bytes")
        return True
    else:
        log.error("✗ Chart generation failed")
        return False


def test_triangle_patterns_tsla():
    """Test triangle pattern detection with TSLA."""
    log.info("\n=== Testing Triangle Pattern Detection (TSLA) ===")
    log.info("Ticker: TSLA")
    log.info("Indicators: vwap, patterns, macd")

    chart_path = render_multipanel_chart(
        ticker="TSLA",
        indicators=["vwap", "patterns", "macd"],
        timeframe="1D",
        out_dir="out/charts/test"
    )

    if chart_path:
        log.info("✓ Chart generated successfully")
        log.info(f"  Path: {chart_path}")
        log.info(f"  Size: {chart_path.stat().st_size} bytes")
        return True
    else:
        log.error("✗ Chart generation failed")
        return False


def test_triangle_patterns_spy():
    """Test triangle pattern detection with SPY."""
    log.info("\n=== Testing Triangle Pattern Detection (SPY) ===")
    log.info("Ticker: SPY")
    log.info("Indicators: triangles, bollinger, rsi")

    chart_path = render_multipanel_chart(
        ticker="SPY",
        indicators=["triangles", "bollinger", "rsi"],
        timeframe="1D",
        out_dir="out/charts/test"
    )

    if chart_path:
        log.info("✓ Chart generated successfully")
        log.info(f"  Path: {chart_path}")
        log.info(f"  Size: {chart_path.stat().st_size} bytes")
        return True
    else:
        log.error("✗ Chart generation failed")
        return False


if __name__ == "__main__":
    log.info("Starting triangle pattern detection tests...")

    results = []
    results.append(("AAPL", test_triangle_patterns_aapl()))
    results.append(("TSLA", test_triangle_patterns_tsla()))
    results.append(("SPY", test_triangle_patterns_spy()))

    # Summary
    log.info("\n=== Test Summary ===")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for ticker, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        log.info(f"{status}: {ticker}")

    log.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        log.info("✓ All tests passed!")
        sys.exit(0)
    else:
        log.error(f"✗ {total - passed} test(s) failed")
        sys.exit(1)
