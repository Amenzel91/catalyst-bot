"""
Test script to generate a chart with Fibonacci retracement levels.
This demonstrates the visual output of the Fibonacci integration.
"""

import sys
import os
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    """Generate a test chart with Fibonacci levels."""
    print("=" * 60)
    print("Fibonacci Chart Generation Test")
    print("=" * 60)

    # Test ticker (choose a liquid stock for good data)
    ticker = "AAPL"
    print(f"\nGenerating chart for {ticker} with Fibonacci retracements...")

    try:
        from catalyst_bot.charts import render_multipanel_chart

        # Generate chart with Fibonacci levels
        # Include VWAP, RSI, and Fibonacci indicators
        chart_path = render_multipanel_chart(
            ticker=ticker,
            timeframe="1D",
            indicators=["vwap", "rsi", "fibonacci"],
            out_dir="out/charts"
        )

        if chart_path and chart_path.exists():
            print(f"\n✓ Chart generated successfully!")
            print(f"  Path: {chart_path.absolute()}")
            print(f"  Size: {chart_path.stat().st_size:,} bytes")
            print(f"\nExpected output:")
            print(f"  - Gold dashed horizontal lines for Fibonacci levels")
            print(f"  - 7 levels: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%")
            print(f"  - Swing high/low auto-detected from price data")
            print(f"  - VWAP overlay on price panel")
            print(f"  - RSI panel below")
            print(f"\nRecommendation: Open the chart to verify Fibonacci lines are visible")
            return 0
        else:
            print("\n✗ Chart generation failed - no file created")
            print("  This may indicate missing dependencies (matplotlib/mplfinance)")
            print("  or insufficient market data for the ticker")
            return 1

    except ImportError as e:
        print(f"\n✗ Import error: {e}")
        print("  Please ensure matplotlib and mplfinance are installed:")
        print("  pip install matplotlib mplfinance")
        return 1

    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
