# Manual Capture Enhancement - Implementation Plan

> **Status**: DRAFT - Pending Review
> **Created**: 2026-01-14
> **Author**: Claude Code
> **Estimated Effort**: 20-25 hours total

---

## Executive Summary

The Manual Capture feature allows users to submit missed trading opportunities via Discord screenshots. Vision LLM extracts data, which flows to MOA (Missed Opportunities Analyzer) for learning.

**Current Problem**: The pipeline has critical gaps that prevent MOA from learning effectively:
1. Vision keywords don't map to classifier categories
2. All captures labeled "MISSED_COMPLETELY" (not actionable)
3. No way to correct extraction errors
4. Price data not validated against market data

**Solution**: Implement keyword mapping, correction UI, rejection taxonomy, and data validation.

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Implementation Phases](#2-implementation-phases)
3. [Phase 0: Critical Fixes](#3-phase-0-critical-fixes)
4. [Phase 1: Quality Improvements](#4-phase-1-quality-improvements)
5. [Phase 2: Learning Amplification](#5-phase-2-learning-amplification)
6. [Phase 3: Advanced Features](#6-phase-3-advanced-features)
7. [Testing Strategy](#7-testing-strategy)
8. [Parallel Execution Guide](#8-parallel-execution-guide)
9. [Progress Tracking](#9-progress-tracking)
10. [Rollback Plan](#10-rollback-plan)
11. [Claude Code Prompts](#11-claude-code-prompts)

---

## 1. Current State Analysis

### Data Flow (Current)
```
User posts screenshot → Vision LLM extracts data → Save to manual_captures
                                                          ↓
                                            outcome_tracker exports to outcomes.jsonl
                                                          ↓
                                            MOA analyzes (but keywords don't match!)
```

### Key Files
| File | Purpose | Lines |
|------|---------|-------|
| `src/catalyst_bot/moa/discord_listener.py` | Discord message handling | 338 |
| `src/catalyst_bot/moa/manual_capture.py` | Capture processing | 624 |
| `src/catalyst_bot/moa/vision_analyzer.py` | Vision LLM prompts | 382 |
| `src/catalyst_bot/moa/outcome_tracker.py` | Price tracking & export | 544 |
| `src/catalyst_bot/moa/database.py` | Database schema | 350 |
| `src/catalyst_bot/config.py` | Keyword categories | ~200 (lines 1381-1580) |
| `src/catalyst_bot/moa_historical_analyzer.py` | MOA analysis | 1993 |

### Critical Gaps Identified

| Gap | Impact | Severity |
|-----|--------|----------|
| Keywords not mapped to categories | MOA can't learn from captures | **CRITICAL** |
| No correction mechanism | Bad extractions stay wrong | **HIGH** |
| "MISSED_COMPLETELY" only reason | Can't tune specific filters | **HIGH** |
| Price data not validated | Noisy return calculations | **MEDIUM** |
| No weight amplification | Manual captures undervalued | **MEDIUM** |

---

## 2. Implementation Phases

### Overview

| Phase | Focus | Tickets | Effort | Parallelizable |
|-------|-------|---------|--------|----------------|
| **P0** | Critical Fixes | MC-01, MC-02 | 7h | Yes (2 tracks) |
| **P1** | Quality | MC-03, MC-04 | 4h | Yes (2 tracks) |
| **P2** | Learning | MC-05, MC-06 | 3h | No |
| **P3** | Advanced | MC-07, MC-08, MC-09 | 10h | Yes (3 tracks) |

### Dependency Graph
```
MC-01 (Keyword Mapper) ──────────────────────────────┐
                                                     ├──► MC-05 (Weight Amplification)
MC-02 (Correction UI) ───► MC-04 (Price Validation) ─┤
                                                     │
MC-03 (Rejection Taxonomy) ──────────────────────────┘

MC-06 (Alert Cross-Reference) ─── Independent
MC-07 (Bulk Capture) ─── Independent
MC-08 (Historical Backfill) ─── Depends on MC-04
MC-09 (Temporal Analysis) ─── Depends on MC-05
```

---

## 3. Phase 0: Critical Fixes

### MC-01: Keyword Category Mapper

**Priority**: P0 (Critical)
**Effort**: 3 hours
**Parallelizable**: Yes (Track A)

#### Description
Create a mapping layer that converts vision-extracted freeform keywords to classifier category names. This is essential for MOA to learn from manual captures.

#### Files to Create/Modify
- **CREATE**: `src/catalyst_bot/moa/keyword_mapper.py`
- **MODIFY**: `src/catalyst_bot/moa/manual_capture.py` (lines 220-250)

#### Implementation Details

**New File: `keyword_mapper.py`**
```python
"""
Keyword Category Mapper.

Maps freeform vision-extracted keywords to classifier category names.
Essential for MOA learning from manual captures.
"""

import re
from typing import Dict, List, Set, Tuple
from ..config import get_settings
from ..logging_utils import get_logger

log = get_logger("moa.keyword_mapper")

# Cache for compiled patterns
_category_patterns: Dict[str, List[re.Pattern]] = {}


def _compile_category_patterns() -> Dict[str, List[re.Pattern]]:
    """Compile regex patterns for each keyword category."""
    global _category_patterns

    if _category_patterns:
        return _category_patterns

    settings = get_settings()
    categories = getattr(settings, "keyword_categories", {})

    for category, keywords in categories.items():
        patterns = []
        for kw in keywords:
            # Create case-insensitive pattern with word boundaries
            pattern = re.compile(r'\b' + re.escape(kw.lower()) + r'\b', re.IGNORECASE)
            patterns.append(pattern)
        _category_patterns[category] = patterns

    log.info("keyword_patterns_compiled categories=%d", len(_category_patterns))
    return _category_patterns


def map_keywords_to_categories(
    vision_keywords: List[str],
    headline: str = "",
    include_scores: bool = False
) -> List[str] | List[Tuple[str, float]]:
    """
    Map vision-extracted keywords to classifier categories.

    Args:
        vision_keywords: Freeform keywords from vision LLM
        headline: Article headline for additional matching
        include_scores: If True, return (category, confidence) tuples

    Returns:
        List of matched category names, or (category, confidence) tuples
    """
    patterns = _compile_category_patterns()

    # Combine keywords and headline for matching
    text_to_match = " ".join(vision_keywords).lower()
    if headline:
        text_to_match += " " + headline.lower()

    matches: Dict[str, int] = {}  # category -> match count

    for category, category_patterns in patterns.items():
        match_count = 0
        for pattern in category_patterns:
            if pattern.search(text_to_match):
                match_count += 1

        if match_count > 0:
            matches[category] = match_count

    if not matches:
        log.debug("no_category_matches keywords=%s", vision_keywords[:3])
        return []

    # Sort by match count (most matches first)
    sorted_matches = sorted(matches.items(), key=lambda x: x[1], reverse=True)

    if include_scores:
        # Normalize scores (max matches = 1.0)
        max_matches = sorted_matches[0][1]
        return [(cat, count / max_matches) for cat, count in sorted_matches]

    return [cat for cat, _ in sorted_matches]


def get_primary_category(
    vision_keywords: List[str],
    vision_catalyst_type: str,
    headline: str = ""
) -> str:
    """
    Get the primary (best matching) category for a capture.

    Falls back to vision_catalyst_type if no mapping found.

    Args:
        vision_keywords: Freeform keywords from vision
        vision_catalyst_type: Catalyst type from vision (fallback)
        headline: Article headline

    Returns:
        Best matching category name
    """
    matches = map_keywords_to_categories(vision_keywords, headline, include_scores=True)

    if matches:
        primary = matches[0][0]
        confidence = matches[0][1]
        log.debug(
            "primary_category_mapped category=%s confidence=%.2f vision_type=%s",
            primary, confidence, vision_catalyst_type
        )
        return primary

    # Fallback: normalize vision catalyst type
    normalized = vision_catalyst_type.lower().replace(" ", "_")

    # Map common vision types to categories
    vision_to_category = {
        "partnership": "partnership",
        "fda": "fda",
        "clinical": "clinical",
        "earnings": "earnings",
        "guidance": "guidance",
        "acquisition": "acquisition",
        "contract": "tech_contracts",
        "discovery": "energy_discovery",
        "crypto": "crypto_blockchain",
        "blockchain": "crypto_blockchain",
        "mining": "mining_resources",
        "compliance": "compliance",
        "institutional": "activist_institutional",
        "other": "other",
    }

    return vision_to_category.get(normalized, normalized)


def extract_matched_keywords(
    vision_keywords: List[str],
    headline: str = ""
) -> Dict[str, List[str]]:
    """
    Extract which specific keywords matched each category.

    Useful for debugging and user feedback.

    Returns:
        {category: [matched_keywords]}
    """
    patterns = _compile_category_patterns()
    text_to_match = " ".join(vision_keywords).lower()
    if headline:
        text_to_match += " " + headline.lower()

    results: Dict[str, List[str]] = {}

    for category, category_patterns in patterns.items():
        matched = []
        for pattern in category_patterns:
            match = pattern.search(text_to_match)
            if match:
                matched.append(match.group())

        if matched:
            results[category] = matched

    return results
```

**Modify: `manual_capture.py` (in `save_manual_capture` function)**
```python
# After line 220, add keyword mapping:
from .keyword_mapper import map_keywords_to_categories, get_primary_category

# Map vision keywords to categories for MOA learning
if article_analysis and article_analysis.keywords:
    mapped_categories = map_keywords_to_categories(
        vision_keywords=article_analysis.keywords,
        headline=article_analysis.headline or ""
    )

    # Store both: original vision keywords AND mapped categories
    # MOA uses mapped_categories, humans see original keywords
    keywords_for_moa = json.dumps(mapped_categories)
    keywords_original = json.dumps(article_analysis.keywords)

    # Update catalyst_type to mapped primary category
    if article_analysis.catalyst_type:
        mapped_catalyst = get_primary_category(
            vision_keywords=article_analysis.keywords,
            vision_catalyst_type=article_analysis.catalyst_type,
            headline=article_analysis.headline or ""
        )
    else:
        mapped_catalyst = mapped_categories[0] if mapped_categories else "other"
```

#### Acceptance Criteria
- [ ] `keyword_mapper.py` created with all functions
- [ ] `map_keywords_to_categories()` returns classifier category names
- [ ] `get_primary_category()` provides single best match
- [ ] `manual_capture.py` uses mapper before database save
- [ ] Keywords stored in MOA-compatible format

#### Smoke Tests
```bash
# Test 1: Basic mapping
python -c "
from catalyst_bot.moa.keyword_mapper import map_keywords_to_categories
result = map_keywords_to_categories(['FDA approval', 'breakthrough therapy'])
assert 'fda' in result, f'Expected fda in {result}'
print('PASS: FDA keywords mapped correctly')
"

# Test 2: Crypto/blockchain mapping
python -c "
from catalyst_bot.moa.keyword_mapper import map_keywords_to_categories
result = map_keywords_to_categories(['Bitcoin', 'crypto partnership'])
assert 'crypto_blockchain' in result, f'Expected crypto_blockchain in {result}'
print('PASS: Crypto keywords mapped correctly')
"

# Test 3: Primary category selection
python -c "
from catalyst_bot.moa.keyword_mapper import get_primary_category
result = get_primary_category(
    ['Partners with Crypto.com', 'prediction markets'],
    'partnership',
    'High Roller Partners with Crypto.com'
)
assert result in ['crypto_blockchain', 'partnership'], f'Got {result}'
print(f'PASS: Primary category = {result}')
"
```

#### Pre-Commit Test
Add to `tests/test_moa_keyword_mapper.py`:
```python
"""Tests for keyword category mapper."""
import pytest
from catalyst_bot.moa.keyword_mapper import (
    map_keywords_to_categories,
    get_primary_category,
    extract_matched_keywords,
)


class TestKeywordMapper:
    def test_fda_keywords_map_to_fda_category(self):
        result = map_keywords_to_categories(["FDA approval", "drug approved"])
        assert "fda" in result

    def test_clinical_keywords_map_to_clinical_category(self):
        result = map_keywords_to_categories(["phase 3 results", "trial data"])
        assert "clinical" in result

    def test_crypto_keywords_map_to_crypto_blockchain(self):
        result = map_keywords_to_categories(["Bitcoin", "blockchain partnership"])
        assert "crypto_blockchain" in result

    def test_empty_keywords_return_empty_list(self):
        result = map_keywords_to_categories([])
        assert result == []

    def test_no_match_returns_empty_list(self):
        result = map_keywords_to_categories(["random words here"])
        assert result == []

    def test_headline_adds_matching_context(self):
        # Keywords alone might not match, but headline helps
        result = map_keywords_to_categories(
            ["company news"],
            headline="FDA Approves New Drug Treatment"
        )
        assert "fda" in result

    def test_primary_category_returns_best_match(self):
        result = get_primary_category(
            ["FDA breakthrough", "clinical trial"],
            "clinical",
            "FDA Grants Breakthrough Designation"
        )
        assert result == "fda"  # FDA has more matches

    def test_primary_category_fallback_to_vision_type(self):
        result = get_primary_category(
            ["some random keywords"],
            "earnings",
            "Company Reports Results"
        )
        assert result == "earnings"  # Falls back to vision type

    def test_extract_matched_keywords_shows_what_matched(self):
        result = extract_matched_keywords(
            ["FDA approval granted", "breakthrough therapy"],
            "Drug Gets FDA Nod"
        )
        assert "fda" in result
        assert len(result["fda"]) > 0
```

---

### MC-02: Correction UI (Buttons + Modal)

**Priority**: P0 (Critical)
**Effort**: 4 hours
**Parallelizable**: Yes (Track B)

#### Description
Add buttons to capture confirmation messages allowing users to approve, correct, or reject extractions. Clicking "Correct" opens a modal with pre-filled fields.

#### Files to Create/Modify
- **CREATE**: `src/catalyst_bot/moa/correction_handler.py`
- **MODIFY**: `src/catalyst_bot/moa/discord_listener.py`
- **MODIFY**: `src/catalyst_bot/moa/manual_capture.py`
- **MODIFY**: `src/catalyst_bot/moa/database.py` (add correction tracking columns)

#### Database Schema Changes
```sql
-- Add to manual_captures table
ALTER TABLE manual_captures ADD COLUMN corrected_by TEXT;
ALTER TABLE manual_captures ADD COLUMN correction_count INTEGER DEFAULT 0;
ALTER TABLE manual_captures ADD COLUMN last_corrected_at TIMESTAMP;
ALTER TABLE manual_captures ADD COLUMN keywords_original TEXT;  -- Vision's raw extraction
ALTER TABLE manual_captures ADD COLUMN approved_at TIMESTAMP;
ALTER TABLE manual_captures ADD COLUMN approved_by TEXT;
```

#### Implementation Details

**New File: `correction_handler.py`**
See detailed implementation in Claude Code Prompt MC-02 below.

Key components:
- `CorrectionModal` class extending `discord.ui.Modal`
- `CaptureConfirmationView` class with buttons
- `handle_capture_interaction()` router function
- `apply_capture_corrections()` database function
- Input validation and error handling

**Modify: `discord_listener.py`**
```python
# In ManualCaptureClient class, add:
async def on_interaction(self, interaction: discord.Interaction):
    """Handle button/modal interactions."""
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("capture_"):
            from .correction_handler import handle_capture_interaction
            await handle_capture_interaction(interaction)

# In on_message(), change reply to use View:
from .correction_handler import CaptureConfirmationView

# Instead of plain reply:
view = CaptureConfirmationView(capture_id=result["record_id"])
embed = format_confirmation_embed(result)
await message.reply(embed=embed, view=view)
```

#### Acceptance Criteria
- [ ] Confirmation message shows 3 buttons: Approve, Correct, Reject
- [ ] Clicking "Correct" opens modal with pre-filled values
- [ ] Modal validates input (ticker format, price range, etc.)
- [ ] Corrections update database and edit original message
- [ ] Approve removes buttons and adds approval badge
- [ ] Reject deletes the capture

#### Smoke Tests
```bash
# Test 1: View renders without error
python -c "
from catalyst_bot.moa.correction_handler import CaptureConfirmationView
view = CaptureConfirmationView(capture_id=1)
assert len(view.children) == 3, 'Expected 3 buttons'
print('PASS: View has 3 buttons')
"

# Test 2: Correction parsing validates correctly
python -c "
from catalyst_bot.moa.correction_handler import parse_corrections
result = parse_corrections({
    'ticker': 'AAPL',
    'catalyst_type': 'fda',
    'entry_price': '5.50',
    'peak_price': '8.25',
})
assert result['is_valid'], f'Validation failed: {result[\"errors\"]}'
print('PASS: Valid corrections parsed')
"

# Test 3: Invalid input caught
python -c "
from catalyst_bot.moa.correction_handler import parse_corrections
result = parse_corrections({
    'ticker': 'TOOLONG',  # Invalid: >5 chars
    'entry_price': '-5.00',  # Invalid: negative
})
assert not result['is_valid'], 'Should have validation errors'
assert len(result['errors']) >= 2
print(f'PASS: Caught {len(result[\"errors\"])} validation errors')
"
```

#### Pre-Commit Test
Add to `tests/test_moa_correction_handler.py`:
```python
"""Tests for correction handler."""
import pytest
from catalyst_bot.moa.correction_handler import (
    parse_corrections,
    CaptureConfirmationView,
)


class TestCorrectionParsing:
    def test_valid_ticker_accepted(self):
        result = parse_corrections({"ticker": "AAPL"})
        assert result["is_valid"]
        assert result["corrections"]["ticker"] == "AAPL"

    def test_lowercase_ticker_uppercased(self):
        result = parse_corrections({"ticker": "aapl"})
        assert result["corrections"]["ticker"] == "AAPL"

    def test_invalid_ticker_rejected(self):
        result = parse_corrections({"ticker": "TOOLONG123"})
        assert not result["is_valid"]
        assert any("ticker" in e.lower() for e in result["errors"])

    def test_valid_prices_accepted(self):
        result = parse_corrections({
            "entry_price": "5.50",
            "peak_price": "10.25"
        })
        assert result["is_valid"]
        assert result["corrections"]["entry_price"] == 5.50
        assert result["corrections"]["peak_price"] == 10.25

    def test_negative_price_rejected(self):
        result = parse_corrections({"entry_price": "-5.00"})
        assert not result["is_valid"]

    def test_valid_catalyst_types_accepted(self):
        for cat in ["fda", "clinical", "earnings", "crypto"]:
            result = parse_corrections({"catalyst_type": cat})
            assert result["is_valid"], f"Failed for {cat}"

    def test_invalid_catalyst_type_rejected(self):
        result = parse_corrections({"catalyst_type": "invalid_type"})
        assert not result["is_valid"]

    def test_keywords_split_by_comma(self):
        result = parse_corrections({"keywords": "FDA, approval, drug"})
        assert result["is_valid"]
        assert result["corrections"]["keywords"] == ["FDA", "approval", "drug"]

    def test_too_many_keywords_rejected(self):
        keywords = ", ".join([f"kw{i}" for i in range(15)])  # 15 keywords
        result = parse_corrections({"keywords": keywords})
        assert not result["is_valid"]


class TestConfirmationView:
    def test_view_has_three_buttons(self):
        view = CaptureConfirmationView(capture_id=1)
        assert len(view.children) == 3

    def test_button_custom_ids_include_capture_id(self):
        view = CaptureConfirmationView(capture_id=42)
        custom_ids = [child.custom_id for child in view.children]
        assert all("42" in cid for cid in custom_ids)
```

---

## 4. Phase 1: Quality Improvements

### MC-03: Rejection Reason Taxonomy

**Priority**: P1
**Effort**: 2 hours
**Parallelizable**: Yes (Track A)

#### Description
Replace "MISSED_COMPLETELY" with specific rejection reasons to enable targeted threshold tuning.

#### Rejection Reason Categories
```python
REJECTION_REASONS = {
    # Bot saw and rejected
    "REJECTED_LOW_SCORE": "Score below threshold",
    "REJECTED_PRICE_FILTER": "Above price ceiling",
    "REJECTED_SENTIMENT": "Negative sentiment override",
    "REJECTED_DILUTION": "Flagged as dilutive",
    "REJECTED_SOURCE": "Low-tier source filtered",
    "REJECTED_STALE": "Article too old",

    # Bot never saw
    "MISSED_KEYWORDS": "No matching keywords",
    "MISSED_TICKER": "Ticker not extracted",
    "MISSED_FEED": "Not in any feed",
    "MISSED_COMPLETELY": "Unknown reason (fallback)",
}
```

#### Files to Modify
- **CREATE**: `src/catalyst_bot/moa/rejection_classifier.py`
- **MODIFY**: `src/catalyst_bot/moa/manual_capture.py`
- **MODIFY**: `src/catalyst_bot/moa/outcome_tracker.py`

#### Acceptance Criteria
- [ ] New rejection reasons defined and documented
- [ ] `classify_rejection_reason()` function analyzes capture context
- [ ] Rejection reason stored in database
- [ ] MOA analysis groups by rejection reason

---

### MC-04: Price Validation

**Priority**: P1
**Effort**: 2 hours
**Parallelizable**: Yes (Track B)

#### Description
Validate vision-extracted prices against actual OHLC data to reduce noise in return calculations.

#### Files to Modify
- **MODIFY**: `src/catalyst_bot/moa/manual_capture.py`
- **ADD FUNCTION**: `validate_price_extraction()`

#### Validation Rules
1. Peak price >= Entry price (swap if inverted)
2. Prices within daily OHLC range (±10% tolerance)
3. Calculated move matches vision pct_move (±5% tolerance)
4. Flag low-confidence extractions for review

---

## 5. Phase 2: Learning Amplification

### MC-05: Weight Amplification for Manual Captures

**Priority**: P2
**Effort**: 1 hour
**Depends On**: MC-01

#### Description
Apply 2x weight multiplier to manual captures in MOA analysis since they're user-curated high-quality signals.

#### Files to Modify
- **MODIFY**: `src/catalyst_bot/moa_historical_analyzer.py` (lines 277-341)

---

### MC-06: Alert Cross-Reference

**Priority**: P2
**Effort**: 2 hours
**Parallelizable**: Independent

#### Description
Check if bot alerted on submitted ticker within ±2 hours. Helps distinguish "bot saw but user missed" vs "bot completely missed".

---

## 6. Phase 3: Advanced Features

### MC-07: Bulk Capture

**Priority**: P3
**Effort**: 4 hours

Multi-screenshot upload for end-of-day batch capture.

---

### MC-08: Historical Backfill

**Priority**: P3
**Effort**: 6 hours
**Depends On**: MC-04

Add old missed opportunities with historical OHLC data.

---

### MC-09: Temporal Pattern Analysis

**Priority**: P3
**Effort**: 3 hours
**Depends On**: MC-05

Analyze best hours/days for catalysts.

---

## 7. Testing Strategy

### Unit Tests
- Located in `tests/test_moa_*.py`
- Run with: `pytest tests/test_moa_*.py -v`
- Coverage target: 80%+

### Integration Tests
```python
# tests/integration/test_manual_capture_flow.py

@pytest.mark.integration
async def test_full_capture_flow():
    """Test complete capture flow from Discord message to MOA export."""
    # 1. Simulate Discord message with image
    # 2. Verify vision extraction
    # 3. Verify keyword mapping
    # 4. Verify database save
    # 5. Verify outcome export includes capture
```

### E2E Tests
```bash
# Manual E2E test procedure

## Test 1: Basic Capture
1. Post screenshot to #missed-alerts
2. Verify bot responds with embed + buttons
3. Verify data in database:
   sqlite3 data/moa/rejected_tracking.db "SELECT * FROM manual_captures ORDER BY id DESC LIMIT 1"

## Test 2: Correction Flow
1. Submit capture with intentional error
2. Click "Correct Data" button
3. Fix values in modal
4. Verify database updated
5. Verify message edited

## Test 3: MOA Integration
1. Submit capture
2. Wait for outcome tracking (or manually trigger)
3. Export outcomes: python -c "from catalyst_bot.moa.outcome_tracker import export_outcomes_to_jsonl; export_outcomes_to_jsonl()"
4. Verify capture in outcomes.jsonl with mapped keywords
```

### Pre-Commit Hooks
Add to `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: local
    hooks:
      - id: test-moa-modules
        name: Test MOA modules
        entry: pytest tests/test_moa_*.py -v --tb=short
        language: system
        pass_filenames: false
        files: ^src/catalyst_bot/moa/
```

---

## 8. Parallel Execution Guide

### Phase 0 Parallel Tracks

**Track A (MC-01: Keyword Mapper)**
```
Agent prompt: "Implement MC-01 from MANUAL_CAPTURE_ENHANCEMENT_PLAN.md"
```

**Track B (MC-02: Correction UI)**
```
Agent prompt: "Implement MC-02 from MANUAL_CAPTURE_ENHANCEMENT_PLAN.md"
```

### Merge Point
After both tracks complete:
1. Run all tests: `pytest tests/test_moa_*.py -v`
2. Manual E2E test: Submit capture, verify buttons, test correction
3. Merge to main

### Phase 1 Parallel Tracks

**Track A (MC-03: Rejection Taxonomy)**
**Track B (MC-04: Price Validation)**

Can run in parallel after Phase 0 complete.

---

## 9. Progress Tracking

### TodoWrite Updates

Update the todo list after completing each ticket:

```python
# After completing MC-01:
TodoWrite([
    {"content": "MC-01: Keyword Category Mapper", "status": "completed", "activeForm": "Keyword mapper implemented"},
    {"content": "MC-02: Correction UI (Buttons + Modal)", "status": "in_progress", "activeForm": "Implementing correction UI"},
    {"content": "MC-03: Rejection Reason Taxonomy", "status": "pending", "activeForm": "Implementing rejection taxonomy"},
    {"content": "MC-04: Price Validation", "status": "pending", "activeForm": "Implementing price validation"},
    # ... rest of tickets
])
```

### Progress Log Format
After each ticket, add to `docs/IMPLEMENTATION_LOG.md`:
```markdown
## MC-01: Keyword Category Mapper
- **Status**: Complete
- **Completed**: 2026-01-15 10:30
- **Files Changed**:
  - Created: `src/catalyst_bot/moa/keyword_mapper.py`
  - Modified: `src/catalyst_bot/moa/manual_capture.py`
- **Tests Added**: `tests/test_moa_keyword_mapper.py` (8 tests)
- **Smoke Test Results**: All 3 passing
- **Notes**: Added fallback for unmatched keywords
```

---

## 10. Rollback Plan

### Feature Flags
```python
# In config.py
feature_manual_capture_v2: bool = _b("FEATURE_MANUAL_CAPTURE_V2", False)
feature_keyword_mapping: bool = _b("FEATURE_KEYWORD_MAPPING", True)
feature_correction_ui: bool = _b("FEATURE_CORRECTION_UI", True)
```

### Rollback Steps
1. Set feature flag to False in `.env`
2. Restart bot
3. Old behavior restored

### Database Rollback
New columns are additive - no data loss on rollback. To remove:
```sql
-- Only if needed (not recommended)
ALTER TABLE manual_captures DROP COLUMN corrected_by;
ALTER TABLE manual_captures DROP COLUMN correction_count;
-- etc.
```

---

## 11. Claude Code Prompts

### Prompt: Implement MC-01 (Keyword Mapper)

```
Implement the Keyword Category Mapper (MC-01) from docs/MANUAL_CAPTURE_ENHANCEMENT_PLAN.md

Tasks:
1. Create src/catalyst_bot/moa/keyword_mapper.py with:
   - map_keywords_to_categories() function
   - get_primary_category() function
   - extract_matched_keywords() function

2. Modify src/catalyst_bot/moa/manual_capture.py to use the mapper:
   - Import the mapper functions
   - Before saving to database, map vision keywords to categories
   - Store mapped_categories as the keywords field for MOA
   - Optionally store original keywords in keywords_original field

3. Create tests/test_moa_keyword_mapper.py with unit tests

4. Run smoke tests from the plan document

5. Update TodoWrite to mark MC-01 complete

Reference the detailed implementation in MANUAL_CAPTURE_ENHANCEMENT_PLAN.md for exact code.
```

### Prompt: Implement MC-02 (Correction UI)

```
Implement the Correction UI (MC-02) from docs/MANUAL_CAPTURE_ENHANCEMENT_PLAN.md

Tasks:
1. Add database columns for correction tracking:
   - corrected_by, correction_count, last_corrected_at
   - approved_at, approved_by
   - keywords_original

2. Create src/catalyst_bot/moa/correction_handler.py with:
   - CorrectionModal class (discord.ui.Modal)
   - CaptureConfirmationView class (discord.ui.View with 3 buttons)
   - parse_corrections() validation function
   - apply_capture_corrections() database function
   - handle_capture_interaction() router

3. Modify src/catalyst_bot/moa/discord_listener.py:
   - Add on_interaction handler for buttons
   - Update on_message to use CaptureConfirmationView

4. Modify src/catalyst_bot/moa/manual_capture.py:
   - Add format_confirmation_embed() function

5. Create tests/test_moa_correction_handler.py

6. Run smoke tests from the plan document

7. Update TodoWrite to mark MC-02 complete
```

### Prompt: Run All Phase 0 Tests

```
Run all tests for Phase 0 implementation:

1. Unit tests:
   pytest tests/test_moa_keyword_mapper.py tests/test_moa_correction_handler.py -v

2. Smoke tests from MANUAL_CAPTURE_ENHANCEMENT_PLAN.md (MC-01 and MC-02 sections)

3. Integration test:
   - Start the bot
   - Post a test screenshot to #missed-alerts
   - Verify:
     - Bot responds with embed + buttons
     - Keywords are mapped to categories in database
     - Clicking "Correct" opens modal
     - Corrections are saved

4. Report any failures with full error messages
```

---

## Appendix: File Reference

### Files to Create
| File | Ticket | Purpose |
|------|--------|---------|
| `src/catalyst_bot/moa/keyword_mapper.py` | MC-01 | Map vision keywords to categories |
| `src/catalyst_bot/moa/correction_handler.py` | MC-02 | Discord button/modal handling |
| `src/catalyst_bot/moa/rejection_classifier.py` | MC-03 | Classify rejection reasons |
| `tests/test_moa_keyword_mapper.py` | MC-01 | Unit tests |
| `tests/test_moa_correction_handler.py` | MC-02 | Unit tests |

### Files to Modify
| File | Tickets | Changes |
|------|---------|---------|
| `src/catalyst_bot/moa/manual_capture.py` | MC-01, MC-02, MC-03, MC-04 | Keyword mapping, embed formatting |
| `src/catalyst_bot/moa/discord_listener.py` | MC-02 | Add interaction handler |
| `src/catalyst_bot/moa/database.py` | MC-02 | Add correction columns |
| `src/catalyst_bot/moa/outcome_tracker.py` | MC-03 | Use new rejection reasons |
| `src/catalyst_bot/moa_historical_analyzer.py` | MC-05 | Weight amplification |
| `src/catalyst_bot/config.py` | All | Feature flags |

---

*Document Version: 1.0*
*Last Updated: 2026-01-14*
