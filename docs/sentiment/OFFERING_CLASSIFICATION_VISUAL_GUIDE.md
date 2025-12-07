# Offering Classification Visual Guide

## Quick Reference Chart

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OFFERING CLASSIFICATION MATRIX                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  DEBT/NOTES OFFERINGS (No Dilution)                                    │
│  ┌────────────────────────────────────────────────────┐                │
│  │ Keywords: notes, bonds, unsecured, senior, debt    │                │
│  │ Stage: "debt"                                      │  ┌──────────┐  │
│  │ Sentiment: +0.3 (neutral/positive)                 │  │  GREEN/  │  │
│  │ Alert Type: NOT NEGATIVE                           │  │   BLUE   │  │
│  │ Border: Green/Blue (based on price)                │  │  BORDER  │  │
│  │ Example: PSEC $167M unsecured notes                │  └──────────┘  │
│  └────────────────────────────────────────────────────┘                │
│                                                                          │
│  OFFERING CLOSINGS (Completion, Anti-Dilutive)                         │
│  ┌────────────────────────────────────────────────────┐                │
│  │ Keywords: closing, closes, completed, consummation │                │
│  │ Stage: "closing"                                   │  ┌──────────┐  │
│  │ Sentiment: +0.2 (slightly positive)                │  │  GREEN/  │  │
│  │ Alert Type: NOT NEGATIVE                           │  │   BLUE   │  │
│  │ Border: Green/Blue (based on price)                │  │  BORDER  │  │
│  │ Example: POET $150M offering closing               │  └──────────┘  │
│  └────────────────────────────────────────────────────┘                │
│                                                                          │
│  DILUTIVE EQUITY OFFERINGS (Negative for Shareholders)                 │
│  ┌────────────────────────────────────────────────────┐                │
│  │ ANNOUNCEMENT                                       │                │
│  │  - Keywords: announces offering                    │  ┌──────────┐  │
│  │  - Stage: "announcement"                           │  │   RED    │  │
│  │  - Sentiment: -0.6 (bearish)                       │  │  BORDER  │  │
│  │  - Alert Type: NEGATIVE                            │  └──────────┘  │
│  │  - Border: RED                                     │                │
│  ├────────────────────────────────────────────────────┤                │
│  │ PRICING                                            │                │
│  │  - Keywords: prices offering at                    │  ┌──────────┐  │
│  │  - Stage: "pricing"                                │  │   RED    │  │
│  │  - Sentiment: -0.5 (bearish)                       │  │  BORDER  │  │
│  │  - Alert Type: NEGATIVE                            │  └──────────┘  │
│  │  - Border: RED                                     │                │
│  ├────────────────────────────────────────────────────┤                │
│  │ UPSIZE                                             │                │
│  │  - Keywords: upsizes, increases size               │  ┌──────────┐  │
│  │  - Stage: "upsize"                                 │  │   RED    │  │
│  │  - Sentiment: -0.7 (very bearish)                  │  │  BORDER  │  │
│  │  - Alert Type: NEGATIVE                            │  └──────────┘  │
│  │  - Border: RED                                     │                │
│  └────────────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────────────┘
```

## Real-World Examples

### ✅ PSEC - Debt Offering (Correct: Green/Blue Border)

```
┌───────────────────────────────────────────────────────────────┐
│ 📄 PSEC                                                        │
├───────────────────────────────────────────────────────────────┤
│ Prospect Capital Corporation Announces Pricing of            │
│ $167 Million 5.5% Oversubscribed Institutional                │
│ Unsecured Notes Offering                                      │
│                                                               │
│ Stage: debt                                                   │
│ Sentiment: +0.3                                               │
│ Alert Type: NOT NEGATIVE                                      │
│ Border Color: GREEN/BLUE ✅                                   │
│                                                               │
│ Why Green?                                                    │
│ - Unsecured notes = debt, not equity                         │
│ - No dilution of existing shareholders                       │
│ - Access to capital without dilution                         │
│ - Oversubscribed = strong demand signal                      │
└───────────────────────────────────────────────────────────────┘
```

### ✅ POET - Offering Closing (Fixed: Green/Blue Border)

```
┌───────────────────────────────────────────────────────────────┐
│ ✅ POET                                                        │
├───────────────────────────────────────────────────────────────┤
│ POET Technologies Announces Closing of US$150 Million        │
│ Oversubscribed Registered Direct Offering                     │
│                                                               │
│ Stage: closing                                                │
│ Sentiment: +0.2                                               │
│ Alert Type: NOT NEGATIVE                                      │
│ Border Color: GREEN/BLUE ✅ (was red ❌, now fixed)          │
│                                                               │
│ Why Green?                                                    │
│ - CLOSING = completion of offering                           │
│ - No MORE dilution coming                                    │
│ - Anti-dilutive signal (relief)                              │
│ - Oversubscribed = demand was strong                         │
└───────────────────────────────────────────────────────────────┘
```

### ❌ Generic Offering Announcement (Correct: Red Border)

```
┌───────────────────────────────────────────────────────────────┐
│ 💰 XYZ                                                         │
├───────────────────────────────────────────────────────────────┤
│ XYZ Corp Announces $100M Public Offering                     │
│                                                               │
│ Stage: announcement                                           │
│ Sentiment: -0.6                                               │
│ Alert Type: NEGATIVE                                          │
│ Border Color: RED ❌                                          │
│                                                               │
│ Why Red?                                                      │
│ - NEW dilution coming                                        │
│ - Existing shares will be diluted                            │
│ - Typically bearish for stock price                          │
│ - Warning signal for traders                                 │
└───────────────────────────────────────────────────────────────┘
```

## Decision Tree

```
Is it an offering-related news?
│
├─ YES → Check if debt/notes
│   │
│   ├─ YES → 🟢 DEBT OFFERING
│   │         Stage: "debt"
│   │         Sentiment: +0.3
│   │         Border: Green/Blue
│   │         Alert Type: NOT NEGATIVE
│   │
│   └─ NO → Check stage
│       │
│       ├─ CLOSING → 🟢 CLOSING
│       │             Stage: "closing"
│       │             Sentiment: +0.2
│       │             Border: Green/Blue
│       │             Alert Type: NOT NEGATIVE
│       │
│       ├─ ANNOUNCEMENT → 🔴 NEGATIVE
│       │                  Stage: "announcement"
│       │                  Sentiment: -0.6
│       │                  Border: Red
│       │                  Alert Type: NEGATIVE
│       │
│       ├─ PRICING → 🔴 NEGATIVE
│       │             Stage: "pricing"
│       │             Sentiment: -0.5
│       │             Border: Red
│       │             Alert Type: NEGATIVE
│       │
│       └─ UPSIZE → 🔴 VERY NEGATIVE
│                    Stage: "upsize"
│                    Sentiment: -0.7
│                    Border: Red
│                    Alert Type: NEGATIVE
│
└─ NO → Standard classification
```

## Color Meanings

### 🟢 Green/Blue Border (NOT NEGATIVE)
- **Meaning**: Non-dilutive or positive catalyst
- **Scenarios**:
  - Debt/notes offerings (no equity dilution)
  - Offering closings (completion, no more dilution)
  - Price-based coloring (green = up, blue = flat/mixed)
- **Action**: Normal evaluation, not an exit signal

### 🔴 Red Border (NEGATIVE)
- **Meaning**: Dilutive or negative catalyst
- **Scenarios**:
  - NEW equity offerings (announcement, pricing)
  - Offering upsizes (more dilution than expected)
  - Warrant exercises, distress signals
- **Action**: Caution warranted, potential exit signal

## Technical Implementation

### alerts.py (Lines 1706-1731)
```python
# Check if this is a negative catalyst alert
is_negative_alert = False
if scored:
    alert_type = scored.get("alert_type")
    if alert_type == "NEGATIVE":
        is_negative_alert = True

