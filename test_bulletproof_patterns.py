#!/usr/bin/env python3
"""
Test bulletproof retrospective article patterns
"""
import re

def _is_retrospective_article_bulletproof(title: str, summary: str = "") -> bool:
    """
    Bulletproof implementation that handles:
    1. Ticker prefixes: [TICK] Why...
    2. Company names with tickers: Why Company (TICK) Stock...
    3. Multi-word company names: Why Company Name Stock...
    4. Various "falling/trading lower" phrasings
    """
    try:
        text = f"{title} {summary}".lower()

        # BULLETPROOF PATTERNS:
        # Use \b for word boundaries instead of ^ for start-of-string
        # Use .{0,50} to skip over ticker prefixes and company names flexibly
        # Use non-greedy matching to avoid over-matching

        retrospective_patterns = [
            # "Why" patterns - most common offenders
            r"\bwhy\s+.{0,50}?\s+(stock|shares)\s+(is|are|has|have)\s+(down|up|falling|rising|trading|moving|getting)",
            r"\bwhy\s+.{0,50}?\s+(stock|shares)\s+(dropped|fell|slid|dipped|rose|jumped|climbed|surged)",
            r"\bwhy\s+.{0,50}?\s+(investors|traders)\s+(are|were)\s+(buying|selling|dumping|fleeing)",

            # "Here's why" - always retrospective
            r"\bhere'?s\s+why\b",

            # "What happened" - always retrospective
            r"\bwhat\s+happened\s+(to|with)\b",

            # Past-tense movement with percentages
            r"(stock|shares)\s+(dropped|fell|slid|dipped|plunged|tanked|crashed|tumbled|sank)\s+\d+%",
            r"(stock|shares)\s+(surged|soared|jumped|climbed|rallied|spiked)\s+\d+%",

            # "is/are down/up X%" patterns
            r"(stock|shares)\s+(is|are)\s+(down|up)\s+\d+%",

            # "shares slide/drop/fall despite/after" patterns
            r"(shares|stock)\s+(slide|slid|drop|dropped|fall|fell|dip|dipped|plunge|plunged)\s+(despite|after|on|following)",

            # "getting obliterated/destroyed/crushed" - dramatic past-tense
            r"(shares|stock|investors)\s+(is|are|getting|got)\s+(obliterated|destroyed|crushed|hammered|pummeled|demolished)",
        ]

        for pattern in retrospective_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    except Exception:
        return False


# Test cases - ALL articles that should be filtered
test_articles = [
    # The 5 that got through
    "[MX] Why Magnachip (MX) Stock Is Trading Lower Today",
    "[CLOV] Why Clover Health (CLOV) Stock Is Falling Today",
    "[PAYO] Why Payoneer (PAYO) Stock Is Trading Lower Today",
    "[HTZ] Why Hertz (HTZ) Shares Are Getting Obliterated Today",
    "[JELD] Why JELD-WEN (JELD) Stock Is Down Today",

    # Original test cases
    "Why BYND Stock Dropped 14.6%",
    "Here's why investors aren't happy",
    "Stock Slides Despite Earnings Beat",
    "Why XYZ Stock Is Falling",

    # More variations that should be caught
    "Why Tesla Stock Is Up 5% Today",
    "Why Investors Are Selling Apple Stock",
    "What Happened to NVDA Stock Today",
    "Why AMD Shares Have Fallen",
    "TSLA Stock Dropped 10% on Earnings Miss",
    "Shares Slid Despite Strong Revenue",
    "Why Meta Investors Got Crushed Today",
]

# Articles that should NOT be filtered (actual catalysts)
should_not_filter = [
    "Company Announces Major Partnership Deal",
    "FDA Approves New Drug - Stock Surges",
    "Earnings Beat Estimates - Guidance Raised",
    "Merger Agreement Reached",
    "New Product Launch Scheduled",
    "CEO Announces Share Buyback Program",
    "Quarterly Revenue Exceeds Expectations",
]

print("=" * 80)
print("TESTING RETROSPECTIVE ARTICLES (Should be filtered)")
print("=" * 80)

all_pass = True
for title in test_articles:
    result = _is_retrospective_article_bulletproof(title)
    status = "PASS" if result else "FAIL"
    if not result:
        all_pass = False
    print(f"{status}: {title}")

print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")

print("\n" + "=" * 80)
print("TESTING CATALYST ARTICLES (Should NOT be filtered)")
print("=" * 80)

all_pass = True
for title in should_not_filter:
    result = _is_retrospective_article_bulletproof(title)
    status = "PASS" if not result else "FAIL (false positive)"
    if result:
        all_pass = False
    print(f"{status}: {title}")

print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FALSE POSITIVES'}")

print("\n" + "=" * 80)
print("PATTERN EXPLANATION")
print("=" * 80)
print("""
KEY IMPROVEMENTS:

1. REMOVED ^ ANCHORS
   - Old: r"^why\\s+\\w+\\s+(stock|shares...)"
   - New: r"\\bwhy\\s+.{0,50}?\\s+(stock|shares)..."
   - Allows matching "why" anywhere after a word boundary
   - Handles ticker prefixes like "[TICK] Why..."

2. FLEXIBLE COMPANY NAME MATCHING
   - Old: r"\\w+\\s+\\w+" (only 2 words)
   - New: r".{0,50}?" (any characters, up to 50, non-greedy)
   - Handles "Clover Health (CLOV)" and multi-word names

3. COMPREHENSIVE VERB COVERAGE
   - Added: trading, moving, getting, obliterated, crushed, etc.
   - Covers all the creative ways financial media describes price moves

4. BIDIRECTIONAL PATTERNS
   - Covers both drops AND rises (retrospective applies to both)
   - "Why Stock Is Up" is just as retrospective as "Why Stock Is Down"

5. NON-GREEDY MATCHING
   - .{0,50}? stops at first match, prevents over-matching
   - More precise and performant
""")
