#!/usr/bin/env python3
"""
Analyze MOA (Missed Opportunities) historical data.

Analyzes outcomes.jsonl to identify patterns in rejected catalysts.
"""

import json
from collections import defaultdict, Counter
from pathlib import Path
from statistics import mean, median, stdev


def load_outcomes(path: str) -> list:
    """Load all outcomes from JSONL file."""
    outcomes = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                outcomes.append(json.loads(line))
    return outcomes


def analyze_rejection_reasons(outcomes: list) -> dict:
    """Analyze distribution of rejection reasons."""
    reasons = Counter(o.get('rejection_reason', 'UNKNOWN') for o in outcomes)
    return dict(reasons)


def analyze_missed_opportunities(outcomes: list) -> dict:
    """Analyze missed opportunity statistics."""
    total = len(outcomes)
    missed = sum(1 for o in outcomes if o.get('is_missed_opportunity', False))

    # Collect returns for missed opportunities
    missed_returns = []
    for o in outcomes:
        if o.get('is_missed_opportunity'):
            missed_returns.append(o.get('max_return_pct', 0))

    return {
        'total_rejections': total,
        'missed_opportunities': missed,
        'missed_pct': (missed / total * 100) if total > 0 else 0,
        'avg_max_return': mean(missed_returns) if missed_returns else 0,
        'median_max_return': median(missed_returns) if missed_returns else 0,
        'max_return': max(missed_returns) if missed_returns else 0,
    }


def analyze_timeframes(outcomes: list) -> dict:
    """Analyze which timeframes had best returns."""
    timeframes = ['15m', '30m', '1h', '4h', '1d', '7d']
    stats = {}

    for tf in timeframes:
        returns = []
        for o in outcomes:
            tf_data = o.get('outcomes', {}).get(tf)
            if tf_data and 'return_pct' in tf_data:
                returns.append(tf_data['return_pct'])

        if returns:
            positive = sum(1 for r in returns if r > 0)
            negative = sum(1 for r in returns if r < 0)

            stats[tf] = {
                'count': len(returns),
                'avg_return': mean(returns),
                'median_return': median(returns),
                'positive_pct': (positive / len(returns) * 100),
                'negative_pct': (negative / len(returns) * 100),
                'max_return': max(returns),
                'min_return': min(returns),
            }

    return stats


def analyze_sectors(outcomes: list) -> dict:
    """Analyze sector patterns in missed opportunities."""
    sector_stats = defaultdict(lambda: {'total': 0, 'missed': 0, 'avg_return': []})

    for o in outcomes:
        sector = o.get('sector_context', {}).get('sector', 'UNKNOWN')
        sector_stats[sector]['total'] += 1

        if o.get('is_missed_opportunity'):
            sector_stats[sector]['missed'] += 1
            sector_stats[sector]['avg_return'].append(o.get('max_return_pct', 0))

    # Calculate percentages
    result = {}
    for sector, stats in sector_stats.items():
        result[sector] = {
            'total_rejections': stats['total'],
            'missed_opportunities': stats['missed'],
            'missed_pct': (stats['missed'] / stats['total'] * 100) if stats['total'] > 0 else 0,
            'avg_return': mean(stats['avg_return']) if stats['avg_return'] else 0,
        }

    # Sort by missed opportunities
    return dict(sorted(result.items(), key=lambda x: x[1]['missed_opportunities'], reverse=True))


def analyze_market_conditions(outcomes: list) -> dict:
    """Analyze market regime patterns."""
    regime_stats = defaultdict(lambda: {'total': 0, 'missed': 0, 'avg_return': []})

    for o in outcomes:
        regime = o.get('market_regime', 'UNKNOWN')
        regime_stats[regime]['total'] += 1

        if o.get('is_missed_opportunity'):
            regime_stats[regime]['missed'] += 1
            regime_stats[regime]['avg_return'].append(o.get('max_return_pct', 0))

    result = {}
    for regime, stats in regime_stats.items():
        result[regime] = {
            'total_rejections': stats['total'],
            'missed_opportunities': stats['missed'],
            'missed_pct': (stats['missed'] / stats['total'] * 100) if stats['total'] > 0 else 0,
            'avg_return': mean(stats['avg_return']) if stats['avg_return'] else 0,
        }

    return result


def analyze_price_levels(outcomes: list) -> dict:
    """Analyze rejection by price level."""
    price_buckets = {
        'under_5': {'total': 0, 'missed': 0},
        '5_to_20': {'total': 0, 'missed': 0},
        '20_to_50': {'total': 0, 'missed': 0},
        '50_to_100': {'total': 0, 'missed': 0},
        'over_100': {'total': 0, 'missed': 0},
    }

    for o in outcomes:
        price = o.get('rejection_price', 0)
        is_missed = o.get('is_missed_opportunity', False)

        if price < 5:
            price_buckets['under_5']['total'] += 1
            if is_missed:
                price_buckets['under_5']['missed'] += 1
        elif price < 20:
            price_buckets['5_to_20']['total'] += 1
            if is_missed:
                price_buckets['5_to_20']['missed'] += 1
        elif price < 50:
            price_buckets['20_to_50']['total'] += 1
            if is_missed:
                price_buckets['20_to_50']['missed'] += 1
        elif price < 100:
            price_buckets['50_to_100']['total'] += 1
            if is_missed:
                price_buckets['50_to_100']['missed'] += 1
        else:
            price_buckets['over_100']['total'] += 1
            if is_missed:
                price_buckets['over_100']['missed'] += 1

    # Calculate percentages
    for bucket, stats in price_buckets.items():
        if stats['total'] > 0:
            stats['missed_pct'] = (stats['missed'] / stats['total'] * 100)
        else:
            stats['missed_pct'] = 0

    return price_buckets


