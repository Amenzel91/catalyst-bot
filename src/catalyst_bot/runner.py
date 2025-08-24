"""Main runtime loop for the live catalyst bot.

This module orchestrates the continuous ingestion of news feeds,
deduplication, classification, and alerting. It is designed to run
indefinitely (unless invoked with ``--once``) and to gracefully
recover from errors without crashing. State such as seen IDs is
persisted between cycles to ensure idempotency.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .alerts import send_alert
from .charts import render_chart
from .classify import classify, load_dynamic_keyword_weights
from .config import get_settings
from .dedupe import hash_title
from .feeds import fetch_all_feeds
from .logs import log_event, setup_logging
from .market import get_latest_price, get_20d_avg_volume, get_intraday
from .models import NewsItem, ScoredItem
from .store import append_jsonl, load_seen_ids, save_seen_ids
from .universe import build_universe, is_under_price_ceiling


def _write_latest_ambiguous(ambiguous: List[NewsItem]) -> None:
    """Persist the most recent ambiguous items to ``out/latest.json``."""
    settings = get_settings()
    out_file = settings.out_dir / "latest.json"
    try:
        data = {
            "generated_at": datetime.utcnow().isoformat(),
            "ambiguous": [
                {
                    "ts_utc": item.ts_utc.isoformat(),
                    "title": item.title,
                    "url": item.canonical_url,
                    "source_host": item.source_host,
                }
                for item in ambiguous
            ],
        }
        out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def run_cycle(
    universe: Dict[str, float],
    seen_ids: Set[str],
    keyword_weights: Dict[str, float],
) -> None:
    """Execute a single cycle of the live bot."""
    settings = get_settings()
    logger = logging.getLogger("catalyst_bot")
    try:
        items = fetch_all_feeds()
    except Exception as exc:
        log_event({
            "ts_utc": datetime.utcnow().isoformat(),
            "level": "error",
            "message": "RSS fetch failed",
            "error": str(exc),
        })
        items = []
    new_scored: List[ScoredItem] = []
    ambiguous: List[NewsItem] = []
    for item in items:
        # Compute a stable ID for deduplication (hash of title)
        item_id = hash_title(item.title)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        # Persist raw record by date
        date_str = item.ts_utc.strftime("%Y%m%d")
        raw_file = settings.data_dir / "raw" / f"news-{date_str}.jsonl"
        append_jsonl(raw_file, {
            "ts_utc": item.ts_utc.isoformat(),
            "title": item.title,
            "canonical_url": item.canonical_url,
            "source_host": item.source_host,
            "ticker": item.ticker,
            "raw_text": item.raw_text,
        })
        # Append to last24 processed file
        last24_file = settings.data_dir / "processed" / "last24.jsonl"
        append_jsonl(last24_file, {
            "ts_utc": item.ts_utc.isoformat(),
            "title": item.title,
            "canonical_url": item.canonical_url,
            "source_host": item.source_host,
            "ticker": item.ticker,
            "raw_text": item.raw_text,
        })
        if settings.feature_record_only:
            continue
        if not item.ticker:
            # Record ambiguous items with no ticker for later inspection
            ambiguous.append(item)
            continue
        try:
            scored = classify(item, keyword_weights=keyword_weights)
        except Exception as exc:
            log_event({
                "ts_utc": datetime.utcnow().isoformat(),
                "level": "error",
                "message": "Classification failed",
                "ticker": item.ticker,
                "error": str(exc),
            })
            continue
        # Filter by price ceiling using latest price
        if not is_under_price_ceiling(item.ticker):
            continue
        new_scored.append(scored)
    # Save ambiguous items summary
    if ambiguous:
        _write_latest_ambiguous(ambiguous)
    if settings.feature_record_only or not settings.feature_alerts:
        return
    # Sort scored items by total_score and recency; ensure distinct tickers
    new_scored.sort(key=lambda s: (s.total_score, s.item.ts_utc), reverse=True)
    seen_tickers: Set[str] = set()
    alerts_to_send: List[ScoredItem] = []
    for scored in new_scored:
        ticker = scored.item.ticker
        if ticker in seen_tickers:
            continue
        alerts_to_send.append(scored)
        seen_tickers.add(ticker)
        if len(alerts_to_send) >= settings.max_alerts:
            break
    # Send alerts
    for scored in alerts_to_send:
        ticker = scored.item.ticker or ""
        # Fetch additional price context
        price = None
        pct_change = None
        vol_ratio = None
        try:
            price = get_latest_price(ticker)
            # Compute percent change vs previous close if possible
            intraday_df = get_intraday(ticker, interval="60min", output_size="compact")
            if intraday_df is not None and not intraday_df.empty:
                prev_close = intraday_df["close"].iloc[0]
                last_close = intraday_df["close"].iloc[-1]
                pct_change = (last_close - prev_close) / prev_close if prev_close else None
            # Compute relative volume
            avg_vol = get_20d_avg_volume(ticker)
            if avg_vol:
                session_vol = intraday_df["volume"].sum() if intraday_df is not None else None
                if session_vol:
                    vol_ratio = session_vol / avg_vol
        except Exception:
            pass
        # Render chart
        chart_path = None
        try:
            chart_path = render_chart(ticker, interval="5min", output_size="compact")
        except Exception:
            chart_path = None
        # Send alert
        try:
            send_alert(
                scored_item=scored,
                price=price,
                percent_change=pct_change,
                volume_ratio=vol_ratio,
                chart_relative_path=chart_path,
            )
        except Exception as exc:
            log_event({
                "ts_utc": datetime.utcnow().isoformat(),
                "level": "error",
                "message": "Alert sending failed",
                "ticker": ticker,
                "error": str(exc),
            })


def main(once: bool = False, loop: bool = False) -> None:
    """Entry point for the live runner.

    Parameters
    ----------
    once : bool, optional
        If ``True``, run a single cycle and exit.
    loop : bool, optional
        If ``True``, run continuously until interrupted.
    """
    settings = get_settings()
    logger = setup_logging()
    logger.info(
        f"Catalyst bot starting (record_only={settings.feature_record_only}, alerts={settings.feature_alerts})"
    )
    # Build universe once at startup
    try:
        universe = build_universe(price_ceiling=settings.price_ceiling)
    except Exception as exc:
        logger.error(f"Failed to build universe: {exc}")
        universe = {}
    # Load dynamic weights once per session
    keyword_weights = load_dynamic_keyword_weights()
    seen_ids_path = settings.data_dir / "seen_ids.json"
    seen_ids = load_seen_ids(seen_ids_path)

    stop_requested = False

    def handle_signal(signum, frame):  # type: ignore[override]
        nonlocal stop_requested
        stop_requested = True

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while True:
        cycle_start = datetime.utcnow()
        try:
            run_cycle(universe, seen_ids, keyword_weights)
        except Exception as exc:
            log_event({
                "ts_utc": datetime.utcnow().isoformat(),
                "level": "critical",
                "message": "Unhandled exception in run_cycle",
                "error": str(exc),
            })
        # Persist seen IDs after each cycle
        save_seen_ids(seen_ids, seen_ids_path)
        if once or stop_requested:
            break
        # Sleep until next cycle, accounting for execution time
        elapsed = (datetime.utcnow() - cycle_start).total_seconds()
        sleep_duration = max(settings.loop_seconds - elapsed, 1.0)
        time.sleep(sleep_duration)

    logger.info("Catalyst bot stopped")