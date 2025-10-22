import json
from pathlib import Path
from collections import defaultdict

# Load outcomes
outcomes_path = Path('data/moa/outcomes.jsonl')
outcomes = []
with open(outcomes_path, 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            outcomes.append(json.loads(line))

# Analyze specific keywords
keywords_to_check = ['dilution', 'offering', 'capital_raise', 'reverse_stock_split']

print('='*80)
print('VALIDATION ANALYSIS: Are these recommendations sound?')
print('='*80)
print()

for keyword in keywords_to_check:
    print(f"\n{'='*80}")
    print(f"KEYWORD: {keyword}")
    print('='*80)

    # Find all missed opportunities with this keyword
    matching = [o for o in outcomes if keyword in o.get('keywords', []) and o.get('is_missed_opportunity')]

    if not matching:
        print(f"No missed opportunities found for {keyword}")
        continue

    print(f"Missed opportunities: {len(matching)}")
    print()

    # Analyze price patterns
    already_running_count = 0
    gave_back_gains_count = 0
    mechanical_artifact_count = 0
    solid_opportunities_count = 0

    print("SAMPLE ANALYSIS (first 10):")
    print("-" * 80)

    for i, outcome in enumerate(matching[:10], 1):
        ticker = outcome.get('ticker', '?')
        rejection_price = outcome.get('rejection_price', 0)
        rejection_reason = outcome.get('rejection_reason', '?')

        pre = outcome.get('pre_event_context', {})
        price_7d_before = pre.get('price_7d_before')
        momentum_7d = pre.get('momentum_7d')

        outcomes_data = outcome.get('outcomes', {})
        ret_7d = outcomes_data.get('7d', {}).get('return_pct', 0)
        ret_1d = outcomes_data.get('1d', {}).get('return_pct', 0)

        print(f"\n{i}. {ticker} - Rejected: {rejection_reason}")
        print(f"   Rejection price: ${rejection_price:.2f}")

        # Check if already running
        if price_7d_before and momentum_7d:
            if momentum_7d > 20:
                print(f"   ⚠️  ALREADY RUNNING: +{momentum_7d:.1f}% in 7 days before catalyst")
                already_running_count += 1
            else:
                print(f"   Pre-momentum: {momentum_7d:+.1f}% (7d before)")

        # Check for mechanical artifacts (reverse splits)
        if keyword == 'reverse_stock_split':
            if price_7d_before and price_7d_before > rejection_price * 10:
                print(f"   🚨 MECHANICAL ARTIFACT: Price crashed from ${price_7d_before:.2f} to ${rejection_price:.2f}")
                mechanical_artifact_count += 1

        # Check if gains held
        if ret_1d and ret_7d:
            if ret_7d < ret_1d * 0.5:
                print(f"   ⚠️  GAVE BACK GAINS: 1d={ret_1d:+.1f}%, 7d={ret_7d:+.1f}%")
                gave_back_gains_count += 1
            else:
                print(f"   ✓ Held gains: 1d={ret_1d:+.1f}%, 7d={ret_7d:+.1f}%")
                solid_opportunities_count += 1
        else:
            print(f"   Return: 7d={ret_7d:+.1f}%")
            if ret_7d > 10:
                solid_opportunities_count += 1

    print()
    print(f"SUMMARY FOR {keyword}:")
    print(f"  Already running before catalyst: {already_running_count}/{len(matching[:10])}")
    print(f"  Gave back gains by day 7: {gave_back_gains_count}/{len(matching[:10])}")
    print(f"  Mechanical artifacts: {mechanical_artifact_count}/{len(matching[:10])}")
    print(f"  Solid opportunities: {solid_opportunities_count}/{len(matching[:10])}")

print()
print("="*80)
print("OVERALL ASSESSMENT")
print("="*80)
print()
print("Questions to answer:")
print("1. Are dilution/offering keywords catching stocks already running up?")
print("2. Do these gains hold after 7 days?")
print("3. Are reverse stock splits creating fake returns?")
print("4. What's the actual tradeable opportunity?")
