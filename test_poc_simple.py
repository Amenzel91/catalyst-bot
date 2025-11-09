"""
Simple POC/VAH/VAL test with debug logging.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["CHART_VOLUME_PROFILE_SHOW_POC"] = "1"

import pandas as pd
import numpy as np
from catalyst_bot.charts import render_chart_with_panels
from catalyst_bot.logging_utils import get_logger

log = get_logger("test_poc")

# Create synthetic data
dates = pd.date_range(start='2024-01-01 09:30', periods=100, freq='5min')
prices = 150 + np.sin(np.linspace(0, 4*np.pi, 100)) * 5
volumes = 1000000 + (1 - (np.abs(prices - 150) / 5)) * 5000000
volumes = np.maximum(volumes, 100000)

df = pd.DataFrame({
    'Open': (prices + np.random.randn(100) * 0.5).astype(np.float64),
    'High': (prices + np.random.randn(100) * 0.5 + 1).astype(np.float64),
    'Low': (prices + np.random.randn(100) * 0.5 - 1).astype(np.float64),
    'Close': prices.astype(np.float64),
    'Volume': volumes.astype(np.float64)
}, index=dates)

df['High'] = df[['Open', 'High', 'Low', 'Close']].max(axis=1).astype(np.float64)
df['Low'] = df[['Open', 'High', 'Low', 'Close']].min(axis=1).astype(np.float64)

print(f"Data shape: {df.shape}")
print(f"Volume sum: {df['Volume'].sum():.0f}")
print(f"Price range: [{df['Close'].min():.2f}, {df['Close'].max():.2f}]")

# Generate chart
print("\nGenerating chart with indicators: ['volume_profile', 'vwap']")
chart_path = render_chart_with_panels(
    ticker="TEST",
    df=df,
    indicators=['volume_profile', 'vwap'],
    out_dir="out/test_charts"
)

if chart_path:
    print(f"\nChart generated: {chart_path}")
    print("Check logs above for 'volume_profile_lines_added' message")
else:
    print("\nChart generation failed")
