"""
Example: Using BacktestEngine with Custom Data Sources
========================================================

This example demonstrates how to use the BacktestEngine with:
1. Custom data source files
2. Custom data filters
3. Various filtering strategies
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from catalyst_bot.backtesting import BacktestEngine


def example_1_custom_data_source():
    """Example 1: Load data from a custom file path."""
    print("\n=== Example 1: Custom Data Source ===")

    engine = BacktestEngine(
        start_date="2025-01-01",
        end_date="2025-01-31",
        initial_capital=10000.0,
        data_source="data/custom_events.jsonl",  # Custom path
    )

    print(f"Data source: {engine.data_source}")
    print("Loads alerts from custom_events.jsonl instead of default events.jsonl")


def example_2_ticker_filter():
    """Example 2: Filter to only trade specific tickers."""
    print("\n=== Example 2: Ticker Filter ===")

    # Define filter: only AAPL and TSLA
    def ticker_filter(alert):
        allowed_tickers = ["AAPL", "TSLA"]
        return alert.get("ticker") in allowed_tickers

    engine = BacktestEngine(
        start_date="2025-01-01",
        end_date="2025-01-31",
        initial_capital=10000.0,
        data_source="data/events.jsonl",
        data_filter=ticker_filter,
    )

    alerts = engine.load_historical_alerts()
    print(f"Filtered to {len(alerts)} alerts")
    print("Only AAPL and TSLA alerts will be processed")


def example_3_high_score_filter():
    """Example 3: Only trade high-confidence alerts."""
    print("\n=== Example 3: High Score Filter ===")

    # Filter: only alerts with score >= 0.7
    def high_score_filter(alert):
        score = alert.get("cls", {}).get("score", 0.0)
        return score >= 0.7

    engine = BacktestEngine(
        start_date="2025-01-01",
        end_date="2025-01-31",
        initial_capital=10000.0,
        data_filter=high_score_filter,
    )

    print("Only processing alerts with score >= 0.7")


def example_4_fda_catalyst_filter():
    """Example 4: Only trade FDA-related catalysts."""
    print("\n=== Example 4: FDA Catalyst Filter ===")

    # Filter: only FDA-related events
    def fda_filter(alert):
        keywords = alert.get("cls", {}).get("keywords", [])
        fda_keywords = ["fda", "approval", "clearance", "clinical"]
        return any(kw.lower() in " ".join(keywords).lower() for kw in fda_keywords)

    engine = BacktestEngine(
        start_date="2025-01-01",
        end_date="2025-01-31",
        initial_capital=10000.0,
        data_filter=fda_filter,
    )

    print("Only processing FDA-related catalyst events")


def example_5_combined_filters():
    """Example 5: Combine multiple filter conditions."""
    print("\n=== Example 5: Combined Filters ===")

    # Complex filter: high score + positive sentiment + specific source
    def combined_filter(alert):
        score = alert.get("cls", {}).get("score", 0.0)
        sentiment = alert.get("cls", {}).get("sentiment", 0.0)
        source = alert.get("source", "")

        return (
            score >= 0.6  # High confidence
            and sentiment >= 0.5  # Positive sentiment
            and source in ["sec_filings", "news_feed"]  # Trusted sources
        )

    engine = BacktestEngine(
        start_date="2025-01-01",
        end_date="2025-01-31",
        initial_capital=10000.0,
        data_filter=combined_filter,
    )

    print("Filtering on: score >= 0.6, sentiment >= 0.5, trusted sources only")


def example_6_sector_filter():
    """Example 6: Filter by sector or industry."""
    print("\n=== Example 6: Sector Filter ===")

    # Filter: only biotech/pharma sector
    def biotech_filter(alert):
        keywords = alert.get("cls", {}).get("keywords", [])
        biotech_keywords = ["biotech", "pharma", "drug", "fda", "clinical", "trial"]
        return any(kw.lower() in " ".join(keywords).lower() for kw in biotech_keywords)

    engine = BacktestEngine(
        start_date="2025-01-01",
        end_date="2025-01-31",
        initial_capital=10000.0,
        data_filter=biotech_filter,
    )

    print("Only processing biotech/pharma sector alerts")


def example_7_time_based_filter():
    """Example 7: Filter by time of day or day of week."""
    print("\n=== Example 7: Time-Based Filter ===")

    from datetime import datetime

    # Filter: only alerts from market hours (9:30 AM - 4:00 PM ET)
    def market_hours_filter(alert):
        ts_str = alert.get("ts") or alert.get("timestamp")
        if not ts_str:
            return False

        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        hour = ts.hour

        # Simple approximation (doesn't account for timezone properly)
        return 9 <= hour <= 16

    engine = BacktestEngine(
        start_date="2025-01-01",
        end_date="2025-01-31",
        initial_capital=10000.0,
        data_filter=market_hours_filter,
    )

    print("Only processing alerts during market hours")


def example_8_backtest_comparison():
    """Example 8: Compare strategies with different data filters."""
    print("\n=== Example 8: Strategy Comparison ===")

    # Strategy 1: All alerts
    engine1 = BacktestEngine(
        start_date="2025-01-01",
        end_date="2025-01-31",
        initial_capital=10000.0,
        strategy_params={"min_score": 0.25},
    )

    # Strategy 2: High-score alerts only
    def high_score_filter(alert):
        return alert.get("cls", {}).get("score", 0.0) >= 0.7

    engine2 = BacktestEngine(
        start_date="2025-01-01",
        end_date="2025-01-31",
        initial_capital=10000.0,
        strategy_params={"min_score": 0.25},
        data_filter=high_score_filter,
    )

    print("Strategy 1: All alerts (default)")
    print("Strategy 2: High-score alerts only (score >= 0.7)")
    print("\nYou can run both strategies and compare results!")


if __name__ == "__main__":
    print("BacktestEngine Custom Data Source Examples")
    print("=" * 60)

    example_1_custom_data_source()
    example_2_ticker_filter()
    example_3_high_score_filter()
    example_4_fda_catalyst_filter()
    example_5_combined_filters()
    example_6_sector_filter()
    example_7_time_based_filter()
    example_8_backtest_comparison()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("\nKey Takeaways:")
    print("1. Use 'data_source' parameter to load from custom files")
    print("2. Use 'data_filter' parameter to filter alerts programmatically")
    print("3. Filters receive alert dict and return True/False")
    print("4. Combine multiple conditions in a single filter function")
    print("5. Default behavior unchanged for backward compatibility")
