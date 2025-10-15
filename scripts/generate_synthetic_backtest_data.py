"""
Generate Synthetic Backtest Data
=================================

Creates realistic synthetic historical alert data for backtesting purposes.
Generates events.jsonl with 500+ events spanning 2023-2025.

Usage:
    python scripts/generate_synthetic_backtest_data.py --start 2023-01-01 --end 2025-01-01 --count 500

Author: Claude Code
Date: 2025-10-14
"""

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any

# Penny stock tickers (real stocks under $10)
PENNY_TICKERS = [
    "SNDL", "LCID", "PLTR", "SOFI", "NIO", "PLUG", "XPEV", "WISH",
    "CLOV", "BBIG", "ATER", "CEI", "GREE", "PROG", "BKKT", "PHUN",
    "DWAC", "MARK", "MULN", "AMTD", "HKD", "APPH", "NILE", "BNGO",
    "OCGN", "EXPR", "KOSS", "WKHS", "RIDE", "GOEV", "NKLA", "HYLN",
    "SKLZ", "DKNG", "SPCE", "OPEN", "HOOD", "COIN", "RBLX", "PATH",
    "AFRM", "UPST", "BARK", "STEM", "CLSK", "RIOT", "MARA", "EBON",
]

# Catalyst keywords (weighted by frequency)
KEYWORD_POOL = {
    # High frequency (common catalysts)
    "earnings": 0.15,
    "revenue": 0.12,
    "fda": 0.08,
    "clinical": 0.08,
    "trial": 0.07,
    "partnership": 0.06,
    "contract": 0.06,
    "approval": 0.05,
    "upgrade": 0.05,
    # Medium frequency
    "merger": 0.04,
    "acquisition": 0.04,
    "phase": 0.04,
    "breakthrough": 0.03,
    "patent": 0.03,
    "positive": 0.03,
    "strong": 0.03,
    # Lower frequency (rare catalysts)
    "buyout": 0.02,
    "breakthrough": 0.02,
}

# Source credibility weights
SOURCES = [
    ("sec_8k", 0.95),
    ("globenewswire", 0.85),
    ("businesswire", 0.85),
    ("accesswire", 0.75),
    ("sec_424b5", 0.90),
]


def generate_random_date(start: datetime, end: datetime) -> datetime:
    """Generate random datetime between start and end during market hours."""
    delta = end - start
    random_days = random.randint(0, delta.days)
    date = start + timedelta(days=random_days)

    # Set to market hours (9:30 AM - 4:00 PM ET)
    market_open_hour = 9 + random.randint(0, 6)  # 9 AM to 3 PM
    market_minute = random.randint(0, 59)

    return date.replace(
        hour=market_open_hour,
        minute=market_minute,
        second=0,
        microsecond=0,
        tzinfo=timezone.utc
    )


def generate_keywords(num_keywords: int = None) -> List[str]:
    """Generate weighted random keywords."""
    if num_keywords is None:
        num_keywords = random.choices([1, 2, 3, 4], weights=[0.3, 0.4, 0.2, 0.1])[0]

    keywords = []
    keyword_list = list(KEYWORD_POOL.keys())
    weights = list(KEYWORD_POOL.values())

    for _ in range(num_keywords):
        kw = random.choices(keyword_list, weights=weights)[0]
        if kw not in keywords:
            keywords.append(kw)

    return keywords


def generate_price() -> float:
    """Generate realistic penny stock price ($0.10 - $10.00)."""
    # Weighted towards lower prices (more penny stocks under $5)
    if random.random() < 0.7:
        # $0.10 - $5.00 (70% of stocks)
        return round(random.uniform(0.10, 5.00), 2)
    else:
        # $5.00 - $10.00 (30% of stocks)
        return round(random.uniform(5.00, 10.00), 2)


def generate_score() -> float:
    """Generate classification score (biased towards higher scores since these are alerts)."""
    # Most alerts should be above threshold (0.25)
    # Use beta distribution to bias towards higher scores
    score = random.betavariate(5, 2)  # Skewed towards 1.0
    return round(max(0.25, min(1.0, score)), 2)


def generate_sentiment() -> float:
    """Generate sentiment score (biased positive for alerts)."""
    # Alerts tend to have positive sentiment
    sentiment = random.gauss(0.6, 0.25)  # Mean 0.6, std 0.25
    return round(max(-1.0, min(1.0, sentiment)), 2)


def generate_confidence() -> float:
    """Generate confidence score."""
    confidence = random.betavariate(4, 2)  # Skewed towards higher confidence
    return round(confidence, 2)


