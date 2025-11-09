"""
Test script for triangle pattern detection with synthetic data.

Creates synthetic price data with triangle patterns and tests
the integration of pattern detection into chart rendering.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_bot.charts import render_chart_with_panels
from catalyst_bot.logging_utils import get_logger

log = get_logger("test_triangle_patterns_synthetic")


def create_ascending_triangle_data(n_bars=50):
    """Create synthetic data with an ascending triangle pattern."""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n_bars, freq='5min')

    # Base price around 100
    base_price = 100.0

    # Create ascending triangle: flat resistance at 110, rising support
    prices = []
    for i in range(n_bars):
        # Rising support line
        support = 95 + (i / n_bars) * 10  # Goes from 95 to 105
        # Flat resistance around 110
        resistance = 110

        # Oscillate between support and resistance
        if i % 6 < 3:
            # Moving toward resistance
            price = support + (resistance - support) * 0.7
        else:
            # Moving toward support
            price = support + (resistance - support) * 0.3

        # Add small noise
        price += np.random.randn() * 0.5
        prices.append(price)

    df = pd.DataFrame({
        'Open': prices,
        'High': [p + abs(np.random.randn() * 0.5) for p in prices],
        'Low': [p - abs(np.random.randn() * 0.5) for p in prices],
        'Close': prices,
        'Volume': [1000000 + np.random.randint(-100000, 100000) for _ in range(n_bars)]
    }, index=dates)

    return df


def create_descending_triangle_data(n_bars=50):
    """Create synthetic data with a descending triangle pattern."""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n_bars, freq='5min')

    # Create descending triangle: falling resistance, flat support at 90
    prices = []
    for i in range(n_bars):
        # Flat support at 90
        support = 90
        # Falling resistance line
        resistance = 110 - (i / n_bars) * 15  # Goes from 110 to 95

        # Oscillate between support and resistance
        if i % 6 < 3:
            price = support + (resistance - support) * 0.7
        else:
            price = support + (resistance - support) * 0.3

        # Add small noise
        price += np.random.randn() * 0.5
        prices.append(price)

    df = pd.DataFrame({
        'Open': prices,
        'High': [p + abs(np.random.randn() * 0.5) for p in prices],
        'Low': [p - abs(np.random.randn() * 0.5) for p in prices],
        'Close': prices,
        'Volume': [1000000 + np.random.randint(-100000, 100000) for _ in range(n_bars)]
    }, index=dates)

    return df


def create_symmetrical_triangle_data(n_bars=50):
    """Create synthetic data with a symmetrical triangle pattern."""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n_bars, freq='5min')

    # Create symmetrical triangle: converging lines
    prices = []
    for i in range(n_bars):
        # Falling resistance line
        resistance = 110 - (i / n_bars) * 10  # Goes from 110 to 100
        # Rising support line
        support = 90 + (i / n_bars) * 10  # Goes from 90 to 100

        # Oscillate between support and resistance
        if i % 6 < 3:
            price = support + (resistance - support) * 0.6
        else:
            price = support + (resistance - support) * 0.4

        # Add small noise
        price += np.random.randn() * 0.5
        prices.append(price)

    df = pd.DataFrame({
        'Open': prices,
        'High': [p + abs(np.random.randn() * 0.5) for p in prices],
        'Low': [p - abs(np.random.randn() * 0.5) for p in prices],
        'Close': prices,
        'Volume': [1000000 + np.random.randint(-100000, 100000) for _ in range(n_bars)]
    }, index=dates)

    return df


def test_ascending_triangle():
    """Test ascending triangle pattern detection."""
    log.info("=== Testing Ascending Triangle Pattern ===")

    df = create_ascending_triangle_data(n_bars=50)
    log.info(f"Created synthetic data: {len(df)} bars")
    log.info(f"Price range: ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")

    chart_path = render_chart_with_panels(
        ticker="SYNTHETIC_ASCENDING",
        df=df,
        indicators=["triangles"],
        out_dir="out/charts/test"
    )

    if chart_path and chart_path.exists():
        log.info("✓ Chart generated successfully")
        log.info(f"  Path: {chart_path}")
        log.info(f"  Size: {chart_path.stat().st_size} bytes")
        return True
    else:
        log.error("✗ Chart generation failed")
        return False


def test_descending_triangle():
    """Test descending triangle pattern detection."""
    log.info("\n=== Testing Descending Triangle Pattern ===")

    df = create_descending_triangle_data(n_bars=50)
    log.info(f"Created synthetic data: {len(df)} bars")
    log.info(f"Price range: ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")

    chart_path = render_chart_with_panels(
        ticker="SYNTHETIC_DESCENDING",
        df=df,
        indicators=["triangles"],
        out_dir="out/charts/test"
    )

    if chart_path and chart_path.exists():
        log.info("✓ Chart generated successfully")
        log.info(f"  Path: {chart_path}")
        log.info(f"  Size: {chart_path.stat().st_size} bytes")
        return True
    else:
        log.error("✗ Chart generation failed")
        return False


def test_symmetrical_triangle():
    """Test symmetrical triangle pattern detection."""
    log.info("\n=== Testing Symmetrical Triangle Pattern ===")

    df = create_symmetrical_triangle_data(n_bars=50)
    log.info(f"Created synthetic data: {len(df)} bars")
    log.info(f"Price range: ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")

    chart_path = render_chart_with_panels(
        ticker="SYNTHETIC_SYMMETRICAL",
        df=df,
        indicators=["triangles"],
        out_dir="out/charts/test"
    )

    if chart_path and chart_path.exists():
        log.info("✓ Chart generated successfully")
        log.info(f"  Path: {chart_path}")
        log.info(f"  Size: {chart_path.stat().st_size} bytes")
        return True
    else:
        log.error("✗ Chart generation failed")
        return False


def test_triangle_with_vwap_rsi():
    """Test triangle patterns with other indicators."""
    log.info("\n=== Testing Triangle + VWAP + RSI ===")

    df = create_ascending_triangle_data(n_bars=100)

    # Add VWAP
    df['vwap'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

    # Add RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    log.info(f"Created synthetic data: {len(df)} bars with VWAP and RSI")

    chart_path = render_chart_with_panels(
        ticker="SYNTHETIC_MULTI",
        df=df,
        indicators=["vwap", "triangles", "rsi"],
        out_dir="out/charts/test"
    )

    if chart_path and chart_path.exists():
        log.info("✓ Chart generated successfully")
        log.info(f"  Path: {chart_path}")
        log.info(f"  Size: {chart_path.stat().st_size} bytes")
        return True
    else:
        log.error("✗ Chart generation failed")
        return False


if __name__ == "__main__":
    log.info("Starting triangle pattern detection tests with synthetic data...")

    results = []
    results.append(("Ascending Triangle", test_ascending_triangle()))
    results.append(("Descending Triangle", test_descending_triangle()))
    results.append(("Symmetrical Triangle", test_symmetrical_triangle()))
    results.append(("Multi-Indicator", test_triangle_with_vwap_rsi()))

    # Summary
    log.info("\n=== Test Summary ===")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        log.info(f"{status}: {name}")

    log.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        log.info("✓ All tests passed!")
        sys.exit(0)
    else:
        log.error(f"✗ {total - passed} test(s) failed")
        sys.exit(1)
