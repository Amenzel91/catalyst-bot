"""
Simple test to verify triangle pattern detection works.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_bot.indicators.patterns import detect_triangles
import numpy as np

print("=== Testing Triangle Pattern Detection ===\n")

# Test 1: Ascending Triangle (flat resistance, rising support)
print("Test 1: Ascending Triangle")
prices = []
highs = []
lows = []

for i in range(30):
    # Flat resistance at 110
    resistance = 110
    # Rising support from 95 to 105
    support = 95 + (i / 30) * 10

    # Price oscillates between support and resistance
    mid = (support + resistance) / 2
    price = mid + (np.random.rand() - 0.5) * 5

    prices.append(price)
    highs.append(min(price + abs(np.random.randn() * 1.5), resistance))
    lows.append(max(price - abs(np.random.randn() * 1.5), support))

patterns = detect_triangles(prices, highs, lows, min_touches=3, lookback=30)
print(f"  Detected: {len(patterns)} pattern(s)")
for p in patterns:
    print(f"    - Type: {p['type']}")
    print(f"      Confidence: {p['confidence']:.1%}")
    print(f"      Description: {p['description']}")

# Test 2: Descending Triangle (falling resistance, flat support)
print("\nTest 2: Descending Triangle")
prices = []
highs = []
lows = []

for i in range(30):
    # Flat support at 90
    support = 90
    # Falling resistance from 110 to 95
    resistance = 110 - (i / 30) * 15

    # Price oscillates between support and resistance
    mid = (support + resistance) / 2
    price = mid + (np.random.rand() - 0.5) * 5

    prices.append(price)
    highs.append(min(price + abs(np.random.randn() * 1.5), resistance))
    lows.append(max(price - abs(np.random.randn() * 1.5), support))

patterns = detect_triangles(prices, highs, lows, min_touches=3, lookback=30)
print(f"  Detected: {len(patterns)} pattern(s)")
for p in patterns:
    print(f"    - Type: {p['type']}")
    print(f"      Confidence: {p['confidence']:.1%}")
    print(f"      Description: {p['description']}")

# Test 3: Symmetrical Triangle (converging lines)
print("\nTest 3: Symmetrical Triangle")
prices = []
highs = []
lows = []

for i in range(30):
    # Falling resistance from 110 to 100
    resistance = 110 - (i / 30) * 10
    # Rising support from 90 to 100
    support = 90 + (i / 30) * 10

    # Price oscillates between support and resistance
    mid = (support + resistance) / 2
    price = mid + (np.random.rand() - 0.5) * 3

    prices.append(price)
    highs.append(min(price + abs(np.random.randn() * 1), resistance))
    lows.append(max(price - abs(np.random.randn() * 1), support))

patterns = detect_triangles(prices, highs, lows, min_touches=3, lookback=30)
print(f"  Detected: {len(patterns)} pattern(s)")
for p in patterns:
    print(f"    - Type: {p['type']}")
    print(f"      Confidence: {p['confidence']:.1%}")
    print(f"      Description: {p['description']}")

print("\n=== Testing Complete ===")