def print_report(outcomes: list):
    """Generate comprehensive analysis report."""
    print("=" * 80)
    print("MOA HISTORICAL DATA ANALYSIS")
    print("=" * 80)
    print()

    # 1. Overall Statistics
    print("1. OVERALL STATISTICS")
    print("-" * 80)
    moa_stats = analyze_missed_opportunities(outcomes)
    print(f"Total Rejections: {moa_stats['total_rejections']:,}")
    print(f"Missed Opportunities: {moa_stats['missed_opportunities']:,} ({moa_stats['missed_pct']:.1f}%)")
    print(f"Average Max Return (Missed): {moa_stats['avg_max_return']:.2f}%")
    print(f"Median Max Return (Missed): {moa_stats['median_max_return']:.2f}%")
    print(f"Best Return (Missed): {moa_stats['max_return']:.2f}%")
    print()

    # 2. Rejection Reasons
    print("2. REJECTION REASON DISTRIBUTION")
    print("-" * 80)
    reasons = analyze_rejection_reasons(outcomes)
    for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
        pct = (count / moa_stats['total_rejections'] * 100)
        print(f"{reason:20s}: {count:4d} ({pct:5.1f}%)")
    print()

    # 3. Timeframe Analysis
    print("3. TIMEFRAME PERFORMANCE")
    print("-" * 80)
    tf_stats = analyze_timeframes(outcomes)
    print(f"{'Timeframe':<10} {'Avg Return':>12} {'Median':>10} {'Positive%':>10} {'Max':>10} {'Min':>10}")
    print("-" * 80)
    for tf in ['15m', '30m', '1h', '4h', '1d', '7d']:
        if tf in tf_stats:
            s = tf_stats[tf]
            print(f"{tf:<10} {s['avg_return']:>11.2f}% {s['median_return']:>9.2f}% {s['positive_pct']:>9.1f}% {s['max_return']:>9.1f}% {s['min_return']:>9.1f}%")
    print()

    # 4. Sector Analysis
    print("4. TOP SECTORS BY MISSED OPPORTUNITIES")
    print("-" * 80)
    sector_stats = analyze_sectors(outcomes)
    top_sectors = list(sector_stats.items())[:10]
    print(f"{'Sector':<30} {'Total':>8} {'Missed':>8} {'Miss%':>8} {'AvgRet':>10}")
    print("-" * 80)
    for sector, stats in top_sectors:
        sector_name = sector if sector else "NONE"
        print(f"{sector_name:<30} {stats['total_rejections']:>8} {stats['missed_opportunities']:>8} {stats['missed_pct']:>7.1f}% {stats['avg_return']:>9.1f}%")
    print()

    # 5. Market Regime Analysis
    print("5. MARKET REGIME PATTERNS")
    print("-" * 80)
    regime_stats = analyze_market_conditions(outcomes)
    print(f"{'Regime':<20} {'Total':>8} {'Missed':>8} {'Miss%':>8} {'AvgRet':>10}")
    print("-" * 80)
    for regime, stats in regime_stats.items():
        print(f"{regime:<20} {stats['total_rejections']:>8} {stats['missed_opportunities']:>8} {stats['missed_pct']:>7.1f}% {stats['avg_return']:>9.1f}%")
    print()

    # 6. Price Level Analysis
    print("6. REJECTION BY PRICE LEVEL")
    print("-" * 80)
    price_stats = analyze_price_levels(outcomes)
    print(f"{'Price Range':<20} {'Total':>8} {'Missed':>8} {'Miss%':>8}")
    print("-" * 80)
    for bucket, stats in price_stats.items():
        print(f"{bucket.replace('_', ' ').title():<20} {stats['total']:>8} {stats['missed']:>8} {stats['missed_pct']:>7.1f}%")
    print()

    # 7. Key Insights
    print("7. KEY INSIGHTS")
    print("-" * 80)

    # Best timeframe
    best_tf = max(tf_stats.items(), key=lambda x: x[1]['avg_return'])
    print(f"[*] Best Timeframe: {best_tf[0]} (avg {best_tf[1]['avg_return']:.2f}% return)")

    # Most missed sector
    if top_sectors:
        top_sector = top_sectors[0]
        print(f"[*] Most Missed Sector: {top_sector[0]} ({top_sector[1]['missed_opportunities']} opportunities)")

    # Price sweet spot
    best_price_bucket = max(price_stats.items(), key=lambda x: x[1]['missed_pct'] if x[1]['total'] > 10 else 0)
    print(f"[*] Price Sweet Spot: {best_price_bucket[0].replace('_', ' ').title()} ({best_price_bucket[1]['missed_pct']:.1f}% miss rate)")

    # Market regime impact
    best_regime = max(regime_stats.items(), key=lambda x: x[1]['missed_pct'])
    print(f"[*] Best Market Regime: {best_regime[0]} ({best_regime[1]['missed_pct']:.1f}% miss rate)")

    print()
    print("=" * 80)


def main():
    outcomes_path = Path("data/moa/outcomes.jsonl")

    if not outcomes_path.exists():
        print(f"ERROR: {outcomes_path} not found")
        return 1

    print(f"Loading outcomes from {outcomes_path}...")
    outcomes = load_outcomes(outcomes_path)
    print(f"Loaded {len(outcomes):,} outcomes")
    print()

    print_report(outcomes)

    return 0


if __name__ == "__main__":
    exit(main())
