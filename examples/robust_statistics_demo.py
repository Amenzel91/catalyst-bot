"""
Robust Statistics Demo for Catalyst-Bot Backtesting
====================================================

This demo shows how to use robust statistics for analyzing penny stock
backtest results with extreme outliers (500%+ gains, -90% losses).

CRITICAL: These methods are essential for valid 2-year backtest analysis.

Run this script:
    python examples/robust_statistics_demo.py
"""

import numpy as np
from scipy import stats as scipy_stats

# Import robust statistics from validator
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from catalyst_bot.backtesting.validator import (
    median_absolute_deviation,
    robust_zscore,
    trimmed_mean,
    winsorize,
)


def demo_problem():
    """Demonstrate the problem: outliers break traditional statistics."""
    print("=" * 80)
    print("PROBLEM: Traditional Statistics Fail with Penny Stock Outliers")
    print("=" * 80)
    print()

    # Simulate 2-year backtest: 500 trades
    np.random.seed(42)
    returns = np.random.normal(0.03, 0.12, 500)  # Typical: 3% mean, 12% std

    # Add realistic penny stock outliers (pump-and-dumps)
    returns[10] = 2.5  # 250% gain
    returns[50] = -0.85  # 85% loss
    returns[150] = 3.1  # 310% gain
    returns[300] = -0.78  # 78% loss
    returns[450] = 4.2  # 420% gain

    # Traditional statistics
    mean = np.mean(returns)
    std = np.std(returns, ddof=1)
    sharpe = (mean / std) * np.sqrt(252)

    print(f"Sample: 500 trades over 2 years")
    print(f"  - 495 typical trades (normally distributed)")
    print(f"  - 5 extreme outliers (250%, 310%, 420%, -85%, -78%)")
    print()
    print("Traditional Statistics (UNRELIABLE):")
    print(f"  Mean Return:      {mean:>8.2%} <- INFLATED by outliers!")
    print(f"  Std Deviation:    {std:>8.2%} <- INFLATED by outliers!")
    print(f"  Sharpe Ratio:     {sharpe:>8.2f} <- MISLEADING!")
    print()

    # What an investor sees: "Wow, 4.57% average return, 2.3 Sharpe!"
    # Reality: Most trades made 3%, a few crazy outliers skewed everything

    return returns


def demo_winsorization(returns):
    """Demonstrate winsorization: clip outliers at percentiles."""
    print("=" * 80)
    print("SOLUTION 1: Winsorization - Clip Extreme Outliers")
    print("=" * 80)
    print()

    # Winsorize at 1st/99th percentile (clip top/bottom 1%)
    winsorized = winsorize(returns, limits=(0.01, 0.01))

    # Compare statistics
    original_mean = np.mean(returns)
    original_std = np.std(returns, ddof=1)

    winsorized_mean = np.mean(winsorized)
    winsorized_std = np.std(winsorized, ddof=1)

    print("Winsorization: Replace values below 1st percentile and above 99th")
    print("percentile with the values at those percentiles.")
    print()
    print("Effect on Statistics:")
    print(f"  Original Mean:     {original_mean:>8.2%}")
    print(f"  Winsorized Mean:   {winsorized_mean:>8.2%}  <- More realistic!")
    print()
    print(f"  Original Std Dev:  {original_std:>8.2%}")
    print(f"  Winsorized Std Dev:{winsorized_std:>8.2%}  <- More stable!")
    print()

    # Calculate Sharpe ratios
    original_sharpe = (original_mean / original_std) * np.sqrt(252)
    winsorized_sharpe = (winsorized_mean / winsorized_std) * np.sqrt(252)

    print(f"  Original Sharpe:   {original_sharpe:>8.2f}")
    print(f"  Winsorized Sharpe: {winsorized_sharpe:>8.2f}  <- More accurate!")
    print()

    print("When to use: Before calculating means, std devs, correlations")
    print("Benefit: Preserves sample size while reducing outlier impact")
    print()


