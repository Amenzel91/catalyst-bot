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

if recs:
    print('\nFirst recommendation structure:')
    print(json.dumps(recs[0], indent=2))

    print('\nAll recommendation keys:')
    for i, r in enumerate(recs[:5], 1):
        print(f'{i}. Keys: {list(r.keys())}')
