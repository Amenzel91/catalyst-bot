"""Generate sample WeBull-style charts to verify Phase 1 implementation.

This script generates sample charts demonstrating the WeBull dark theme
with multi-panel layouts, support/resistance lines, and proper styling.

Run with: python generate_sample_webull_chart.py
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.catalyst_bot import charts
from src.catalyst_bot.indicators.support_resistance import detect_support_resistance


def generate_sample_ohlcv_data(
    start_price: float = 100.0, num_bars: int = 100, volatility: float = 0.02
) -> pd.DataFrame:
    """Generate realistic-looking OHLCV data for testing.

    Parameters
    ----------
    start_price : float
        Starting price
    num_bars : int
        Number of bars to generate
    volatility : float
        Daily volatility (0.02 = 2%)

    Returns
    -------
    pd.DataFrame
        OHLCV DataFrame with DatetimeIndex
    """
    # Generate timestamps (5-minute intervals)
    start_time = datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)
    timestamps = [start_time + timedelta(minutes=5 * i) for i in range(num_bars)]

    # Generate price data with trend
    np.random.seed(42)  # For reproducibility
    returns = np.random.normal(
        0.0001, volatility / np.sqrt(78), num_bars
    )  # 78 5-min bars in a trading day
    close_prices = start_price * np.exp(np.cumsum(returns))

    # Generate OHLC from close
    data = []
    for i, close in enumerate(close_prices):
        # Add some intrabar volatility
        high_factor = 1 + np.random.uniform(0, volatility * 0.5)
        low_factor = 1 - np.random.uniform(0, volatility * 0.5)

        if i == 0:
            open_price = start_price
        else:
            open_price = close_prices[i - 1]

        high = max(open_price, close) * high_factor
        low = min(open_price, close) * low_factor
        volume = np.random.randint(50000, 200000)

        data.append(
            {
                "Open": open_price,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume,
            }
        )

    df = pd.DataFrame(data, index=timestamps)
    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate technical indicators for the chart.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV DataFrame

    Returns
    -------
    pd.DataFrame
        DataFrame with added indicator columns
    """
    # VWAP
    df["vwap"] = (df["Close"] * df["Volume"]).cumsum() / df["Volume"].cumsum()

    # RSI (14-period)
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    # Bollinger Bands (20, 2)
    df["bb_middle"] = df["Close"].rolling(window=20).mean()
    bb_std = df["Close"].rolling(window=20).std()
    df["bb_upper"] = df["bb_middle"] + (bb_std * 2)
    df["bb_lower"] = df["bb_middle"] - (bb_std * 2)

    return df


def main():
    """Generate sample WeBull-style charts."""
    # Set environment variables for WeBull style
    os.environ["CHART_STYLE"] = "webull"
    os.environ["CHART_THEME"] = "dark"
    os.environ["CHART_AXIS_LABEL_SIZE"] = "12"
    os.environ["CHART_TITLE_SIZE"] = "16"
    os.environ["CHART_PANEL_RATIOS"] = "6,1.5,1.25,1.25"

    print("=" * 70)
    print("WeBull Chart Enhancement - Phase 1 Sample Generation")
    print("=" * 70)

    # Check if chart dependencies are available
    if not charts.CHARTS_OK:
        print("\nERROR: matplotlib and/or mplfinance not installed")
        print("Install with: pip install matplotlib mplfinance")
        return

    # Create output directory
    output_dir = Path("out/charts/webull_samples")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {output_dir.absolute()}")

    # Generate sample data
    print("\nGenerating sample OHLCV data...")
    df = generate_sample_ohlcv_data(start_price=150.0, num_bars=100, volatility=0.03)

    # Calculate indicators
    print("Calculating technical indicators (VWAP, RSI, MACD, Bollinger Bands)...")
    df = calculate_indicators(df)

    # Detect support/resistance levels
    print("Detecting support/resistance levels...")
    close_prices = df["Close"].tolist()
    volumes = df["Volume"].tolist()
    support_levels, resistance_levels = detect_support_resistance(
        close_prices, volumes, sensitivity=0.02, min_touches=2, max_levels=3
    )

    print(f"  Found {len(support_levels)} support levels")
    print(f"  Found {len(resistance_levels)} resistance levels")

    # Generate charts with different configurations
    charts_to_generate = [
        {
            "name": "basic",
            "ticker": "SAMPLE",
            "indicators": [],
            "sr": False,
            "description": "Basic candlestick chart with volume",
        },
        {
            "name": "with_vwap",
            "ticker": "SAMPLE",
            "indicators": ["vwap"],
            "sr": False,
            "description": "Chart with VWAP indicator",
        },
        {
            "name": "with_rsi",
            "ticker": "SAMPLE",
            "indicators": ["vwap", "rsi"],
            "sr": False,
            "description": "Chart with VWAP and RSI panels",
        },
        {
            "name": "full_indicators",
            "ticker": "SAMPLE",
            "indicators": ["vwap", "rsi", "macd", "bollinger"],
            "sr": False,
            "description": "Full multi-panel chart with all indicators",
        },
        {
            "name": "with_sr_lines",
            "ticker": "SAMPLE",
            "indicators": ["vwap", "rsi", "macd"],
            "sr": True,
            "description": "Chart with support/resistance lines",
        },
    ]

    print(f"\nGenerating {len(charts_to_generate)} sample charts...")
    print("-" * 70)

    for i, config in enumerate(charts_to_generate, 1):
        print(f"\n[{i}/{len(charts_to_generate)}] {config['description']}")
        print(f"  Indicators: {config['indicators'] or 'None'}")
        print(f"  S/R Lines: {'Yes' if config['sr'] else 'No'}")

        # Prepare parameters
        support = support_levels if config["sr"] else []
        resistance = resistance_levels if config["sr"] else []

        # Generate chart
        output_path = charts.render_chart_with_panels(
            ticker=config["ticker"],
            df=df,
            indicators=config["indicators"],
            support_levels=support,
            resistance_levels=resistance,
            out_dir=output_dir,
        )

        if output_path:
            # Rename to descriptive name
            new_path = output_dir / f"webull_{config['name']}.png"
            if output_path.exists():
                output_path.rename(new_path)
                print(f"  Saved: {new_path.name}")
                print(f"  Size: {new_path.stat().st_size / 1024:.1f} KB")
        else:
            print("  FAILED: Could not generate chart")

    # Print summary
    print("\n" + "=" * 70)
    print("GENERATION COMPLETE")
    print("=" * 70)
    print(f"\nGenerated charts saved to: {output_dir.absolute()}")
    print("\nVerification Checklist:")
    print("  [ ] Background color is #1b1f24 (dark)")
    print("  [ ] Up candles are #3dc985 (green)")
    print("  [ ] Down candles are #ef4f60 (red)")
    print("  [ ] Grid lines are #2c2e31 (subtle)")
    print("  [ ] Text is 12pt (readable on mobile)")
    print("  [ ] Titles are 16pt (bold)")
    print("  [ ] Volume panel shows below price")
    print("  [ ] RSI panel shows 0-100 range")
    print("  [ ] MACD panel shows below RSI")
    print("  [ ] Support lines are green (#4CAF50)")
    print("  [ ] Resistance lines are red (#F44336)")
    print("\nOpen the PNG files to visually verify WeBull styling!")


if __name__ == "__main__":
    main()
