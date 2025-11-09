"""
Test script to verify Fibonacci integration into chart rendering.
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

def test_fibonacci_imports():
    """Test that Fibonacci module can be imported."""
    print("Testing Fibonacci imports...")
    try:
        from catalyst_bot.indicators.fibonacci import (
            calculate_fibonacci_levels,
            find_swing_points,
        )
        print("✓ Fibonacci imports successful")
        return True
    except Exception as e:
        print(f"✗ Fibonacci import failed: {e}")
        return False


def test_fibonacci_calculation():
    """Test that Fibonacci calculations work correctly."""
    print("\nTesting Fibonacci calculations...")
    try:
        from catalyst_bot.indicators.fibonacci import (
            calculate_fibonacci_levels,
            find_swing_points,
        )

        # Test with sample price data
        prices = [100, 105, 110, 115, 120, 125, 130, 125, 120, 115, 110, 105, 100]

        # Find swing points
        swing_high, swing_low, h_idx, l_idx = find_swing_points(prices, lookback=13, min_bars=2)

        if swing_high and swing_low:
            print(f"  Swing High: {swing_high} at index {h_idx}")
            print(f"  Swing Low: {swing_low} at index {l_idx}")

            # Calculate Fibonacci levels
            fib_levels = calculate_fibonacci_levels(swing_high, swing_low)

            print(f"  Fibonacci Levels ({len(fib_levels)} total):")
            for level_name, price in sorted(fib_levels.items(), key=lambda x: x[1], reverse=True):
                print(f"    {level_name}: ${price:.2f}")

            # Verify we have 7 standard levels
            if len(fib_levels) == 7:
                print("✓ Fibonacci calculation successful (7 levels)")
                return True
            else:
                print(f"✗ Expected 7 levels, got {len(fib_levels)}")
                return False
        else:
            print("✗ Failed to find swing points")
            return False

    except Exception as e:
        print(f"✗ Fibonacci calculation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_charts_integration():
    """Test that charts.py has the Fibonacci integration."""
    print("\nTesting charts.py integration...")
    try:
        from catalyst_bot import charts

        # Check if INDICATOR_COLORS has fibonacci
        if "fibonacci" in charts.INDICATOR_COLORS:
            color = charts.INDICATOR_COLORS["fibonacci"]
            print(f"✓ Fibonacci color configured: {color}")
        else:
            print("✗ Fibonacci color not found in INDICATOR_COLORS")
            return False

        # Check if render_chart_with_panels has fib_levels parameter
        import inspect
        sig = inspect.signature(charts.render_chart_with_panels)
        if "fib_levels" in sig.parameters:
            print("✓ render_chart_with_panels accepts fib_levels parameter")
        else:
            print("✗ render_chart_with_panels missing fib_levels parameter")
            return False

        # Check if render_multipanel_chart exists
        if hasattr(charts, "render_multipanel_chart"):
            print("✓ render_multipanel_chart function exists")
        else:
            print("✗ render_multipanel_chart function not found")
            return False

        print("✓ Charts integration successful")
        return True

    except Exception as e:
        print(f"✗ Charts integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Fibonacci Integration Test Suite")
    print("=" * 60)

    results = []
    results.append(("Fibonacci Imports", test_fibonacci_imports()))
    results.append(("Fibonacci Calculation", test_fibonacci_calculation()))
    results.append(("Charts Integration", test_charts_integration()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(result[1] for result in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
        print("\nFibonacci integration is ready for use!")
        print("Usage: Add 'fibonacci' or 'fib' to indicators list")
        print("Example: render_multipanel_chart('AAPL', indicators=['vwap', 'rsi', 'fibonacci'])")
    else:
        print("✗ SOME TESTS FAILED")
        print("\nPlease review the errors above.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
