"""
AGENT 4: Import & Dependency Validation Test Suite
Tests all critical imports and measures performance
"""

import sys
import time
import traceback
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))

def test_import(module_path, from_items=None):
    """Test importing a module and return results"""
    start = time.time()
    try:
        if from_items:
            exec(f"from {module_path} import {', '.join(from_items)}")
        else:
            exec(f"import {module_path}")
        elapsed = time.time() - start
        return {
            'status': 'PASS',
            'time': elapsed,
            'error': None
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            'status': 'FAIL',
            'time': elapsed,
            'error': str(e),
            'traceback': traceback.format_exc()
        }

print("=" * 80)
print("AGENT 4: IMPORT & DEPENDENCY VALIDATION")
print("=" * 80)

# Test 1: Core Module Imports
print("\n[TEST 1] Core Module Imports")
print("-" * 80)

core_modules = [
    ('catalyst_bot.config', None),
    ('catalyst_bot.runner', None),
    ('catalyst_bot.classify', None),
    ('catalyst_bot.alerts', None),
    ('catalyst_bot.charts_advanced', None),
    ('catalyst_bot.feeds', None),
    ('catalyst_bot.float_data', None),
    ('catalyst_bot.ticker_validation', None),
    ('catalyst_bot.dedupe', None),
]

core_results = []
for module, items in core_modules:
    result = test_import(module, items)
    core_results.append((module, result))
    status_icon = "[PASS]" if result['status'] == 'PASS' else "[FAIL]"
    print(f"{status_icon} {module}: {result['status']} ({result['time']:.3f}s)")
    if result['error']:
        print(f"  ERROR: {result['error']}")

# Test 2: Wave 2-4 New Module Imports
print("\n[TEST 2] Wave 2-4 New Module Imports")
print("-" * 80)

wave_modules = [
    ('catalyst_bot.catalyst_badges', ['extract_catalyst_badges']),
    ('catalyst_bot.multi_ticker_handler', ['score_ticker_relevance']),
    ('catalyst_bot.offering_sentiment', ['detect_offering_stage']),
    ('catalyst_bot.sentiment_gauge', ['create_enhanced_sentiment_gauge']),
    ('catalyst_bot.discord_interactions', None),
    ('catalyst_bot.llm_hybrid', None),
    ('catalyst_bot.moa_historical_analyzer', None),
    ('catalyst_bot.sentiment_tracking', None),
    ('catalyst_bot.trade_plan', None),
]

wave_results = []
for module, items in wave_modules:
    result = test_import(module, items)
    wave_results.append((module, result))
    status_icon = "[PASS]" if result['status'] == 'PASS' else "[FAIL]"
    print(f"{status_icon} {module}: {result['status']} ({result['time']:.3f}s)")
    if result['error']:
        print(f"  ERROR: {result['error']}")

# Test 3: Individual Module Isolation Test (Circular Dependency Check)
print("\n[TEST 3] Circular Dependency Check")
print("-" * 80)

# Reset imports for fresh test
import importlib
isolated_modules = [
    'catalyst_bot.config',
    'catalyst_bot.alerts',
    'catalyst_bot.classify',
    'catalyst_bot.runner',
    'catalyst_bot.discord_interactions',
    'catalyst_bot.llm_hybrid',
]

circular_issues = []
for module in isolated_modules:
    # Try importing in fresh state
    try:
        if module in sys.modules:
            del sys.modules[module]
        result = test_import(module)
        if result['status'] == 'FAIL':
            circular_issues.append((module, result['error']))
            print(f"[FAIL] {module}: Potential circular dependency")
        else:
            print(f"[PASS] {module}: Clean import")
    except Exception as e:
        circular_issues.append((module, str(e)))
        print(f"[FAIL] {module}: Import failed - {e}")

# Test 4: Third-Party Dependencies
print("\n[TEST 4] Third-Party Dependencies")
print("-" * 80)

required_packages = [
    'pandas',
    'numpy',
    'matplotlib',
    'discord',
    'requests',
    'yfinance',
    'pandas_ta',
    'anthropic',
    'openai',
]

missing_packages = []
for package in required_packages:
    try:
        __import__(package)
        print(f"[OK] {package}: Installed")
    except ImportError:
        missing_packages.append(package)
        print(f"[MISSING] {package}: NOT INSTALLED")

# Test 5: Import Performance Analysis
print("\n[TEST 5] Import Performance Analysis")
print("-" * 80)

all_results = core_results + wave_results
slow_imports = [(m, r) for m, r in all_results if r['status'] == 'PASS' and r['time'] > 1.0]

if slow_imports:
    print("Slow imports (>1.0s):")
    for module, result in slow_imports:
        print(f"  [WARN] {module}: {result['time']:.3f}s")
else:
    print("[OK] All imports complete in <1.0s")

# Calculate metrics
total_tests = len(core_results) + len(wave_results)
passed_tests = sum(1 for _, r in core_results + wave_results if r['status'] == 'PASS')
core_passed = sum(1 for _, r in core_results if r['status'] == 'PASS')
wave_passed = sum(1 for _, r in wave_results if r['status'] == 'PASS')

# Calculate health score
health_score = int((passed_tests / total_tests) * 100) if total_tests > 0 else 0
if missing_packages:
    health_score -= len(missing_packages) * 5  # Deduct 5 points per missing package
if circular_issues:
    health_score -= len(circular_issues) * 10  # Deduct 10 points per circular dependency
health_score = max(0, health_score)

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Core Imports: {core_passed}/{len(core_results)} passed")
print(f"Wave 2-4 Imports: {wave_passed}/{len(wave_results)} passed")
print(f"Circular Dependencies: {len(circular_issues)} found")
print(f"Missing Dependencies: {len(missing_packages)} ({', '.join(missing_packages) if missing_packages else 'None'})")
print(f"Import Health Score: {health_score}/100")
print(f"Deployment Blocker: {'YES' if health_score < 70 else 'NO'}")

# Detailed error report
if any(r['status'] == 'FAIL' for _, r in core_results + wave_results):
    print("\n" + "=" * 80)
    print("DETAILED ERROR REPORT")
    print("=" * 80)
    for module, result in core_results + wave_results:
        if result['status'] == 'FAIL':
            print(f"\n{module}:")
            print(result['traceback'])

# Export results for report generation
import json
results_data = {
    'core_results': [(m, r) for m, r in core_results],
    'wave_results': [(m, r) for m, r in wave_results],
    'circular_issues': circular_issues,
    'missing_packages': missing_packages,
    'slow_imports': [(m, r['time']) for m, r in slow_imports],
    'metrics': {
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'core_passed': core_passed,
        'wave_passed': wave_passed,
        'health_score': health_score,
        'deployment_blocker': health_score < 70
    }
}

with open('import_validation_results.json', 'w') as f:
    json.dump(results_data, f, indent=2, default=str)

print("\n[OK] Results saved to import_validation_results.json")
