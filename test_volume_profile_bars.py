"""
test_volume_profile_bars.py
============================

Test script for WeBull-style horizontal volume profile bars visualization.

Tests:
1. Basic volume profile bar rendering
2. HVN/LVN coloring
3. Integration with render_multipanel_chart()
4. Environment variable controls
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.charts import render_multipanel_chart
from catalyst_bot.logging_utils import get_logger

log = get_logger("test_vp_bars")


def test_volume_profile_bars():
    """Test volume profile horizontal bars visualization."""

    log.info("=" * 60)
    log.info("Testing Volume Profile Horizontal Bars Visualization")
    log.info("=" * 60)

    # Test 1: Basic volume profile bars with AAPL
    log.info("\nTest 1: Basic volume profile bars (AAPL)")
    log.info("-" * 60)

    # Enable volume profile bars
    os.environ["CHART_VOLUME_PROFILE_SHOW_BARS"] = "1"
    os.environ["CHART_VOLUME_PROFILE_BINS"] = "25"

    try:
        path = render_multipanel_chart(
            ticker="AAPL",
            timeframe="1D",
            indicators=["vwap", "volume_profile"],
            out_dir="out/test_charts"
        )

        if path and path.exists():
            log.info(f"✓ Volume profile bars chart generated: {path}")
            log.info(f"  File size: {path.stat().st_size / 1024:.1f} KB")
        else:
            log.error("✗ Failed to generate volume profile bars chart")
    except Exception as err:
        log.error(f"✗ Test 1 failed: {err}")

    # Test 2: Volume profile with RSI and MACD
    log.info("\nTest 2: Volume profile with indicators (TSLA)")
    log.info("-" * 60)

    try:
        path = render_multipanel_chart(
            ticker="TSLA",
            timeframe="1D",
            indicators=["vwap", "rsi", "macd", "volume_profile"],
            out_dir="out/test_charts"
        )

        if path and path.exists():
            log.info(f"✓ Multi-indicator chart with VP bars generated: {path}")
            log.info(f"  File size: {path.stat().st_size / 1024:.1f} KB")
        else:
            log.error("✗ Failed to generate multi-indicator chart")
    except Exception as err:
        log.error(f"✗ Test 2 failed: {err}")

    # Test 3: Volume profile using 'vp' alias
    log.info("\nTest 3: Volume profile using 'vp' alias (SPY)")
    log.info("-" * 60)

    try:
        path = render_multipanel_chart(
            ticker="SPY",
            timeframe="1D",
            indicators=["vwap", "vp"],  # Using 'vp' alias
            out_dir="out/test_charts"
        )

        if path and path.exists():
            log.info(f"✓ Volume profile (vp alias) chart generated: {path}")
            log.info(f"  File size: {path.stat().st_size / 1024:.1f} KB")
        else:
            log.error("✗ Failed to generate vp alias chart")
    except Exception as err:
        log.error(f"✗ Test 3 failed: {err}")

    # Test 4: Different bin sizes
    log.info("\nTest 4: Volume profile with different bin sizes (NVDA)")
    log.info("-" * 60)

    for bins in [15, 20, 30]:
        try:
            os.environ["CHART_VOLUME_PROFILE_BINS"] = str(bins)
            path = render_multipanel_chart(
                ticker="NVDA",
                timeframe="1D",
                indicators=["volume_profile"],
                out_dir=f"out/test_charts/bins_{bins}"
            )

            if path and path.exists():
                log.info(f"✓ Volume profile chart with {bins} bins generated: {path}")
            else:
                log.error(f"✗ Failed to generate chart with {bins} bins")
        except Exception as err:
            log.error(f"✗ Test with {bins} bins failed: {err}")

    # Test 5: Volume profile bars disabled
    log.info("\nTest 5: Volume profile bars disabled (should only show POC/VAH/VAL)")
    log.info("-" * 60)

    os.environ["CHART_VOLUME_PROFILE_SHOW_BARS"] = "0"
    os.environ["CHART_VOLUME_PROFILE_SHOW_POC"] = "1"

    try:
        path = render_multipanel_chart(
            ticker="MSFT",
            timeframe="1D",
            indicators=["volume_profile"],
            out_dir="out/test_charts"
        )

        if path and path.exists():
            log.info(f"✓ Chart with POC/VAH/VAL only (no bars) generated: {path}")
        else:
            log.error("✗ Failed to generate POC/VAH/VAL only chart")
    except Exception as err:
        log.error(f"✗ Test 5 failed: {err}")

    log.info("\n" + "=" * 60)
    log.info("Volume Profile Bars Testing Complete!")
    log.info("=" * 60)
    log.info("\nCheck the following directory for output:")
    log.info("  out/test_charts/")
    log.info("\nExpected output:")
    log.info("  - Horizontal volume bars on right 15% of price panel")
    log.info("  - Green bars for High Volume Nodes (HVN)")
    log.info("  - Red bars for Low Volume Nodes (LVN)")
    log.info("  - Cyan bars for regular volume levels")
    log.info("  - POC/VAH/VAL lines overlaid on price chart")


if __name__ == "__main__":
    test_volume_profile_bars()
