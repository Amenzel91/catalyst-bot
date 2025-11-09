"""
test_complex_patterns.py
=========================

Test script for Head & Shoulders and Double Top/Bottom pattern visualization.

This script tests the integration of complex pattern detection into the chart
rendering system. It generates a multi-panel chart with pattern overlays for
a specified ticker.

Usage:
    python tests/test_complex_patterns.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from catalyst_bot.charts import render_multipanel_chart


def test_complex_patterns():
    """Test H&S and double patterns on TSLA."""
    print("Testing complex pattern visualization...")
    print("=" * 60)

    # Test with TSLA - often has interesting patterns
    ticker = "TSLA"
    indicators = ["vwap", "patterns", "rsi", "macd"]
    out_dir = "out/charts/test"

    print(f"\nGenerating chart for {ticker}")
    print(f"Indicators: {indicators}")
    print(f"Output directory: {out_dir}")
    print()

    try:
        chart_path = render_multipanel_chart(
            ticker=ticker,
            indicators=indicators,
            timeframe="1D",
            out_dir=out_dir,
        )

        if chart_path:
            print("[OK] Chart generated successfully!")
            print(f"  Path: {chart_path}")
            print()
            print("Pattern detection includes:")
            print("  - Triangle patterns (ascending, descending, symmetrical)")
            print("  - Head & Shoulders (classic and inverse)")
            print("  - Double Tops (bearish reversal)")
            print("  - Double Bottoms (bullish reversal)")
            print()
            print("Visual elements:")
            print("  - H&S: Circle markers for shoulders/head, gold neckline")
            print("  - Double Tops: Red 'v' markers, resistance line")
            print("  - Double Bottoms: Green '^' markers, support line")
            print("  - All patterns show confidence % and price targets")
        else:
            print("[FAIL] Chart generation failed - check logs for details")

    except Exception as err:
        print(f"[ERROR] Error during chart generation: {err}")
        import traceback

        traceback.print_exc()

    print()
    print("=" * 60)


def test_specific_tickers():
    """Test patterns on multiple tickers known for different pattern types."""
    tickers = ["AAPL", "NVDA", "SPY"]

    print("\nTesting multiple tickers for pattern diversity...")
    print("=" * 60)

    for ticker in tickers:
        print(f"\nGenerating chart for {ticker}...")

        try:
            chart_path = render_multipanel_chart(
                ticker=ticker,
                indicators=["vwap", "patterns"],
                timeframe="1D",
                out_dir="out/charts/test",
            )

            if chart_path:
                print(f"  [OK] {ticker}: {chart_path}")
            else:
                print(f"  [FAIL] {ticker}: Failed")

        except Exception as err:
            print(f"  [ERROR] {ticker}: Error - {err}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("COMPLEX PATTERN VISUALIZATION TEST")
    print("=" * 60)

    # Test main ticker
    test_complex_patterns()

    # Optional: Test multiple tickers
    response = input("\nTest additional tickers? (y/n): ").strip().lower()
    if response == "y":
        test_specific_tickers()

    print("\nTest complete!")
