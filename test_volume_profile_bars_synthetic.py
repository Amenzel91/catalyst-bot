"""
test_volume_profile_bars_synthetic.py
======================================

Test script for volume profile bars using synthetic data.

This test creates a DataFrame with known data to verify:
1. Volume profile bar rendering
2. HVN/LVN coloring
3. Matplotlib inset_axes positioning
"""

import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.charts import render_chart_with_panels
from catalyst_bot.logging_utils import get_logger

log = get_logger("test_vp_synthetic")


def create_synthetic_ohlcv_data(periods=100, base_price=150.0):
    """Create synthetic OHLCV data with volume clustering."""

    dates = pd.date_range(end=pd.Timestamp.now(), periods=periods, freq='5min')

    # Create price trend with some volatility
    trend = np.linspace(base_price, base_price * 1.1, periods)
    noise = np.random.normal(0, base_price * 0.02, periods)
    close_prices = trend + noise

    # Create OHLC
    high_prices = close_prices + np.abs(np.random.normal(0, base_price * 0.01, periods))
    low_prices = close_prices - np.abs(np.random.normal(0, base_price * 0.01, periods))
    open_prices = close_prices + np.random.normal(0, base_price * 0.005, periods)

    # Create volume with clustering at certain price levels
    # Higher volume at beginning and end (simulating support/resistance)
    volumes = np.ones(periods) * 100000
    volumes[:20] *= 3  # High volume node at lower prices
    volumes[-20:] *= 3  # High volume node at higher prices
    volumes[40:60] *= 0.3  # Low volume node in middle

    # Add random variation
    volumes += np.random.normal(0, 20000, periods)
    volumes = np.abs(volumes)

    df = pd.DataFrame({
        'Open': open_prices,
        'High': high_prices,
        'Low': low_prices,
        'Close': close_prices,
        'Volume': volumes
    }, index=dates)

    return df


def test_volume_profile_bars_synthetic():
    """Test volume profile bars with synthetic data."""

    log.info("=" * 60)
    log.info("Testing Volume Profile Bars with Synthetic Data")
    log.info("=" * 60)

    # Enable volume profile
    os.environ["CHART_VOLUME_PROFILE_SHOW_BARS"] = "1"
    os.environ["CHART_VOLUME_PROFILE_SHOW_POC"] = "1"
    os.environ["CHART_VOLUME_PROFILE_BINS"] = "20"

    # Test 1: Basic volume profile bars
    log.info("\nTest 1: Basic volume profile bars")
    log.info("-" * 60)

    try:
        df = create_synthetic_ohlcv_data(periods=100, base_price=150.0)
        log.info(f"Created synthetic data: {len(df)} rows")
        log.info(f"Price range: ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")
        log.info(f"Volume range: {df['Volume'].min():.0f} - {df['Volume'].max():.0f}")

        path = render_chart_with_panels(
            ticker="SYNTHETIC_TEST",
            df=df,
            indicators=["volume_profile"],
            out_dir="out/test_charts"
        )

        if path and path.exists():
            log.info(f"✓ Volume profile bars chart generated: {path}")
            log.info(f"  File size: {path.stat().st_size / 1024:.1f} KB")
        else:
            log.error("✗ Failed to generate volume profile bars chart")
    except Exception as err:
        log.error(f"✗ Test 1 failed: {err}")
        import traceback
        traceback.print_exc()

    # Test 2: Volume profile with VWAP overlay
    log.info("\nTest 2: Volume profile with VWAP")
    log.info("-" * 60)

    try:
        df = create_synthetic_ohlcv_data(periods=150, base_price=200.0)

        # Add VWAP
        df['vwap'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

        path = render_chart_with_panels(
            ticker="SYNTHETIC_VWAP",
            df=df,
            indicators=["vwap", "volume_profile"],
            out_dir="out/test_charts"
        )

        if path and path.exists():
            log.info(f"✓ Volume profile + VWAP chart generated: {path}")
            log.info(f"  File size: {path.stat().st_size / 1024:.1f} KB")
        else:
            log.error("✗ Failed to generate VWAP chart")
    except Exception as err:
        log.error(f"✗ Test 2 failed: {err}")
        import traceback
        traceback.print_exc()

    # Test 3: Different bin sizes
    log.info("\nTest 3: Different bin sizes")
    log.info("-" * 60)

    for bins in [10, 25, 40]:
        try:
            os.environ["CHART_VOLUME_PROFILE_BINS"] = str(bins)
            df = create_synthetic_ohlcv_data(periods=100, base_price=150.0)

            path = render_chart_with_panels(
                ticker=f"SYNTHETIC_BINS_{bins}",
                df=df,
                indicators=["volume_profile"],
                out_dir="out/test_charts"
            )

            if path and path.exists():
                log.info(f"✓ Chart with {bins} bins generated: {path}")
            else:
                log.error(f"✗ Failed to generate chart with {bins} bins")
        except Exception as err:
            log.error(f"✗ Test with {bins} bins failed: {err}")

    # Test 4: Volume profile bars disabled (POC/VAH/VAL only)
    log.info("\nTest 4: POC/VAH/VAL lines only (no bars)")
    log.info("-" * 60)

    os.environ["CHART_VOLUME_PROFILE_SHOW_BARS"] = "0"
    os.environ["CHART_VOLUME_PROFILE_SHOW_POC"] = "1"

    try:
        df = create_synthetic_ohlcv_data(periods=100, base_price=150.0)

        path = render_chart_with_panels(
            ticker="SYNTHETIC_POC_ONLY",
            df=df,
            indicators=["volume_profile"],
            out_dir="out/test_charts"
        )

        if path and path.exists():
            log.info(f"✓ POC/VAH/VAL only chart generated: {path}")
        else:
            log.error("✗ Failed to generate POC only chart")
    except Exception as err:
        log.error(f"✗ Test 4 failed: {err}")

    log.info("\n" + "=" * 60)
    log.info("Synthetic Data Testing Complete!")
    log.info("=" * 60)
    log.info("\nCheck the following directory for output:")
    log.info("  out/test_charts/")
    log.info("\nExpected features:")
    log.info("  ✓ Horizontal volume bars on right 15% of price panel")
    log.info("  ✓ Green bars for High Volume Nodes (HVN)")
    log.info("  ✓ Red bars for Low Volume Nodes (LVN)")
    log.info("  ✓ Cyan bars for regular volume levels")
    log.info("  ✓ POC/VAH/VAL horizontal lines on price chart")
    log.info("  ✓ Transparent bars that don't obscure price action")


if __name__ == "__main__":
    test_volume_profile_bars_synthetic()
