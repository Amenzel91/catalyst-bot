#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract and display actual news headlines from feeds to analyze ticker patterns."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from catalyst_bot import feeds
from catalyst_bot.title_ticker import extract_tickers_from_title

def main():
    """Fetch feeds and display headlines with ticker extraction results."""

    print("=" * 100)
    print("FETCHING ACTUAL NEWS HEADLINES")
    print("=" * 100)

    # Get all items from feeds
    all_items = feeds.fetch_pr_feeds()

    print(f"\nTotal items fetched: {len(all_items)}")

    # Group by source
    by_source = {}
    for item in all_items:
        source = item.get('source', 'unknown')
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(item)

    print(f"\nSources: {list(by_source.keys())}")

    # Show news items (not earnings)
    news_sources = ['finviz_news', 'globenewswire_public', 'finnhub']

    for source in news_sources:
        if source not in by_source:
            continue

        items = by_source[source]
        print(f"\n{'=' * 100}")
        print(f"{source.upper()} - {len(items)} items")
        print(f"{'=' * 100}")

        # Show first 20 items from this source
        for i, item in enumerate(items[:20], 1):
            # Get title/headline
            title = item.get('title') or item.get('headline') or item.get('summary', '')
            if isinstance(title, str):
                title = title[:200]  # Truncate long titles

            # Try to extract ticker
            tickers = extract_tickers_from_title(title)
            ticker_str = f"Ticker: {tickers[0] if tickers else 'NONE'}"

            # Get timestamp
            ts = item.get('timestamp', item.get('datetime', item.get('published', '')))

            print(f"\n[{i}] {ticker_str}")
            print(f"    Title: {title}")
            print(f"    Time:  {ts}")

            # Show raw item for first few to understand structure
            if i <= 3:
                print(f"    Raw keys: {list(item.keys())}")

if __name__ == "__main__":
    main()