def generate_synthetic_events(
    start_date: str,
    end_date: str,
    count: int = 500,
) -> List[Dict[str, Any]]:
    """
    Generate synthetic historical alert events.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        count: Number of events to generate

    Returns:
        List of event dictionaries
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    events = []

    # Track ticker frequency to avoid unrealistic clustering
    ticker_usage = {ticker: 0 for ticker in PENNY_TICKERS}

    for i in range(count):
        # Select ticker (avoid overusing same tickers)
        available_tickers = [
            t for t, usage in ticker_usage.items() if usage < count // len(PENNY_TICKERS) + 5
        ]
        if not available_tickers:
            available_tickers = list(ticker_usage.keys())

        ticker = random.choice(available_tickers)
        ticker_usage[ticker] += 1

        # Generate timestamp
        ts = generate_random_date(start_dt, end_dt)

        # Generate price
        price = generate_price()

        # Generate keywords
        keywords = generate_keywords()

        # Select source
        source, source_weight = random.choices(
            [(s, w) for s, w in SOURCES],
            weights=[w for _, w in SOURCES]
        )[0]

        # Generate scores
        base_score = generate_score()
        sentiment = generate_sentiment()
        confidence = generate_confidence()

        # Create event
        event = {
            "ts": ts.isoformat(),
            "ticker": ticker,
            "price": price,
            "source": source,
            "cls": {
                "keywords": keywords,
                "score": base_score,
                "sentiment": sentiment,
                "confidence": confidence,
            },
        }

        events.append(event)

    # Sort by timestamp
    events.sort(key=lambda e: e["ts"])

    return events


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic backtest data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 500 events for 2023-2025
  python scripts/generate_synthetic_backtest_data.py --start 2023-01-01 --end 2025-01-01 --count 500

  # Generate 1000 events for full 2-year backtest
  python scripts/generate_synthetic_backtest_data.py --start 2023-01-01 --end 2025-01-01 --count 1000

  # Append to existing events.jsonl
  python scripts/generate_synthetic_backtest_data.py --start 2024-01-01 --end 2025-01-01 --count 200 --append
        """,
    )

    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--count", type=int, default=500, help="Number of events (default: 500)")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing events.jsonl (default: overwrite)"
    )
    parser.add_argument(
        "--output",
        default="data/events.jsonl",
        help="Output file path (default: data/events.jsonl)"
    )

    args = parser.parse_args()

    # Validate dates
    try:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
        end_dt = datetime.strptime(args.end, "%Y-%m-%d")

        if start_dt >= end_dt:
            print("Error: Start date must be before end date")
            return 1

        if end_dt > datetime.now():
            print("Warning: End date is in the future - using current date instead")
            args.end = datetime.now().strftime("%Y-%m-%d")

    except ValueError as e:
        print(f"Error: Invalid date format - {e}")
        return 1

    print(f"Generating {args.count} synthetic events...")
    print(f"  Date range: {args.start} to {args.end}")
    print(f"  Mode: {'append' if args.append else 'overwrite'}")
    print()

    # Generate events
    events = generate_synthetic_events(args.start, args.end, args.count)

    # Create output directory if needed
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to file
    mode = "a" if args.append else "w"

    with open(output_path, mode, encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    print(f"[OK] Generated {len(events)} events")
    print(f"[OK] Written to {output_path}")
    print()

    # Print statistics
    tickers = set(e["ticker"] for e in events)
    sources = {}
    keywords = {}

    for event in events:
        source = event.get("source", "unknown")
        sources[source] = sources.get(source, 0) + 1

        for kw in event.get("cls", {}).get("keywords", []):
            keywords[kw] = keywords.get(kw, 0) + 1

    print("Statistics:")
    print(f"  Unique tickers: {len(tickers)}")
    print(f"  Sources: {', '.join(f'{s}={c}' for s, c in sorted(sources.items()))}")
    print(f"  Top keywords: {', '.join(f'{k}={c}' for k, c in sorted(keywords.items(), key=lambda x: -x[1])[:10])}")
    print()

    avg_score = sum(e["cls"]["score"] for e in events) / len(events)
    avg_sentiment = sum(e["cls"]["sentiment"] for e in events) / len(events)
    price_range = (
        min(e["price"] for e in events),
        max(e["price"] for e in events)
    )

    print(f"  Avg score: {avg_score:.3f}")
    print(f"  Avg sentiment: {avg_sentiment:.3f}")
    print(f"  Price range: ${price_range[0]:.2f} - ${price_range[1]:.2f}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
