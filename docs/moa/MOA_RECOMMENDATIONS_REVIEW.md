# MOA Keyword Recommendations - Critical Review

## 🚨 **CRITICAL FINDINGS**

### 1. Reverse Stock Split - **REJECT THIS RECOMMENDATION**
**Evidence of mechanical artifacts:**
- BESS example shows 7,042% "return"
  - Price 7 days before: $8.40
  - Price at catalyst: $0.07 (99.17% CRASH)
  - Price 7 days after: $5.00
  - **This is comparing pre-split price to post-split price!**
  - **NOT A TRADEABLE OPPORTUNITY** - you cannot buy at $0.07 pre-split and sell at $5.00 post-split

**Verdict:** ❌ **REJECT** - These are data artifacts, not real opportunities

---

## ⚠️  **QUESTIONABLE RECOMMENDATIONS** (Need More Analysis)

### 2. Distress Negative - HIGH RISK
**Definition:** Delisting risk, going concern warnings, financial distress signals
- Recommended: 2.5x boost
- Evidence: 5 occurrences, 1,038% avg return
- **Examples:** US BC +160%, FORD +32.4%, TTNP +22.5%

**Questions:**
- These are supposed to be NEGATIVE catalysts (delisting = bad news)
- Why would distress signals lead to price increases?
- Possible explanations:
  - Dead cat bounces (extreme oversold conditions)
  - Rescue financing announcements
  - Need to verify these aren't also mechanical artifacts or pre-running

**Verdict:** ⚠️  **HOLD FOR MANUAL REVIEW** - Needs case-by-case analysis

---

### 3. Dilution/Offering Keywords - **CONTEXT DEPENDENT**
**Keywords affected:**
- dilution_risk (2.5x boost, 60.9% avg return, 12 occurrences)
- dilution (2.2x boost, 24.0% avg return, 69 occurrences)
- offering (2.2x boost, 21.8% avg return, 58 occurrences)
- capital_raise (2.4x boost, 39.4% avg return, 32 occurrences)
- atm (2.3x boost, 31.4% avg return, 25 occurrences)

**Your Valid Concerns:**
1. **Are prices already elevated before the dilution news?**
   - Dilution often announced AFTER a stock has run up
   - Company takes advantage of elevated share price to raise capital
   - This would be catching the TAIL of a move, not the start

2. **Do these gains hold after 7 days?**
   - Dilution typically causes SHORT-TERM selling pressure
   - Gains might evaporate quickly as new shares hit market

3. **What's the actual tradeable pattern here?**
   - Need to verify:
     - Price 7-30 days BEFORE catalyst (was it already running?)
     - Price at catalyst announcement
     - Price 1h, 4h, 1d, 7d after
     - Did it hold gains or give them back?

**Verdict:** ⚠️  **CONDITIONAL APPROVE** - Only if we can verify:
- Stocks weren't already up 20%+ before the catalyst
- 7-day returns held at least 50% of peak gains
- Pattern is repeatable and not cherry-picked

---

## ✅ **LIKELY SAFE RECOMMENDATIONS**

### 4. Management Change - Seems Reasonable
- 2.5x boost, 48.5% avg return, 14 occurrences, 100% success
- Management changes are typically viewed positively (fresh leadership)
- **Verdict:** ✅ **APPROVE**

### 5. Earnings Beat - Makes Sense
- 2.2x boost, 21.5% avg return, 4 occurrences
- Straightforward positive catalyst
- **Verdict:** ✅ **APPROVE**

---

## 📊 **RECOMMENDED ACTION PLAN**

### Immediate Actions:

1. **REJECT completely:**
   - reverse_stock_split (mechanical artifacts)

2. **Manual review required:**
   - distress_negative (counterintuitive, needs explanation)
   - dilution_risk (need to check pre-catalyst momentum)
   - dilution (same)
   - offering (same)
   - capital_raise (same)
   - atm (same)

3. **Safe to approve:**
   - management_change
   - earnings_beat
   - partnership
   - collaboration
   - acquisition
   - board_appointment

### Data Quality Improvements Needed:

The MOA analyzer should be enhanced to detect and flag:
1. **Mechanical artifacts:**
   - Reverse stock splits (compare pre/post-split prices)
   - Stock splits
   - Ticker changes

2. **Pre-catalyst momentum:**
   - Flag if stock was up >20% in 7 days before catalyst
   - Distinguish "catch the move" vs "start of move"

3. **Gain sustainability:**
   - Compare peak return vs 7-day return
   - Flag if 7d < 50% of peak (gave back gains)
   - Report median/p50 returns, not just averages (outliers skew data)

4. **Context enrichment:**
   - Show if price was already elevated (vs 30d average)
   - Show volume pattern (was it already seeing unusual activity?)
   - Show sector performance (rising tide lifting all boats?)

---

## 🎯 **FINAL RECOMMENDATION**

**DO NOT apply all 33 recommendations automatically.**

Instead:
1. **REJECT**: 1 recommendation (reverse_stock_split)
2. **HOLD FOR REVIEW**: 6 recommendations (distress_negative, dilution family)
3. **APPROVE**: 26 recommendations (management, partnerships, conservative estimates)

**Conservative approach:**
- Apply only the 26 safe recommendations
- Monitor performance for 30 days
- Manually investigate the 6 questionable keywords with real examples
- Once validated, selectively enable the ones that check out

This prevents potentially harmful false positives while still capturing legitimate improvements.
