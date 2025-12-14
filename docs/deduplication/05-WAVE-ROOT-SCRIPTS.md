# WAVE 5: ROOT-LEVEL SCRIPT ORGANIZATION

**Status:** Planning
**Priority:** Medium
**Effort:** 2-3 hours
**Risk:** Low (mostly organizational)
**Created:** 2025-12-14

---

## Executive Summary

The project root contains **89 Python files**, creating organizational chaos and making it difficult to:
- Find the right script for a task
- Understand which scripts are current vs. deprecated
- Maintain consistency across similar scripts
- Distinguish between production code and ad-hoc testing scripts

This wave proposes a systematic reorganization of all root-level scripts into a logical directory structure under `/scripts/`, eliminating true duplicates while preserving intentional variations.

### Key Findings

- **11 analysis scripts** (`analyze_*.py`) - Data analysis and diagnostics
- **51 test scripts** (`test_*.py`) - Ad-hoc testing (should be in `/tests/` or `/scripts/`)
- **9 duplicate groups** - Scripts with overlapping functionality
- **3 groups of near-identical files** - True duplicates to consolidate
- **15 utility/maintenance scripts** - Fix, check, verify, etc.
- **3 data processing scripts** - MOA, SEC, keyword extraction

---

## Current State Analysis

### Complete File Inventory (89 files)

#### 1. Analysis Scripts (11 files)

Scripts for analyzing data, performance, and system behavior:

| File | Size | Purpose |
|------|------|---------|
| `analyze_dec9_api.py` | 13K | Analyze December 9th API performance issues |
| `analyze_dec9_llm.py` | 8.7K | Analyze December 9th LLM response issues |
| `analyze_embed.py` | 1.3K | Analyze Discord embed structure (comprehensive) |
| `analyze_embed3.py` | 1.4K | Analyze Discord embed structure (error-focused) |
| `analyze_latency.py` | 4.6K | Analyze system latency metrics |
| `analyze_moa_data.py` | 11K | Analyze MOA (Missed Opportunity Analysis) data |
| `analyze_recommendation_quality.py` | 3.2K | Analyze quality of keyword recommendations |
| `analyze_slowdown.py` | 13K | Analyze system slowdown causes |
| `analyze_tiingo_responses.py` | 8.4K | Analyze Tiingo API responses |
| `analyze_today.py` | 1.6K | Analyze today's bot performance |
| `analyze_todays_alerts.py` | 1.8K | Analyze today's generated alerts |

**Purpose:** These are diagnostic and analysis scripts used for debugging specific issues or analyzing system performance. Most are dated (e.g., "dec9") and may be historical.

#### 2. Test Scripts (51 files)

Ad-hoc test scripts at root level (should be in `/tests/` or `/scripts/debugging/`):

```
test_analyst_sentiment.py          (7.0K) - Test analyst recommendations feed
test_analyst_sentiment_mock.py     (3.1K) - Mock version for testing
test_badges_simple.py              (1.4K) - Test catalyst badge extraction
test_broker_connection.py          (2.5K) - Test broker API connection
test_bulletproof_patterns.py       (4.2K) - Test pattern detection robustness
test_chart_gen.py                  (1.2K) - Test chart generation
test_closed_loop.py                (9.0K) - Test closed-loop system integration
test_clov_specific.py              (2.1K) - Test specific ticker (CLOV)
test_dedup_quick.py                (1.8K) - Quick deduplication test
test_dedup_sec_fix.py              (7.9K) - Test SEC deduplication fix
test_discord_alert.py              (3.3K) - Test Discord alert sending
test_discord_upload.py             (2.7K) - Test Discord file upload
test_discord_webhook.py            (1.5K) - Test Discord webhook multipart upload
test_divergence.py                 (2.3K) - Test price divergence detection
test_enhanced_heartbeat.py         (14K)  - Test enhanced heartbeat feature
test_extended_hours.py             (3.8K) - Test extended hours trading
test_fast_classify.py              (2.1K) - Test fast classification
test_fibonacci_chart.py            (2.2K) - Test Fibonacci chart generation
test_fibonacci_integration.py      (4.7K) - Test Fibonacci integration
test_fibonacci_standalone.py       (5.3K) - Standalone Fibonacci test
test_final_patterns.py             (3.9K) - Test final pattern detection
test_float_manual.py               (1.9K) - Manual float data test
test_gemini_direct.py              (3.4K) - Direct Gemini API test
test_gemini_edge_cases.py          (5.6K) - Gemini API edge cases
test_gemini_markdown_fix.py        (2.8K) - Test Gemini markdown parsing fix
test_google_trends.py              (4.3K) - Test Google Trends integration
test_google_trends_unit.py         (8.8K) - Unit tests for Google Trends
test_imports.py                    (1.2K) - Basic import test
test_imports_agent4.py             (6.9K) - Comprehensive import test with metrics
test_imports_final.py              (6.3K) - Final import test (ML disabled)
test_imports_simple.py             (3.2K) - Simple import validation
test_llm_service.py                (2.4K) - Test LLM service
test_negative_alerts.py            (8.5K) - Test negative sentiment alerts
test_negative_threshold_bypass.py  (3.7K) - Test negative threshold bypass
test_news_velocity.py              (13K)  - Test news velocity detection
test_p2_async_safe_seen_store.py   (2.9K) - Test async-safe seen store (perf)
test_p3_lru_cache_seen_store.py    (3.4K) - Test LRU cache seen store (perf)
test_p4_price_prefilter.py         (4.1K) - Test price prefilter (perf)
test_poc_simple.py                 (1.8K) - Simple proof-of-concept
test_poc_vah_val_lines.py          (6.8K) - POC for VAH/VAL volume profile lines
test_position_management.py        (5.2K) - Test position management
test_positive_quick.py             (2.3K) - Quick positive alert test
test_premarket_sentiment.py        (8.9K) - Test premarket sentiment analysis
test_retrospective_patterns.py     (4.6K) - Test retrospective pattern analysis
test_sec_cache_nullable_ticker.py  (2.1K) - Test SEC cache with null tickers
test_sec_llm_summary.py            (3.8K) - Test SEC filing LLM summarization
test_sec_processor.py              (5.4K) - Test SEC filing processor
test_short_interest_sentiment.py   (6.6K) - Test short interest sentiment
test_verbose.py                    (1.1K) - Test verbose logging
test_volume_profile_bars.py        (5.5K) - Test volume profile bars
test_volume_profile_bars_synthetic.py (4.2K) - Test with synthetic data
```

