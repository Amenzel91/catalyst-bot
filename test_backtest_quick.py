"""
Quick Backtest Validation Script
=================================

Tests the backtesting system with quick validation:
1. Single ticker backtest
2. Monte Carlo parameter sweep
3. Slippage calculation validation
4. Volume-weighted fills
5. Analytics metrics verification
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.backtesting.analytics import (  # noqa: E402
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
)
from catalyst_bot.backtesting.engine import BacktestEngine  # noqa: E402
from catalyst_bot.backtesting.monte_carlo import MonteCarloSimulator  # noqa: E402
from catalyst_bot.backtesting.trade_simulator import (  # noqa: E402
    PennyStockTradeSimulator,
)
from catalyst_bot.logging_utils import get_logger  # noqa: E402

log = get_logger("test_backtest")


def test_single_ticker_backtest():
    """Test backtesting a single ticker."""
    print("\n" + "=" * 60)
    print("TEST 1: Single Ticker Backtest")
    print("=" * 60)

    # Use last 30 days
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=30)

    ticker = "AAPL"  # Use a liquid stock for testing

    print(f"\nBacktesting {ticker}")
    print(f"Period: {start_date.date()} to {end_date.date()}")

    engine = BacktestEngine(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=10000.0,
        strategy_params={
            "min_score": 0.25,
            "take_profit_pct": 0.20,
            "stop_loss_pct": 0.10,
            "max_hold_hours": 24,
            "position_size_pct": 0.10,
        },
    )

    try:
        results = engine.run_backtest()
        metrics = results["metrics"]

        print("\n[*] Backtest Results:")
        print(f"  Total Return: {metrics['total_return_pct']:+.2f}%")
        print(f"  Win Rate: {metrics['win_rate']:.1f}%")
        print(f"  Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
        print(f"  Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
        print(f"  Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        print(f"  Total Trades: {metrics['total_trades']}")

        # Verify metrics
        assert "total_return_pct" in metrics, "Missing total_return_pct"
        assert "win_rate" in metrics, "Missing win_rate"
        assert "sharpe_ratio" in metrics, "Missing sharpe_ratio"
        assert "total_trades" in metrics, "Missing total_trades"

        print("\n[PASS] Single ticker backtest PASSED")
        return True

    except Exception as e:
        print(f"\n[FAIL] Single ticker backtest FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_monte_carlo_parameter_sweep():
    """Test Monte Carlo parameter sweep."""
    print("\n" + "=" * 60)
    print("TEST 2: Monte Carlo Parameter Sweep")
    print("=" * 60)

    # Use shorter period for speed
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=14)

    print("\nTesting MIN_SCORE parameter")
    print(f"Period: {start_date.date()} to {end_date.date()}")

    simulator = MonteCarloSimulator(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=10000.0,
        base_strategy_params={"take_profit_pct": 0.20, "stop_loss_pct": 0.10},
    )

    try:
        # Test different min_score values
        test_values = [0.20, 0.25, 0.30]

        print(f"\nTesting values: {test_values}")
        print("Running 3 simulations per value...\n")

        sweep_results = simulator.run_parameter_sweep(
            parameter="min_score",
            values=test_values,
            num_simulations=3,  # Small number for quick test
            randomize=False,  # Disable for deterministic test
        )

        print(" Parameter Sweep Results:")
        for result in sweep_results["results"]:
            print(f"\n  min_score = {result['value']}")
            print(f"    Avg Sharpe: {result['avg_sharpe']:.2f}")
            print(f"    Avg Return: {result['avg_return_pct']:.2f}%")
            print(f"    Avg Win Rate: {result['avg_win_rate']:.1%}")
            print(f"    Std Dev: {result['std_dev_return']:.2f}")

        print(f"\n  Optimal Value: {sweep_results['optimal_value']}")
        print(f"  Confidence: {sweep_results['confidence']:.2f}")

        # Verify structure
        assert "parameter" in sweep_results, "Missing parameter"
        assert "results" in sweep_results, "Missing results"
        assert "optimal_value" in sweep_results, "Missing optimal_value"

        print("\n Monte Carlo parameter sweep PASSED")
        return True

    except Exception as e:
        print(f"\n Monte Carlo parameter sweep FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_slippage_calculation():
    """Test slippage calculation with different volumes."""
    print("\n" + "=" * 60)
    print("TEST 3: Slippage Calculation")
    print("=" * 60)

    simulator = PennyStockTradeSimulator(
        initial_capital=10000.0,
        slippage_model="adaptive",
    )

    test_cases = [
        # (ticker, price, volume, shares, direction, expected_slippage_range)
        ("AAPL", 150.0, 1000000, 100, "buy", (0.01, 0.05)),  # Low slippage
        ("PENNY", 0.50, 50000, 1000, "buy", (0.05, 0.15)),  # High slippage
        ("MID", 2.50, 200000, 500, "sell", (0.02, 0.08)),  # Medium slippage
    ]

    print("\n Slippage Test Cases:\n")

    all_passed = True

    for ticker, price, volume, shares, direction, (min_slip, max_slip) in test_cases:
        try:
            fill_price = simulator.calculate_slippage(
                ticker=ticker,
                price=price,
                volume=volume,
                order_size=shares,
                direction=direction,
                volatility_pct=10.0,
            )

            slippage_pct = abs((fill_price - price) / price)

            print(f"  {ticker} ({direction}):")
            print(f"    Quote: ${price:.2f}, Fill: ${fill_price:.2f}")
            print(f"    Slippage: {slippage_pct:.2%}")
            print(f"    Volume: {volume:,}, Order: {shares}")

            # Verify slippage is within expected range
            if not (min_slip <= slippage_pct <= max_slip):
                print(
                    f"     Warning: Slippage {slippage_pct:.2%} "
                    f"outside expected range [{min_slip:.2%}, {max_slip:.2%}]"
                )

            # Verify direction is correct
            if direction == "buy":
                assert (
                    fill_price >= price
                ), f"Buy slippage should increase price: {fill_price} < {price}"
            else:
                assert (
                    fill_price <= price
                ), f"Sell slippage should decrease price: {fill_price} > {price}"

            print("     Passed")

        except Exception as e:
            print(f"     Failed: {e}")
            all_passed = False

    if all_passed:
        print("\n Slippage calculation PASSED")
    else:
        print("\n Slippage calculation FAILED")

    return all_passed


def test_volume_weighted_fills():
    """Test volume-weighted fill execution."""
    print("\n" + "=" * 60)
    print("TEST 4: Volume-Weighted Fills")
    print("=" * 60)

    simulator = PennyStockTradeSimulator(
        initial_capital=10000.0,
        position_size_pct=0.10,
        max_daily_volume_pct=0.05,
    )

    test_cases = [
        # (ticker, price, volume, expected_execution)
        ("LIQUID", 100.0, 10000000, True),  # High volume, should execute
        ("THIN", 1.0, 5000, False),  # Too low volume, should reject
        ("MEDIUM", 5.0, 500000, True),  # Medium volume, should execute
    ]

    print("\n Volume Constraint Tests:\n")

    all_passed = True

    for ticker, price, volume, should_execute in test_cases:
        try:
            result = simulator.execute_trade(
                ticker=ticker,
                action="buy",
                price=price,
                volume=volume,
                timestamp=int(datetime.now(timezone.utc).timestamp()),
                available_capital=10000.0,
            )

            print(f"  {ticker}:")
            print(f"    Price: ${price:.2f}, Volume: {volume:,}")
            print(f"    Executed: {result.executed}")
            print(f"    Shares: {result.shares}")

            if result.executed:
                volume_pct = (result.shares / volume) * 100 if volume > 0 else 0
                print(f"    % of Volume: {volume_pct:.2f}%")
                print(f"    Reason: {result.reason}")

                # Verify we didn't exceed max volume %
                assert (
                    volume_pct <= 5.1
                ), f"Exceeded max volume: {volume_pct}% > 5%"  # Allow small tolerance
            else:
                print(f"    Reason: {result.reason}")

            # Verify execution matches expected
            assert (
                result.executed == should_execute
            ), f"Expected executed={should_execute}, got {result.executed}"

            print("     Passed")

        except Exception as e:
            print(f"     Failed: {e}")
            all_passed = False

    if all_passed:
        print("\n Volume-weighted fills PASSED")
    else:
        print("\n Volume-weighted fills FAILED")

    return all_passed


def test_analytics_metrics():
    """Test analytics metrics calculations."""
    print("\n" + "=" * 60)
    print("TEST 5: Analytics Metrics")
    print("=" * 60)

    # Create sample returns data
    returns = [0.05, -0.02, 0.08, -0.03, 0.10, -0.05, 0.06, -0.01, 0.07, -0.04]

    print("\nTest data (returns):", returns)

    try:
        # Test Sharpe ratio
        sharpe = calculate_sharpe_ratio(
            returns, risk_free_rate=0.02, periods_per_year=252
        )
        print(f"\n Sharpe Ratio: {sharpe:.2f}")
        assert isinstance(sharpe, float), "Sharpe ratio should be float"
        assert sharpe != 0, "Sharpe ratio should not be zero for non-empty returns"

        # Test Sortino ratio
        sortino = calculate_sortino_ratio(
            returns, risk_free_rate=0.02, periods_per_year=252
        )
        print(f" Sortino Ratio: {sortino:.2f}")
        assert isinstance(sortino, float), "Sortino ratio should be float"

        # Test max drawdown
        equity_curve = []
        value = 10000.0
        timestamp = int(datetime.now(timezone.utc).timestamp())

        for ret in returns:
            value *= 1 + ret
            equity_curve.append((timestamp, value))
            timestamp += 3600  # 1 hour increments

        drawdown_info = calculate_max_drawdown(equity_curve)
        print(f"\n Max Drawdown: {drawdown_info['max_drawdown_pct']:.2f}%")
        print(f"   Peak: ${drawdown_info['peak_value']:.2f}")
        print(f"   Trough: ${drawdown_info['trough_value']:.2f}")

        assert "max_drawdown_pct" in drawdown_info, "Missing max_drawdown_pct"
        assert drawdown_info["max_drawdown_pct"] >= 0, "Drawdown should be non-negative"

        # Test profit factor
        trades = [
            {"profit": 100},
            {"profit": -50},
            {"profit": 80},
            {"profit": -30},
            {"profit": 120},
        ]

        pf = calculate_profit_factor(trades)
        print(f"\n Profit Factor: {pf:.2f}")
        assert isinstance(pf, float), "Profit factor should be float"
        assert pf > 0, "Profit factor should be positive for mixed trades"

        print("\n Analytics metrics PASSED")
        return True

    except Exception as e:
        print(f"\n Analytics metrics FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all backtest tests."""
    print("\n" + "=" * 60)
    print("BACKTEST QUICK VALIDATION")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Single Ticker Backtest", test_single_ticker_backtest()))
    results.append(("Monte Carlo Parameter Sweep", test_monte_carlo_parameter_sweep()))
    results.append(("Slippage Calculation", test_slippage_calculation()))
    results.append(("Volume-Weighted Fills", test_volume_weighted_fills()))
    results.append(("Analytics Metrics", test_analytics_metrics()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = " PASS" if result else " FAIL"
        print(f"  {status}: {test_name}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n All tests PASSED")
        return 0
    else:
        print(f"\n {total - passed} test(s) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
