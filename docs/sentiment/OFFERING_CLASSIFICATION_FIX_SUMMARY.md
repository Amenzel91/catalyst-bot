# SEC Offering Classification Fix - Summary Report

## Issue Description

Two offerings from October 28, 2025 had classification issues reported by the user:

### 1. PSEC (Prospect Capital Corporation)
**Title**: "Prospect Capital Corporation Announces Pricing of $167 Million 5.5% Oversubscribed Institutional Unsecured Notes Offering"

**User Feedback**: "the outline of the embed is green. negative alerts should be red. could you double check this type of offering too, maybe its good?"

**Analysis**: The bot was actually CORRECT - this is a **debt/notes offering** (unsecured notes), which does NOT dilute equity shareholders. Debt offerings should be treated as neutral to positive because:
- No dilution of existing shares
- Shows access to capital
- Oversubscribed = strong demand signal

**Status**: ✅ The green border was appropriate. However, the offering sentiment correction system was not being applied.

---

### 2. POET (POET Technologies)
**Title**: "POET Technologies Announces Closing of US$150 Million Oversubscribed Registered Direct Offering"

**User Feedback**: "is this negative? idk, the share price did flatline for the day. no pump whatsoever."

**Analysis**: This is an **equity offering CLOSING**, not an announcement. The bot was treating it as a negative alert (red border) because:
- The keyword "offering" triggered the "offering_negative" category
- ALL offerings were being marked as NEGATIVE regardless of stage
- **Closing = completion** of offering (no more dilution coming)
- Closings should be slightly positive (anti-dilutive, relief signal)

**Status**: ❌ Should have had a green/blue border (slightly positive), not red.

---

## Root Cause Analysis

### The Bug
The `offering_sentiment.py` module existed with sophisticated stage detection logic, but it was **NEVER IMPORTED OR USED** in `classify.py`. This meant:

1. All offerings triggered the "offering_negative" keyword category
2. All offerings were marked as `alert_type="NEGATIVE"`
3. All offerings got red borders regardless of:
   - Stage (announcement vs closing)
   - Type (equity vs debt)
   - Context (oversubscribed, etc.)

### The Code Issue

**Before (classify.py lines 857-879)**:
```python
# --- NEGATIVE KEYWORD DETECTION ---
negative_keywords = []
negative_keyword_categories = {
    "offering_negative",
    "warrant_negative",
    "dilution_negative",
    "distress_negative",
}

for category in hits:
    if category in negative_keyword_categories:
        negative_keywords.append(category)

alert_type = "N/A"
if negative_keywords and getattr(settings, "feature_negative_alerts", False):
    alert_type = "NEGATIVE"  # ALL offerings marked negative
    total_keyword_score = total_keyword_score * -2.0
```

**Missing Integration**:
- `offering_sentiment.py` was never imported
- `apply_offering_sentiment_correction()` was never called
- Stage detection (closing, announcement, pricing, upsize) was unused
- Debt vs equity distinction was not made

---

## The Fix

### Changes Made

#### 1. **offering_sentiment.py Enhancements**
- Added `is_debt_offering()` function to detect notes/bonds offerings
- Enhanced `apply_offering_sentiment_correction()` to check debt first
- Added "debt" stage with +0.3 sentiment (neutral/positive)
- Added debt offering keywords:
  - "notes offering", "unsecured notes", "secured notes"
  - "convertible notes", "debt offering", "bond offering"
  - "senior notes", "subordinated notes", "institutional notes"

#### 2. **classify.py Integration** (2 locations)
- Imported offering sentiment correction functions
- Added offering sentiment correction BEFORE negative alert detection
- Logic flow:
  1. Check if "offering_negative" in negative_keywords
  2. If yes, apply offering sentiment correction
  3. Detect stage: debt, closing, pricing, announcement, upsize
  4. If stage is "debt" or "closing" → remove from negative_keywords
  5. Update sentiment with corrected value
  6. Only mark as NEGATIVE if negative_keywords still has items

#### 3. **Border Color Logic** (alerts.py lines 1728-1731)
```python
if is_negative_alert:
    color = 0xFF0000  # Red for negative alerts
else:
    # Green/blue based on price movement or indicators
```

**Now**:
- Debt offerings → NOT negative alert → green/blue border
- Offering closings → NOT negative alert → green/blue border
- Dilutive offerings (announcement/pricing/upsize) → NEGATIVE alert → red border

---

## Offering Classification Rules

### Non-Dilutive (Neutral to Positive)
These offerings do NOT dilute existing shareholders:

| Type | Sentiment | Border Color | Reasoning |
|------|-----------|--------------|-----------|
| **Debt/Notes** | +0.3 | Green/Blue | No equity dilution, access to capital |
| **Closing** | +0.2 | Green/Blue | Completion, no more dilution coming |

### Dilutive (Negative)
These offerings dilute existing shareholders:

| Type | Sentiment | Border Color | Reasoning |
|------|-----------|--------------|-----------|
| **Announcement** | -0.6 | Red | NEW dilution coming |
| **Pricing** | -0.5 | Red | Dilution confirmed at price |
| **Upsize** | -0.7 | Red | MORE dilution than expected |

---

## Test Coverage

### New Tests Created
`tests/test_offering_classification_fix.py` - 17 comprehensive tests:

#### PSEC Scenario Tests (3)
- ✅ Detect as debt offering
- ✅ Correct sentiment to +0.3
- ✅ Not marked as negative alert

#### POET Scenario Tests (3)
- ✅ Detect as equity offering closing
- ✅ Correct sentiment to +0.2
- ✅ Not marked as negative alert