**Purpose:** These are ad-hoc test scripts created during feature development. Most should either be:
- Moved to `/tests/` as proper unit tests (if they use pytest)
- Moved to `/scripts/debugging/` (if they're one-off diagnostic scripts)
- Deleted (if they're obsolete)

#### 3. Show/Display Scripts (3 files - DUPLICATES)

Scripts that display MOA recommendation data:

| File | Size | Approach | Keep? |
|------|------|----------|-------|
| `show_recommendations.py` | 1.6K | Basic display with boost/penalize groups | ❌ No |
| `show_recommendations_final.py` | 2.2K | Enhanced with sorting and confidence | ✅ **YES** |
| `show_recs_debug.py` | 0.6K | Debug version showing JSON structure | ❌ No |

**Analysis:** These three files load `data/moa/analysis_report.json` and display recommendations. They differ only in output formatting:
- `show_recommendations.py`: Groups by action (boost/penalize)
- `show_recommendations_final.py`: Sorts by confidence with detailed evidence
- `show_recs_debug.py`: Shows raw JSON structure for debugging

**Recommendation:** Keep only `show_recommendations_final.py`, delete the others.

#### 4. Import Test Scripts (4 files - SIMILAR)

Scripts that test module imports:

| File | Size | Approach | Keep? |
|------|------|----------|-------|
| `test_imports.py` | 1.2K | Basic chart imports test | ❌ No |
| `test_imports_simple.py` | 3.2K | Simple validation with health score | ❌ No |
| `test_imports_agent4.py` | 6.9K | Comprehensive with performance analysis | ❌ No |
| `test_imports_final.py` | 6.3K | Final version (ML disabled, saves JSON) | ✅ **YES** |

**Analysis:** These evolved over time as testing requirements changed:
- `test_imports.py`: Early version testing just chart imports
- `test_imports_simple.py`: Added health score and comprehensive module list
- `test_imports_agent4.py`: Added performance tracking and circular dependency checks
- `test_imports_final.py`: Disabled ML features to prevent model downloads, most complete

**Recommendation:** Keep only `test_imports_final.py` as it's the most mature version.

#### 5. Embed Analysis Scripts (2 files - SIMILAR)

Scripts that analyze Discord embed validation issues:

| File | Size | Approach | Keep? |
|------|------|----------|-------|
| `analyze_embed.py` | 1.3K | Comprehensive structure analysis | ❌ No |
| `analyze_embed3.py` | 1.4K | Focused error detection | ✅ **YES** |

**Analysis:** Both parse Discord embed logs to find validation issues:
- `analyze_embed.py`: Shows complete structure with first 10 fields
- `analyze_embed3.py`: Focused on finding null values and type errors across ALL fields

**Recommendation:** Keep `analyze_embed3.py` as it's more thorough (checks all fields, not just first 10).

#### 6. Flake8 Fix Scripts (2 files - DIFFERENT)

Scripts for fixing flake8 linting errors:

| File | Size | Approach | Keep? |
|------|------|----------|-------|
| `fix_flake8.py` | 2.3K | Function-based approach with specific fixes | ✅ Keep |
| `fix_all_flake8.py` | 3.1K | Data-driven approach with fix list | ✅ Keep |

**Analysis:** These use different approaches and may be complementary:
- `fix_flake8.py`: Defines functions for each fix type
- `fix_all_flake8.py`: Takes a list of fixes and applies them

**Recommendation:** Keep both but move to `/scripts/maintenance/`.

#### 7. Environment Check Scripts (2 files - DIFFERENT)

Scripts for validating environment configuration:

| File | Size | Approach | Keep? |
|------|------|----------|-------|
| `check_env.py` | 0.3K | Simple .env variable checker | ❌ No |
| `verify_env.py` | 2.1K | Production environment validator | ✅ **YES** |

**Analysis:**
- `check_env.py`: Prints 3 feature flags (minimal)
- `verify_env.py`: Comprehensive production readiness checks

**Recommendation:** Keep only `verify_env.py`.

#### 8. MOA Data Processing Scripts (8 files)

Scripts for MOA (Missed Opportunity Analysis) keyword recommendations:

```
analyze_moa_data.py              (11K)  - Analyze MOA outcomes data
apply_safe_recommendations.py    (5.0K) - Apply approved keyword weight changes
discover_keywords_now.py         (14K)  - NLP-based keyword extraction from MOA data
extract_moa_keywords.py          (8.3K) - Extract keywords from MOA dataset
merge_classified_keywords.py     (2.8K) - Merge classified keyword lists
moa_backfill_14days.py          (4.9K) - Backfill 14 days of MOA data
quick_merge_keywords.py          (1.9K) - Quick keyword merge utility
show_recommendations_final.py    (2.2K) - Display MOA recommendations
validate_recommendations.py      (3.3K) - Validate keyword recommendations
```

**Purpose:** These form a workflow for analyzing rejected trading alerts and extracting keyword patterns to improve future alerts.

**Recommendation:** Move to `/scripts/analysis/moa/`.

#### 9. Data Extraction/Processing Scripts (8 files)

Various data processing utilities:

```
backfill_with_classification.py  (7.7K) - Backfill data with classifications
convert_sec_tickers.py           (1.4K) - Convert SEC ticker format
diagnose_na_items.py             (2.4K) - Diagnose N/A items in data
extract_rejections.py            (2.9K) - Extract rejection data
investigate_na_tickers.py        (6.7K) - Investigate N/A ticker issues
lookup_high_score_items.py       (1.7K) - Look up high-scoring items
parse_rejections.py              (1.5K) - Parse rejection logs
rejection_report.py              (2.6K) - Generate rejection report
```

**Purpose:** Data processing and diagnostic scripts.

**Recommendation:** Move to `/scripts/data/`.

#### 10. Other Utility Scripts (3 files)

```
fix_missing_keywords.py          (2.1K) - Fix missing keywords in data
fix_webhook_env.py               (1.2K) - Fix webhook environment config
multi_window_analysis_poc.py     (15K)  - Multi-timeframe analysis POC
```

**Purpose:** One-off utilities and proof-of-concepts.

**Recommendation:** Move to appropriate subdirectories.

#### 11. Core Files (2 files)

```
__init__.py                      (0.3K) - Package initialization (KEEP AT ROOT)
main.py                          (2.1K) - CLI entry point (KEEP AT ROOT)
```

**Purpose:** These are legitimate root-level files:
- `__init__.py`: Makes the directory a Python package
- `main.py`: CLI entry point for the bot

**Recommendation:** **Keep these at root level.**

---

## Duplicate Analysis

### TRUE DUPLICATES (Can be safely deleted)

#### Group 1: Show Recommendations
- **Files:** `show_recommendations.py`, `show_recs_debug.py`
- **Keep:** `show_recommendations_final.py`
- **Reason:** Final version has best output format with confidence sorting
- **Safe to delete:** ✅ Yes - identical functionality, just different display formats

#### Group 2: Import Tests
- **Files:** `test_imports.py`, `test_imports_simple.py`, `test_imports_agent4.py`
- **Keep:** `test_imports_final.py`
- **Reason:** Most comprehensive, disables ML to prevent unwanted downloads
- **Safe to delete:** ✅ Yes - these are iterations toward the final version

#### Group 3: Embed Analysis
- **Files:** `analyze_embed.py`
- **Keep:** `analyze_embed3.py`
- **Reason:** Checks ALL fields instead of just first 10
- **Safe to delete:** ✅ Yes - analyze_embed3 is strictly better

#### Group 4: Environment Check
- **Files:** `check_env.py`
- **Keep:** `verify_env.py`
- **Reason:** Comprehensive production checks vs. simple variable dump
- **Safe to delete:** ✅ Yes - verify_env supersedes check_env

### SIMILAR BUT DIFFERENT (Keep both/all)

#### Group 5: Flake8 Fixers
- **Files:** `fix_flake8.py`, `fix_all_flake8.py`
- **Keep:** Both
- **Reason:** Different approaches (function-based vs. data-driven)
- **Action:** Move to `/scripts/maintenance/`

#### Group 6: Fibonacci Tests
- **Files:** `test_fibonacci_chart.py`, `test_fibonacci_integration.py`, `test_fibonacci_standalone.py`
- **Keep:** All (but move to `/scripts/debugging/fibonacci/`)
- **Reason:** Different test scopes (chart, integration, standalone)
- **Action:** Organize in subdirectory

#### Group 7: Gemini Tests
- **Files:** `test_gemini_direct.py`, `test_gemini_edge_cases.py`, `test_gemini_markdown_fix.py`
- **Keep:** All (but move to `/scripts/debugging/llm/`)
- **Reason:** Different test aspects (direct API, edge cases, markdown parsing)
- **Action:** Organize in subdirectory

#### Group 8: Performance Tests
- **Files:** `test_p2_async_safe_seen_store.py`, `test_p3_lru_cache_seen_store.py`, `test_p4_price_prefilter.py`
- **Keep:** All (but move to `/scripts/debugging/performance/`)
- **Reason:** Different performance optimization strategies
- **Action:** Organize in subdirectory

---

## Proposed Directory Structure

```
/home/user/catalyst-bot/
├── __init__.py                         # KEEP AT ROOT
├── main.py                             # KEEP AT ROOT
├── scripts/
│   ├── analysis/
│   │   ├── moa/                       # MOA keyword analysis workflow
│   │   │   ├── analyze_moa_data.py
│   │   │   ├── apply_safe_recommendations.py
│   │   │   ├── discover_keywords_now.py
│   │   │   ├── extract_moa_keywords.py
│   │   │   ├── merge_classified_keywords.py
│   │   │   ├── quick_merge_keywords.py
│   │   │   ├── show_recommendations_final.py
│   │   │   └── validate_recommendations.py
│   │   ├── performance/               # Performance analysis
│   │   │   ├── analyze_latency.py
│   │   │   ├── analyze_slowdown.py
│   │   │   └── analyze_today.py
│   │   ├── api/                       # API response analysis
│   │   │   ├── analyze_dec9_api.py
│   │   │   ├── analyze_dec9_llm.py
│   │   │   └── analyze_tiingo_responses.py
│   │   └── alerts/                    # Alert analysis
│   │       ├── analyze_todays_alerts.py
│   │       ├── analyze_recommendation_quality.py
│   │       └── analyze_embed3.py
│   │
│   ├── data/                          # Data processing scripts
│   │   ├── backfill_with_classification.py
│   │   ├── convert_sec_tickers.py
│   │   ├── diagnose_na_items.py
│   │   ├── extract_rejections.py
│   │   ├── investigate_na_tickers.py
│   │   ├── lookup_high_score_items.py
│   │   ├── moa_backfill_14days.py
│   │   ├── parse_rejections.py
│   │   └── rejection_report.py
│   │
│   ├── maintenance/                   # Maintenance and fix scripts
│   │   ├── fix_flake8.py
│   │   ├── fix_all_flake8.py
│   │   ├── fix_missing_keywords.py
│   │   ├── fix_webhook_env.py
│   │   ├── verify_env.py
│   │   └── test_imports_final.py
│   │
│   ├── debugging/                     # Debug and diagnostic scripts
│   │   ├── fibonacci/
│   │   │   ├── test_fibonacci_chart.py
│   │   │   ├── test_fibonacci_integration.py
│   │   │   └── test_fibonacci_standalone.py
│   │   ├── llm/
│   │   │   ├── test_gemini_direct.py
│   │   │   ├── test_gemini_edge_cases.py
│   │   │   └── test_gemini_markdown_fix.py
│   │   ├── performance/
│   │   │   ├── test_p2_async_safe_seen_store.py
│   │   │   ├── test_p3_lru_cache_seen_store.py
│   │   │   └── test_p4_price_prefilter.py
│   │   ├── charts/
│   │   │   ├── test_chart_gen.py
│   │   │   ├── test_volume_profile_bars.py
│   │   │   └── test_volume_profile_bars_synthetic.py
│   │   ├── discord/
│   │   │   ├── test_discord_alert.py
│   │   │   ├── test_discord_upload.py
│   │   │   └── test_discord_webhook.py
│   │   ├── feeds/
│   │   │   ├── test_analyst_sentiment.py
│   │   │   ├── test_analyst_sentiment_mock.py
│   │   │   ├── test_google_trends.py
│   │   │   ├── test_google_trends_unit.py
│   │   │   └── test_short_interest_sentiment.py
│   │   ├── classification/
│   │   │   ├── test_badges_simple.py
│   │   │   ├── test_bulletproof_patterns.py
│   │   │   ├── test_fast_classify.py
│   │   │   ├── test_final_patterns.py
│   │   │   └── test_retrospective_patterns.py
│   │   ├── integration/
│   │   │   ├── test_closed_loop.py
│   │   │   ├── test_enhanced_heartbeat.py
│   │   │   ├── test_negative_alerts.py
│   │   │   └── test_positive_quick.py
│   │   └── misc/
│   │       ├── test_broker_connection.py
│   │       ├── test_clov_specific.py
│   │       ├── test_dedup_quick.py
│   │       ├── test_dedup_sec_fix.py
│   │       ├── test_divergence.py
│   │       ├── test_extended_hours.py
│   │       ├── test_float_manual.py
│   │       ├── test_llm_service.py
│   │       ├── test_negative_threshold_bypass.py
│   │       ├── test_news_velocity.py
│   │       ├── test_poc_simple.py
│   │       ├── test_poc_vah_val_lines.py
│   │       ├── test_position_management.py
│   │       ├── test_premarket_sentiment.py
│   │       ├── test_sec_cache_nullable_ticker.py
│   │       ├── test_sec_llm_summary.py
│   │       ├── test_sec_processor.py
│   │       └── test_verbose.py
│   │
│   └── archive/                       # Deprecated/historical scripts
│       ├── ARCHIVE_README.md
│       ├── show_recommendations.py    # Superseded by show_recommendations_final.py
│       ├── show_recs_debug.py         # Superseded by show_recommendations_final.py
│       ├── analyze_embed.py           # Superseded by analyze_embed3.py
│       ├── test_imports.py            # Superseded by test_imports_final.py
│       ├── test_imports_simple.py     # Superseded by test_imports_final.py
│       ├── test_imports_agent4.py     # Superseded by test_imports_final.py
│       ├── check_env.py               # Superseded by verify_env.py
│       └── multi_window_analysis_poc.py  # Old POC
│
└── tests/                             # Existing proper test directory
    └── (pytest-based unit tests)
```

### Directory Purpose Summary

| Directory | Purpose | File Count |
|-----------|---------|------------|
| `/scripts/analysis/moa/` | MOA keyword recommendation workflow | 8 |
| `/scripts/analysis/performance/` | Performance diagnostics | 3 |
| `/scripts/analysis/api/` | API response analysis | 3 |
| `/scripts/analysis/alerts/` | Alert quality analysis | 3 |
| `/scripts/data/` | Data processing utilities | 9 |
| `/scripts/maintenance/` | Maintenance and validation | 6 |
| `/scripts/debugging/fibonacci/` | Fibonacci feature debugging | 3 |
| `/scripts/debugging/llm/` | LLM/Gemini debugging | 3 |
| `/scripts/debugging/performance/` | Performance testing | 3 |
| `/scripts/debugging/charts/` | Chart generation debugging | 3 |
| `/scripts/debugging/discord/` | Discord integration debugging | 3 |
| `/scripts/debugging/feeds/` | Data feed debugging | 5 |
| `/scripts/debugging/classification/` | Classification debugging | 5 |
| `/scripts/debugging/integration/` | Integration testing | 4 |
| `/scripts/debugging/misc/` | Miscellaneous debugging | 15 |
| `/scripts/archive/` | Deprecated scripts | 8 |

**Total:** 81 files moved, 2 kept at root, 8 archived

---

## Migration Plan

### Phase 1: Create Directory Structure (5 minutes)

```bash
# Navigate to project root
cd /home/user/catalyst-bot

# Create new directory structure
mkdir -p scripts/analysis/{moa,performance,api,alerts}
mkdir -p scripts/data
mkdir -p scripts/maintenance
mkdir -p scripts/debugging/{fibonacci,llm,performance,charts,discord,feeds,classification,integration,misc}
mkdir -p scripts/archive
```

### Phase 2: Move Analysis Scripts (10 minutes)

```bash
# MOA analysis workflow
mv analyze_moa_data.py scripts/analysis/moa/
mv apply_safe_recommendations.py scripts/analysis/moa/
mv discover_keywords_now.py scripts/analysis/moa/
mv extract_moa_keywords.py scripts/analysis/moa/
mv merge_classified_keywords.py scripts/analysis/moa/
mv quick_merge_keywords.py scripts/analysis/moa/
mv show_recommendations_final.py scripts/analysis/moa/
mv validate_recommendations.py scripts/analysis/moa/

# Performance analysis
mv analyze_latency.py scripts/analysis/performance/
mv analyze_slowdown.py scripts/analysis/performance/
mv analyze_today.py scripts/analysis/performance/

# API analysis
mv analyze_dec9_api.py scripts/analysis/api/
mv analyze_dec9_llm.py scripts/analysis/api/
mv analyze_tiingo_responses.py scripts/analysis/api/

# Alert analysis
mv analyze_todays_alerts.py scripts/analysis/alerts/
mv analyze_recommendation_quality.py scripts/analysis/alerts/
mv analyze_embed3.py scripts/analysis/alerts/
```

### Phase 3: Move Data Processing Scripts (5 minutes)

```bash
mv backfill_with_classification.py scripts/data/
mv convert_sec_tickers.py scripts/data/
mv diagnose_na_items.py scripts/data/
mv extract_rejections.py scripts/data/
mv investigate_na_tickers.py scripts/data/
mv lookup_high_score_items.py scripts/data/
mv moa_backfill_14days.py scripts/data/
mv parse_rejections.py scripts/data/
mv rejection_report.py scripts/data/
```

### Phase 4: Move Maintenance Scripts (5 minutes)

```bash
mv fix_flake8.py scripts/maintenance/
mv fix_all_flake8.py scripts/maintenance/
mv fix_missing_keywords.py scripts/maintenance/
mv fix_webhook_env.py scripts/maintenance/
mv verify_env.py scripts/maintenance/
mv test_imports_final.py scripts/maintenance/
```

### Phase 5: Move Debugging Scripts (20 minutes)

```bash
# Fibonacci debugging
mv test_fibonacci_chart.py scripts/debugging/fibonacci/
mv test_fibonacci_integration.py scripts/debugging/fibonacci/
mv test_fibonacci_standalone.py scripts/debugging/fibonacci/

# LLM/Gemini debugging
mv test_gemini_direct.py scripts/debugging/llm/
mv test_gemini_edge_cases.py scripts/debugging/llm/
mv test_gemini_markdown_fix.py scripts/debugging/llm/

# Performance testing
mv test_p2_async_safe_seen_store.py scripts/debugging/performance/
mv test_p3_lru_cache_seen_store.py scripts/debugging/performance/
mv test_p4_price_prefilter.py scripts/debugging/performance/

# Chart debugging
mv test_chart_gen.py scripts/debugging/charts/
mv test_volume_profile_bars.py scripts/debugging/charts/
mv test_volume_profile_bars_synthetic.py scripts/debugging/charts/

# Discord debugging
mv test_discord_alert.py scripts/debugging/discord/
mv test_discord_upload.py scripts/debugging/discord/
mv test_discord_webhook.py scripts/debugging/discord/

# Feed debugging
mv test_analyst_sentiment.py scripts/debugging/feeds/
mv test_analyst_sentiment_mock.py scripts/debugging/feeds/
mv test_google_trends.py scripts/debugging/feeds/
mv test_google_trends_unit.py scripts/debugging/feeds/
mv test_short_interest_sentiment.py scripts/debugging/feeds/

# Classification debugging
mv test_badges_simple.py scripts/debugging/classification/
mv test_bulletproof_patterns.py scripts/debugging/classification/
mv test_fast_classify.py scripts/debugging/classification/
mv test_final_patterns.py scripts/debugging/classification/
mv test_retrospective_patterns.py scripts/debugging/classification/

# Integration testing
mv test_closed_loop.py scripts/debugging/integration/
mv test_enhanced_heartbeat.py scripts/debugging/integration/
mv test_negative_alerts.py scripts/debugging/integration/
mv test_positive_quick.py scripts/debugging/integration/

# Miscellaneous
mv test_broker_connection.py scripts/debugging/misc/
mv test_clov_specific.py scripts/debugging/misc/
mv test_dedup_quick.py scripts/debugging/misc/
mv test_dedup_sec_fix.py scripts/debugging/misc/
mv test_divergence.py scripts/debugging/misc/
mv test_extended_hours.py scripts/debugging/misc/
mv test_float_manual.py scripts/debugging/misc/
mv test_llm_service.py scripts/debugging/misc/
mv test_negative_threshold_bypass.py scripts/debugging/misc/
mv test_news_velocity.py scripts/debugging/misc/
mv test_poc_simple.py scripts/debugging/misc/
mv test_poc_vah_val_lines.py scripts/debugging/misc/
mv test_position_management.py scripts/debugging/misc/
mv test_premarket_sentiment.py scripts/debugging/misc/
mv test_sec_cache_nullable_ticker.py scripts/debugging/misc/
mv test_sec_llm_summary.py scripts/debugging/misc/
mv test_sec_processor.py scripts/debugging/misc/
mv test_verbose.py scripts/debugging/misc/
```

### Phase 6: Archive Duplicates (5 minutes)

```bash
# Create archive README
cat > scripts/archive/ARCHIVE_README.md << 'EOF'
# Archived Scripts

This directory contains scripts that have been superseded by newer versions.
These files are kept for historical reference but should not be used.

## Superseded Files

| Archived File | Superseded By | Reason |
|---------------|---------------|--------|
| show_recommendations.py | show_recommendations_final.py | Less detailed output |
| show_recs_debug.py | show_recommendations_final.py | Debug-only version |
| analyze_embed.py | analyze_embed3.py | Only checks first 10 fields |
| test_imports.py | test_imports_final.py | Early iteration |
| test_imports_simple.py | test_imports_final.py | Missing features |
| test_imports_agent4.py | test_imports_final.py | Incomplete |
| check_env.py | verify_env.py | Too minimal |
| multi_window_analysis_poc.py | (none) | Old POC, never productionized |

These files can be safely deleted after 30 days if no issues arise.
EOF

# Move duplicates to archive
mv show_recommendations.py scripts/archive/
mv show_recs_debug.py scripts/archive/
mv analyze_embed.py scripts/archive/
mv test_imports.py scripts/archive/
mv test_imports_simple.py scripts/archive/
mv test_imports_agent4.py scripts/archive/
mv check_env.py scripts/archive/
mv multi_window_analysis_poc.py scripts/archive/
```

### Phase 7: Update Path References (15 minutes)

Check for any hardcoded references to these scripts:

```bash
# Search for references in documentation
grep -r "python .*\.py" docs/ README*.md

# Search for references in shell scripts
grep -r "python .*\.py" *.sh scripts/*.sh 2>/dev/null

# Search for references in Python scripts
grep -r "subprocess.*python.*\.py" src/ scripts/

# Search for references in CI/CD
grep -r "python .*\.py" .github/ 2>/dev/null
```

**Action:** Update any references found to use new paths.

### Phase 8: Verify No Breakage (10 minutes)

```bash
# Run import validation
python scripts/maintenance/test_imports_final.py

# Run existing tests
python -m pytest tests/ -v

# Check that main entry point still works
python main.py --help

# Verify common scripts still work
python scripts/maintenance/verify_env.py
python scripts/analysis/moa/show_recommendations_final.py 2>/dev/null || echo "OK if no data"
```

### Phase 9: Git Commit (5 minutes)

```bash
# Add all changes
git add .

# Commit with detailed message
git commit -m "refactor: organize 89 root-level scripts into /scripts/ directory structure

- Move 11 analysis scripts to /scripts/analysis/ (moa, performance, api, alerts)
- Move 51 test scripts to /scripts/debugging/ (organized by feature)
- Move 9 data scripts to /scripts/data/
- Move 6 maintenance scripts to /scripts/maintenance/
- Archive 8 duplicate/superseded scripts to /scripts/archive/
- Keep __init__.py and main.py at root (legitimate top-level files)

Benefits:
- Clear organization by purpose
- Easy to find relevant scripts
- Duplicates identified and archived
- Maintains backward compatibility

See: docs/deduplication/05-WAVE-ROOT-SCRIPTS.md"
```

---

## Risk Assessment

### Low Risk

✅ **No production code affected**
- All files being moved are scripts, not library code
- Main entry points (`main.py`, `__init__.py`) stay at root
- `/src/` directory is untouched

✅ **No breaking changes to imports**
- These scripts don't import each other
- They're standalone diagnostic/utility scripts
- Moving them doesn't affect module paths in `/src/`

✅ **Easy rollback**
- Git makes it trivial to revert if needed
- All files preserved (just moved)
- Archive directory provides safety net for "deleted" files

### Medium Risk

⚠️ **Potential hardcoded paths**
- Some scripts may reference each other by path
- Documentation may reference old paths
- CI/CD pipelines may run specific scripts

**Mitigation:** Phase 7 searches for all references and updates them.

⚠️ **Developer muscle memory**
- Developers may be used to running scripts from root
- Tab completion patterns will change

**Mitigation:** Update documentation and communicate changes.

### Minimal Risk

The only real risk is breaking a CI/CD pipeline or documented workflow that references these scripts. The search in Phase 7 should catch all of these.

---

## Verification Plan

### Automated Verification

1. **Import Test**
   ```bash
   python scripts/maintenance/test_imports_final.py
   ```
   Should show 100% health score.

2. **Pytest Suite**
   ```bash
   python -m pytest tests/ -v
   ```
   All tests should pass.

3. **Main Entry Point**
   ```bash
   python main.py --help
   ```
   Should display help without errors.

### Manual Verification

1. **Check Directory Structure**
   ```bash
   tree scripts/ -L 2
   ```
   Should match proposed structure.

2. **Verify File Counts**
   ```bash
   find scripts/ -name "*.py" | wc -l  # Should be ~81
   ls *.py | wc -l                      # Should be 2 (__init__.py, main.py)
   ```

3. **Test Sample Scripts**
   ```bash
   # Test a script from each category
   python scripts/maintenance/verify_env.py
   python scripts/analysis/moa/show_recommendations_final.py
   python scripts/debugging/misc/test_verbose.py
   ```

4. **Check for Broken Paths**
   ```bash
   # Search for any remaining references to moved files at root
   grep -r "python analyze_" . --exclude-dir=.git --exclude-dir=scripts
   grep -r "python test_" . --exclude-dir=.git --exclude-dir=scripts
   ```

### Success Criteria

- ✅ All 89 files accounted for (81 moved, 2 kept at root, 8 archived, -2 duplicate deletions)
- ✅ Import validation passes
- ✅ Pytest suite passes
- ✅ No broken path references found
- ✅ Documentation updated with new paths
- ✅ Git history preserved (files moved, not deleted/recreated)

---

## Recommendations

### Immediate Actions (Required)

1. **Execute migration plan** following Phases 1-9
2. **Update documentation** with new script locations
3. **Communicate to team** about new structure

### Short-term Actions (1 week)

1. **Add README.md to each scripts/ subdirectory** explaining purpose
2. **Create quick reference guide** for commonly used scripts
3. **Update any CI/CD pipelines** to use new paths

### Long-term Actions (1 month)

1. **Delete archived files** after 30-day grace period if no issues
2. **Consider converting debugging scripts** to proper pytest tests
3. **Establish naming conventions** for future scripts
4. **Add pre-commit hook** to prevent new root-level scripts

### Script Naming Convention (Future)

To prevent future root clutter:

```
scripts/
├── analysis/      # analyze_*.py, report_*.py
├── data/          # extract_*, convert_*, process_*
├── maintenance/   # fix_*, verify_*, check_*
├── debugging/     # test_* (ad-hoc, not pytest)
└── archive/       # deprecated scripts
```

**Rule:** New scripts must go in appropriate `/scripts/` subdirectory, never at root.

---

## Alternative Approaches Considered

### Alternative 1: Delete All Duplicates Immediately

**Pros:** Cleaner, simpler
**Cons:** Risk of deleting something still referenced
**Decision:** Archive first, delete after grace period

### Alternative 2: Move Everything to `/tools/`

**Pros:** Simpler structure (one directory)
**Cons:** Still cluttered, hard to find things
**Decision:** Use categorized subdirectories for better organization

### Alternative 3: Convert All to Pytest Tests

**Pros:** Proper test infrastructure
**Cons:** Many scripts aren't really tests (analysis, data processing)
**Decision:** Only convert actual test scripts; keep utilities as scripts

### Alternative 4: Leave Everything at Root

**Pros:** No work required
**Cons:** Organizational chaos continues
**Decision:** Not viable - defeats the purpose of deduplication project

---

## Appendix A: Quick Reference

### Most Commonly Used Scripts (After Migration)

```bash
# Environment validation
python scripts/maintenance/verify_env.py

# Import health check
python scripts/maintenance/test_imports_final.py

# MOA recommendation workflow
python scripts/analysis/moa/analyze_moa_data.py
python scripts/analysis/moa/show_recommendations_final.py
python scripts/analysis/moa/apply_safe_recommendations.py

# Performance diagnostics
python scripts/analysis/performance/analyze_today.py
python scripts/analysis/performance/analyze_latency.py

# Alert analysis
python scripts/analysis/alerts/analyze_todays_alerts.py
```

### Directory Cheat Sheet

| Need to... | Look in... |
|------------|------------|
| Analyze system performance | `/scripts/analysis/performance/` |
| Analyze MOA data | `/scripts/analysis/moa/` |
| Analyze API responses | `/scripts/analysis/api/` |
| Debug a specific feature | `/scripts/debugging/{feature}/` |
| Process/transform data | `/scripts/data/` |
| Validate environment | `/scripts/maintenance/` |
| Find old deprecated script | `/scripts/archive/` |

---

## Appendix B: File Migration Checklist

### Phase 1: Structure ✅
- [ ] Create `/scripts/analysis/` subdirectories
- [ ] Create `/scripts/data/`
- [ ] Create `/scripts/maintenance/`
- [ ] Create `/scripts/debugging/` subdirectories
- [ ] Create `/scripts/archive/`

### Phase 2: Analysis Scripts ✅
- [ ] Move 8 MOA scripts
- [ ] Move 3 performance scripts
- [ ] Move 3 API scripts
- [ ] Move 3 alert scripts

### Phase 3: Data Scripts ✅
- [ ] Move 9 data processing scripts

### Phase 4: Maintenance Scripts ✅
- [ ] Move 6 maintenance scripts

### Phase 5: Debugging Scripts ✅
- [ ] Move 3 Fibonacci scripts
- [ ] Move 3 LLM scripts
- [ ] Move 3 performance test scripts
- [ ] Move 3 chart scripts
- [ ] Move 3 Discord scripts
- [ ] Move 5 feed scripts
- [ ] Move 5 classification scripts
- [ ] Move 4 integration scripts
- [ ] Move 15 misc scripts

### Phase 6: Archive ✅
- [ ] Create ARCHIVE_README.md
- [ ] Archive 8 duplicate scripts

### Phase 7: Path Updates ✅
- [ ] Search and update documentation
- [ ] Search and update shell scripts
- [ ] Search and update CI/CD configs
- [ ] Search and update Python references

### Phase 8: Verification ✅
- [ ] Run import validation
- [ ] Run pytest suite
- [ ] Test main entry point
- [ ] Test sample scripts
- [ ] Verify file counts

### Phase 9: Finalization ✅
- [ ] Git commit with detailed message
- [ ] Update documentation
- [ ] Communicate to team
- [ ] Schedule 30-day archive deletion

---

## Appendix C: Before/After Comparison

### Before (Root Directory)

```
/home/user/catalyst-bot/
├── __init__.py
├── main.py
├── analyze_dec9_api.py
├── analyze_dec9_llm.py
├── analyze_embed.py
├── analyze_embed3.py
├── [... 83 more Python files ...]
├── data/
├── docs/
├── scripts/
│   ├── alert_layout_playground.py
│   └── [other existing scripts]
├── src/
└── tests/
```

**Problems:**
- 89 Python files at root
- Hard to find the right script
- Duplicates not obvious
- Mix of production, testing, and analysis code

### After (Organized Structure)

```
/home/user/catalyst-bot/
├── __init__.py                    # Package init
├── main.py                        # CLI entry point
├── data/                          # Data files
├── docs/                          # Documentation
├── scripts/                       # ALL SCRIPTS HERE
│   ├── analysis/                  # Analysis scripts
│   │   ├── moa/                   # 8 MOA workflow scripts
│   │   ├── performance/           # 3 performance scripts
│   │   ├── api/                   # 3 API analysis scripts
│   │   └── alerts/                # 3 alert analysis scripts
│   ├── data/                      # 9 data processing scripts
│   ├── maintenance/               # 6 maintenance scripts
│   ├── debugging/                 # 51 debugging scripts (organized)
│   │   ├── fibonacci/             # 3 scripts
│   │   ├── llm/                   # 3 scripts
│   │   ├── performance/           # 3 scripts
│   │   ├── charts/                # 3 scripts
│   │   ├── discord/               # 3 scripts
│   │   ├── feeds/                 # 5 scripts
│   │   ├── classification/        # 5 scripts
│   │   ├── integration/           # 4 scripts
│   │   └── misc/                  # 15 scripts
│   ├── archive/                   # 8 deprecated scripts
│   └── [existing scripts]         # Scripts already there
├── src/                           # Source code (unchanged)
└── tests/                         # Pytest tests (unchanged)
```

**Benefits:**
- Clean root with only 2 legitimate Python files
- Clear organization by purpose
- Easy to find relevant scripts
- Duplicates identified and archived
- Professional project structure

---

**End of WAVE 5 Documentation**

**Last Updated:** 2025-12-14
**Next Review:** After migration completion
