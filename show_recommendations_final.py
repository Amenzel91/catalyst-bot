import json
from pathlib import Path

# Load the analysis report
report_path = Path('data/moa/analysis_report.json')
with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

# Extract recommendations
recs = report.get('recommendations', [])
print('='*80)
print(f'MOA KEYWORD WEIGHT RECOMMENDATIONS ({len(recs)} total)')
print('='*80)
print()

# Sort by confidence (highest first)
recs_sorted = sorted(recs, key=lambda x: x.get('confidence', 0), reverse=True)

for i, r in enumerate(recs_sorted, 1):
    kw = r.get('keyword', 'unknown')
    rec_weight = r.get('recommended_weight', 0.0)
    conf = r.get('confidence', 0.0)
    evidence = r.get('evidence', {})

    occurrences = evidence.get('occurrences', 0)
    success_rate = evidence.get('success_rate', 0.0)
    avg_return = evidence.get('avg_return_pct', 0.0)
    examples = evidence.get('examples', [])

    # Determine if this is a boost or reduction (compare to baseline 1.0)
    if rec_weight > 1.0:
        action = "BOOST"
        change = f"+{rec_weight - 1.0:.1f}"
    elif rec_weight < 1.0:
        action = "REDUCE"
        change = f"-{1.0 - rec_weight:.1f}"
    else:
        action = "MAINTAIN"
        change = "0.0"

    print(f"{i}. {kw}")
    print(f"   Action: {action} to {rec_weight:.1f} ({change})")
    print(f"   Confidence: {conf:.0%}")
    print(f"   Evidence: {occurrences} occurrences, {success_rate:.0%} success rate, {avg_return:.1f}% avg return")

    # Show top 3 examples
    if examples:
        print(f"   Top examples:")
        for j, ex in enumerate(examples[:3], 1):
            ticker = ex.get('ticker', '?')
            ret_pct = ex.get('return_pct', 0.0)
            reason = ex.get('rejection_reason', '?')
            print(f"      {j}) {ticker}: +{ret_pct:.1f}% (was rejected: {reason})")

    print()

print('='*80)
print('SUMMARY:')
print('='*80)
boost_count = sum(1 for r in recs if r.get('recommended_weight', 1.0) > 1.0)
reduce_count = sum(1 for r in recs if r.get('recommended_weight', 1.0) < 1.0)
maintain_count = sum(1 for r in recs if r.get('recommended_weight', 1.0) == 1.0)

print(f"Boost keywords: {boost_count}")
print(f"Reduce keywords: {reduce_count}")
print(f"Maintain keywords: {maintain_count}")
print()
print('High confidence (≥80%): ' + str(sum(1 for r in recs if r.get('confidence', 0) >= 0.8)))
print('Medium confidence (60-79%): ' + str(sum(1 for r in recs if 0.6 <= r.get('confidence', 0) < 0.8)))
print('Lower confidence (<60%): ' + str(sum(1 for r in recs if r.get('confidence', 0) < 0.6)))