def demo_trimmed_mean(returns):
    """Demonstrate trimmed mean: exclude extreme values."""
    print("=" * 80)
    print("SOLUTION 2: Trimmed Mean - Exclude Extreme Values")
    print("=" * 80)
    print()

    # Calculate trimmed means at different levels
    mean_regular = np.mean(returns)
    mean_5pct = trimmed_mean(returns, proportiontocut=0.05)
    mean_10pct = trimmed_mean(returns, proportiontocut=0.10)
    median = np.median(returns)

    print("Trimmed Mean: Remove top/bottom X% before calculating mean")
    print()
    print("Comparison:")
    print(f"  Regular Mean:     {mean_regular:>8.2%}  <- Skewed by outliers")
    print(f"  Trimmed Mean (5%):{mean_5pct:>8.2%}  <- Remove top/bottom 5%")
    print(f"  Trimmed Mean (10%):{mean_10pct:>8.2%}  <- Remove top/bottom 10%")
    print(f"  Median:           {median:>8.2%}  <- Most robust (50% trim)")
    print()

    print("When to use: Summary statistics, reports, typical performance")
    print("Benefit: Completely ignores outliers, focuses on repeatable results")
    print()


def demo_mad(returns):
    """Demonstrate Median Absolute Deviation: robust std dev."""
    print("=" * 80)
    print("SOLUTION 3: MAD - Robust Alternative to Standard Deviation")
    print("=" * 80)
    print()

    # Calculate std dev and MAD
    std_dev = np.std(returns, ddof=1)
    mad = median_absolute_deviation(returns)

    # For comparison, look at clean data
    clean_returns = returns[(returns > -0.5) & (returns < 0.5)]
    clean_std = np.std(clean_returns, ddof=1)

    print("MAD = Median Absolute Deviation")
    print("Formula: median(|X - median(X)|) * 1.4826")
    print()
    print("Comparison:")
    print(f"  Std Deviation (all data):   {std_dev:>8.2%}  <- Exploded by outliers!")
    print(f"  Std Deviation (clean only): {clean_std:>8.2%}  <- What it should be")
    print(f"  MAD (all data):             {mad:>8.2%}  <- Stable despite outliers!")
    print()

    # Outlier indicator
    ratio = mad / std_dev
    print(f"MAD/StdDev Ratio: {ratio:.3f}")
    if ratio < 0.67:
        print("  -> Ratio < 0.67 indicates STRONG outliers present!")
    print()

    print("When to use: Risk measurement, confidence intervals, Sharpe ratio")
    print("Benefit: 50% breakdown point (can handle up to 50% outliers!)")
    print()


def demo_robust_zscore(returns):
    """Demonstrate robust z-scores for outlier detection."""
    print("=" * 80)
    print("SOLUTION 4: Robust Z-Scores - Detect Anomalous Trades")
    print("=" * 80)
    print()

    # Calculate traditional and robust z-scores
    z_traditional = (returns - np.mean(returns)) / np.std(returns, ddof=1)
    z_robust = robust_zscore(returns)

    # Find outliers (|z| > 3)
    traditional_outliers = np.where(np.abs(z_traditional) > 3)[0]
    robust_outliers = np.where(np.abs(z_robust) > 3)[0]

    print("Robust Z-Score = (X - median) / MAD")
    print("Traditional Z-Score = (X - mean) / std_dev")
    print()
    print("Outlier Detection (|z| > 3):")
    print(f"  Traditional method found: {len(traditional_outliers)} outliers")
    print(f"  Robust method found:      {len(robust_outliers)} outliers")
    print()

    # Show top 5 outliers
    top_outliers = np.argsort(np.abs(z_robust))[-5:][::-1]
    print("Top 5 Outliers (by robust z-score):")
    for i, idx in enumerate(top_outliers, 1):
        print(
            f"  {i}. Trade {idx:>3}: {returns[idx]:>7.1%} return "
            f"(z_robust={z_robust[idx]:>6.1f}, z_trad={z_traditional[idx]:>5.1f})"
        )
    print()

    print("When to use: Flagging suspicious trades, quality control, filtering")
    print("Benefit: Not affected by the outliers being detected")
    print()


