#!/usr/bin/env python3
"""
Test script demonstrating statistical significance testing in validator.

This script shows how to:
1. Run parameter validation with statistical tests
2. Interpret bootstrap confidence intervals
3. Understand p-values and significance
4. Make data-driven decisions about parameter changes
"""

import json
from src.catalyst_bot.backtesting.validator import (
    validate_parameter_change,
    validate_multiple_parameters,
)


def print_validation_results(result):
    """Pretty print validation results with statistical analysis."""
    print("\n" + "=" * 70)
    print("VALIDATION RESULTS")
    print("=" * 70)

    # Basic recommendation
    print(f"\nParameter: {result.get('param', 'Multiple')}")
    print(f"Old Value: {result.get('old_value', 'N/A')}")
    print(f"New Value: {result.get('new_value', 'N/A')}")
    print(f"\nRecommendation: {result['recommendation']}")
    print(f"Confidence: {result['confidence']:.2%}")
    print(f"Reason: {result['reason']}")

    # Performance metrics
    print("\n" + "-" * 70)
    print("PERFORMANCE COMPARISON")
    print("-" * 70)
    if "old_sharpe" in result:
        print(f"Sharpe Ratio:     {result['old_sharpe']:.2f} -> {result['new_sharpe']:.2f}")
        print(f"Total Return:     {result['old_return_pct']:.2f}% -> {result['new_return_pct']:.2f}%")
        print(f"Win Rate:         {result['old_win_rate']:.1f}% -> {result['new_win_rate']:.1f}%")
        print(f"Max Drawdown:     {result['old_max_drawdown']:.2f}% -> {result['new_max_drawdown']:.2f}%")
        print(f"Total Trades:     {result['old_total_trades']} -> {result['new_total_trades']}")

    # Statistical significance tests
    if "statistical_tests" in result:
        stats = result["statistical_tests"]
        print("\n" + "-" * 70)
        print("STATISTICAL SIGNIFICANCE TESTS")
        print("-" * 70)
        print(f"Sample Size Adequate: {stats['sample_size_adequate']}")

        if stats["warning"]:
            print(f"\nWARNING: {stats['warning']}")

        print(f"\nReturns Difference:")
        print(f"  p-value: {stats['returns_pvalue']:.4f}")
        print(f"  Significant: {stats['returns_significant']} (p < 0.05)")

        print(f"\nWin Rate Difference:")
        print(f"  p-value: {stats['win_rate_pvalue']:.4f}")
        print(f"  Significant: {stats['win_rate_significant']} (p < 0.05)")

        # Interpretation
        print("\nInterpretation:")
        if stats["returns_significant"]:
            print("  - Returns improvement is statistically significant!")
            print("  - Strong evidence the change improves performance")
        else:
            print("  - Returns difference not statistically significant")
            print("  - Could be due to random chance, need more data")

    # Confidence intervals
    if "confidence_intervals" in result:
        ci = result["confidence_intervals"]
        print("\n" + "-" * 70)
        print("95% CONFIDENCE INTERVALS (NEW STRATEGY)")
        print("-" * 70)

        win_rate = ci["win_rate"]
        print(f"\nWin Rate:")
        print(f"  Estimate: {win_rate['estimate']:.1f}%")
        print(f"  95% CI: [{win_rate['ci_lower']:.1f}%, {win_rate['ci_upper']:.1f}%]")
        print(f"  Range: {win_rate['ci_upper'] - win_rate['ci_lower']:.1f}% wide")

        avg_return = ci["avg_return"]
        print(f"\nAverage Return per Trade:")
        print(f"  Estimate: {avg_return['estimate']:.2f}%")
        print(f"  95% CI: [{avg_return['ci_lower']:.2f}%, {avg_return['ci_upper']:.2f}%]")
        if avg_return["ci_lower"] > 0:
            print("  - Lower bound > 0: Strategy likely profitable")
        elif avg_return["ci_upper"] < 0:
            print("  - Upper bound < 0: Strategy likely unprofitable")
        else:
            print("  - CI includes 0: Profitability uncertain")

        sharpe = ci["sharpe_ratio"]
        print(f"\nSharpe Ratio:")
        print(f"  Estimate: {sharpe['estimate']:.2f}")
        print(f"  95% CI: [{sharpe['ci_lower']:.2f}, {sharpe['ci_upper']:.2f}]")
        if sharpe["ci_lower"] > 1.0:
            print("  - Lower bound > 1.0: Strong risk-adjusted returns")
        elif sharpe["ci_lower"] > 0:
            print("  - Lower bound > 0: Positive risk-adjusted returns")

    print("\n" + "=" * 70 + "\n")


def example_single_parameter():
    """Example: Validate single parameter change."""
    print("\n" + "#" * 70)
    print("# EXAMPLE 1: Single Parameter Validation")
    print("#" * 70)
    print("\nTesting: take_profit_pct change from 0.15 to 0.20")
    print("This will compare 15% vs 20% take-profit thresholds")

    result = validate_parameter_change(
        param="take_profit_pct",
        old_value=0.15,
        new_value=0.20,
        backtest_days=60,  # 60 days for better sample size
        initial_capital=10000.0,
    )

    print_validation_results(result)


def example_multiple_parameters():
    """Example: Validate multiple parameter changes together."""
    print("\n" + "#" * 70)
    print("# EXAMPLE 2: Multiple Parameter Validation")
    print("#" * 70)
    print("\nTesting combined changes:")
    print("  - min_score: 0.25 -> 0.30 (stricter filtering)")
    print("  - take_profit_pct: 0.20 -> 0.25 (higher profit target)")

    changes = {
        "min_score": (0.25, 0.30),
        "take_profit_pct": (0.20, 0.25),
    }

    result = validate_multiple_parameters(
        changes=changes, backtest_days=60, initial_capital=10000.0
    )

    print_validation_results(result)


def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("STATISTICAL VALIDATION TESTING EXAMPLES")
    print("=" * 70)
    print("\nThis script demonstrates the new statistical significance testing")
    print("capabilities in the validator module.")
    print("\nNOTE: These examples require historical data in data/events.jsonl")
    print("=" * 70)

    try:
        # Example 1: Single parameter
        example_single_parameter()

        # Example 2: Multiple parameters
        example_multiple_parameters()

        print("\n" + "=" * 70)
        print("KEY TAKEAWAYS")
        print("=" * 70)
        print("""
1. CONFIDENCE INTERVALS tell you the range where true values likely lie
   - Narrower = more certain about the estimate
   - If CI for returns includes 0, profitability is uncertain

2. P-VALUES test if differences are statistically significant
   - p < 0.05: Significant difference (95% confidence)
   - p >= 0.05: Cannot conclude there's a real difference

3. SAMPLE SIZE matters for reliable conclusions
   - Need >= 30 trades for valid statistical tests
   - More data = more statistical power

4. DECISION MAKING uses both performance AND statistics
   - Strong improvements: Approved even without significance
   - Moderate improvements: Require statistical significance
   - Degradations: Higher confidence if statistically significant
        """)

    except FileNotFoundError:
        print("\nERROR: data/events.jsonl not found!")
        print("Please ensure you have historical event data to run backtests.")
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