# Set border color
color = 0x5865F2  # Default: Discord blurple
if is_negative_alert:
    color = 0xFF0000  # Red for negative alerts
else:
    # Green for positive price, red for negative price, blue for flat
    color = based_on_price_movement()
```

### classify.py (Lines 888-936)
```python
# --- OFFERING SENTIMENT CORRECTION ---
if is_offering_related and OFFERING_SENTIMENT_AVAILABLE:
    corrected_sentiment, offering_stage, offering_corrected = (
        apply_offering_sentiment_correction(
            title=title,
            text=summary,
            current_sentiment=sentiment,
            min_confidence=0.7,
        )
    )

    if offering_corrected:
        # Override sentiment with corrected value
        sentiment = corrected_sentiment

        # If stage is "closing" or "debt", remove from negative_keywords
        if offering_stage in ("closing", "debt"):
            negative_keywords = [
                kw for kw in negative_keywords if kw != "offering_negative"
            ]
            # This prevents alert_type="NEGATIVE"
            # → No red border
```

## FAQ

### Q: Why is PSEC green? Offerings should be negative!
**A**: PSEC is a DEBT offering (unsecured notes), not an equity offering. Debt doesn't dilute existing shareholders. It's like taking a loan - no new shares are created.

### Q: Why is POET green? It's still an offering!
**A**: POET is an offering CLOSING, not a new offering. The dilution already happened when it was announced/priced. The closing means "it's done, no more dilution coming." This is slightly positive (relief signal).

### Q: When should I be concerned about red offerings?
**A**: Red borders indicate:
1. **NEW** equity offerings (announcement/pricing) - dilution is coming
2. **Upsized** offerings - MORE dilution than expected
3. These are genuine warnings that dilution will impact share price

### Q: Can a closing ever be red?
**A**: Only if there are OTHER negative keywords present (e.g., distress, warrants). But the offering closing itself is no longer treated as negative.

### Q: What about convertible notes?
**A**: Convertible notes are classified as debt until converted. The system will flag them as "debt" offerings (green/blue) at offering time. If/when they convert to equity later, that would be a separate dilution event.

---

## Summary

The fix distinguishes between:

1. **Non-Dilutive** (Green/Blue)
   - Debt/notes offerings
   - Offering closings

2. **Dilutive** (Red)
   - NEW equity offerings
   - Offering upsizes

This provides traders with accurate signals about which offerings are truly negative catalysts versus neutral/positive corporate actions.
