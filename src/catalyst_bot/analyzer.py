"""End‑of‑day and pre‑market analyzer for the catalyst bot.

This module processes the prior session's news items to evaluate their
market impact and update the classifier's keyword weights. It is
intended to be run once per session, either after the market closes
(EOD) or before the market opens (PREMARKET), depending on the
configuration.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import get_settings
from .logs import log_event, setup_logging
from .models import NewsItem, TradeSimResult
from .store import read_jsonl, rolling_last24
from .tradesim import simulate_trades, TradeSimConfig
from .learning import update_keyword_stats


def load_last24_news(date: Optional[str] = None) -> List[NewsItem]:
    """Load news items from the last 24 hours for analysis.

    If a specific date is provided (YYYY‑MM‑DD), this function will look
    for a raw ingest file matching that date in the ``data/raw``
    directory. Otherwise it falls back to the ``last24.jsonl`` file in
    ``data/processed``. Only items with a ticker are returned.
    """
    settings = get_settings()
    news: List[NewsItem] = []
    if date:
        raw_file = settings.data_dir / "raw" / f"news-{date.replace('-', '')}.jsonl"
        recs = read_jsonl(raw_file)
    else:
        last24_file = settings.data_dir / "processed" / "last24.jsonl"
        recs = read_jsonl(last24_file)
    for rec in recs:
        try:
            ts = datetime.fromisoformat(rec.get("ts_utc"))  # type: ignore[arg-type]
        except Exception:
            continue
        item = NewsItem(
            ts_utc=ts,
            title=rec.get("title", ""),
            canonical_url=rec.get("canonical_url", rec.get("link", "")),
            source_host=rec.get("source_host", ""),
            ticker=rec.get("ticker"),
            raw_text=rec.get("raw_text"),
        )
        if item.ticker:
            news.append(item)
    return news


def run_analysis(date: Optional[str] = None) -> None:
    """Perform the analyzer workflow for the specified date."""
    settings = get_settings()
    logger = setup_logging()
    logger.info(f"Analyzer starting for date {date or 'last24'}")
    news_items = load_last24_news(date)
    sim_config = TradeSimConfig()
    all_results: List[TradeSimResult] = []
    for item in news_items:
        try:
            results = simulate_trades(item, config=sim_config)
            all_results.extend(results)
        except Exception as exc:
            log_event({
                "ts_utc": datetime.utcnow().isoformat(),
                "level": "error",
                "message": "Trade simulation failed",
                "ticker": item.ticker,
                "error": str(exc),
            })
    # Aggregate simple metrics: proportion of positive returns
    positives = 0
    negatives = 0
    for res in all_results:
        # Use mid return to classify
        mid_return = res.returns.get("mid", 0.0)
        if mid_return >= settings.analyzer_target_pct:
            positives += 1
        elif mid_return <= -settings.analyzer_target_pct:
            negatives += 1
    total = len(all_results)
    metrics = {
        "total_trades": total,
        "positive_count": positives,
        "negative_count": negatives,
        "positive_rate": positives / total if total else 0.0,
        "negative_rate": negatives / total if total else 0.0,
    }
    # Persist metrics
    date_str = date or datetime.utcnow().strftime("%Y%m%d")
    analyzer_dir = settings.data_dir / "analyzer"
    analyzer_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = analyzer_dir / f"metrics-{date_str}.json"
    try:
        metrics_file.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    except Exception:
        pass
    # Update keyword statistics
    update_keyword_stats(all_results, date_str)
    logger.info(f"Analyzer completed for date {date_str}")


def main(date: Optional[str] = None) -> None:
    """Entry point for CLI invocation."""
    run_analysis(date)