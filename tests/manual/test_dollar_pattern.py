#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quick test for dollar pattern matching."""

import sys
sys.path.insert(0, 'src')

from catalyst_bot import title_ticker
title_ticker._RE_CACHE.clear()

from catalyst_bot.title_ticker import extract_tickers_from_title, _get_regex

text1 = "Price: $GOOGL at $150"
text2 = "PRICE: $GOOGL at $150"
text3 = "$GOOGL shares surge"
text4 = "TSLA: deliveries beat"

print("Testing dollar pattern matching:")
print("="*60)

for text in [text1, text2, text3, text4]:
    result = extract_tickers_from_title(text)
    print(f"\nText: {text!r}")
    print(f"Result: {result}")

# Check pattern directly
print("\n" + "="*60)
print("Pattern matching test:")
pat = _get_regex(False, False)
for text in [text1, text2, text3]:
    print(f"\nText: {text!r}")
    matches = list(pat.finditer(text))
    if matches:
        for m in matches:
            print(f"  Match: {m.group(0)!r} at pos {m.start()}-{m.end()}")
            print(f"  Groups: {m.groups()}")
    else:
        print("  No matches")
