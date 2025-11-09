#!/usr/bin/env python3
"""
Test CLOV specifically
"""
import re

title = "[CLOV] Why Clover Health (CLOV) Stock Is Falling Today"
text = title.lower()

print(f"Title: {title}")
print(f"Lowercase: {text}")
print()

patterns = [
    (r"\bwhy\s+\w+\s+(stock|shares|investors|traders)", "Pattern 1"),
    (r"\bwhy\s+\w+\s+\w+\s+(stock|shares|is|are)", "Pattern 2"),
    (r"\bwhy\s+[\w\-]+\s*\([A-Z]+\)\s+(stock|shares)", "Pattern 3"),
    (r"\w+\s+(stock|shares)\s+(is|are)\s+(down|up|falling|rising|trading\s+(lower|higher))", "Pattern 4"),
]

for pattern, desc in patterns:
    match = re.search(pattern, text, re.IGNORECASE)
    print(f"{desc}: {pattern}")
    print(f"  Result: {'MATCH' if match else 'no match'}")
    if match:
        print(f"  Matched text: '{match.group()}'")
    print()

# Now let's manually break it down:
print("Manual breakdown:")
print(f"Text: '{text}'")
print()

# Pattern 2 should match: \bwhy\s+\w+\s+\w+\s+(stock|shares|is|are)
# Looking for: why + word + word + (stock|shares|is|are)
# In text: "why clover health (clov) stock"
#          why + clover + health + ??? not stock, it's (clov)!

print("Expected match for pattern 2:")
print("  why + [word] + [word] + [stock|shares|is|are]")
print("  why + clover + health + ???")
print("  Next word is '(clov)' which contains parens, not a pure \\w+ match!")
print()

# Pattern 4: \w+\s+(stock|shares)\s+(is|are)\s+(down|up|falling|rising|trading\s+(lower|higher))
print("Pattern 4 breakdown:")
print("  Looking for: [word] + stock/shares + is/are + falling/down/etc")
print("  In text: '(clov) stock is falling'")
print("  First word is '(clov)' which contains parens")
print("  \\w+ only matches word characters (letters, digits, underscore)")
print("  Parens are NOT word characters!")
print()

print("SOLUTION: Need to handle company names with parens/tickers in them")
