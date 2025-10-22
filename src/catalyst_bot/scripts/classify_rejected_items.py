"""
Retroactive Keyword Extraction for Rejected Items
==================================================

This script processes rejected items in data/rejected_items.jsonl that are
missing keyword data. It runs classification on each item to extract:
- Keywords from title/summary
- Sentiment scores
- Full classification metadata

The classified data is written to data/rejected_items_classified.jsonl
with the same structure as rejected_items.jsonl but with populated keywords.

This enables MOA (Missed Opportunities Analyzer) to generate keyword weight
recommendations by analyzing which keywords appear in rejected items that
later had significant price movements.

Usage:
    python -m catalyst_bot.scripts.classify_rejected_items [--dry-run] [--limit N]

Options:
    --dry-run    Show what would be processed without writing output
    --limit N    Only process first N items (for testing)
    --force      Reprocess all items, even those with keywords

Author: Claude Code
Date: 2025-10-15
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from catalyst_bot.classify import classify
from catalyst_bot.logging_utils import get_logger
from catalyst_bot.models import NewsItem

log = get_logger(__name__)


def load_rejected_items(file_path: Path) -> List[Dict[str, Any]]:
    """
    Load rejected items from JSONL file.

    Args:
        file_path: Path to rejected_items.jsonl

    Returns:
        List of rejected item dicts
    """
    if not file_path.exists():
        log.error(f"rejected_items_file_not_found path={file_path}")
        return []

    items = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
                items.append(item)
            except json.JSONDecodeError as e:
                log.warning(
                    f"rejected_items_parse_failed line={line_num} err={e}"
                )

    log.info(f"rejected_items_loaded count={len(items)} path={file_path}")
    return items


def needs_classification(item: Dict[str, Any], force: bool = False) -> bool:
    """
    Check if item needs classification (missing or empty keywords).

    Args:
        item: Rejected item dict
        force: Force classification even if keywords exist

    Returns:
        True if item should be classified
    """
    if force:
        return True

    cls = item.get("cls", {})
    keywords = cls.get("keywords", [])

    # Need classification if:
    # 1. No cls section
    # 2. No keywords field
    # 3. Empty keywords list
    return not cls or not keywords or len(keywords) == 0


def classify_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Run classification on a rejected item.

    Args:
        item: Rejected item dict with title, ticker, source, etc.

    Returns:
        Updated item dict with classification data, or None on error
    """
    try:
        # Build NewsItem object for classification
        news_item = NewsItem(
            title=item.get("title", ""),
            link=item.get("link", ""),
            source_host=item.get("source", ""),
            ts=item.get("ts", ""),
            ticker=item.get("ticker", ""),
            summary=item.get("summary", ""),
            raw=item.get("raw", {}),
        )

        # Run classification
        scored = classify(news_item)

        # Extract classification results
        score = 0.0
        sentiment = 0.0
        keywords = []

        if scored:
            # Extract score
            if hasattr(scored, "source_weight"):
                score = float(scored.source_weight)
            elif isinstance(scored, dict):
                score = float(scored.get("score", 0.0))

            # Extract sentiment
            if hasattr(scored, "sentiment"):
                sentiment = float(scored.sentiment)
            elif isinstance(scored, dict):
                sentiment = float(scored.get("sentiment", 0.0))

            # Extract keywords (tags/keyword_hits)
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

        # Update cls section with classification results
        updated_item = item.copy()
        updated_item["cls"] = {
            "score": score,
            "sentiment": sentiment,
            "keywords": keywords,
        }

        # Preserve existing sentiment breakdown if available
        if "sentiment_breakdown" in item.get("cls", {}):
            updated_item["cls"]["sentiment_breakdown"] = item["cls"]["sentiment_breakdown"]
        if "sentiment_confidence" in item.get("cls", {}):
            updated_item["cls"]["sentiment_confidence"] = item["cls"]["sentiment_confidence"]
        if "sentiment_sources_used" in item.get("cls", {}):
            updated_item["cls"]["sentiment_sources_used"] = item["cls"]["sentiment_sources_used"]

        # Add classification metadata
        updated_item["classified_at"] = datetime.now(timezone.utc).isoformat()
        updated_item["classification_version"] = "retroactive_v1"

        return updated_item

    except Exception as e:
        log.error(
            f"classification_failed ticker={item.get('ticker')} err={e}"
        )
        return None


