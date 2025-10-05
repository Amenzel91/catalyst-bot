"""Test script for advanced multi-panel charts.

Usage:
    python test_advanced_charts.py AAPL
    python test_advanced_charts.py TSLA 5D
    python test_advanced_charts.py SPY --all-timeframes
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.charts_advanced import (
    generate_multi_panel_chart,
    generate_all_timeframes,
    TIMEFRAME_CONFIG,
)
from catalyst_bot.chart_cache import get_cache


def test_single_chart(ticker: str, timeframe: str = "1D"):
    """Test generating a single chart."""
    print(f"\n{'='*60}")
    print(f"Testing: {ticker} - {timeframe}")
    print(f"{'='*60}\n")

    # Generate chart
    print(f"Generating {timeframe} chart for {ticker}...")
    chart_path = generate_multi_panel_chart(
        ticker=ticker,
        timeframe=timeframe,
        style="dark"
    )

    if chart_path and chart_path.exists():
        print(f"[OK] SUCCESS!")
        print(f"   Path: {chart_path}")
        print(f"   Size: {chart_path.stat().st_size / 1024:.1f} KB")

        # Test cache
        print(f"\nTesting cache...")
        cache = get_cache()
        cached_path = cache.get(ticker, timeframe)

        if cached_path:
            print(f"[OK] Chart found in cache!")
            print(f"   Cache key: {ticker}_{timeframe}")
        else:
            print(f"[WARN] Chart not in cache, adding...")
            cache.put(ticker, timeframe, chart_path)
            print(f"[OK] Added to cache")

        # Cache stats
        stats = cache.stats()
        print(f"\nCache Statistics:")
        print(f"   Total entries: {stats['size']}")
        print(f"   Expired: {stats['expired']}")
        print(f"   TTL: {stats['ttl_seconds']}s")

        return True
    else:
        print(f"[FAIL] FAILED to generate chart")
        return False


def test_all_timeframes(ticker: str):
    """Test generating all timeframes."""
    print(f"\n{'='*60}")
    print(f"Testing ALL timeframes for: {ticker}")
    print(f"{'='*60}\n")

    results = generate_all_timeframes(ticker, style="dark")

    success_count = 0
    total_size = 0

    for tf, path in results.items():
        if path and path.exists():
            size_kb = path.stat().st_size / 1024
            total_size += size_kb
            print(f"[OK] {tf:4s}: {path.name} ({size_kb:.1f} KB)")
            success_count += 1
        else:
            print(f"[FAIL] {tf:4s}: FAILED")

    print(f"\n{'='*60}")
    print(f"Results: {success_count}/{len(results)} succeeded")
    print(f"Total size: {total_size:.1f} KB")
    print(f"{'='*60}\n")

    return success_count == len(results)


def test_cache_operations():
    """Test cache operations."""
    print(f"\n{'='*60}")
    print(f"Testing Cache Operations")
    print(f"{'='*60}\n")

    cache = get_cache()

    # Stats
    stats = cache.stats()
    print(f"Current cache stats:")
    print(f"   Size: {stats['size']}")
    print(f"   Expired: {stats['expired']}")
    print(f"   TTL: {stats['ttl_seconds']}s")
    print(f"   Oldest: {stats['oldest']}")
    print(f"   Newest: {stats['newest']}")

    # Test clear expired
    print(f"\nClearing expired entries...")
    removed = cache.clear_expired()
    print(f"[OK] Removed {removed} expired entries")

    # New stats
    stats = cache.stats()
    print(f"\nUpdated cache stats:")
    print(f"   Size: {stats['size']}")
    print(f"   Expired: {stats['expired']}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Test advanced multi-panel chart generation"
    )
    parser.add_argument(
        "ticker",
        help="Stock ticker symbol (e.g., AAPL, TSLA, SPY)"
    )
    parser.add_argument(
        "timeframe",
        nargs="?",
        default="1D",
        choices=list(TIMEFRAME_CONFIG.keys()),
        help="Timeframe to generate (default: 1D)"
    )
    parser.add_argument(
        "--all-timeframes",
        action="store_true",
        help="Generate all timeframes"
    )
    parser.add_argument(
        "--test-cache",
        action="store_true",
        help="Test cache operations"
    )

    args = parser.parse_args()

    # Set test mode environment variables
    os.environ.setdefault("CHART_CACHE_TTL_SECONDS", "300")
    os.environ.setdefault("CHART_CACHE_DIR", "out/charts/test_cache")

    print(f"\n>>> Advanced Charts Test Suite")
    print(f"{'='*60}")

    success = True

    if args.all_timeframes:
        success = test_all_timeframes(args.ticker)
    else:
        success = test_single_chart(args.ticker, args.timeframe)

    if args.test_cache:
        success = test_cache_operations() and success

    print(f"\n{'='*60}")
    if success:
        print(f"[SUCCESS] ALL TESTS PASSED!")
    else:
        print(f"[FAILED] SOME TESTS FAILED")
    print(f"{'='*60}\n")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
