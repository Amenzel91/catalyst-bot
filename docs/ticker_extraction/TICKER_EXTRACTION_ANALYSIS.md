# Ticker Extraction Analysis - Real Headlines

**Date**: October 14, 2025
**Test Run**: 819 items fetched (88 FinViz, 20 Globenewswire, 30 Finnhub, 463 Earnings, 218 SEC)
**Problem**: ALL high-scoring news items had `ticker=None` despite containing ticker information

---

## Critical Finding: Ticker in Parentheses Pattern (NO Exchange)

The most common pattern that **FAILS** is when tickers appear in parentheses WITHOUT an exchange qualifier:

### FinViz News Examples (FAILING):
```
[15] "Earnings To Watch: Bank OZK (OZK) Reports Q3 Results Tomorrow"
     Expected: OZK
     Got: NONE

[16] "CSX (CSX) Reports Q3: Everything You Need To Know Ahead Of Earnings"
     Expected: CSX
     Got: NONE

[17] "Independent Bank (INDB) Reports Earnings Tomorrow: What To Expect"
     Expected: INDB
     Got: NONE

[18] "Insteel (IIIN) To Report Earnings Tomorrow: Here Is What To Expect"
     Expected: IIIN
     Got: NONE

[19] "Glacier Bancorp Earnings: What To Look For From GBCI"
     Expected: GBCI
     Got: NONE

[20] "ManpowerGroup (MAN) Reports Q3: Everything You Need To Know Ahead Of Earnings"
     Expected: MAN
     Got: NONE
```

**Pattern**: `CompanyName (TICKER)` - Very common in earnings announcements and financial news

---

## Foreign Exchange Tickers (FAILING)

### Globenewswire Example:
```
[1] "Mowi ASA (OSE:MOWI): Q3 2025 Trading update"
    Expected: MOWI (or skip - it's OSE Oslo exchange)
    Got: NONE
```

**Pattern**: `CompanyName (EXCHANGE:TICKER)` where EXCHANGE is not NYSE/NASDAQ/OTC

---

## Company Name Only (NO Ticker in Headline)

Many high-quality news items mention well-known companies by name only:

### FinViz Examples:
```
[2] "China industry minister meets with Apple's Tim Cook"
    Company: Apple
    Ticker should be: AAPL
    Got: NONE

[3] "Coinbase boosts investment in Indias CoinDCX, valuing exchange at $2.45B"
    Company: Coinbase
    Ticker should be: COIN
    Got: NONE

[5] "CME Group Expands into the Middle East with Dubai International Financial Centre Opening"
    Company: CME Group
    Ticker should be: CME
    Got: NONE

[7] "RTX breaks ground on $53 million expansion..."
    Company: RTX
    Ticker should be: RTX
    Got: NONE

[14] "Apple to Build Home Hub and Robot in Vietnam in Pivot From China"
    Company: Apple
    Ticker should be: AAPL
    Got: NONE
```

### Globenewswire Examples:
```
[3] "EyePoint Announces Pricing of Public Offering"
    Company: EyePoint
    Ticker should be: EYPT
    Got: NONE

[8] "El Pollo Loco Celebrates Growth Milestone with 500th U.S. Restaurant"
    Company: El Pollo Loco
    Ticker should be: LOCO
    Got: NONE

[10] "Smart Logistics Global Limited Announces Pricing of Its Initial Public Offering"
    Company: Smart Logistics Global Limited
    Got: NONE (likely OTC or foreign)

[11] "Bombardier Unveils BOND as Customer Behind June 2025 Landmark Order"
    Company: Bombardier
    Got: NONE (Canadian ticker BBD.B)
```

---

## Current Working Patterns

Based on the extraction code, these patterns DO work:

1. **Exchange-qualified tickers**: `(NYSE: AAPL)`, `(Nasdaq: TSLA)`, `(OTC: GRLT)`
2. **Dollar-sign tickers**: `$NVDA`, `$AAPL`, `$TSLA`

---

## Recommended Fixes (Priority Order)

### 1. HIGH PRIORITY: Company (TICKER) Pattern
Add regex to match tickers in parentheses without exchange:
```regex
r'\b([A-Z][a-z\s&.]+)\s+\(([A-Z]{1,5})\)'
```

Examples this would catch:
- "Bank OZK (OZK)" → OZK
- "CSX (CSX)" → CSX
- "Independent Bank (INDB)" → INDB
- "ManpowerGroup (MAN)" → MAN

**Risk**: May match non-ticker acronyms like "LIFE", "BOND", "STEM"
**Mitigation**: Validate against known ticker database

### 2. MEDIUM PRIORITY: Ticker at End of Headline
Many earnings headlines end with just the ticker:
```regex
r'\b([A-Z]{2,5})$'
```

Example:
- "Glacier Bancorp Earnings: What To Look For From GBCI" → GBCI

### 3. LOWER PRIORITY: Company Name → Ticker Lookup
For company names only (no ticker in headline):
- Maintain a mapping of common company names to tickers
- "Apple" → AAPL
- "Coinbase" → COIN
- "CME Group" → CME

**Risk**: High false positive rate (many "Apple" mentions not about AAPL stock)
**Mitigation**: Use only for specific news sources (Globenewswire, FinViz)

### 4. SKIP: Foreign Exchange Tickers
Headlines like "(OSE:MOWI)" should be filtered OUT since they're not U.S. tradeable:
- OSE = Oslo Stock Exchange
- LSE = London Stock Exchange
- TSX = Toronto Stock Exchange

---

## Impact Assessment

Based on the test run:

- **88 FinViz items**: ~20+ items (23%) had extractable tickers that were missed
- **20 Globenewswire items**: ~8+ items (40%) had extractable tickers that were missed
- **Total missed opportunities**: 28+ high-quality news items per cycle

With multiple cycles per hour, this represents **significant signal loss**.

---

## Next Steps

1. Implement Fix #1 (Company (TICKER) pattern) - catches most earnings news
2. Add ticker validation against known ticker database
3. Test on historical data to measure false positive rate
4. Consider Fix #2 (ticker at end) for additional coverage
