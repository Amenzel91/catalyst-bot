import json
from pathlib import Path

# Load the analysis report
report_path = Path('data/moa/analysis_report.json')
with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

# Extract recommendations
recs = report.get('recommendations', [])
print(f'Total Recommendations: {len(recs)}')
print('='*70)

# Group by recommendation type for clarity
boost_recs = [r for r in recs if r.get('action') == 'boost']
penalize_recs = [r for r in recs if r.get('action') == 'penalize']

print(f'\nBOOST RECOMMENDATIONS ({len(boost_recs)}):')
print('-'*70)
for i, r in enumerate(boost_recs, 1):
    kw = r.get('keyword', 'unknown')
    curr = r.get('current_weight', 0.0)
    rec = r.get('recommended_weight', 0.0)
    delta = r.get('weight_delta', 0.0)
    conf = r.get('confidence', 0.0)
    misses = r.get('misses', 0)
    ret = r.get('avg_return', 0.0)

    print(f'{i}. {kw}')
    print(f'   Current weight: {curr:.2f}')
    print(f'   Recommended: {rec:.2f} (change: {delta:+.2f})')
    print(f'   Confidence: {conf:.1%}')
    print(f'   Evidence: {misses} misses, avg return {ret:.1f}%')
    print()

print(f'\nPENALIZE RECOMMENDATIONS ({len(penalize_recs)}):')
print('-'*70)
for i, r in enumerate(penalize_recs, 1):
    kw = r.get('keyword', 'unknown')
    curr = r.get('current_weight', 0.0)
    rec = r.get('recommended_weight', 0.0)
    delta = r.get('weight_delta', 0.0)
    conf = r.get('confidence', 0.0)
    misses = r.get('misses', 0)
    ret = r.get('avg_return', 0.0)

    print(f'{i}. {kw}')
    print(f'   Current weight: {curr:.2f}')
    print(f'   Recommended: {rec:.2f} (change: {delta:+.2f})')
    print(f'   Confidence: {conf:.1%}')
    print(f'   Evidence: {misses} misses, avg return {ret:.1f}%')
    print()