def demo_complete_workflow(returns):
    """Demonstrate complete robust statistics workflow."""
    print("=" * 80)
    print("COMPLETE WORKFLOW: Robust Backtest Analysis")
    print("=" * 80)
    print()

    # Step 1: Identify outliers
    print("STEP 1: Identify Outliers with Robust Z-Scores")
    print("-" * 80)
    z_scores = robust_zscore(returns)
    outlier_mask = np.abs(z_scores) > 3
    outlier_count = np.sum(outlier_mask)

    print(f"Found {outlier_count} outliers (|z| > 3) out of {len(returns)} trades")
    print(f"Outlier percentage: {outlier_count/len(returns):.1%}")
    print()

    # Step 2: Calculate typical performance (without outliers)
    print("STEP 2: Calculate Typical Performance (Trimmed Mean)")
    print("-" * 80)
    typical_return = trimmed_mean(returns, proportiontocut=0.05)
    print(f"Typical Return (5% trimmed mean): {typical_return:.2%}")
    print()

    # Step 3: Calculate robust risk (MAD)
    print("STEP 3: Calculate Robust Risk (MAD)")
    print("-" * 80)
    risk_mad = median_absolute_deviation(returns)
    risk_std = np.std(returns, ddof=1)
    print(f"Robust Risk (MAD):           {risk_mad:.2%}")
    print(f"Traditional Risk (Std Dev):  {risk_std:.2%}")
    print()

    # Step 4: Calculate robust Sharpe ratio
    print("STEP 4: Calculate Robust Sharpe Ratio")
    print("-" * 80)
    median_return = np.median(returns)
    robust_sharpe = (median_return / risk_mad) * np.sqrt(252)
    traditional_sharpe = (np.mean(returns) / risk_std) * np.sqrt(252)

    print(f"Robust Sharpe (median/MAD):    {robust_sharpe:.2f}")
    print(f"Traditional Sharpe (mean/std): {traditional_sharpe:.2f}")
    print()

    # Step 5: Robust confidence intervals (winsorized bootstrap)
    print("STEP 5: Robust Confidence Intervals (Winsorized Bootstrap)")
    print("-" * 80)
    winsorized = winsorize(returns, limits=(0.01, 0.01))

    result = scipy_stats.bootstrap(
        (winsorized,),
        np.mean,
        n_resamples=10000,
        confidence_level=0.95,
        random_state=42,
    )

    ci_lower = result.confidence_interval.low
    ci_upper = result.confidence_interval.high

    print(f"Mean Return: {np.mean(winsorized):.2%}")
    print(f"95% CI: [{ci_lower:.2%}, {ci_upper:.2%}]")
    print()

    # Final summary
    print("=" * 80)
    print("SUMMARY: Robust vs Traditional Statistics")
    print("=" * 80)
    print()
    print("Traditional (MISLEADING):")
    print(f"  Mean: {np.mean(returns):.2%}, Sharpe: {traditional_sharpe:.2f}")
    print()
    print("Robust (RELIABLE):")
    print(f"  Typical Return: {typical_return:.2%}")
    print(f"  Robust Risk: {risk_mad:.2%}")
    print(f"  Robust Sharpe: {robust_sharpe:.2f}")
    print(f"  95% CI: [{ci_lower:.2%}, {ci_upper:.2%}]")
    print()
    print("Recommendation: Use ROBUST statistics for penny stock backtests!")
    print()


def main():
    """Run complete demo."""
    print()
    print("=" * 80)
    print(" " * 15 + "ROBUST STATISTICS FOR PENNY STOCK BACKTESTING")
    print(" " * 10 + "Critical for Valid 2-Year Backtest Results with Outliers")
    print("=" * 80)
    print()

    # Generate data
    returns = demo_problem()
    print()

    # Demo each method
    demo_winsorization(returns)
    demo_trimmed_mean(returns)
    demo_mad(returns)
    demo_robust_zscore(returns)

    # Complete workflow
    demo_complete_workflow(returns)

    print()
    print("=" * 80)
    print("For more details, see:")
    print("  - C:/Users/menza/OneDrive/Desktop/Catalyst-Bot/catalyst-bot/src/catalyst_bot/backtesting/validator.py")
    print("  - Docstrings in winsorize(), trimmed_mean(), median_absolute_deviation(),")
    print("    robust_zscore() functions")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
