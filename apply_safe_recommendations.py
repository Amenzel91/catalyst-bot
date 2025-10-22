import json
from pathlib import Path
from datetime import datetime

# Keywords to REJECT (mechanical artifacts)
REJECT_KEYWORDS = {
    'reverse_stock_split',  # Mechanical artifact from stock splits
}

# Keywords to HOLD for manual review (need deeper analysis)
HOLD_KEYWORDS = {
    'distress_negative',  # Counterintuitive (negative events showing gains)
    'dilution_risk',      # Need to verify pre-catalyst momentum
    'dilution',           # Same - might be catching tail of runs
    'offering',           # Same - opportunistic timing concern
    'capital_raise',      # Same - need to check if already running
    'atm',                # Same - at-the-market offerings timing
}

# Load the analysis report
report_path = Path('data/moa/analysis_report.json')
with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

recommendations = report.get('recommendations', [])

# Filter recommendations
rejected = [r for r in recommendations if r['keyword'] in REJECT_KEYWORDS]
held = [r for r in recommendations if r['keyword'] in HOLD_KEYWORDS]
approved = [r for r in recommendations if r['keyword'] not in (REJECT_KEYWORDS | HOLD_KEYWORDS)]

print('='*80)
print('MOA RECOMMENDATIONS - CONSERVATIVE APPROVAL')
print('='*80)
print()
print(f"Total recommendations: {len(recommendations)}")
print(f"  REJECTED: {len(rejected)} (mechanical artifacts)")
print(f"  HELD: {len(held)} (need manual review)")
print(f"  APPROVED: {len(approved)} (safe to apply)")
print()

# Show what's being rejected
if rejected:
    print("REJECTED KEYWORDS:")
    for r in rejected:
        print(f"  REJECT: {r['keyword']} - {r['recommended_weight']:.1f}x (mechanical artifact)")
    print()

# Show what's being held
if held:
    print("HELD FOR REVIEW:")
    for r in held:
        print(f"  HOLD: {r['keyword']} - {r['recommended_weight']:.1f}x ({r.get('confidence', 0):.0%} conf)")
    print()

# Show what's being approved
print("APPROVED FOR APPLICATION:")
for i, r in enumerate(approved, 1):
    print(f"  {i}. {r['keyword']} -> {r['recommended_weight']:.1f}x ({r.get('confidence', 0):.0%} conf)")

print()
print('='*80)

# Apply approved recommendations to keyword_stats.json
keyword_stats_path = Path('data/keyword_stats.json')

# Load existing keyword stats
if keyword_stats_path.exists():
    with open(keyword_stats_path, 'r', encoding='utf-8') as f:
        keyword_stats = json.load(f)
else:
    keyword_stats = {}

print()
print("APPLYING RECOMMENDATIONS TO keyword_stats.json...")
print("-" * 80)

applied_count = 0
for rec in approved:
    keyword = rec['keyword']
    new_weight = rec['recommended_weight']
    confidence = rec.get('confidence', 0)
    evidence = rec.get('evidence', {})

    # Create or update keyword entry
    if keyword not in keyword_stats:
        keyword_stats[keyword] = {
            'weight': new_weight,
            'confidence': confidence,
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'source': 'moa_analysis',
            'evidence': evidence
        }
        print(f"  NEW: {keyword} = {new_weight:.1f}x")
        applied_count += 1
    else:
        old_weight = keyword_stats[keyword].get('weight', 1.0)
        keyword_stats[keyword]['weight'] = new_weight
        keyword_stats[keyword]['confidence'] = confidence
        keyword_stats[keyword]['last_updated'] = datetime.utcnow().isoformat() + 'Z'
        keyword_stats[keyword]['source'] = 'moa_analysis'
        keyword_stats[keyword]['evidence'] = evidence
        print(f"  UPDATED: {keyword} = {old_weight:.1f}x -> {new_weight:.1f}x")
        applied_count += 1

# Save updated keyword stats
with open(keyword_stats_path, 'w', encoding='utf-8') as f:
    json.dump(keyword_stats, f, indent=2)

print()
print(f"Applied {applied_count} keyword weight updates to {keyword_stats_path}")
print()

# Create approval report
report_data = {
    'applied_date': datetime.utcnow().isoformat() + 'Z',
    'total_recommendations': len(recommendations),
    'rejected': {
        'count': len(rejected),
        'keywords': [r['keyword'] for r in rejected],
        'reason': 'Mechanical artifacts (reverse stock splits create fake returns)'
    },
    'held': {
        'count': len(held),
        'keywords': [r['keyword'] for r in held],
        'reason': 'Need manual review (pre-catalyst momentum, counterintuitive patterns)'
    },
    'approved': {
        'count': len(approved),
        'keywords': [r['keyword'] for r in approved],
        'applied_to': str(keyword_stats_path)
    }
}

report_output_path = Path('data/moa/conservative_approval_report.json')
with open(report_output_path, 'w', encoding='utf-8') as f:
    json.dump(report_data, f, indent=2)

print(f"Approval report saved to {report_output_path}")
print()
print('='*80)
print('NEXT STEPS:')
print('='*80)
print('1. Monitor bot performance for 30 days with these weights')
print('2. Manually review the 6 HELD keywords:')
for r in held:
    print(f"   - {r['keyword']}: Check pre-catalyst momentum and gain sustainability")
print('3. After validation, consider adding HELD keywords selectively')
print('4. NEVER apply reverse_stock_split (mechanical artifact)')
print()
