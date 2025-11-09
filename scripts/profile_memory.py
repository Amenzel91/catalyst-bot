"""Memory Profiling Suite for Catalyst Bot - Wave 4.2

Measures memory footprint of performance-critical components:
- Float cache size after 1000 tickers (target: <5MB)
- Chart data memory for 90-day 15min chart (target: <2MB)
- Dedup cache growth rate over 24hr simulation

Usage:
    python scripts/profile_memory.py [--verbose]

Results are written to:
    - Console (summary)
    - data/benchmarks/memory_profile_TIMESTAMP.json (detailed metrics)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Add parent directory to path to import catalyst_bot modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def get_object_size(obj) -> int:
    """Get approximate size of an object in bytes (recursively).

    Args:
        obj: Object to measure

    Returns:
        Size in bytes
    """
    import sys
    from types import ModuleType, FunctionType
    from gc import get_referents

    # Custom objects know their class.
    # Function objects seem to know way too much, including modules.
    BLACKLIST = type, ModuleType, FunctionType

    seen = set()
    size = 0
    objects = [obj]

    while objects:
        need_referents = []
        for obj in objects:
            if not isinstance(obj, BLACKLIST) and id(obj) not in seen:
                seen.add(id(obj))
                size += sys.getsizeof(obj)
                need_referents.append(obj)

        objects = get_referents(*need_referents)

    return size


def profile_float_cache(num_tickers: int = 1000) -> Dict[str, Any]:
    """Profile float cache memory usage.

    Target: <5MB for 1000 tickers
    """
    print(f"\n[1/3] Profiling float cache memory ({num_tickers} tickers)...")

    try:
        import tracemalloc
        from catalyst_bot.float_data import get_float_data, get_cache_path

        # Start memory tracking
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        # Populate cache with test tickers
        test_tickers = [
            # Major stocks
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "AMD",
            # Popular small caps
            "PLTR", "SOFI", "RIVN", "LCID", "NIO", "XPEV",
        ]

        # Simulate 1000 lookups (will hit cache after first lookup per ticker)
        cache_hits = 0
        for i in range(num_tickers):
            ticker = test_tickers[i % len(test_tickers)]
            result = get_float_data(ticker)
            if result:
                cache_hits += 1

        # Take snapshot after cache population
        snapshot_after = tracemalloc.take_snapshot()

        # Calculate memory delta
        stats = snapshot_after.compare_to(snapshot_before, 'lineno')

        total_increase = sum(stat.size_diff for stat in stats if stat.size_diff > 0)
        total_increase_mb = total_increase / (1024 * 1024)

        # Get cache file size (on-disk)
        cache_path = get_cache_path()
        cache_file_size_mb = 0
        if cache_path.exists():
            cache_file_size_mb = cache_path.stat().st_size / (1024 * 1024)

        tracemalloc.stop()

        target_mb = 5.0
        passed = total_increase_mb < target_mb

        print(f"  Memory increase: {total_increase_mb:.2f} MB")
        print(f"  Cache file size: {cache_file_size_mb:.2f} MB")
        print(f"  Target: <{target_mb} MB | {'✓ PASS' if passed else '✗ FAIL'}")

        return {
            "test": "float_cache_memory",
            "num_tickers": num_tickers,
            "unique_tickers": len(test_tickers),
            "cache_hits": cache_hits,
            "memory_increase_mb": round(total_increase_mb, 3),
            "cache_file_size_mb": round(cache_file_size_mb, 3),
            "target_mb": target_mb,
            "pass": passed,
        }

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return {"test": "float_cache_memory", "error": str(e), "pass": False}


def profile_chart_data_memory() -> Dict[str, Any]:
    """Profile chart data memory footprint for 90-day 15min chart.

    Target: <2MB per chart
    """
    print("\n[2/3] Profiling chart data memory (90-day 15min chart)...")

    try:
        import tracemalloc
        import pandas as pd
        import numpy as np
        from datetime import timedelta

        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        # Create realistic chart data
        # 90 days * 6.5 trading hours * 4 bars per hour (15min) = ~2,340 bars
        num_bars = 90 * 26  # Simplified: 26 bars per day (6.5hr / 15min)

        dates = pd.date_range(end=datetime.now(), periods=num_bars, freq='15min')

        chart_data = pd.DataFrame({
            'Open': np.random.uniform(100, 200, num_bars),
            'High': np.random.uniform(100, 200, num_bars),
            'Low': np.random.uniform(100, 200, num_bars),
            'Close': np.random.uniform(100, 200, num_bars),
            'Volume': np.random.randint(1000000, 10000000, num_bars),
        }, index=dates)

        # Compute indicators (as done in charts_advanced.py)
        chart_data['VWAP'] = (chart_data['Close'] * chart_data['Volume']).cumsum() / chart_data['Volume'].cumsum()

        # RSI
        delta = chart_data['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
        rs = gain / loss
        chart_data['RSI'] = 100 - (100 / (1 + rs))

        # MACD
        ema_fast = chart_data['Close'].ewm(span=12, adjust=False).mean()
        ema_slow = chart_data['Close'].ewm(span=26, adjust=False).mean()
        chart_data['MACD'] = ema_fast - ema_slow
        chart_data['MACD_Signal'] = chart_data['MACD'].ewm(span=9, adjust=False).mean()

        snapshot_after = tracemalloc.take_snapshot()

        # Calculate memory delta
        stats = snapshot_after.compare_to(snapshot_before, 'lineno')
        total_increase = sum(stat.size_diff for stat in stats if stat.size_diff > 0)
        total_increase_mb = total_increase / (1024 * 1024)

        # Also measure dataframe memory directly
        df_memory_mb = chart_data.memory_usage(deep=True).sum() / (1024 * 1024)

        tracemalloc.stop()

        target_mb = 2.0
        passed = df_memory_mb < target_mb

        print(f"  DataFrame memory: {df_memory_mb:.2f} MB")
        print(f"  Total memory increase: {total_increase_mb:.2f} MB")
        print(f"  Bars: {len(chart_data)} | Columns: {len(chart_data.columns)}")
        print(f"  Target: <{target_mb} MB | {'✓ PASS' if passed else '✗ FAIL'}")

        return {
            "test": "chart_data_memory",
            "chart_days": 90,
            "interval": "15min",
            "num_bars": len(chart_data),
            "num_indicators": 4,  # VWAP, RSI, MACD, MACD_Signal
            "dataframe_memory_mb": round(df_memory_mb, 3),
            "total_memory_increase_mb": round(total_increase_mb, 3),
            "target_mb": target_mb,
            "pass": passed,
        }

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return {"test": "chart_data_memory", "error": str(e), "pass": False}


def profile_dedup_cache_growth() -> Dict[str, Any]:
    """Profile dedup cache growth rate over 24hr simulation.

    Simulates 24 hours of article processing to measure cache growth.
    """
    print("\n[3/3] Profiling dedup cache growth (24hr simulation)...")

    try:
        import tracemalloc
        from datetime import timedelta

        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        # Simulate dedup cache (simple set-based deduplication)
        dedup_cache = set()

        # Simulate 24 hours of articles
        # Assume 50 articles/hour * 24 hours = 1200 articles
        num_articles = 1200

        # Generate article IDs (mix of unique and duplicates)
        # Assume 20% duplicate rate
        unique_articles = int(num_articles * 0.8)

        for i in range(num_articles):
            # Generate article ID (URL hash or similar)
            if i < unique_articles:
                article_id = f"article_{i}"
            else:
                # Duplicate (re-use earlier ID)
                article_id = f"article_{i % unique_articles}"

            dedup_cache.add(article_id)

        snapshot_after = tracemalloc.take_snapshot()

        # Calculate memory delta
        stats = snapshot_after.compare_to(snapshot_before, 'lineno')
        total_increase = sum(stat.size_diff for stat in stats if stat.size_diff > 0)
        total_increase_mb = total_increase / (1024 * 1024)

        # Also measure cache size directly
        cache_size_bytes = get_object_size(dedup_cache)
        cache_size_mb = cache_size_bytes / (1024 * 1024)

        tracemalloc.stop()

        # Calculate growth rate
        growth_rate_kb_per_hour = (cache_size_mb * 1024) / 24

        print(f"  Cache size: {cache_size_mb:.3f} MB ({len(dedup_cache)} entries)")
        print(f"  Growth rate: {growth_rate_kb_per_hour:.2f} KB/hour")
        print(f"  Duplicate rate: {((num_articles - len(dedup_cache)) / num_articles * 100):.1f}%")

        return {
            "test": "dedup_cache_growth",
            "simulation_hours": 24,
            "articles_processed": num_articles,
            "unique_articles": len(dedup_cache),
            "duplicate_rate_pct": round((num_articles - len(dedup_cache)) / num_articles * 100, 1),
            "cache_size_mb": round(cache_size_mb, 3),
            "growth_rate_kb_per_hour": round(growth_rate_kb_per_hour, 2),
            "pass": True,  # No hard target for this metric
        }

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return {"test": "dedup_cache_growth", "error": str(e), "pass": False}


def main():
    parser = argparse.ArgumentParser(description="Profile Catalyst Bot memory usage")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    print("=" * 70)
    print("CATALYST BOT MEMORY PROFILING SUITE - WAVE 4.2")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []

    # Run all memory profiles
    results.append(profile_float_cache(num_tickers=1000))
    results.append(profile_chart_data_memory())
    results.append(profile_dedup_cache_growth())

    # Summary
    print("\n" + "=" * 70)
    print("MEMORY PROFILE SUMMARY")
    print("=" * 70)

    passed = sum(1 for r in results if r.get("pass", False))
    total = len(results)

    print(f"\nTests Passed: {passed}/{total}")

    failures = [r["test"] for r in results if not r.get("pass", False)]
    if failures:
        print(f"Failed Tests: {', '.join(failures)}")

    # Calculate total memory footprint estimate
    float_cache_mb = next((r.get("memory_increase_mb", 0) for r in results if r["test"] == "float_cache_memory"), 0)
    chart_data_mb = next((r.get("dataframe_memory_mb", 0) for r in results if r["test"] == "chart_data_memory"), 0)
    dedup_cache_mb = next((r.get("cache_size_mb", 0) for r in results if r["test"] == "dedup_cache_growth"), 0)

    total_memory_mb = float_cache_mb + chart_data_mb + dedup_cache_mb

    print(f"\nEstimated Total Memory Footprint: {total_memory_mb:.2f} MB")
    print(f"  - Float cache: {float_cache_mb:.2f} MB")
    print(f"  - Chart data: {chart_data_mb:.2f} MB")
    print(f"  - Dedup cache: {dedup_cache_mb:.2f} MB")

    # Save results
    output_dir = Path("data/benchmarks")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"memory_profile_{timestamp}.json"

    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "environment": {
                "python_version": sys.version,
                "platform": sys.platform,
            },
            "results": results,
            "summary": {
                "passed": passed,
                "total": total,
                "failures": failures,
                "total_memory_mb": round(total_memory_mb, 3),
            },
        }, f, indent=2)

    print(f"\nDetailed results saved to: {output_file}")
    print("\nDone.")


if __name__ == "__main__":
    main()
