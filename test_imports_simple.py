"""
Simple import test - no complex timing or exec
"""
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))

print("=" * 80)
print("IMPORT VALIDATION TEST")
print("=" * 80)

results = {}

# Test 1: Core imports
print("\n[TEST 1] Core Module Imports")
core_modules = [
    'catalyst_bot.config',
    'catalyst_bot.runner',
    'catalyst_bot.classify',
    'catalyst_bot.alerts',
    'catalyst_bot.charts_advanced',
    'catalyst_bot.feeds',
    'catalyst_bot.float_data',
    'catalyst_bot.ticker_validation',
    'catalyst_bot.dedupe',
]

for mod in core_modules:
    try:
        __import__(mod)
        print(f"[PASS] {mod}")
        results[mod] = 'PASS'
    except Exception as e:
        print(f"[FAIL] {mod}: {str(e)[:80]}")
        results[mod] = f'FAIL: {str(e)}'

# Test 2: Wave modules
print("\n[TEST 2] Wave 2-4 Module Imports")
wave_modules = [
    'catalyst_bot.catalyst_badges',
    'catalyst_bot.multi_ticker_handler',
    'catalyst_bot.offering_sentiment',
    'catalyst_bot.sentiment_gauge',
    'catalyst_bot.discord_interactions',
    'catalyst_bot.llm_hybrid',
    'catalyst_bot.moa_historical_analyzer',
    'catalyst_bot.sentiment_tracking',
    'catalyst_bot.trade_plan',
]

for mod in wave_modules:
    try:
        __import__(mod)
        print(f"[PASS] {mod}")
        results[mod] = 'PASS'
    except Exception as e:
        print(f"[FAIL] {mod}: {str(e)[:80]}")
        results[mod] = f'FAIL: {str(e)}'

# Test 3: Third-party packages
print("\n[TEST 3] Third-Party Dependencies")
packages = ['pandas', 'numpy', 'matplotlib', 'discord', 'requests',
            'yfinance', 'pandas_ta', 'anthropic', 'openai']

missing = []
for pkg in packages:
    try:
        __import__(pkg)
        print(f"[OK] {pkg}")
    except ImportError:
        print(f"[MISSING] {pkg}")
        missing.append(pkg)

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
total = len(core_modules) + len(wave_modules)
passed = sum(1 for v in results.values() if v == 'PASS')
print(f"Total modules tested: {total}")
print(f"Passed: {passed}")
print(f"Failed: {total - passed}")
print(f"Missing packages: {len(missing)}")
if missing:
    print(f"  - {', '.join(missing)}")

health = int((passed / total) * 100) if total > 0 else 0
print(f"\nHealth Score: {health}/100")
print(f"Deployment Blocker: {'YES' if health < 70 else 'NO'}")

# Save results
import json
with open('import_validation_simple.json', 'w') as f:
    json.dump({
        'results': results,
        'missing_packages': missing,
        'health_score': health
    }, f, indent=2)

print("\n[OK] Results saved")
