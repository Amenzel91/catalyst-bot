#!/usr/bin/env python3
"""Example usage of the fundamental_data module.

This script demonstrates how to use the FinViz Elite fundamental data collector
to fetch float shares and short interest for tickers.

Before running:
    1. Set FINVIZ_API_KEY environment variable with your FinViz Elite auth cookie
    2. Ensure you have an active FinViz Elite subscription

Usage:
    python examples/fundamental_data_usage.py
"""

from catalyst_bot.fundamental_data import (
    get_float_shares,
    get_short_interest,
    get_fundamentals,
    clear_cache,
)


def main():
    """Demonstrate fundamental data collection."""

    print("=" * 80)
    print("FinViz Elite Fundamental Data Collector - Example Usage")
    print("=" * 80)

    # Example 1: Get float shares for a ticker
    print("\n1. Fetching float shares for AAPL...")
    float_shares = get_float_shares("AAPL")
    if float_shares:
        print(f"   ✓ AAPL Float: {float_shares:,.0f} shares")
        if float_shares < 10_000_000:
            print("   ⚠ Low float detected - high volatility potential!")
    else:
        print("   ✗ Float shares not available")

    # Example 2: Get short interest for a ticker
    print("\n2. Fetching short interest for GME...")
    short_pct = get_short_interest("GME")
    if short_pct:
        print(f"   ✓ GME Short Interest: {short_pct:.2f}%")
        if short_pct > 15.0:
            print("   ⚠ High short interest - squeeze potential!")
        elif short_pct > 10.0:
            print("   ℹ Moderate short interest")
        else:
            print("   ℹ Low short interest")
    else:
        print("   ✗ Short interest not available")

    # Example 3: Get both metrics efficiently
    print("\n3. Fetching both metrics for TSLA...")
    float_shares, short_pct = get_fundamentals("TSLA")
    if float_shares and short_pct:
        print(f"   ✓ TSLA Float: {float_shares:,.0f} shares")
        print(f"   ✓ TSLA Short Interest: {short_pct:.2f}%")

        # Volatility analysis
        volatility_score = 0
        if float_shares < 50_000_000:
            volatility_score += 3
            print("   → Low float (3 points)")
        elif float_shares < 100_000_000:
            volatility_score += 2
            print("   → Medium float (2 points)")
        else:
            volatility_score += 1
            print("   → High float (1 point)")

        if short_pct > 20.0:
            volatility_score += 3
            print("   → Very high short interest (3 points)")
        elif short_pct > 15.0:
            volatility_score += 2
            print("   → High short interest (2 points)")
        elif short_pct > 10.0:
            volatility_score += 1
            print("   → Moderate short interest (1 point)")

        print(f"\n   Volatility Score: {volatility_score}/6")
        if volatility_score >= 5:
            print("   ⚡ EXTREME volatility potential!")
        elif volatility_score >= 3:
            print("   ⚠ High volatility potential")
        else:
            print("   ℹ Normal volatility expected")
    else:
        print("   ✗ Data not available")

    # Example 4: Batch processing
    print("\n4. Batch processing multiple tickers...")
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    results = []

    for ticker in tickers:
        float_shares, short_pct = get_fundamentals(ticker)
        results.append({
            "ticker": ticker,
            "float": float_shares,
            "short_pct": short_pct,
        })

    print("\n   Results:")
    print(f"   {'Ticker':<8} {'Float':>15} {'Short %':>10}")
    print("   " + "-" * 35)
    for r in results:
        float_str = f"{r['float']:,.0f}" if r['float'] else "N/A"
        short_str = f"{r['short_pct']:.2f}%" if r['short_pct'] else "N/A"
        print(f"   {r['ticker']:<8} {float_str:>15} {short_str:>10}")

    # Example 5: Cache management
    print("\n5. Cache management...")
    print("   Cache stores data to minimize API calls:")
    print("   - Float shares: 30-day cache")
    print("   - Short interest: 14-day cache")
    print("\n   To clear cache for a specific ticker:")
    print("   >>> clear_cache('AAPL')")
    print("\n   To clear all cache:")
    print("   >>> clear_cache()")

    print("\n" + "=" * 80)
    print("Example complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