def write_classified_items(
    items: List[Dict[str, Any]], output_path: Path
) -> int:
    """
    Write classified items to output file.

    Args:
        items: List of classified item dicts
        output_path: Path to output JSONL file

    Returns:
        Number of items written
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1

    log.info(f"classified_items_written count={count} path={output_path}")
    return count


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Retroactively classify rejected items to extract keywords",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all items missing keywords
  python -m catalyst_bot.scripts.classify_rejected_items

  # Dry run to see what would be processed
  python -m catalyst_bot.scripts.classify_rejected_items --dry-run

  # Process first 10 items for testing
  python -m catalyst_bot.scripts.classify_rejected_items --limit 10

  # Force reprocess all items (even those with keywords)
  python -m catalyst_bot.scripts.classify_rejected_items --force
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without writing output",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process first N items (for testing)",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all items, even those with keywords",
    )

    parser.add_argument(
        "--input",
        type=str,
        default="data/rejected_items.jsonl",
        help="Input file path (default: data/rejected_items.jsonl)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="data/rejected_items_classified.jsonl",
        help="Output file path (default: data/rejected_items_classified.jsonl)",
    )

    args = parser.parse_args()

    # Resolve paths
    input_path = Path(args.input)
    output_path = Path(args.output)

    print("=" * 70)
    print("RETROACTIVE KEYWORD EXTRACTION FOR REJECTED ITEMS")
    print("=" * 70)
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Mode:   {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.limit:
        print(f"Limit:  {args.limit} items")
    if args.force:
        print("Force:  Reprocessing ALL items")
    print()

    # Load rejected items
    print("Loading rejected items...")
    all_items = load_rejected_items(input_path)

    if not all_items:
        print("No items found. Exiting.")
        return 0

    print(f"Loaded {len(all_items)} total items")
    print()

    # Filter items that need classification
    print("Filtering items that need classification...")
    items_to_process = [
        item for item in all_items if needs_classification(item, force=args.force)
    ]

    print(f"Found {len(items_to_process)} items needing classification")
    print(f"Skipping {len(all_items) - len(items_to_process)} items with keywords")
    print()

    if not items_to_process:
        print("No items need classification. Exiting.")
        return 0

    # Apply limit if specified
    if args.limit and args.limit > 0:
        items_to_process = items_to_process[: args.limit]
        print(f"Limited to first {len(items_to_process)} items")
        print()

    # Dry run: just show what would be processed
    if args.dry_run:
        print("DRY RUN - Would process these items:")
        print("-" * 70)
        for i, item in enumerate(items_to_process[:10], 1):  # Show first 10
            ticker = item.get("ticker", "N/A")
            title = item.get("title", "")[:50]
            print(f"{i}. {ticker}: {title}...")

        if len(items_to_process) > 10:
            print(f"... and {len(items_to_process) - 10} more")

        print("-" * 70)
        print(f"\nTotal items to process: {len(items_to_process)}")
        print("Run without --dry-run to actually process items.")
        return 0

    # Process items
    print(f"Processing {len(items_to_process)} items...")
    print("-" * 70)

    classified_items = []
    success_count = 0
    error_count = 0

    for i, item in enumerate(items_to_process, 1):
        ticker = item.get("ticker", "N/A")
        title = item.get("title", "")[:50]

        # Show progress every 10 items
        if i % 10 == 0 or i == len(items_to_process):
            print(f"Progress: {i}/{len(items_to_process)} ({i/len(items_to_process)*100:.1f}%)")

        # Classify item
        classified = classify_item(item)

        if classified:
            classified_items.append(classified)
            success_count += 1

            # Show keyword extraction results
            keywords = classified.get("cls", {}).get("keywords", [])
            if keywords:
                log.debug(
                    f"keywords_extracted ticker={ticker} count={len(keywords)} "
                    f"keywords={','.join(keywords[:5])}"
                )
        else:
            error_count += 1
            log.warning(f"classification_failed ticker={ticker}")

    print("-" * 70)
    print()

    # Write results
    if classified_items:
        print(f"Writing {len(classified_items)} classified items to {output_path}...")
        write_classified_items(classified_items, output_path)
        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total items processed:     {len(items_to_process)}")
    print(f"Successfully classified:   {success_count}")
    print(f"Errors:                    {error_count}")
    print(f"Output written to:         {output_path}")
    print()

    # Show sample of classified items
    if classified_items:
        print("Sample classified items:")
        print("-" * 70)
        for item in classified_items[:5]:
            ticker = item.get("ticker", "N/A")
            keywords = item.get("cls", {}).get("keywords", [])
            score = item.get("cls", {}).get("score", 0.0)
            sentiment = item.get("cls", {}).get("sentiment", 0.0)

            print(f"Ticker:    {ticker}")
            print(f"Score:     {score:.2f}")
            print(f"Sentiment: {sentiment:.2f}")
            print(f"Keywords:  {', '.join(keywords) if keywords else '(none)'}")
            print()

        if len(classified_items) > 5:
            print(f"... and {len(classified_items) - 5} more")

    print("=" * 70)
    print("DONE")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
