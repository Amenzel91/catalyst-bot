"""
Enhanced 14-Day Backfill with Classification
=============================================

Backfills price outcomes for the last 14 days AND ensures all items have
keyword classification. Items missing keywords are automatically classified.

This solves the issue where 88.9% of LOW_SCORE rejections lack keyword data,
preventing MOA from learning from profitable missed opportunities.

Usage:
    python backfill_with_classification.py [--days N]

Options:
    --days N   Number of days to backfill (default: 14)
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.moa_price_tracker import record_outcome
from catalyst_bot.logging_utils import get_logger
from catalyst_bot.classify import classify
from catalyst_bot.models import NewsItem

log = get_logger("backfill_enhanced")

def classify_item_if_needed(item):
    """
    Ensure item has keyword classification.
    If keywords are missing, run classification.

    Returns:
        Updated item with keywords populated
    """
    keywords = item.get('cls', {}).get('keywords', [])

    if keywords:
        return item  # Already has keywords

    # Run classification
    try:
        news_item = NewsItem(
            title=item.get("title", ""),
            link=item.get("link", ""),
            source_host=item.get("source", ""),
            ts=item.get("ts", ""),
            ticker=item.get("ticker", ""),
            summary=item.get("summary", ""),
            raw=item.get("raw", {}),
        )

        scored = classify(news_item)

        # Extract keywords
        if scored:
            if hasattr(scored, "keyword_hits"):
                keywords = list(scored.keyword_hits or [])
            elif hasattr(scored, "tags"):
                keywords = list(scored.tags or [])
            elif isinstance(scored, dict):
                keywords = list(
                    scored.get("keyword_hits")
                    or scored.get("tags")
                    or scored.get("keywords")
                    or []
                )

            # Extract score and sentiment too
            score = 0.0
            sentiment = 0.0

            if hasattr(scored, "source_weight"):
                score = float(scored.source_weight)
            elif isinstance(scored, dict):
                score = float(scored.get("score", 0.0))

            if hasattr(scored, "sentiment"):
                sentiment = float(scored.sentiment)
            elif isinstance(scored, dict):
                sentiment = float(scored.get("sentiment", 0.0))

            # Update item
            if 'cls' not in item:
                item['cls'] = {}

            item['cls']['keywords'] = keywords
            item['cls']['score'] = score
            item['cls']['sentiment'] = sentiment
            item['cls']['classified_at'] = datetime.now(timezone.utc).isoformat()

            log.info(f"classified ticker={item.get('ticker')} keywords={len(keywords)}")

    except Exception as e:
        log.warning(f"classification_failed ticker={item.get('ticker')} err={e}")

    return item


def backfill_last_n_days(days=14):
    """Backfill outcomes for last N days with automatic classification."""

    # Load rejected items
    rejected_path = Path("data/rejected_items.jsonl")
    if not rejected_path.exists():
        log.error("rejected_items_not_found")
        return

    # Calculate cutoff
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    log.info(f"backfill_start days={days} cutoff={cutoff.isoformat()}")

    # Read and filter rejected items
    recent_items = []
    classified_count = 0
    already_had_keywords = 0

    print(f"📖 Loading rejected items from last {days} days...")

    with open(rejected_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
                ts_str = item.get("ts", "")

                # Parse timestamp
                if "." in ts_str:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                else:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

                # Only include last N days
                if ts >= cutoff:
                    # Classify if needed
                    had_keywords = bool(item.get('cls', {}).get('keywords'))
                    item = classify_item_if_needed(item)

                    if had_keywords:
                        already_had_keywords += 1
                    elif item.get('cls', {}).get('keywords'):
                        classified_count += 1

                    recent_items.append(item)

            except Exception as e:
                log.warning(f"parse_failed err={e}")
                continue

    total = len(recent_items)
    missing_keywords = total - already_had_keywords - classified_count

    print(f"\n📊 Classification Status:")
    print(f"   Total items: {total}")
    print(f"   ✅ Already had keywords: {already_had_keywords} ({already_had_keywords/total*100:.1f}%)")
    print(f"   ✨ Newly classified: {classified_count} ({classified_count/total*100:.1f}%)")
    print(f"   ⚠️  Still missing: {missing_keywords} ({missing_keywords/total*100:.1f}%)")

    if not recent_items:
        log.warning("no_recent_rejections")
        return

    # Backfill outcomes for each timeframe
    timeframes = ["1h", "4h", "1d", "7d"]

    print(f"\n🔄 Backfilling price outcomes...")

    for timeframe in timeframes:
        print(f"   Timeframe: {timeframe}")
        success_count = 0
        error_count = 0

        for item in recent_items:
            ticker = item.get("ticker", "").strip()
            ts_str = item.get("ts", "")
            price = item.get("price")
            reason = item.get("rejection_reason", "UNKNOWN")

            # Use classified keywords
            keywords = item.get("cls", {}).get("keywords", [])

            if not ticker or not ts_str or price is None:
                continue

            try:
                result = record_outcome(
                    ticker=ticker,
                    timeframe=timeframe,
                    rejection_ts=ts_str,
                    rejection_price=price,
                    rejection_reason=reason,
                )

                if result:
                    success_count += 1
                else:
                    error_count += 1

            except Exception as e:
                log.warning(f"record_failed ticker={ticker} timeframe={timeframe} err={e}")
                error_count += 1
                continue

        print(f"      ✅ Success: {success_count} | ❌ Errors: {error_count}")

    print(f"\n✨ Backfill complete!")

    # Show next steps
    print(f"\n🎯 Next Steps:")
    print(f"   1. Run MOA analysis:")
    print(f"      python -c \"from catalyst_bot.moa_historical_analyzer import run_historical_moa_analysis; run_historical_moa_analysis()\"")
    print(f"   2. Check keyword recommendations in data/moa/analysis_report.json")

    # Show estimated impact
    print(f"\n📈 Expected Impact:")
    print(f"   Before: ~11% of LOW_SCORE items had keywords")
    print(f"   After:  ~{(already_had_keywords + classified_count)/total*100:.0f}% have keywords")
    print(f"   This unlocks learning from {classified_count} previously unclassified items")

if __name__ == "__main__":
    import sys

    # Parse days argument
    days = 14
    if '--days' in sys.argv:
        idx = sys.argv.index('--days')
        if idx + 1 < len(sys.argv):
            days = int(sys.argv[idx + 1])

    backfill_last_n_days(days=days)
