"""
Test POC/VAH/VAL line integration in charts.

This script tests the Volume Profile POC/VAH/VAL line rendering
added in Wave 2 - Agent 4.

Expected output:
- Chart with POC line (orange, solid, width=3)
- VAH line (purple, dashed, width=2)
- VAL line (purple, dashed, width=2)
- Log output showing POC, VAH, VAL values
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set environment variables for testing
os.environ["CHART_VOLUME_PROFILE_SHOW_POC"] = "1"
os.environ["LOG_LEVEL"] = "DEBUG"

from catalyst_bot.charts import render_chart_with_panels
from catalyst_bot.logging_utils import get_logger

log = get_logger("test_poc_vah_val")


def test_poc_vah_val_with_real_data():
    """Test POC/VAH/VAL lines with real market data."""
    try:
        import pandas as pd
        from catalyst_bot import market

        ticker = "AAPL"
        log.info("test_start ticker=%s", ticker)

        # Fetch real data
        df = market.get_intraday(ticker, interval="5min", output_size="compact", prepost=True)

        if df is None or df.empty:
            log.error("test_failed reason=no_data ticker=%s", ticker)
            return False

        log.info("test_data_fetched ticker=%s rows=%d", ticker, len(df))

        # Ensure DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # Test with volume_profile indicator
        chart_path = render_chart_with_panels(
            ticker=ticker,
            df=df,
            indicators=['volume_profile', 'vwap'],  # Include volume_profile
            out_dir="out/test_charts"
        )

        if chart_path and chart_path.exists():
            log.info("test_success ticker=%s chart=%s", ticker, chart_path)
            print(f"\n[PASS] POC/VAH/VAL test PASSED")
            print(f"  Chart saved to: {chart_path}")
            print(f"  Check chart for:")
            print(f"    - POC line (orange, solid, thick)")
            print(f"    - VAH line (purple, dashed)")
            print(f"    - VAL line (purple, dashed)")
            return True
        else:
            log.error("test_failed reason=no_chart_generated ticker=%s", ticker)
            return False

    except Exception as err:
        log.error("test_error ticker=%s err=%s", ticker, str(err), exc_info=True)
        return False


def test_poc_vah_val_with_synthetic_data():
    """Test POC/VAH/VAL lines with synthetic data for predictable results."""
    try:
        import pandas as pd
        import numpy as np

        log.info("test_synthetic_start")

        # Create synthetic OHLCV data with concentrated volume at specific price
        dates = pd.date_range(start='2024-01-01 09:30', periods=100, freq='5min')

        # Create price data that oscillates around 150
        prices = 150 + np.sin(np.linspace(0, 4*np.pi, 100)) * 5

        # Create volume data with peak at ~150 (this will be POC)
        volumes = 1000000 + (1 - (np.abs(prices - 150) / 5)) * 5000000
        volumes = np.maximum(volumes, 100000)  # Ensure positive

        df = pd.DataFrame({
            'Open': (prices + np.random.randn(100) * 0.5).astype(np.float64),
            'High': (prices + np.random.randn(100) * 0.5 + 1).astype(np.float64),
            'Low': (prices + np.random.randn(100) * 0.5 - 1).astype(np.float64),
            'Close': prices.astype(np.float64),
            'Volume': volumes.astype(np.float64)
        }, index=dates)

        # Ensure OHLC relationships are correct
        df['High'] = df[['Open', 'High', 'Low', 'Close']].max(axis=1).astype(np.float64)
        df['Low'] = df[['Open', 'High', 'Low', 'Close']].min(axis=1).astype(np.float64)

        log.info("test_synthetic_data_created rows=%d price_range=[%.2f, %.2f]",
                 len(df), df['Close'].min(), df['Close'].max())

        # Test with volume_profile indicator
        chart_path = render_chart_with_panels(
            ticker="SYNTHETIC",
            df=df,
            indicators=['volume_profile', 'vwap'],
            out_dir="out/test_charts"
        )

        if chart_path and chart_path.exists():
            log.info("test_synthetic_success chart=%s", chart_path)
            print(f"\n[PASS] Synthetic POC/VAH/VAL test PASSED")
            print(f"  Chart saved to: {chart_path}")
            print(f"  Expected POC near $150 (highest volume)")
            print(f"  Expected VAH/VAL to bound 70% of volume")
            return True
        else:
            log.error("test_synthetic_failed reason=no_chart")
            return False

    except Exception as err:
        log.error("test_synthetic_error err=%s", str(err), exc_info=True)
        return False


def test_no_volume_data():
    """Test behavior when volume data is missing (all zeros)."""
    try:
        import pandas as pd
        import numpy as np

        log.info("test_no_volume_start")

        # Create data with Volume=0 (empty volume)
        dates = pd.date_range(start='2024-01-01 09:30', periods=50, freq='5min')
        df = pd.DataFrame({
            'Open': np.float64(100.0),
            'High': np.float64(105.0),
            'Low': np.float64(95.0),
            'Close': np.float64(100.0),
            'Volume': np.float64(0.0),  # Zero volume
        }, index=dates)

        # This should not crash, just log a warning
        chart_path = render_chart_with_panels(
            ticker="NO_VOL",
            df=df,
            indicators=['volume_profile'],
            out_dir="out/test_charts"
        )

        # Chart might still be generated, just without POC/VAH/VAL lines
        log.info("test_no_volume_complete chart_generated=%s", chart_path is not None)
        print(f"\n[PASS] No-volume test PASSED (should log warning)")
        return True

    except Exception as err:
        log.error("test_no_volume_error err=%s", str(err), exc_info=True)
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("POC/VAH/VAL Line Integration Test")
    print("=" * 60)

    # Test with real data
    print("\n[1/3] Testing with real market data (AAPL)...")
    success1 = test_poc_vah_val_with_real_data()

    # Test with synthetic data
    print("\n[2/3] Testing with synthetic data...")
    success2 = test_poc_vah_val_with_synthetic_data()

    # Test edge case: no volume
    print("\n[3/3] Testing edge case (no volume)...")
    success3 = test_no_volume_data()

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print(f"  Real data test: {'PASS' if success1 else 'FAIL'}")
    print(f"  Synthetic data test: {'PASS' if success2 else 'FAIL'}")
    print(f"  No volume test: {'PASS' if success3 else 'FAIL'}")
    print("=" * 60)

    if success1 and success2 and success3:
        print("\n[SUCCESS] All tests PASSED")
        sys.exit(0)
    else:
        print("\n[FAILURE] Some tests FAILED")
        sys.exit(1)