#### Negative Offering Tests (3)
- ✅ Announcements remain negative (-0.6)
- ✅ Pricing remains negative (-0.5)
- ✅ Upsizes remain negative (-0.7)

#### Debt Offering Variations (3)
- ✅ Senior notes detected
- ✅ Convertible notes detected
- ✅ Bond offerings detected

#### Border Color Logic (3)
- ✅ Debt offerings get green/blue border
- ✅ Closings get green/blue border
- ✅ Dilutive offerings get red border

#### Oversubscribed Tests (2)
- ✅ PSEC oversubscribed debt → positive
- ✅ POET oversubscribed closing → positive

### Existing Tests
All 31 existing offering sentiment tests pass after fix.

**Total Test Coverage**: 48 tests, all passing ✅

---

## Example Classifications

### PSEC - Debt Offering (✅ Now Correct)
```
Title: "Prospect Capital Corporation Announces Pricing of $167 Million
       5.5% Oversubscribed Institutional Unsecured Notes Offering"
Stage: debt
Sentiment: +0.3 (neutral/positive)
Alert Type: NOT NEGATIVE
Border Color: Green/Blue
Reasoning: Unsecured notes = debt, no equity dilution
```

### POET - Offering Closing (✅ Now Fixed)
```
Title: "POET Technologies Announces Closing of US$150 Million
       Oversubscribed Registered Direct Offering"
Stage: closing
Sentiment: +0.2 (slightly positive)
Alert Type: NOT NEGATIVE
Border Color: Green/Blue
Reasoning: Completion of offering, no more dilution coming
```

### Generic Offering Announcement (✅ Remains Negative)
```
Title: "Company announces $100M public offering"
Stage: announcement
Sentiment: -0.6 (bearish)
Alert Type: NEGATIVE
Border Color: Red
Reasoning: NEW dilution coming
```

---

## Files Modified

### Core Logic
1. **src/catalyst_bot/offering_sentiment.py**
   - Added `is_debt_offering()` function
   - Enhanced `apply_offering_sentiment_correction()` with debt detection
   - Added debt keywords and "debt" stage
   - Updated stage labels and emojis

2. **src/catalyst_bot/classify.py** (2 locations)
   - Imported offering sentiment correction functions
   - Added offering sentiment correction logic before negative alert detection
   - Handle "debt" and "closing" stages to remove from negative_keywords

### Tests
3. **tests/test_offering_classification_fix.py** (NEW)
   - 17 comprehensive tests covering PSEC/POET scenarios
   - Border color logic validation
   - Debt offering variations

---

## Verification Steps

### For PSEC-like Cases (Debt Offerings)
1. Search for keywords: "notes", "bonds", "unsecured notes", "senior notes"
2. If found → classify as "debt" stage
3. Sentiment: +0.3 (neutral/positive)
4. Remove from negative_keywords
5. Border: green/blue (based on price movement)

### For POET-like Cases (Offering Closings)
1. Search for patterns: "closing of", "closes", "completed", "consummation"
2. If found → classify as "closing" stage
3. Sentiment: +0.2 (slightly positive)
4. Remove from negative_keywords
5. Border: green/blue (based on price movement)

### For Dilutive Offerings
1. Check stage: announcement, pricing, or upsize
2. Keep in negative_keywords
3. Sentiment: -0.6, -0.5, or -0.7 respectively
4. Alert type: NEGATIVE
5. Border: red

---

## Impact

### Before Fix
- ❌ All offerings marked as negative alerts (red border)
- ❌ Debt offerings incorrectly flagged as dilutive
- ❌ Offering closings incorrectly flagged as new dilution
- ❌ Traders confused by negative signals on non-dilutive events

### After Fix
- ✅ Intelligent stage detection (closing, announcement, pricing, upsize, debt)
- ✅ Debt offerings correctly marked as neutral/positive (no dilution)
- ✅ Offering closings correctly marked as slightly positive (completion)
- ✅ Dilutive offerings still marked as negative (correct warning)
- ✅ Border colors match sentiment appropriately

---

## User Feedback Resolution

### PSEC Question
> "the outline of the embed is green. negative alerts should be red. could you double check this type of offering too, maybe its good?"

**Answer**: The green border was actually CORRECT for PSEC. This is an unsecured notes offering (debt), which doesn't dilute equity shareholders. Debt offerings are neutral to positive because they provide capital without dilution. The fix ensures this logic is consistently applied.

### POET Question
> "is this negative? idk, the share price did flatline for the day. no pump whatsoever."

**Answer**: An offering CLOSING is not negative - it's the completion of the offering, meaning no more dilution is coming. The flat price action might be due to:
1. Offering already priced in
2. Selling pressure from new shareholders
3. Market conditions

The fix now correctly marks offering closings as slightly positive (sentiment +0.2, green/blue border) to distinguish them from NEW offerings (negative, red border).

---

## Conclusion

The offering sentiment correction system is now fully integrated and working correctly:

- ✅ **48/48 tests passing**
- ✅ Debt offerings properly classified (PSEC scenario)
- ✅ Offering closings properly classified (POET scenario)
- ✅ Dilutive offerings still correctly flagged as negative
- ✅ Border colors match sentiment appropriately

The system now provides traders with accurate signals:
- **Red border**: Dilutive offerings (announcement/pricing/upsize) - caution warranted
- **Green/Blue border**: Non-dilutive offerings (debt/closing) - no dilution concern

---

**Implementation Date**: October 28, 2025
**Test Status**: All tests passing ✅
**Production Ready**: Yes ✅
