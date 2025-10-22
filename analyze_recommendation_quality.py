import json
from pathlib import Path

# Load the analysis report
report_path = Path('data/moa/analysis_report.json')
with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

# Load the outcomes data to get detailed price movements
outcomes_path = Path('data/moa/outcomes.jsonl')
outcomes = []
with open(outcomes_path, 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            outcomes.append(json.loads(line))

print('='*80)
print('DEEP DIVE: RECOMMENDATION QUALITY ANALYSIS')
print('='*80)
print()

# Focus on the top suspicious keywords
suspicious_keywords = [
    'dilution_risk',
    'distress_negative',
    'reverse_stock_split',
    'executive_compensation',
    'dilution',
    'offering',
    'capital_raise'
]

for keyword in suspicious_keywords:
    print(f"\n{'='*80}")
    print(f"KEYWORD: {keyword}")
    print('='*80)

    # Find this keyword in recommendations
    rec = next((r for r in report['recommendations'] if r['keyword'] == keyword), None)
    if not rec:
        print("Not found in recommendations")
        continue

    evidence = rec.get('evidence', {})
    examples = evidence.get('examples', [])

    print(f"Recommended weight: {rec.get('recommended_weight', 0):.1f}x")
    print(f"Confidence: {rec.get('confidence', 0):.0%}")
    print(f"Occurrences: {evidence.get('occurrences', 0)}")
    print(f"Success rate: {evidence.get('success_rate', 0):.0%}")
    print(f"Avg return: {evidence.get('avg_return_pct', 0):.1f}%")
    print()

    # For each example, find the full outcome data
    print("DETAILED EXAMPLES:")
    print("-" * 80)

    for i, ex in enumerate(examples[:5], 1):
        ticker = ex.get('ticker', '?')
        ret_pct = ex.get('return_pct', 0)
        reason = ex.get('rejection_reason', '?')

        # Find matching outcome in outcomes.jsonl
        matching = [o for o in outcomes if o.get('ticker') == ticker and keyword in o.get('keywords', [])]

        if matching:
            outcome = matching[0]  # Take first match

            print(f"\n{i}. {ticker} - Rejected: {reason}")
            print(f"   Return: {ret_pct:.1f}%")

            # Show price context
            prices = outcome.get('prices', {})
            baseline_price = prices.get('baseline_price', 0)
            price_1h = prices.get('price_1h')
            price_4h = prices.get('price_4h')
            price_1d = prices.get('price_1d')
            price_7d = prices.get('price_7d')

            print(f"   Baseline price: ${baseline_price:.2f}")

            # Calculate returns at each timeframe
            if price_1h:
                ret_1h = ((price_1h - baseline_price) / baseline_price) * 100
                print(f"   1h:  ${price_1h:.2f} ({ret_1h:+.1f}%)")
            if price_4h:
                ret_4h = ((price_4h - baseline_price) / baseline_price) * 100
                print(f"   4h:  ${price_4h:.2f} ({ret_4h:+.1f}%)")
            if price_1d:
                ret_1d = ((price_1d - baseline_price) / baseline_price) * 100
                print(f"   1d:  ${price_1d:.2f} ({ret_1d:+.1f}%)")
            if price_7d:
                ret_7d = ((price_7d - baseline_price) / baseline_price) * 100
                print(f"   7d:  ${price_7d:.2f} ({ret_7d:+.1f}%)")

                # Check if price holds
                if price_1h and price_7d:
                    peak_ret = max(ret_1h if price_1h else 0,
                                 ret_4h if price_4h else 0,
                                 ret_1d if price_1d else 0)
                    if ret_7d < peak_ret * 0.5:
                        print(f"   ⚠️  Price gave back {((peak_ret - ret_7d) / peak_ret * 100):.0f}% from peak")
                    else:
                        print(f"   ✓ Price held well (7d = {(ret_7d/peak_ret*100):.0f}% of peak)")

            # Show title for context
            title = outcome.get('title', '')
            if title:
                print(f"   Title: {title[:100]}...")
        else:
            print(f"\n{i}. {ticker} - Rejected: {reason}, Return: {ret_pct:.1f}%")
            print(f"   (No detailed outcome data found)")

print("\n" + "="*80)
print("SUMMARY ANALYSIS")
print("="*80)
print()
print("Key Questions:")
print("1. Are reverse stock split returns mechanical artifacts?")
print("2. Do dilution/offering catalysts hold price after 7 days?")
print("3. What is 'distress_negative' keyword?")
print("4. Are these stocks already running before the catalyst?")
