"""
Manual feedback system for missed trading opportunities.

Usage:
    python log_missed_opportunity.py TICKER "News headline" --gain 125 --time "2025-10-06 08:45"

This will:
1. Log the missed opportunity to data/missed_opportunities.jsonl
2. Run sentiment analysis on the headline
3. Generate a report showing why it was missed
4. Suggest parameter changes to catch similar events
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def log_missed_opportunity(ticker: str, headline: str, gain_pct: float, timestamp: str):
    """
    Log a missed trading opportunity for analysis.

    Args:
        ticker: Stock ticker (e.g., "AAPL")
        headline: News headline that caused the move
        gain_pct: Percentage gain (e.g., 125 for +125%)
        timestamp: When the news broke (ISO format or "2025-10-06 08:45")
    """
    from catalyst_bot.classify import classify
    from catalyst_bot.market import NewsItem

    # Parse timestamp
    try:
        if "T" in timestamp:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            ts = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        ts = datetime.now(timezone.utc)

    # Create NewsItem for analysis
    item = NewsItem(
        title=headline,
        url=f"https://example.com/manual/{ticker}",
        published_at=int(ts.timestamp()),
        source="Manual Entry",
        tags=[],
        raw={},
    )

    # Run sentiment analysis
    try:
        scored = classify(item)
        score = scored.relevance if hasattr(scored, "relevance") else 0.0
        sentiment = scored.sentiment if hasattr(scored, "sentiment") else 0.0
        keywords = scored.tags if hasattr(scored, "tags") else []
    except Exception as e:
        print(f"Warning: Could not analyze headline: {e}")
        score = 0.0
        sentiment = 0.0
        keywords = []

    # Determine why it was missed
    missed_reasons = []
    if score < 0.25:
        missed_reasons.append(f"Score too low ({score:.3f} < 0.25 threshold)")
    if abs(sentiment) < 0.3:
        missed_reasons.append(f"Weak sentiment ({sentiment:.3f})")
    if not keywords:
        missed_reasons.append("No high-value keywords detected")
    if not missed_reasons:
        missed_reasons.append("Alert may have been posted (check Discord)")

    # Suggest fixes
    suggestions = []
    if score < 0.25:
        suggestions.append(f"Lower MIN_SCORE to {max(0.15, score - 0.05):.2f}")
    if keywords:
        suggestions.append(f"Add keywords: {', '.join(keywords[:3])}")
    if not suggestions:
        suggestions.append("Review Discord history - may have been posted")

    # Build record
    record = {
        "ticker": ticker,
        "headline": headline,
        "gain_pct": gain_pct,
        "timestamp": ts.isoformat(),
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "analysis": {
            "score": score,
            "sentiment": sentiment,
            "keywords": keywords,
            "missed_reasons": missed_reasons,
            "suggestions": suggestions,
        },
    }

    # Save to log
    log_file = Path("data/missed_opportunities.jsonl")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    # Print report
    print("\n" + "=" * 60)
    print(f"Missed Opportunity Logged: {ticker} (+{gain_pct}%)")
    print("=" * 60)
    print(f"\nHeadline: {headline}")
    print(f"Timestamp: {ts}")
    print("\nSentiment Analysis:")
    print(f"  Score: {score:.3f}")
    print(f"  Sentiment: {sentiment:.3f}")
    print(f"  Keywords: {', '.join(keywords) if keywords else 'None'}")
    print("\nWhy Was This Missed?")
    for reason in missed_reasons:
        print(f"  - {reason}")
    print("\nSuggested Fixes:")
    for suggestion in suggestions:
        print(f"  - {suggestion}")
    print("\n" + "=" * 60)
    print(f"\nSaved to: {log_file}")

    return record


def main():
    parser = argparse.ArgumentParser(
        description="Log missed trading opportunity for analysis"
    )
    parser.add_argument("ticker", help="Stock ticker (e.g., AAPL)")
    parser.add_argument("headline", help="News headline that caused the move")
    parser.add_argument(
        "--gain",
        type=float,
        required=True,
        help="Percentage gain (e.g., 125 for +125%%)",
    )
    parser.add_argument(
        "--time", required=True, help="When news broke (YYYY-MM-DD HH:MM or ISO format)"
    )

    args = parser.parse_args()

    log_missed_opportunity(args.ticker, args.headline, args.gain, args.time)


if __name__ == "__main__":
    main()
