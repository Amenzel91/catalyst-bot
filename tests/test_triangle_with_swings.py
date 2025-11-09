"""
Test triangle pattern detection with clear swing points.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_bot.indicators.patterns import detect_triangles
import numpy as np

print("=== Testing Triangle Pattern Detection with Swing Points ===\n")

# Test 1: Ascending Triangle with clear swing highs and lows
print("Test 1: Ascending Triangle with Swing Points")
prices = []
highs = []
lows = []

# Create alternating swings that form ascending triangle
# Swing highs should be roughly flat around 110
# Swing lows should be rising from 95 to 105

swing_high_prices = [110, 109.5, 110.5, 110, 109.8, 110.2]  # Flat resistance
swing_low_prices = [95, 97, 99, 101, 103, 105]  # Rising support

for i in range(len(swing_high_prices)):
    # Add swing high
    prices.append(swing_high_prices[i])
    highs.append(swing_high_prices[i] + 0.5)
    lows.append(swing_high_prices[i] - 0.5)

    # Add swing low
    if i < len(swing_low_prices):
        prices.append(swing_low_prices[i])
        highs.append(swing_low_prices[i] + 0.5)
        lows.append(swing_low_prices[i] - 0.5)

    # Add a few bars in between for smoothness
    for j in range(2):
        mid = (swing_high_prices[i] + swing_low_prices[i]) / 2
        p = mid + (np.random.rand() - 0.5) * 3
        prices.append(p)
        highs.append(p + 1)
        lows.append(p - 1)

patterns = detect_triangles(prices, highs, lows, min_touches=3, lookback=50)
print(f"  Detected: {len(patterns)} pattern(s)")
for p in patterns:
    print(f"    - Type: {p['type']}")
    print(f"      Confidence: {p['confidence']:.1%}")
    print(f"      Description: {p['description']}")
    print(f"      Start/End: {p['start_idx']} to {p['end_idx']}")

# Test 2: Descending Triangle with swing points
print("\nTest 2: Descending Triangle with Swing Points")
prices = []
highs = []
lows = []

swing_high_prices = [110, 107, 104, 101, 98, 95]  # Falling resistance
swing_low_prices = [90, 90.5, 90, 89.8, 90.2, 90]  # Flat support

for i in range(len(swing_high_prices)):
    # Add swing high
    prices.append(swing_high_prices[i])
    highs.append(swing_high_prices[i] + 0.5)
    lows.append(swing_high_prices[i] - 0.5)

    # Add swing low
    if i < len(swing_low_prices):
        prices.append(swing_low_prices[i])
        highs.append(swing_low_prices[i] + 0.5)
        lows.append(swing_low_prices[i] - 0.5)

    # Add a few bars in between
    for j in range(2):
        mid = (swing_high_prices[i] + swing_low_prices[i]) / 2
        p = mid + (np.random.rand() - 0.5) * 3
        prices.append(p)
        highs.append(p + 1)
        lows.append(p - 1)

patterns = detect_triangles(prices, highs, lows, min_touches=3, lookback=50)
print(f"  Detected: {len(patterns)} pattern(s)")
for p in patterns:
    print(f"    - Type: {p['type']}")
    print(f"      Confidence: {p['confidence']:.1%}")
    print(f"      Description: {p['description']}")
    print(f"      Start/End: {p['start_idx']} to {p['end_idx']}")

# Test 3: Symmetrical Triangle with swing points
print("\nTest 3: Symmetrical Triangle with Swing Points")
prices = []
highs = []
lows = []

swing_high_prices = [110, 108, 106, 104, 102, 100]  # Falling resistance
swing_low_prices = [90, 92, 94, 96, 98, 100]  # Rising support

for i in range(len(swing_high_prices)):
    # Add swing high
    prices.append(swing_high_prices[i])
    highs.append(swing_high_prices[i] + 0.5)
    lows.append(swing_high_prices[i] - 0.5)

    # Add swing low
    if i < len(swing_low_prices):
        prices.append(swing_low_prices[i])
        highs.append(swing_low_prices[i] + 0.5)
        lows.append(swing_low_prices[i] - 0.5)

    # Add a few bars in between
    for j in range(2):
        mid = (swing_high_prices[i] + swing_low_prices[i]) / 2
        p = mid + (np.random.rand() - 0.5) * 2
        prices.append(p)
        highs.append(p + 1)
        lows.append(p - 1)

patterns = detect_triangles(prices, highs, lows, min_touches=3, lookback=50)
print(f"  Detected: {len(patterns)} pattern(s)")
for p in patterns:
    print(f"    - Type: {p['type']}")
    print(f"      Confidence: {p['confidence']:.1%}")
    print(f"      Description: {p['description']}")
    print(f"      Start/End: {p['start_idx']} to {p['end_idx']}")

print("\n=== Testing Complete ===")
