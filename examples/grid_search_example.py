"""
Example: Parameter Grid Search Optimization
============================================

Demonstrates how to use validate_parameter_grid() to quickly optimize
multiple parameters simultaneously using vectorized backtesting.

This provides 30-60x speedup compared to testing parameters sequentially.
"""

from catalyst_bot.backtesting.validator import validate_parameter_grid


def basic_grid_search():
    """
    Example 1: Basic grid search over two parameters
    """
    print("=" * 70)
    print("Example 1: Basic Grid Search - Entry Thresholds")
    print("=" * 70)

    results = validate_parameter_grid(
        param_ranges={
            'min_score': [0.20, 0.25, 0.30, 0.35],
            'min_sentiment': [0.0, 0.1, 0.2]
        },
        backtest_days=30,
        initial_capital=10000.0
    )

    print(f"\nResults:")
    print(f"  Tested {results['n_combinations']} combinations")
    print(f"  Execution time: {results['execution_time_sec']:.2f} seconds")
    print(f"  Speedup: ~{results['speedup_estimate']:.0f}x")
    print(f"\nBest Parameters:")
    for param, value in results['best_params'].items():
        print(f"  {param}: {value}")

    print(f"\nBest Metrics:")
    best_metrics = results['best_metrics']
    print(f"  Sharpe Ratio: {best_metrics.get('sharpe_ratio', 0):.2f}")
    print(f"  Sortino Ratio: {best_metrics.get('sortino_ratio', 0):.2f}")
    print(f"  Total Return: {best_metrics.get('total_return', 0):.2%}")
    print(f"  Total Trades: {best_metrics.get('total_trades', 0)}")
    print(f"  Win Rate: {best_metrics.get('win_rate', 0):.1%}")

    return results


def exit_strategy_optimization():
    """
    Example 2: Optimize exit strategy parameters
    """
    print("\n" + "=" * 70)
    print("Example 2: Exit Strategy Optimization")
    print("=" * 70)

    results = validate_parameter_grid(
        param_ranges={
            'take_profit_pct': [0.10, 0.15, 0.20, 0.25],
            'stop_loss_pct': [0.05, 0.08, 0.10, 0.12]
        },
        backtest_days=60
    )

    print(f"\nResults:")
    print(f"  Tested {results['n_combinations']} combinations")
    print(f"  Execution time: {results['execution_time_sec']:.2f} seconds")

    print(f"\nBest Parameters:")
    for param, value in results['best_params'].items():
        print(f"  {param}: {value:.2f}")

    # Display top 5 combinations
    if results['all_results'] is not None:
        print(f"\nTop 5 Parameter Combinations:")
        print(results['all_results'].head())

    return results


def full_strategy_optimization():
    """
    Example 3: Comprehensive strategy optimization
    """
    print("\n" + "=" * 70)
    print("Example 3: Full Strategy Optimization (Multi-Dimensional)")
    print("=" * 70)

    results = validate_parameter_grid(
        param_ranges={
            'min_score': [0.20, 0.25, 0.30],
            'take_profit_pct': [0.15, 0.20, 0.25],
            'stop_loss_pct': [0.08, 0.10, 0.12],
            'max_hold_hours': [12, 18, 24, 36]
        },
        backtest_days=45
    )

    n_combinations = results['n_combinations']
    exec_time = results['execution_time_sec']

    print(f"\nResults:")
    print(f"  Tested {n_combinations} combinations")
    print(f"  Execution time: {exec_time:.2f} seconds")
    print(f"  Speedup: ~{results['speedup_estimate']:.0f}x")
    print(f"  Average time per combination: {exec_time/n_combinations:.3f}s")

    print(f"\nBest Parameters:")
    for param, value in results['best_params'].items():
        print(f"  {param}: {value}")

    # Performance comparison
    if results['all_results'] is not None:
        df = results['all_results']
        print(f"\nPerformance Distribution:")
        print(f"  Mean Sharpe Ratio: {df['sharpe_ratio'].mean():.2f}")
        print(f"  Std Dev Sharpe Ratio: {df['sharpe_ratio'].std():.2f}")
        print(f"  Min Sharpe Ratio: {df['sharpe_ratio'].min():.2f}")
        print(f"  Max Sharpe Ratio: {df['sharpe_ratio'].max():.2f}")

    return results


def demonstrate_workflow():
    """
    Example 4: Complete workflow - Grid search + statistical validation
    """
    print("\n" + "=" * 70)
    print("Example 4: Complete Workflow (Grid Search → Validation)")
    print("=" * 70)

    # Step 1: Grid search
    print("\n[STEP 1] Running grid search to find optimal parameters...")
    grid_results = validate_parameter_grid(
        param_ranges={
            'min_score': [0.20, 0.25, 0.30, 0.35],
            'take_profit_pct': [0.15, 0.20, 0.25]
        },
        backtest_days=30
    )

    print(f"Grid search complete:")
    print(f"  Best parameters: {grid_results['best_params']}")
    print(f"  Best Sharpe: {grid_results['best_metrics'].get('sharpe_ratio', 0):.2f}")

    # Step 2: Statistical validation
    print("\n[STEP 2] Validating best candidate with statistical testing...")
    print("(This would call validate_parameter_change() with the best parameters)")
    print("Example:")
    print(f"  validate_parameter_change(")
    print(f"      param='min_score',")
    print(f"      old_value=0.25,")
    print(f"      new_value={grid_results['best_params'].get('min_score', 0.25)},")
    print(f"      backtest_days=60")
    print(f"  )")

    print("\n[RESULT] If validation passes with statistical significance:")
    print("  → Deploy new parameters to production")
    print("  → Monitor performance for 7-14 days")
    print("  → Compare real-world results to backtest predictions")


if __name__ == "__main__":
    print("Parameter Grid Search Optimization Examples")
    print("=" * 70)
    print()
    print("These examples demonstrate fast parameter optimization using")
    print("vectorized backtesting (VectorBT) for 30-60x speedup.")
    print()

    # Run examples
    try:
        # Example 1: Basic grid search
        basic_grid_search()

        # Example 2: Exit strategy optimization
        exit_strategy_optimization()

        # Example 3: Full strategy optimization
        full_strategy_optimization()

        # Example 4: Complete workflow
        demonstrate_workflow()

        print("\n" + "=" * 70)
        print("All examples completed successfully!")
        print("=" * 70)

    except ImportError as e:
        print(f"\nError: {e}")
        print("\nNote: VectorBT is required for grid search functionality.")
        print("Install with: pip install vectorbt")
    except Exception as e:
        print(f"\nError running examples: {e}")
        print("\nNote: These examples require historical data in data/events.jsonl")
        print("and proper configuration of data loading functions.")
