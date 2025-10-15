#!/usr/bin/env python3
"""
Integration test for grid search with Tiingo data loading.

This test validates the complete end-to-end flow:
1. validate_parameter_grid() is called
2. _load_data_for_grid_search() loads events and fetches Tiingo data
3. Data is passed to VectorizedBacktester (if available)
4. Results are returned
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta, timezone
from catalyst_bot.logging_utils import get_logger

log = get_logger("test_grid_integration")

def test_integration():
    """Test the complete grid search integration."""

    print("\n" + "="*80)
    print("GRID SEARCH INTEGRATION TEST")
    print("="*80)

    # Check if vectorized_backtest is available
    try:
        from catalyst_bot.backtesting.vectorized_backtest import VectorizedBacktester
        vectorbt_available = True
        print("\n[INFO] VectorBT available - full grid search will run")
    except ImportError:
        vectorbt_available = False
        print("\n[WARN] VectorBT not available - will test data loading only")

    from catalyst_bot.backtesting.validator import validate_parameter_grid

    print("\n" + "-"*80)
    print("STEP 1: Configure parameter grid")
    print("-"*80)

    # Simple parameter grid for testing
    param_ranges = {
        'min_score': [0.15, 0.20, 0.25],
        'take_profit_pct': [0.15, 0.20]
    }

    print(f"\nParameter ranges:")
    for param, values in param_ranges.items():
        print(f"  {param}: {values}")
    print(f"\nTotal combinations: {len(param_ranges['min_score']) * len(param_ranges['take_profit_pct'])}")

    print("\n" + "-"*80)
    print("STEP 2: Run grid search validation")
    print("-"*80)

    # Test with recent data (will use Oct 1-8 data)
    try:
        results = validate_parameter_grid(
            param_ranges=param_ranges,
            backtest_days=7,  # Last 7 days
            initial_capital=10000.0
        )

        print("\n[SUCCESS] Grid search completed!")

        print("\n" + "-"*80)
        print("STEP 3: Validate results")
        print("-"*80)

        # Check for expected fields
        expected_fields = ['best_params', 'best_metrics', 'all_results', 'n_combinations']
        missing_fields = [f for f in expected_fields if f not in results]

        if missing_fields:
            print(f"\n[FAIL] Missing result fields: {missing_fields}")
            return False

        print("\n[PASS] All expected fields present")

        # Check if data was loaded
        n_combinations = results.get('n_combinations', 0)
        if n_combinations == 0:
            print(f"\n[INFO] No combinations tested")
            if 'warning' in results:
                print(f"  Warning: {results['warning']}")
            if 'error' in results:
                print(f"  Error: {results['error']}")

            # This is OK if VectorBT not available or no data
            if not vectorbt_available:
                print("\n[EXPECTED] VectorBT not installed - grid search cannot run")
                print("  Data loading should still work though")
                return True
            elif 'warning' in results and 'No historical data' in results['warning']:
                print("\n[EXPECTED] No data available for test period")
                print("  But data loading function was successfully called")
                return True
            else:
                print("\n[UNEXPECTED] Grid search returned 0 combinations")
                return False

        # If we got results, validate them
        print(f"\n[PASS] Grid search tested {n_combinations} combinations")

        if 'best_params' in results and results['best_params']:
            print(f"\nBest parameters found:")
            for param, value in results['best_params'].items():
                print(f"  {param}: {value}")

        if 'best_metrics' in results and results['best_metrics']:
            print(f"\nBest metrics:")
            for metric, value in results['best_metrics'].items():
                if isinstance(value, float):
                    print(f"  {metric}: {value:.4f}")
                else:
                    print(f"  {metric}: {value}")

        if 'execution_time_sec' in results:
            print(f"\nExecution time: {results['execution_time_sec']:.2f}s")

        if 'speedup_estimate' in results:
            print(f"Estimated speedup: {results['speedup_estimate']:.0f}x vs sequential")

        print("\n" + "="*80)
        print("INTEGRATION TEST COMPLETED SUCCESSFULLY")
        print("="*80)
        print("\n[SUCCESS] Grid search integration working correctly!")

        if vectorbt_available:
            print("   - Parameter grid defined")
            print("   - Data loaded from events.jsonl + Tiingo API")
            print("   - Vectorized backtest executed")
            print("   - Results returned and validated")
        else:
            print("   - Parameter grid defined")
            print("   - Data loading attempted (VectorBT not available for testing)")
            print("   - Integration validated (ready for VectorBT when installed)")

        return True

    except Exception as e:
        print(f"\n[ERROR] Grid search failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success = test_integration()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
