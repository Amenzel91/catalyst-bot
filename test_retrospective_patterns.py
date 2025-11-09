#!/usr/bin/env python3
"""
Test the retrospective article patterns against the 5 articles that got through
"""
import re

def _is_retrospective_article(title: str, summary: str = "") -> bool:
    """Current implementation from feeds.py"""
    try:
        # Combine title and summary, case-insensitive
        text = f"{title} {summary}".lower()

        # Retrospective question patterns
        retrospective_patterns = [
            r"^why\s+\w+\s+(stock|shares|investors|traders)",  # "Why XYZ Stock..."
            r"^why\s+\w+\s+\w+\s+(stock|shares|is|are)",       # "Why Company X Stock..."
            r"here'?s\s+why",                                   # "Here's why..."
            r"^what\s+happened\s+to",                          # "What happened to..."
            r"stock\s+(dropped|fell|slid|dipped|plunged|tanked|crashed|tumbled)\s+\d+%",  # "Stock dropped X%"
            r"shares\s+(slide|slid|drop|dropped|fall|fell|dip|dipped|plunge|plunged)\s+(despite|after|on)",  # "Shares slide despite..."
            r"\w+\s+(stock|shares)\s+(is|are)\s+(down|up)\s+\d+%",  # "XYZ Stock is down 14%"
        ]

        for pattern in retrospective_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    except Exception:
        # Conservative default: do not mark as retrospective on errors
        return False


# Test cases - the 5 articles that got through
test_articles = [
    "[MX] Why Magnachip (MX) Stock Is Trading Lower Today",
    "[CLOV] Why Clover Health (CLOV) Stock Is Falling Today",
    "[PAYO] Why Payoneer (PAYO) Stock Is Trading Lower Today",
    "[HTZ] Why Hertz (HTZ) Shares Are Getting Obliterated Today",
    "[JELD] Why JELD-WEN (JELD) Stock Is Down Today",
]

# Also test some that should match
should_match = [
    "Why BYND Stock Dropped 14.6%",
    "Here's why investors aren't happy",
    "Stock Slides Despite Earnings Beat",
    "Why XYZ Stock Is Falling",
]

print("=" * 80)
print("TESTING ARTICLES THAT GOT THROUGH (Should have been filtered but weren't)")
print("=" * 80)
for title in test_articles:
    result = _is_retrospective_article(title)
    print(f"\nTitle: {title}")
    print(f"Filtered: {result}")
    print(f"Status: {'WORKING' if result else 'FAILED - Got through!'}")

    # Test against each pattern individually
    text = title.lower()
    print(f"Lowercase text: '{text}'")
    print("\nPattern matches:")

    patterns = [
        (r"^why\s+\w+\s+(stock|shares|investors|traders)", "Pattern 1: ^why\\s+\\w+\\s+(stock|shares...)"),
        (r"^why\s+\w+\s+\w+\s+(stock|shares|is|are)", "Pattern 2: ^why\\s+\\w+\\s+\\w+\\s+(stock|shares...)"),
        (r"here'?s\s+why", "Pattern 3: here's why"),
        (r"^what\s+happened\s+to", "Pattern 4: what happened to"),
    ]

    for pattern, desc in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        print(f"  {desc}: {'MATCH' if match else 'no match'}")
        if match:
            print(f"    Matched: '{match.group()}'")

print("\n" + "=" * 80)
print("TESTING ARTICLES THAT SHOULD MATCH (Control group)")
print("=" * 80)
for title in should_match:
    result = _is_retrospective_article(title)
    print(f"\nTitle: {title}")
    print(f"Filtered: {result}")
    print(f"Status: {'WORKING' if result else 'FAILED'}")

print("\n" + "=" * 80)
print("ROOT CAUSE ANALYSIS")
print("=" * 80)
print("""
The issue is clear:

1. All 5 titles start with a TICKER in brackets: [MX], [CLOV], [PAYO], etc.
2. The regex patterns use ^ (start of line anchor)
3. After lowercasing, the titles look like:
   '[mx] why magnachip (mx) stock is trading lower today'

4. Pattern 1: r"^why\\s+\\w+\\s+(stock|shares...)"
   - Expects "why" at the START of the string (^why)
   - But the actual start is "[mx] why"
   - DOES NOT MATCH!

5. Pattern 2: r"^why\\s+\\w+\\s+\\w+\\s+(stock|shares...)"
   - Same issue - expects "why" at start
   - DOES NOT MATCH!

The ticker prefix breaks the ^ anchor in all "why" patterns.
""")

print("\n" + "=" * 80)
print("TESTING IMPROVED PATTERNS")
print("=" * 80)

def _is_retrospective_article_fixed(title: str, summary: str = "") -> bool:
    """Improved implementation"""
    try:
        text = f"{title} {summary}".lower()

        # FIXED: Remove ^ anchors and add \b word boundaries
        # This allows matching "why" anywhere in the title after word boundaries
        retrospective_patterns = [
            r"\bwhy\s+\w+\s+(stock|shares|investors|traders)",  # "Why XYZ Stock..."
            r"\bwhy\s+\w+\s+\w+\s+(stock|shares|is|are)",       # "Why Company X Stock..."
            r"\bwhy\s+[\w\-]+\s*\([A-Z]+\)\s+(stock|shares)",   # "Why Company (TICK) Stock..."
            r"here'?s\s+why",                                    # "Here's why..."
            r"\bwhat\s+happened\s+to",                          # "What happened to..."
            r"stock\s+(dropped|fell|slid|dipped|plunged|tanked|crashed|tumbled)\s+\d+%",
            r"shares\s+(slide|slid|drop|dropped|fall|fell|dip|dipped|plunge|plunged)\s+(despite|after|on)",
            r"\w+\s+(stock|shares)\s+(is|are)\s+(down|up|falling|rising|trading\s+(lower|higher))",
        ]

        for pattern in retrospective_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    except Exception:
        return False

print("\nTesting FIXED patterns against articles that got through:")
for title in test_articles:
    result = _is_retrospective_article_fixed(title)
    print(f"\nTitle: {title}")
    print(f"Filtered: {result}")
    print(f"Status: {'FIXED!' if result else 'Still broken'}")
