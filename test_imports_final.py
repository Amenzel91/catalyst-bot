"""
AGENT 4: Final Import Validation Test
Tests all imports with ML sentiment disabled to avoid model downloads
"""
import sys
import os
from pathlib import Path
import time

# Disable ML features that may download models
os.environ['FEATURE_ML_SENTIMENT'] = '0'
os.environ['FEATURE_SEMANTIC_KEYWORDS'] = '0'

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))

print("=" * 80)
print("AGENT 4: IMPORT & DEPENDENCY VALIDATION")
print("=" * 80)
print("Note: ML features disabled to prevent model downloads during import test")
print()

results = {}
import_times = {}

def test_import(module_name, description=""):
    """Test importing a module and track results"""
    start = time.time()
    try:
        __import__(module_name)
        elapsed = time.time() - start
        print(f"[PASS] {module_name:45} ({elapsed:.3f}s) {description}")
        results[module_name] = 'PASS'
        import_times[module_name] = elapsed
        return True
    except Exception as e:
        elapsed = time.time() - start
        error_msg = str(e)[:100]
        print(f"[FAIL] {module_name:45} ({elapsed:.3f}s)")
        print(f"       Error: {error_msg}")
        results[module_name] = f'FAIL: {error_msg}'
        import_times[module_name] = elapsed
        return False

# Test 1: Core Module Imports
print("\n[TEST 1] Core Module Imports")
print("-" * 80)

core_modules = [
    ('catalyst_bot.config', 'Configuration settings'),
    ('catalyst_bot.runner', 'Main bot runner'),
    ('catalyst_bot.classify', 'Classification and scoring'),
    ('catalyst_bot.alerts', 'Alert generation'),
    ('catalyst_bot.charts_advanced', 'Advanced charting'),
    ('catalyst_bot.feeds', 'News feed sources'),
    ('catalyst_bot.float_data', 'Float and share data'),
    ('catalyst_bot.ticker_validation', 'Ticker validation'),
    ('catalyst_bot.dedupe', 'Deduplication logic'),
]

core_pass = 0
for mod, desc in core_modules:
    if test_import(mod, desc):
        core_pass += 1

# Test 2: Wave 2-4 New Module Imports
print("\n[TEST 2] Wave 2-4 Feature Module Imports")
print("-" * 80)

wave_modules = [
    ('catalyst_bot.catalyst_badges', 'Catalyst badge extraction'),
    ('catalyst_bot.multi_ticker_handler', 'Multi-ticker handling'),
    ('catalyst_bot.offering_sentiment', 'Offering stage detection'),
    ('catalyst_bot.sentiment_gauge', 'Enhanced sentiment gauge'),
    ('catalyst_bot.discord_interactions', 'Discord integration'),
    ('catalyst_bot.llm_hybrid', 'LLM hybrid analysis'),
    ('catalyst_bot.moa_historical_analyzer', 'MOA historical analyzer'),
    ('catalyst_bot.sentiment_tracking', 'Sentiment tracking'),
    ('catalyst_bot.trade_plan', 'Trade plan generation'),
]

wave_pass = 0
for mod, desc in wave_modules:
    if test_import(mod, desc):
        wave_pass += 1

# Test 3: Third-Party Dependencies
print("\n[TEST 3] Third-Party Package Dependencies")
print("-" * 80)

packages = [
    ('pandas', 'Data manipulation'),
    ('numpy', 'Numerical computing'),
    ('matplotlib', 'Plotting'),
    ('discord', 'Discord API'),
    ('requests', 'HTTP requests'),
    ('yfinance', 'Yahoo Finance'),
    ('pandas_ta', 'Technical analysis'),
    ('anthropic', 'Anthropic Claude API'),
    ('openai', 'OpenAI API'),
]

missing_packages = []
for pkg, desc in packages:
    try:
        __import__(pkg)
        print(f"[OK] {pkg:20} - {desc}")
    except ImportError:
        print(f"[MISSING] {pkg:20} - {desc}")
        missing_packages.append(pkg)

# Test 4: Import Performance Analysis
print("\n[TEST 4] Import Performance Analysis")
print("-" * 80)

slow_imports = [(m, t) for m, t in import_times.items() if t > 1.0]

if slow_imports:
    print("Slow imports (>1.0s):")
    for module, import_time in sorted(slow_imports, key=lambda x: x[1], reverse=True):
        print(f"  [WARN] {module:45} {import_time:.3f}s")
else:
    print("[OK] All imports complete in <1.0s")

# Test 5: Circular Dependency Check
print("\n[TEST 5] Circular Dependency Analysis")
print("-" * 80)

# Check for common circular dependency patterns
circular_issues = []

# Simple heuristic: if a module failed to import, it might be circular
failed_modules = [m for m, r in results.items() if r.startswith('FAIL')]

if failed_modules:
    print("[WARN] Failed imports may indicate circular dependencies:")
    for mod in failed_modules:
        print(f"  - {mod}: {results[mod]}")
        circular_issues.append((mod, results[mod]))
else:
    print("[OK] No obvious circular dependency issues detected")

# Calculate Health Score
print("\n" + "=" * 80)
print("IMPORT HEALTH SUMMARY")
print("=" * 80)

total_modules = len(core_modules) + len(wave_modules)
total_passed = core_pass + wave_pass

# Calculate health score
health_score = int((total_passed / total_modules) * 100) if total_modules > 0 else 0

# Deduct points for issues
if missing_packages:
    health_score -= len(missing_packages) * 5  # 5 points per missing package
if circular_issues:
    health_score -= len(circular_issues) * 10  # 10 points per circular dependency

health_score = max(0, health_score)

print(f"Core Modules:        {core_pass}/{len(core_modules)} passed")
print(f"Wave 2-4 Modules:    {wave_pass}/{len(wave_modules)} passed")
print(f"Total Passed:        {total_passed}/{total_modules}")
print(f"Missing Packages:    {len(missing_packages)}")
if missing_packages:
    print(f"  - {', '.join(missing_packages)}")
print(f"Circular Issues:     {len(circular_issues)}")
print()
print(f"Import Health Score: {health_score}/100")
print(f"Deployment Blocker:  {'YES - Fix required!' if health_score < 70 else 'NO - Ready to deploy'}")

# Save detailed results
import json

results_data = {
    'core_results': {mod: results[mod] for mod, _ in core_modules},
    'wave_results': {mod: results[mod] for mod, _ in wave_modules},
    'import_times': import_times,
    'missing_packages': missing_packages,
    'circular_issues': [(m, e) for m, e in circular_issues],
    'slow_imports': slow_imports,
    'metrics': {
        'total_modules': total_modules,
        'total_passed': total_passed,
        'core_passed': core_pass,
        'wave_passed': wave_pass,
        'health_score': health_score,
        'deployment_blocker': health_score < 70
    }
}

output_file = 'import_validation_results.json'
with open(output_file, 'w') as f:
    json.dump(results_data, f, indent=2)

print(f"\n[OK] Detailed results saved to {output_file}")

# Exit with appropriate code
sys.exit(0 if health_score >= 70 else 1)
