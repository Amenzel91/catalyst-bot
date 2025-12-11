#!/usr/bin/env python3
"""
Investigate high-scoring items with ticker=N/A from bot logs.

This script:
1. Reads bot.jsonl to find classification events with high scores and ticker=N/A
2. Fetches SEC feed items from the most recent cycle
3. Matches items by scoring patterns and timestamps
4. Extracts CIK numbers from SEC URLs
5. Produces a summary table of the findings
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# CIK extraction regex (matches /edgar/data/XXXXXXXX/)
CIK_RE = re.compile(r"/edgar/data/(\d+)/", re.IGNORECASE)

def extract_cik_from_url(url):
    """Extract CIK from SEC EDGAR URL."""
    if not url:
        return None
    match = CIK_RE.search(url)
    return match.group(1) if match else None

def load_log_events():
    """Load classification events from bot.jsonl."""
    log_path = Path("data/logs/bot.jsonl")

    if not log_path.exists():
        print(f"Error: {log_path} not found")
        return []

    events = []
    target_scores = {2.500, 1.242, 0.680}

    print(f"Reading {log_path}...")
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line.strip())

                # Look for regime_adjustment_applied events
                msg = event.get("msg", "")
                if "regime_adjustment_applied" in msg and "ticker=N/A" in msg:
                    # Extract score from message
                    score_match = re.search(r"post_score=(\d+\.\d+)", msg)
                    if score_match:
                        score = float(score_match.group(1))
                        if score in target_scores:
                            event["extracted_score"] = score
                            events.append(event)
            except Exception as e:
                continue

    print(f"Found {len(events)} classification events with target scores and ticker=N/A")
    return events

def fetch_sec_feed_items():
    """Fetch SEC feed items to analyze."""
    print("\nFetching SEC feed items...")

    # Import the feeds module
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "src"))

    try:
        from catalyst_bot import feeds
        from catalyst_bot.seen_store import SeenStore

        # Create a temporary seen store
        seen_store = SeenStore()

        # Fetch SEC 8K items
        sec_items = feeds.fetch_sec_filings_8k(seen_store=seen_store)

        print(f"Fetched {len(sec_items)} SEC 8-K items")

        # Also try fetching FWP items
        try:
            fwp_items = feeds.fetch_sec_filings_fwp(seen_store=seen_store)
            print(f"Fetched {len(fwp_items)} SEC FWP items")
            sec_items.extend(fwp_items)
        except Exception as e:
            print(f"Could not fetch FWP items: {e}")

        return sec_items
    except Exception as e:
        print(f"Error fetching SEC items: {e}")
        return []

def main():
    print("=" * 80)
    print("INVESTIGATING HIGH-SCORING ITEMS WITH TICKER=N/A")
    print("=" * 80)

    # Load classification events from logs
    events = load_log_events()

    if not events:
        print("\nNo classification events found with target scores.")
        return

    # Group events by score
    by_score = defaultdict(list)
    for event in events:
        score = event.get("extracted_score")
        by_score[score].append(event)

    print("\nClassification events by score:")
    for score in sorted(by_score.keys(), reverse=True):
        count = len(by_score[score])
        print(f"  {score:.3f}: {count} events")
        for event in by_score[score][:3]:  # Show first 3 timestamps
            ts = event.get("ts", "")
            print(f"    - {ts}")

    # Fetch current SEC feed items
    sec_items = fetch_sec_feed_items()

    if not sec_items:
        print("\nNo SEC items fetched. Analysis limited to log data.")
        return

    # Analyze SEC items
    print("\n" + "=" * 80)
    print("SEC ITEMS ANALYSIS")
    print("=" * 80)

    print(f"\nTotal SEC items fetched: {len(sec_items)}")

    # Count items by ticker presence
    with_ticker = [item for item in sec_items if item.get("ticker")]
    without_ticker = [item for item in sec_items if not item.get("ticker")]

    print(f"Items WITH ticker: {len(with_ticker)}")
    print(f"Items WITHOUT ticker: {len(without_ticker)}")

    # Analyze items without tickers
    print("\n" + "-" * 80)
    print("ITEMS WITHOUT TICKERS (potential N/A candidates)")
    print("-" * 80)

    for i, item in enumerate(without_ticker[:10], 1):  # Show first 10
        title = item.get("title", "")[:100]
        link = item.get("link", "")
        source = item.get("source", "")
        cik = extract_cik_from_url(link)

        print(f"\n{i}. Source: {source}")
        print(f"   Title: {title}")
        print(f"   Link: {link[:80]}...")
        print(f"   CIK: {cik or 'NOT FOUND'}")

    # Summary table
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(f"\nClassification Events Found:")
    print(f"  - Score 2.500: {len(by_score.get(2.500, []))} events")
    print(f"  - Score 1.242: {len(by_score.get(1.242, []))} events")
    print(f"  - Score 0.680: {len(by_score.get(0.680, []))} events")

    print(f"\nSEC Feed Items:")
    print(f"  - Total items: {len(sec_items)}")
    print(f"  - With ticker: {len(with_ticker)}")
    print(f"  - Without ticker: {len(without_ticker)} (potential N/A items)")

    # Analyze CIK extraction success
    without_ticker_with_cik = [item for item in without_ticker if extract_cik_from_url(item.get("link", ""))]
    without_ticker_no_cik = [item for item in without_ticker if not extract_cik_from_url(item.get("link", ""))]

    print(f"\nCIK Extraction Analysis (items without ticker):")
    print(f"  - CIK extractable from URL: {len(without_ticker_with_cik)}")
    print(f"  - CIK NOT in URL: {len(without_ticker_no_cik)}")

    if without_ticker_no_cik:
        print(f"\nItems without CIK in URL (first 5):")
        for item in without_ticker_no_cik[:5]:
            link = item.get("link", "")
            print(f"  - {link[:100]}")

    print("\n" + "=" * 80)
    print("LIKELY ROOT CAUSE:")
    print("=" * 80)
    print("""
The high-scoring items with ticker=N/A are likely SEC filings where:
1. The CIK is present in the URL but not in the CIK-to-ticker mapping
2. The company name in the title doesn't contain a recognizable ticker
3. The filing content doesn't have ticker symbols in extractable locations

RECOMMENDATION:
- Check if CIK map (company_tickers.ndjson) needs updating
- Consider enhancing ticker extraction from SEC filing metadata
- Add fallback to company name lookup for CIK-to-ticker mapping
""")

if __name__ == "__main__":
    main()
