"""
Historical Data Bootstrapper - MOA Phase 2.5B
==============================================

Backfill 6-12 months of rejected items and outcomes for the MOA system.

Process:
1. Fetch historical SEC feeds month-by-month with date filtering
2. Run through current classification logic to identify rejections
3. Fetch historical prices at multiple timeframes (15m, 30m, 1h, 4h, 1d, 7d)
4. Write to rejected_items.jsonl and outcomes.jsonl
5. Support checkpoint/resume for long-running scrapes

Author: Claude Code (MOA Phase 2.5B)
Date: 2025-10-11
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import feedparser
import finnhub
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

# Load environment variables from .env file
# This ensures Discord webhooks and API keys are available
_env_path = Path(".") / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from .classify import classify  # noqa: E402
from .config import get_settings  # noqa: E402
from .discord_transport import post_discord_with_backoff  # noqa: E402
from .feeds import _normalize_entry, extract_ticker  # noqa: E402
from .llm_usage_monitor import get_monitor  # noqa: E402
from .logging_utils import get_logger  # noqa: E402
from .rvol import calculate_rvol  # noqa: E402
from .sector_context import get_sector_manager  # noqa: E402
from .ticker_resolver import TickerResolver  # noqa: E402

log = get_logger("historical_bootstrapper")

# Initialize ticker resolver for SEC company name lookups
try:
    _ticker_resolver = TickerResolver()
except Exception as e:
    log.warning(f"ticker_resolver_init_failed err={e}")
    _ticker_resolver = None

# Initialize Finnhub API client for historical price data
try:
    _finnhub_api_key = os.getenv("FINNHUB_API_KEY")
    if not _finnhub_api_key:
        log.warning("finnhub_api_key_missing set FINNHUB_API_KEY environment variable")
        _finnhub_client = None
    else:
        _finnhub_client = finnhub.Client(api_key=_finnhub_api_key)
        log.info("finnhub_client_initialized")
except Exception as e:
    log.warning(f"finnhub_client_init_failed err={e}")
    _finnhub_client = None

# Timeframes to track (in hours) - smart selection based on data age
ALL_TIMEFRAMES = {
    "15m": 0.25,
    "30m": 0.5,
    "1h": 1,
    "4h": 4,
    "1d": 24,
    "7d": 168,
}

# Rate limiting: seconds between price API calls
RATE_LIMIT_SECONDS = 0.5  # Legacy yfinance rate limit (kept for compatibility)
FINNHUB_RATE_LIMIT = 1.2  # Finnhub: 50 calls/min = 1 call per 1.2 seconds (with buffer)

# Phase 2: Bulk fetching configuration
BULK_FETCH_BATCH_SIZE = 10  # Number of tickers to fetch per batch
CACHE_TTL_DAYS = 30  # Cache validity in days

# Feed URL templates - supports both SEC and news feeds
FEED_URLS = {
    # SEC regulatory feeds (require company name lookup)
    "sec_8k": (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcurrent&type=8-K&company=&dateb=&owner=include&"
        "start=0&count=100&output=atom"
    ),
    "sec_424b5": (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcurrent&type=424B5&company=&dateb=&owner=include&"
        "start=0&count=100&output=atom"
    ),
    "sec_fwp": (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcurrent&type=FWP&company=&dateb=&owner=include&"
        "start=0&count=100&output=atom"
    ),
    "sec_13d": (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcurrent&type=SC%2013D&company=&dateb=&owner=include&"
        "start=0&count=100&output=atom"
    ),
    "sec_13g": (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcurrent&type=SC%2013G&company=&dateb=&owner=include&"
        "start=0&count=100&output=atom"
    ),
    # News/PR feeds (have ticker in title, no date filtering)
    "globenewswire_public": (
        "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/"
        "GlobeNewswire%20-%20News%20about%20Public%20Companies"
    ),
    "prnewswire": "https://www.prnewswire.com/rss/all-news.rss",
    "businesswire": "https://www.businesswire.com/portal/site/home/news/?rss=1",
    "accesswire": "https://www.accesswire.com/rss/latest",
}

# SEC feed URL templates (for backwards compatibility)
SEC_FEED_URLS = {k: v for k, v in FEED_URLS.items() if k.startswith("sec_")}


# ============================================================================
# Phase 1 Optimizations: Rate Limiting, Retry Logic, and Utilities
# ============================================================================


class SECRateLimiter:
    """
    Token bucket rate limiter for SEC and yfinance API calls.

    Implements thread-safe rate limiting with token bucket algorithm.
    Supports 10 requests/second for SEC, 2 requests/second for yfinance.
    """

    def __init__(self, requests_per_second: float):
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests allowed per second
        """
        self.requests_per_second = requests_per_second
        self.tokens = requests_per_second
        self.max_tokens = requests_per_second
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        """
        Acquire a token, blocking if necessary until a token is available.

        Uses token bucket algorithm: tokens refill at a constant rate,
        and each request consumes one token.
        """
        with self.lock:
            while True:
                now = time.time()
                elapsed = now - self.last_update

                # Refill tokens based on elapsed time
                self.tokens = min(
                    self.max_tokens, self.tokens + elapsed * self.requests_per_second
                )
                self.last_update = now

                # If we have a token available, consume it and return
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                # Otherwise, calculate wait time for next token
                wait_time = (1.0 - self.tokens) / self.requests_per_second
                time.sleep(wait_time)


def retry_with_backoff(
    max_retries: int = 5,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> Callable:
    """
    Decorator for retrying functions with exponential backoff and jitter.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay after each retry
        max_delay: Maximum delay between retries in seconds
        jitter: Add random jitter to prevent thundering herd

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Final attempt failed, raise the exception
                        log.warning(
                            f"retry_exhausted func={func.__name__} "
                            f"attempts={max_retries + 1} err={e}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    current_delay = min(delay, max_delay)

                    # Add jitter (random variation ±25%) to prevent thundering herd
                    if jitter:
                        jitter_range = current_delay * 0.25
                        current_delay += random.uniform(-jitter_range, jitter_range)

                    log.debug(
                        f"retry_attempt func={func.__name__} attempt={attempt + 1} "
                        f"delay={current_delay:.2f}s err={e}"
                    )

                    time.sleep(max(0, current_delay))
                    delay *= backoff_factor

            # Should never reach here, but just in case
            raise last_exception

        return wrapper

    return decorator


def _extract_sec_ticker(title: str) -> Optional[str]:
    """
    Extract ticker from SEC filing title.

    SEC titles have format: "8-K - Company Name (CIK) (Filer)"
    We extract the company name and use TickerResolver to find the ticker.

    Args:
        title: SEC filing title

    Returns:
        Ticker symbol or None if not found
    """
    if not title or not _ticker_resolver:
        return None

    # Extract company name from SEC title
    # Format: "8-K - Company Name (CIK) (Filer)"
    import re

    match = re.match(r"^[\w\-]+\s+-\s+(.+?)\s+\(\d+\)", title)
    if not match:
        return None

    company_name = match.group(1).strip()
    if not company_name:
        return None

    # Use TickerResolver to look up ticker by company name
    try:
        result = _ticker_resolver.resolve_one(company_name)
        if result:
            log.debug(
                f"sec_ticker_resolved company='{company_name}' ticker={result.ticker}"
            )
            return result.ticker
        else:
            log.debug(f"sec_ticker_not_found company='{company_name}'")
            return None
    except Exception as e:
        log.debug(f"sec_ticker_lookup_failed company='{company_name}' err={e}")
        return None


def _fetch_finnhub_price(
    ticker: str, date: datetime, resolution: str = "D"
) -> Optional[float]:
    """
    Fetch historical price from Finnhub API.

    Args:
        ticker: Stock ticker symbol
        date: Date to fetch price for
        resolution: Resolution (D=daily, 60=hourly, 15=15min, etc.)

    Returns:
        Close price at that date, or None if unavailable
    """
    if not _finnhub_client:
        log.warning("finnhub_client_not_initialized")
        return None

    try:
        # Convert date to UNIX timestamp
        # Finnhub expects timestamps in seconds (not milliseconds)
        start_ts = int(date.timestamp())
        # Add 1 day buffer to ensure we get the data
        end_ts = int((date + timedelta(days=2)).timestamp())

        # Fetch candles from Finnhub
        # Resolution: D (daily), 60 (hourly), 15 (15-min), etc.
        response = _finnhub_client.stock_candles(ticker, resolution, start_ts, end_ts)

        # Check response status
        if not response or response.get("s") != "ok":
            log.debug(
                f"finnhub_no_data ticker={ticker} date={date.date()} "
                f"status={response.get('s') if response else 'none'}"
            )
            return None

        # Extract close prices
        closes = response.get("c", [])
        if not closes:
            return None

        # Return the last close price (closest to our target date)
        return float(closes[-1])

    except Exception as e:
        log.debug(f"finnhub_fetch_failed ticker={ticker} date={date.date()} err={e}")
        return None


# ============================================================================
# Phase 2 Optimizations: Bulk Fetching and Multi-Level Caching
# ============================================================================


def _get_cache_key(ticker: str, date: datetime) -> str:
    """
    Generate cache key for price data.

    Args:
        ticker: Stock ticker
        date: Date for price lookup

    Returns:
        Cache key string
    """
    date_str = date.strftime("%Y-%m-%d")
    return f"{ticker}_{date_str}"


def _get_disk_cache_path(cache_dir: Path, ticker: str, date: datetime) -> Path:
    """
    Get disk cache file path for a ticker/date combination.

    Args:
        cache_dir: Cache directory path
        ticker: Stock ticker
        date: Date for price lookup

    Returns:
        Path to cache file
    """
    # Use hash to create subdirectories and avoid too many files in one dir
    cache_key = _get_cache_key(ticker, date)
    key_hash = hashlib.md5(cache_key.encode()).hexdigest()

    # Create 2-level directory structure: first 2 chars / next 2 chars
    subdir = cache_dir / key_hash[:2] / key_hash[2:4]
    subdir.mkdir(parents=True, exist_ok=True)

    return subdir / f"{cache_key}.pkl"


class HistoricalBootstrapper:
    """
    Backfill 6-12 months of rejected items and outcomes.

    Process:
    1. Fetch historical feeds month-by-month
    2. Run through current classification logic
    3. Identify rejections based on current thresholds
    4. Fetch historical prices at multiple timeframes
    5. Write to rejected_items.jsonl and outcomes.jsonl
    """

    def __init__(
        self,
        start_date: str,  # '2024-01-15'
        end_date: str,  # '2025-01-14'
        sources: List[str],  # ['sec_8k', 'sec_424b5', 'sec_fwp']
        batch_size: int = 100,
        resume: bool = False,
    ):
        """
        Initialize historical bootstrapper.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            sources: List of SEC feed sources to scrape
            batch_size: Number of items to process per batch
            resume: Whether to resume from last checkpoint
        """
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )

        # Validate date range
        if self.start_date >= self.end_date:
            raise ValueError(
                f"start_date ({start_date}) must be before end_date ({end_date})"
            )

        self.sources = sources
        self.batch_size = batch_size
        self.resume = resume

        # Load settings
        self.settings = get_settings()

        # Paths
        self.rejected_path = Path("data/rejected_items.jsonl")
        self.outcomes_path = Path("data/moa/outcomes.jsonl")
        self.checkpoint_path = Path("data/moa/bootstrap_checkpoint.json")
        self.cache_dir = Path("data/cache/bootstrapper")

        # Create directories
        self.rejected_path.parent.mkdir(parents=True, exist_ok=True)
        self.outcomes_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Statistics
        self.stats = {
            "feeds_fetched": 0,
            "items_processed": 0,
            "rejections_found": 0,
            "outcomes_recorded": 0,
            "errors": 0,
            "skipped": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "disk_cache_hits": 0,
            "bulk_fetches": 0,
        }

        # Cache of already processed items (to avoid duplicates)
        self._processed_ids: Set[str] = set()

        # Phase 2: Multi-level price cache (memory + disk)
        # Format: {(ticker, date_str): price}
        self._price_cache: Dict[Tuple[str, str], float] = {}
        self._cache_lock = threading.Lock()

        # Discord notifications
        self._last_progress_time = time.time()
        self._progress_interval = 900  # 15 minutes between progress updates

        log.info(
            f"bootstrap_init start={start_date} end={end_date} "
            f"sources={','.join(sources)} batch_size={batch_size} resume={resume}"
        )

    def run(self) -> Dict[str, Any]:
        """
        Main execution loop - process month by month.

        Returns:
            Statistics dictionary with processing counts
        """
        start_time = time.time()
        self.stats["start_time"] = start_time

        # Send start notification
        start_embed = self._build_start_embed()
        self._send_discord_notification(start_embed)

        # Load checkpoint if resuming
        checkpoint_date = None
        if self.resume:
            checkpoint_date = self._load_checkpoint()
            if checkpoint_date:
                log.info(f"bootstrap_resume checkpoint_date={checkpoint_date.date()}")

        # Determine starting point
        current_date = checkpoint_date if checkpoint_date else self.start_date

        # Process month by month
        while current_date < self.end_date:
            # Calculate month range
            month_start = current_date
            month_end = min(
                month_start + timedelta(days=30), self.end_date  # ~1 month chunks
            )

            log.info(
                f"bootstrap_month_start month={month_start.strftime('%Y-%m')} "
                f"range={month_start.date()} to {month_end.date()}"
            )

            try:
                # Process this month
                self._process_month(month_start, month_end)

                # Save checkpoint
                self._save_checkpoint(month_end)

                # Maybe send progress update
                self._maybe_send_progress_update()

            except Exception as e:
                log.error(
                    f"bootstrap_month_failed month={month_start.strftime('%Y-%m')} err={e}"
                )
                self.stats["errors"] += 1

                # Send error notification
                error_embed = self._build_error_embed(str(e))
                self._send_discord_notification(error_embed)

            # Move to next month
            current_date = month_end

        elapsed = time.time() - start_time
        self.stats["elapsed_seconds"] = round(elapsed, 2)

        log.info(
            f"bootstrap_complete "
            f"feeds={self.stats['feeds_fetched']} "
            f"items={self.stats['items_processed']} "
            f"rejections={self.stats['rejections_found']} "
            f"outcomes={self.stats['outcomes_recorded']} "
            f"errors={self.stats['errors']} "
            f"elapsed={elapsed:.1f}s"
        )

        # Send completion notification
        completion_embed = self._build_completion_embed(elapsed)
        self._send_discord_notification(completion_embed)

        return self.stats

    def _process_month(self, month_start: datetime, month_end: datetime) -> None:
        """Process a single month of historical data."""
        # Fetch feeds for each source
        all_items = []

        for source in self.sources:
            try:
                items = self._fetch_sec_historical(source, month_start, month_end)
                all_items.extend(items)
                self.stats["feeds_fetched"] += 1
                log.info(f"bootstrap_feed_fetched source={source} items={len(items)}")
            except Exception as e:
                log.error(f"bootstrap_feed_failed source={source} err={e}")
                self.stats["errors"] += 1

        # Deduplicate by ID
        unique_items = []
        seen_ids = set()
        for item in all_items:
            item_id = item.get("id", "")
            if (
                item_id
                and item_id not in seen_ids
                and item_id not in self._processed_ids
            ):
                unique_items.append(item)
                seen_ids.add(item_id)
                self._processed_ids.add(item_id)

        log.info(f"bootstrap_dedup total={len(all_items)} unique={len(unique_items)}")

        # Process in batches
        for i in range(0, len(unique_items), self.batch_size):
            batch = unique_items[i : i + self.batch_size]
            self._process_batch(batch)

    def _process_batch(self, items: List[Dict[str, Any]]) -> None:
        """
        Process a batch of historical items (Phase 2: with bulk prefetching).

        Prefetches prices for all items in the batch at once, then processes each item.
        This reduces API calls dramatically.
        """
        # Phase 2: Prefetch all prices for this batch
        ticker_dates = []
        for item in items:
            ticker = item.get("ticker")
            if not ticker:
                # Try standard extraction (for news feeds with ticker in title)
                ticker = extract_ticker(item.get("title", ""))
                # If that fails, try SEC-specific extraction (company name lookup)
                if not ticker:
                    ticker = _extract_sec_ticker(item.get("title", ""))

            if ticker:
                rejection_ts = item.get("ts", "")
                if rejection_ts:
                    try:
                        rejection_date = datetime.fromisoformat(
                            rejection_ts.replace("Z", "+00:00")
                        )
                        ticker_dates.append((ticker, rejection_date))
                    except Exception:
                        pass

        # Bulk prefetch prices
        if ticker_dates:
            self._prefetch_prices_bulk(ticker_dates)

        # Now process each item (prices will be in cache)
        for item in items:
            try:
                self._process_item(item)
                self.stats["items_processed"] += 1
            except Exception as e:
                log.error(f"bootstrap_item_failed item={item.get('id')} err={e}")
                self.stats["errors"] += 1

            # Reduced rate limiting since we're using cache
            time.sleep(0.1)

    def _process_item(self, item: Dict[str, Any]) -> None:
        """Process a single historical item."""
        # Extract ticker
        ticker = item.get("ticker")
        if not ticker:
            # Try standard extraction (for news feeds with ticker in title)
            ticker = extract_ticker(item.get("title", ""))
            # If that fails, try SEC-specific extraction (company name lookup)
            if not ticker:
                ticker = _extract_sec_ticker(item.get("title", ""))

        if not ticker:
            self.stats["skipped"] += 1
            return

        # Get price at time of event
        rejection_ts = item.get("ts", "")
        rejection_date = datetime.fromisoformat(rejection_ts.replace("Z", "+00:00"))

        # Fetch historical price (at event time)
        price = self._get_historical_price(ticker, rejection_date)

        if price is None:
            self.stats["skipped"] += 1
            return

        # Simulate classification (returns tuple: rejection_reason, scored_object)
        rejection_reason, scored = self._simulate_rejection(item, ticker, price)

        if not rejection_reason:
            # Not rejected - skip
            self.stats["skipped"] += 1
            return

        # This item was rejected - log it with classification data
        self._log_rejected_item(
            item, ticker, price, rejection_reason, rejection_ts, scored
        )
        self.stats["rejections_found"] += 1

        # Fetch outcomes for all applicable timeframes
        self._fetch_and_log_outcomes(
            ticker, rejection_ts, rejection_date, price, rejection_reason
        )
        self.stats["outcomes_recorded"] += 1

    def _fetch_sec_historical(
        self, source: str, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical feed with date filtering (SEC and news sources).

        Args:
            source: Feed source (sec_8k, globenewswire_public, etc.)
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            List of normalized feed items
        """
        if source not in FEED_URLS:
            log.warning(f"bootstrap_unknown_source source={source}")
            return []

        base_url = FEED_URLS[source]

        # SEC feeds support date filtering via URL parameters
        if source.startswith("sec_"):
            # SEC uses datea/dateb format (YYYYMMDD)
            # Note: SEC treats datea as "after" and dateb as "before"
            url = base_url.replace(
                "dateb=",
                f"datea={start_date.strftime('%Y%m%d')}&dateb={end_date.strftime('%Y%m%d')}",
            )
        else:
            # News feeds don't support date filtering - fetch all and filter later
            url = base_url

        # Fetch feed
        try:
            headers = {
                "User-Agent": "CatalystBot/1.0 (+https://example.local)",
                "Accept": "application/atom+xml, application/xml",
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Parse with feedparser
            parsed = feedparser.parse(response.text)
            entries = getattr(parsed, "entries", []) or []

            # Normalize entries
            items = []
            for entry in entries:
                normalized = _normalize_entry(source, entry)
                if normalized:
                    # For news feeds, filter by date since URL doesn't support it
                    if not source.startswith("sec_"):
                        try:
                            item_ts = normalized.get("ts", "")
                            if item_ts:
                                item_date = datetime.fromisoformat(
                                    item_ts.replace("Z", "+00:00")
                                )
                                # Skip items outside our date range
                                if item_date < start_date or item_date > end_date:
                                    continue
                        except Exception:
                            # If date parsing fails, skip the item
                            continue

                    items.append(normalized)

            return items

        except Exception as e:
            log.error(f"bootstrap_sec_fetch_failed source={source} err={e}")
            return []

    def _simulate_rejection(
        self, item: Dict[str, Any], ticker: str, price: float
    ) -> Tuple[Optional[str], Optional[Any]]:
        """
        Simulate classification to determine if item would be rejected.

        Args:
            item: News item dict
            ticker: Stock ticker
            price: Current price

        Returns:
            Tuple of (rejection_reason, scored_object)
            - rejection_reason: String if rejected, None otherwise
            - scored_object: Classification result with keywords, or None
        """
        # Check price ceiling (MOA only tracks $0.10-$10.00)
        # For price rejections, we still run classification to get keywords
        price_rejection = None
        if price < 0.10:
            price_rejection = "LOW_PRICE"
        elif price > 10.00:
            price_rejection = "HIGH_PRICE"

        # Build a NewsItem-like object for classification
        from .models import NewsItem

        try:
            news_item = NewsItem(
                title=item.get("title", ""),
                link=item.get("link", ""),
                source_host=item.get("source", ""),
                ts=item.get("ts", ""),
                ticker=ticker,
                summary=item.get("summary", ""),
            )
        except Exception:
            # If NewsItem construction fails, use dict directly
            news_item = item

        # Run through classifier to get keywords and score
        try:
            scored = classify(news_item)

            # HYBRID LLM: If no keywords found and this is a SEC filing, try LLM extraction
            keywords_found = False
            if hasattr(scored, "keyword_hits"):
                keywords_found = bool(scored.keyword_hits)
            elif isinstance(scored, dict):
                keywords_found = bool(
                    scored.get("keyword_hits") or scored.get("keywords")
                )

            # Check if this is a SEC filing that should use LLM
            source = item.get("source", "")
            is_sec_filing = source.startswith("sec_")

            if not keywords_found and is_sec_filing:
                # Try LLM keyword extraction from document content
                try:
                    from .sec_document_fetcher import fetch_sec_document_text
                    from .sec_llm_analyzer import extract_keywords_from_document_sync

                    # Fetch actual document content
                    link = item.get("link", "")
                    if link:
                        doc_text = fetch_sec_document_text(link)

                        if doc_text:
                            # Extract filing type from source (e.g., "sec_8k" -> "8-K")
                            filing_type = (
                                source.replace("sec_", "").upper().replace("_", "-")
                            )

                            # Use LLM to extract keywords
                            llm_result = extract_keywords_from_document_sync(
                                doc_text, item.get("title", ""), filing_type
                            )

                            # Merge LLM keywords into scored object
                            if llm_result and llm_result.get("keywords"):
                                log.info(
                                    f"llm_keywords_extracted ticker={ticker} "
                                    f"keywords={llm_result['keywords']} source={source}"
                                )

                                # Update scored object with LLM keywords
                                if hasattr(scored, "keyword_hits"):
                                    scored.keyword_hits = llm_result["keywords"]
                                elif isinstance(scored, dict):
                                    scored["keyword_hits"] = llm_result["keywords"]
                                    scored["keywords"] = llm_result["keywords"]

                                # Update sentiment if available
                                if llm_result.get("sentiment") and hasattr(
                                    scored, "sentiment"
                                ):
                                    scored.sentiment = llm_result["sentiment"]
                                elif isinstance(scored, dict):
                                    scored["sentiment"] = llm_result.get(
                                        "sentiment", 0.0
                                    )

                except Exception as e:
                    log.debug(f"llm_keyword_extraction_failed ticker={ticker} err={e}")

            # If we already determined price rejection, return it with classification
            if price_rejection:
                return (price_rejection, scored)

            # Extract score (handle both object and dict responses)
            if hasattr(scored, "source_weight"):
                score = float(scored.source_weight)
            elif isinstance(scored, dict):
                score = float(scored.get("score", 0.0))
            else:
                score = 0.0

            # Check against threshold
            min_score = getattr(self.settings, "min_score", 0.70)

            if score < min_score:
                return ("LOW_SCORE", scored)

            # Not rejected
            return (None, scored)

        except Exception as e:
            log.debug(f"bootstrap_classify_failed ticker={ticker} err={e}")
            # Return error with no classification data
            return ("CLASSIFY_ERROR", None)

    # ========================================================================
    # Phase 2: Caching and Bulk Fetching Methods
    # ========================================================================

    def _get_from_cache(self, ticker: str, date: datetime) -> Optional[float]:
        """
        Get price from multi-level cache (memory → disk → None).

        Args:
            ticker: Stock ticker
            date: Date to fetch price for

        Returns:
            Cached price or None if not found
        """
        date_str = date.strftime("%Y-%m-%d")
        cache_key = (ticker, date_str)

        # Level 1: Memory cache
        with self._cache_lock:
            if cache_key in self._price_cache:
                self.stats["cache_hits"] += 1
                return self._price_cache[cache_key]

        # Level 2: Disk cache
        cache_path = _get_disk_cache_path(self.cache_dir, ticker, date)

        if cache_path.exists():
            # Validate cache file is within expected directory (path traversal protection)
            try:
                cache_path.resolve().relative_to(self.cache_dir.resolve())
            except ValueError:
                log.warning(
                    f"cache_path_traversal_attempt ticker={ticker} path={cache_path}"
                )
                return None

            try:
                # Security Note: Loading pickle from application-controlled cache directory
                # Files are created by this application only. Do not load from untrusted sources.
                with open(cache_path, "rb") as f:
                    cache_data = pickle.load(f)

                # Check TTL
                cached_date = cache_data.get("cached_at")
                price = cache_data.get("price")

                if cached_date and price is not None:
                    # Check if cache is still valid (within TTL)
                    cache_age_days = (datetime.now(timezone.utc) - cached_date).days

                    if cache_age_days <= CACHE_TTL_DAYS:
                        # Valid cache - load into memory and return
                        with self._cache_lock:
                            self._price_cache[cache_key] = price

                        self.stats["disk_cache_hits"] += 1
                        return price

            except Exception as e:
                log.debug(f"disk_cache_load_failed ticker={ticker} err={e}")

        # Cache miss
        self.stats["cache_misses"] += 1
        return None

    def _put_in_cache(self, ticker: str, date: datetime, price: float) -> None:
        """
        Put price in multi-level cache (memory + disk).

        Args:
            ticker: Stock ticker
            date: Date of price
            price: Price value
        """
        date_str = date.strftime("%Y-%m-%d")
        cache_key = (ticker, date_str)

        # Store in memory cache
        with self._cache_lock:
            self._price_cache[cache_key] = price

        # Store in disk cache
        try:
            cache_path = _get_disk_cache_path(self.cache_dir, ticker, date)
            cache_data = {
                "ticker": ticker,
                "date": date_str,
                "price": price,
                "cached_at": datetime.now(timezone.utc),
            }

            with open(cache_path, "wb") as f:
                pickle.dump(cache_data, f)

        except Exception as e:
            log.debug(f"disk_cache_write_failed ticker={ticker} err={e}")

    def _prefetch_prices_bulk(
        self, ticker_dates: List[Tuple[str, datetime]]
    ) -> Dict[Tuple[str, str], float]:
        """
        Bulk fetch prices using Finnhub API with fallback to yfinance.

        Finnhub provides 1 year of historical data per call at 50 calls/min.
        Falls back to yfinance for batch operations if Finnhub rate limits are hit.

        Args:
            ticker_dates: List of (ticker, date) tuples to fetch

        Returns:
            Dictionary mapping (ticker, date_str) -> price
        """
        if not ticker_dates:
            return {}

        results = {}

        # Filter out cached items
        to_fetch = []
        for ticker, date in ticker_dates:
            cached_price = self._get_from_cache(ticker, date)
            if cached_price is not None:
                date_str = date.strftime("%Y-%m-%d")
                results[(ticker, date_str)] = cached_price
            else:
                to_fetch.append((ticker, date))

        if not to_fetch:
            return results

        # Phase 1: Try Finnhub for individual fetches (respecting rate limits)
        finnhub_failed = []

        for ticker, date in to_fetch:
            # Apply Finnhub rate limiting
            time.sleep(FINNHUB_RATE_LIMIT)

            price = _fetch_finnhub_price(ticker, date, resolution="D")

            if price is not None:
                date_str = date.strftime("%Y-%m-%d")
                results[(ticker, date_str)] = price
                self._put_in_cache(ticker, date, price)
                self.stats["bulk_fetches"] += 1
            else:
                # Mark for yfinance fallback
                finnhub_failed.append((ticker, date))

        # Phase 2: Fallback to yfinance bulk fetching for failed items
        if not finnhub_failed:
            log.info(
                f"finnhub_bulk_complete total={len(to_fetch)} fetched={len(to_fetch)}"
            )
            return results

        # Group by date range for efficient bulk fetching
        # Group tickers that have similar date ranges together
        date_groups: Dict[Tuple[str, str], List[str]] = {}

        for ticker, date in finnhub_failed:
            start_date = (date - timedelta(days=1)).strftime("%Y-%m-%d")
            end_date = (date + timedelta(days=1)).strftime("%Y-%m-%d")
            range_key = (start_date, end_date)

            if range_key not in date_groups:
                date_groups[range_key] = []
            date_groups[range_key].append((ticker, date))

        # Fetch each date group in batches (yfinance fallback)
        for (start_date, end_date), ticker_date_list in date_groups.items():
            # Process in batches of BULK_FETCH_BATCH_SIZE
            for i in range(0, len(ticker_date_list), BULK_FETCH_BATCH_SIZE):
                batch = ticker_date_list[i : i + BULK_FETCH_BATCH_SIZE]
                tickers = [t for t, _ in batch]

                try:
                    # Bulk download with threading
                    data = yf.download(
                        tickers,
                        start=start_date,
                        end=end_date,
                        interval="1d",
                        threads=True,
                        progress=False,
                    )

                    self.stats["bulk_fetches"] += 1

                    if data is None or data.empty:
                        continue

                    # Extract prices for each ticker/date
                    for ticker, date in batch:
                        date_str = date.strftime("%Y-%m-%d")

                        try:
                            if len(tickers) == 1:
                                # Single ticker - data is a simple DataFrame
                                if "Close" in data.columns and not data["Close"].empty:
                                    price = float(data["Close"].iloc[-1])
                                    results[(ticker, date_str)] = price
                                    self._put_in_cache(ticker, date, price)
                            else:
                                # Multiple tickers - data has MultiIndex columns
                                if ("Close", ticker) in data.columns:
                                    ticker_data = data["Close"][ticker]
                                    if not ticker_data.empty and not pd.isna(
                                        ticker_data.iloc[-1]
                                    ):
                                        price = float(ticker_data.iloc[-1])
                                        results[(ticker, date_str)] = price
                                        self._put_in_cache(ticker, date, price)

                        except Exception as e:
                            log.debug(f"bulk_extract_failed ticker={ticker} err={e}")
                            continue

                except Exception as e:
                    log.warning(f"bulk_fetch_failed tickers={len(batch)} err={e}")

                    # Fallback: try individual fetches for this batch
                    for ticker, date in batch:
                        try:
                            price = self._get_historical_price_direct(ticker, date)
                            if price is not None:
                                date_str = date.strftime("%Y-%m-%d")
                                results[(ticker, date_str)] = price
                                self._put_in_cache(ticker, date, price)
                        except Exception as e2:
                            log.debug(f"fallback_fetch_failed ticker={ticker} err={e2}")

                # Small delay between bulk batches
                time.sleep(0.1)

        log.info(
            f"bulk_prefetch_complete total={len(ticker_dates)} "
            f"finnhub={len(to_fetch) - len(finnhub_failed)} "
            f"yfinance_fallback={len(finnhub_failed)} "
            f"cached={len(results) - len(to_fetch)}"
        )

        return results

    def _get_historical_price_direct(
        self, ticker: str, date: datetime
    ) -> Optional[float]:
        """
        Direct Finnhub fetch without caching (fallback method).

        Args:
            ticker: Stock ticker
            date: Date to fetch price for

        Returns:
            Price at that date, or None if unavailable
        """
        # Apply Finnhub rate limiting
        time.sleep(FINNHUB_RATE_LIMIT)

        # Try Finnhub first (daily resolution)
        price = _fetch_finnhub_price(ticker, date, resolution="D")

        if price is not None:
            return price

        # Fallback to yfinance if Finnhub fails
        try:
            ticker_obj = yf.Ticker(ticker)
            start = (date - timedelta(days=1)).strftime("%Y-%m-%d")
            end = (date + timedelta(days=1)).strftime("%Y-%m-%d")

            hist = ticker_obj.history(start=start, end=end, interval="1d")

            if hist is None or hist.empty:
                return None

            close_price = hist["Close"].iloc[-1]
            return float(close_price)

        except Exception as e:
            log.debug(
                f"fallback_fetch_failed ticker={ticker} date={date.date()} err={e}"
            )
            return None

    def _fetch_outcomes_batch(
        self, ticker: str, rejection_date: datetime, rejection_price: float
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch all timeframe outcomes in a single batched API call.

        Instead of 6 separate API calls (one per timeframe), fetch a larger
        date range once and extract all timeframes from it.

        When Tiingo is enabled, uses Tiingo IEX API for 15m/30m historical data
        (20+ years available). Otherwise falls back to yfinance with limitations.

        Args:
            ticker: Stock ticker
            rejection_date: Date of rejection
            rejection_price: Price at rejection

        Returns:
            Dictionary mapping timeframe -> outcome data
        """
        timeframes = self._get_available_timeframes(rejection_date)

        if not timeframes:
            return {}

        # Calculate the maximum date range needed for all timeframes
        max_hours = max(ALL_TIMEFRAMES[tf] for tf in timeframes)
        target_date = rejection_date + timedelta(hours=max_hours)

        # Don't fetch future data
        if target_date > datetime.now(timezone.utc):
            target_date = datetime.now(timezone.utc)

        # Determine appropriate interval based on timeframes
        needs_intraday = any(tf in ["15m", "30m", "1h", "4h"] for tf in timeframes)
        interval = "15m" if needs_intraday else "1d"
        log.info(
            f"TIMEFRAMES_SELECTED ticker={ticker} timeframes={timeframes} needs_intraday={needs_intraday}"  # noqa: E501
        )

        outcomes = {}
        hist = None

        try:
            # Try Tiingo first if enabled and we need intraday data
            # Note: Always read directly from environment since Settings object
            # is created before .env is loaded (module import order issue)
            tiingo_api_key = os.getenv("TIINGO_API_KEY", "").strip()
            feature_tiingo_str = os.getenv("FEATURE_TIINGO", "0").strip().lower()
            feature_tiingo_enabled = feature_tiingo_str in {
                "1",
                "true",
                "yes",
                "on",
            }

            # Use Tiingo for intraday data if available
            # DEBUG: Print all three conditions with immediate flush
            import sys

            sys.stderr.write(
                f"DEBUG: needs_intraday={needs_intraday}, feature_enabled={feature_tiingo_enabled}, has_key={bool(tiingo_api_key)}\n"  # noqa: E501
            )
            sys.stderr.flush()

            if needs_intraday and feature_tiingo_enabled and tiingo_api_key:
                log.info(
                    f"TIINGO_ATTEMPTING ticker={ticker} enabled={feature_tiingo_enabled} has_key={bool(tiingo_api_key)}"  # noqa: E501
                )
                try:
                    # Import Tiingo direct API function to use explicit date ranges
                    from .market import _tiingo_intraday_series

                    # Tiingo can provide historical intraday data with explicit dates
                    # Call _tiingo_intraday_series directly with rejection_date range
                    # This properly fetches Nov 2024 data instead of recent data
                    hist = _tiingo_intraday_series(
                        ticker,
                        tiingo_api_key,
                        start_date=rejection_date.strftime("%Y-%m-%d"),
                        end_date=(target_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                        resample_freq="15min",
                        after_hours=True,
                        timeout=30,  # 30-second timeout for historical data fetches
                    )

                    if hist is not None and not hist.empty:
                        log.info(
                            f"TIINGO_SUCCESS ticker={ticker} "
                            f"interval=15min rows={len(hist)} "
                            f"date_range={rejection_date.date()} to {target_date.date()}"
                        )
                    else:
                        hist = None  # Empty result
                except Exception as e:
                    log.info(
                        f"TIINGO_FAILED ticker={ticker} err={e} "
                        "falling_back_to_yfinance"
                    )
                    hist = None

            # Fallback to yfinance if Tiingo not available or failed
            if hist is None or (hasattr(hist, "empty") and hist.empty):
                ticker_obj = yf.Ticker(ticker)
                start = rejection_date.strftime("%Y-%m-%d")
                end = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

                hist = ticker_obj.history(start=start, end=end, interval=interval)

                if hist is not None and not hist.empty:
                    log.debug(
                        f"yfinance_intraday_success ticker={ticker} "
                        f"interval={interval} rows={len(hist)}"
                    )

            if hist is None or hist.empty:
                return outcomes

            # Extract price for each timeframe from the same dataset
            for timeframe in timeframes:
                hours = ALL_TIMEFRAMES[timeframe]
                tf_target_date = rejection_date + timedelta(hours=hours)

                # Skip if target is in the future
                if tf_target_date > datetime.now(timezone.utc):
                    continue

                try:
                    target_price = None

                    if timeframe in ["1d", "7d"]:
                        # Use daily close
                        target_price = float(hist["Close"].iloc[-1])
                    else:
                        # For intraday, find closest bar
                        hist_index = hist.index
                        time_diffs = [
                            (idx, abs((idx - tf_target_date).total_seconds()))
                            for idx in hist_index
                        ]
                        if time_diffs:
                            closest_idx, _ = min(time_diffs, key=lambda x: x[1])
                            target_price = float(hist.loc[closest_idx, "Close"])

                    if target_price is not None:
                        # Guard against division by zero
                        if rejection_price == 0 or rejection_price is None:
                            continue

                        return_pct = (
                            (target_price - rejection_price) / rejection_price
                        ) * 100.0

                        # Extract intraday prices and volume data
                        try:
                            # Determine which index to use (daily vs intraday)
                            if timeframe in ["1d", "7d"]:
                                # Use last available bar for daily
                                data_row = hist.iloc[-1]
                            else:
                                # For intraday, use closest_idx from above
                                data_row = hist.loc[closest_idx]

                            # Extract OHLC prices
                            open_price = float(data_row["Open"])
                            high_price = float(data_row["High"])
                            low_price = float(data_row["Low"])
                            close_price = float(data_row["Close"])

                            # Calculate peak returns (high/low vs rejection price)
                            high_return_pct = round(
                                (high_price - rejection_price) / rejection_price * 100,
                                2,
                            )
                            low_return_pct = round(
                                (low_price - rejection_price) / rejection_price * 100, 2
                            )

                            # Extract volume data
                            volume = int(data_row["Volume"])

                            # Calculate 20-day average volume and relative volume
                            avg_volume_20d = None
                            relative_volume = None

                            if len(hist) >= 20:
                                avg_vol = hist["Volume"].rolling(20).mean().iloc[-1]
                                if not pd.isna(avg_vol) and avg_vol > 0:
                                    avg_volume_20d = int(avg_vol)
                                    relative_volume = round(volume / avg_vol, 2)

                            outcomes[timeframe] = {
                                "close": close_price,
                                "open": open_price,
                                "high": high_price,
                                "low": low_price,
                                "return_pct": round(return_pct, 2),
                                "high_return_pct": high_return_pct,
                                "low_return_pct": low_return_pct,
                                "volume": volume,
                                "avg_volume_20d": avg_volume_20d,
                                "relative_volume": relative_volume,
                                "checked_at": datetime.now(timezone.utc).isoformat(),
                            }

                        except (KeyError, IndexError, ValueError) as e:
                            log.debug(
                                f"outcome_data_extract_failed ticker={ticker} "
                                f"timeframe={timeframe} err={e}"
                            )
                            # Fallback to basic structure if data extraction fails
                            outcomes[timeframe] = {
                                "close": target_price,
                                "return_pct": round(return_pct, 2),
                                "checked_at": datetime.now(timezone.utc).isoformat(),
                            }

                except Exception as e:
                    log.debug(
                        f"batch_outcome_extract_failed ticker={ticker} "
                        f"timeframe={timeframe} err={e}"
                    )
                    continue

        except Exception as e:
            log.warning(f"batch_outcomes_failed ticker={ticker} err={e}")
            # Fallback to individual timeframe fetching
            return {}

        return outcomes

    def _get_historical_price(self, ticker: str, date: datetime) -> Optional[float]:
        """
        Get historical price for ticker at specific date (with caching).

        Phase 2: Now uses multi-level cache (memory → disk → API).

        Args:
            ticker: Stock ticker
            date: Date to fetch price for

        Returns:
            Price at that date, or None if unavailable
        """
        # Try cache first
        cached_price = self._get_from_cache(ticker, date)
        if cached_price is not None:
            return cached_price

        # Cache miss - fetch from API
        price = self._get_historical_price_direct(ticker, date)

        # Store in cache if successful
        if price is not None:
            self._put_in_cache(ticker, date, price)

        return price

    def _get_available_timeframes(self, rejection_date: datetime) -> List[str]:
        """
        Choose timeframes based on data age and available data providers.

        Behavior:
        - Tiingo enabled (FEATURE_TIINGO=1 with API key):
          Returns all timeframes ["15m", "30m", "1h", "4h", "1d", "7d"] regardless
          of data age, as Tiingo provides 20+ years of intraday historical data
          with $30/month subscription.

        - Tiingo disabled (default):
          Falls back to yfinance limitations:
          - Last 60 days: Include 15m/30m (yfinance has intraday data)
          - Older than 60 days: Only 1h/4h/1d/7d (yfinance limitation)

        This enables MOA analysis to understand flash catalyst reactions across
        all historical data when Tiingo is available.

        Args:
            rejection_date: Date of the rejection event

        Returns:
            List of applicable timeframe strings
        """
        # Check if Tiingo is enabled via environment variable
        # Note: Always read directly from environment since Settings object
        # is created before .env is loaded (module import order issue)
        tiingo_api_key = os.getenv("TIINGO_API_KEY", "").strip()
        feature_tiingo_str = os.getenv("FEATURE_TIINGO", "0").strip().lower()
        feature_tiingo_enabled = feature_tiingo_str in {"1", "true", "yes", "on"}

        # If Tiingo is enabled with valid API key, return all timeframes
        if feature_tiingo_enabled and tiingo_api_key:
            log.info(
                "tiingo_enabled_all_timeframes "
                "rejection_age_days=%d "
                "timeframes=15m,30m,1h,4h,1d,7d "
                "reason='Tiingo provides 20+ years of intraday data'",
                (datetime.now(timezone.utc) - rejection_date).days,
            )
            return ["15m", "30m", "1h", "4h", "1d", "7d"]

        # Tiingo not enabled - use yfinance with age-based limitations
        age_days = (datetime.now(timezone.utc) - rejection_date).days

        if age_days <= 60:
            # Recent data - all timeframes available via yfinance
            log.debug(
                "yfinance_all_timeframes "
                "rejection_age_days=%d "
                "timeframes=15m,30m,1h,4h,1d,7d",
                age_days,
            )
            return ["15m", "30m", "1h", "4h", "1d", "7d"]
        else:
            # Old data - only hourly+ timeframes (yfinance limitation)
            log.info(
                "yfinance_limited_timeframes "
                "rejection_age_days=%d "
                "timeframes=1h,4h,1d,7d "
                "reason='yfinance lacks 15m/30m data beyond 60 days' "
                "tip='Enable FEATURE_TIINGO=1 for historical intraday data'",
                age_days,
            )
            return ["1h", "4h", "1d", "7d"]

    def _fetch_and_log_outcomes(
        self,
        ticker: str,
        rejection_ts: str,
        rejection_date: datetime,
        rejection_price: float,
        rejection_reason: str,
    ) -> None:
        """
        Fetch outcomes for all applicable timeframes and write to outcomes.jsonl.

        Phase 2: Uses batch fetching to reduce API calls from 6 to 1 per ticker.
        Phase 3 (Agent 3): Added sector context tracking.

        Args:
            ticker: Stock ticker
            rejection_ts: ISO timestamp of rejection
            rejection_date: Datetime of rejection
            rejection_price: Price at rejection time
            rejection_reason: Reason for rejection
        """
        # Fetch pre-event and market context
        pre_event_context = self._fetch_pre_event_context(ticker, rejection_date)
        market_context = self._fetch_market_context(rejection_date, rejection_price)

        # Fetch sector context (Agent 3: sector/industry tracking)
        sector_context = self._fetch_sector_context(ticker, rejection_date)

        # Calculate RVOL at rejection time (Agent 1: Relative Volume)
        rvol_data = calculate_rvol(ticker, rejection_date, use_cache=True)

        # Fetch market regime at rejection time
        # Note: For historical data, we fetch current regime as a placeholder.
        # Ideally, we would fetch VIX/SPY at the historical date, but that requires
        # additional API calls. Current regime is logged with a note for future enhancement.
        regime_data = {}
        try:
            from .market_regime import get_current_regime

            regime_data = get_current_regime()
            log.debug(
                f"regime_fetched_for_historical ticker={ticker} "
                f"regime={regime_data.get('regime')} vix={regime_data.get('vix')} "
                f"note='Current regime used as placeholder for historical date'"
            )
        except ImportError:
            log.debug("market_regime_module_not_available")
        except Exception as e:
            log.debug(f"regime_fetch_failed ticker={ticker} err={e}")

        # Build outcome record
        outcome_record = {
            "ticker": ticker,
            "rejection_ts": rejection_ts,
            "rejection_price": rejection_price,
            "rejection_reason": rejection_reason,
            "pre_event_context": pre_event_context,
            "market_context": market_context,
            "sector_context": sector_context,
            "rvol": rvol_data.get("rvol") if rvol_data else None,
            "rvol_20d_avg_volume": (
                rvol_data.get("avg_volume_20d") if rvol_data else None
            ),
            "current_volume": rvol_data.get("current_volume") if rvol_data else None,
            "rvol_category": rvol_data.get("rvol_category") if rvol_data else None,
            "market_regime": regime_data.get("regime"),
            "market_vix": regime_data.get("vix"),
            "market_spy_trend": regime_data.get("spy_trend"),
            "market_regime_multiplier": regime_data.get("multiplier"),
            "outcomes": {},
            "is_missed_opportunity": False,
            "max_return_pct": 0.0,
        }

        # Phase 2: Try batch fetching first (1 API call for all timeframes)
        batch_outcomes = self._fetch_outcomes_batch(
            ticker, rejection_date, rejection_price
        )

        if batch_outcomes:
            # Successfully got outcomes from batch fetch
            outcome_record["outcomes"] = batch_outcomes

            # Calculate max return and missed opportunity
            for outcome_data in batch_outcomes.values():
                return_pct = outcome_data.get("return_pct", 0.0)
                if return_pct > outcome_record["max_return_pct"]:
                    outcome_record["max_return_pct"] = return_pct

                if return_pct > 10.0:
                    outcome_record["is_missed_opportunity"] = True
        else:
            # Fallback to individual fetching if batch fails
            timeframes = self._get_available_timeframes(rejection_date)

            for timeframe in timeframes:
                outcome_data = self._fetch_outcome_for_timeframe(
                    ticker, rejection_date, rejection_price, timeframe
                )

                if outcome_data:
                    outcome_record["outcomes"][timeframe] = outcome_data

                    # Update max return
                    return_pct = outcome_data.get("return_pct", 0.0)
                    if return_pct > outcome_record["max_return_pct"]:
                        outcome_record["max_return_pct"] = return_pct

                    # Check for missed opportunity (>10% return)
                    if return_pct > 10.0:
                        outcome_record["is_missed_opportunity"] = True

        # Write to outcomes.jsonl
        try:
            with open(self.outcomes_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(outcome_record, ensure_ascii=False) + "\n")
        except Exception as e:
            log.error(f"bootstrap_outcome_write_failed ticker={ticker} err={e}")

    def _fetch_pre_event_context(
        self, ticker: str, rejection_date: datetime
    ) -> Dict[str, Any]:
        """
        Fetch price context before catalyst event.

        Returns dict with:
        - price_1d_before: float or None
        - price_7d_before: float or None
        - price_30d_before: float or None
        - momentum_1d: percent change (if data available)
        - momentum_7d: percent change (if data available)
        - momentum_30d: percent change (if data available)

        Args:
            ticker: Stock ticker
            rejection_date: Date of rejection/catalyst event

        Returns:
            Dictionary with pre-event price context
        """
        context = {
            "price_1d_before": None,
            "price_7d_before": None,
            "price_30d_before": None,
            "momentum_1d": None,
            "momentum_7d": None,
            "momentum_30d": None,
        }

        try:
            # Calculate dates to fetch
            date_1d = rejection_date - timedelta(days=1)
            date_7d = rejection_date - timedelta(days=7)
            date_30d = rejection_date - timedelta(days=30)

            # Fetch prices at each timepoint (using existing cache)
            price_1d = self._get_historical_price(ticker, date_1d)
            price_7d = self._get_historical_price(ticker, date_7d)
            price_30d = self._get_historical_price(ticker, date_30d)

            # Get rejection price for momentum calculations
            rejection_price = self._get_historical_price(ticker, rejection_date)

            # Store prices
            context["price_1d_before"] = price_1d
            context["price_7d_before"] = price_7d
            context["price_30d_before"] = price_30d

            # Calculate momentum (percent change from past to rejection date)
            if rejection_price and price_1d and price_1d > 0:
                context["momentum_1d"] = round(
                    ((rejection_price - price_1d) / price_1d) * 100.0, 2
                )

            if rejection_price and price_7d and price_7d > 0:
                context["momentum_7d"] = round(
                    ((rejection_price - price_7d) / price_7d) * 100.0, 2
                )

            if rejection_price and price_30d and price_30d > 0:
                context["momentum_30d"] = round(
                    ((rejection_price - price_30d) / price_30d) * 100.0, 2
                )

            log.debug(
                f"pre_event_context_fetched ticker={ticker} "
                f"momentum_1d={context['momentum_1d']} "
                f"momentum_7d={context['momentum_7d']} "
                f"momentum_30d={context['momentum_30d']}"
            )

        except Exception as e:
            log.warning(f"pre_event_context_failed ticker={ticker} err={e}")

        return context

    def _fetch_market_context(
        self, rejection_date: datetime, rejection_price: float
    ) -> Dict[str, Any]:
        """
        Fetch SPY performance for same period.

        Returns dict with:
        - spy_return_1d: percent change
        - spy_return_7d: percent change

        Args:
            rejection_date: Date of rejection/catalyst event
            rejection_price: Price at rejection (not used but kept for signature consistency)

        Returns:
            Dictionary with SPY market context
        """
        context = {
            "spy_return_1d": None,
            "spy_return_7d": None,
        }

        try:
            # Calculate dates
            date_1d = rejection_date - timedelta(days=1)
            date_7d = rejection_date - timedelta(days=7)

            # Fetch SPY prices (using existing cache mechanism)
            spy_current = self._get_historical_price("SPY", rejection_date)
            spy_1d = self._get_historical_price("SPY", date_1d)
            spy_7d = self._get_historical_price("SPY", date_7d)

            # Calculate returns
            if spy_current and spy_1d and spy_1d > 0:
                context["spy_return_1d"] = round(
                    ((spy_current - spy_1d) / spy_1d) * 100.0, 2
                )

            if spy_current and spy_7d and spy_7d > 0:
                context["spy_return_7d"] = round(
                    ((spy_current - spy_7d) / spy_7d) * 100.0, 2
                )

            log.debug(
                f"market_context_fetched "
                f"spy_return_1d={context['spy_return_1d']} "
                f"spy_return_7d={context['spy_return_7d']}"
            )

        except Exception as e:
            log.warning(f"market_context_failed err={e}")

        return context

    def _fetch_sector_context(
        self, ticker: str, rejection_date: datetime
    ) -> Dict[str, Any]:
        """
        Fetch sector and industry context for ticker.

        Returns dict with:
        - sector: str or None
        - industry: str or None
        - sector_1d_return: float (percent) or None
        - sector_5d_return: float (percent) or None
        - sector_vs_spy: float (sector outperformance vs SPY) or None
        - sector_rvol: float (relative volume) or None

        Args:
            ticker: Stock ticker
            rejection_date: Date of rejection/catalyst event

        Returns:
            Dictionary with sector context
        """
        context = {
            "sector": None,
            "industry": None,
            "sector_1d_return": None,
            "sector_5d_return": None,
            "sector_vs_spy": None,
            "sector_rvol": None,
        }

        try:
            # Get sector manager
            sector_mgr = get_sector_manager()

            # Get sector and industry
            sector_info = sector_mgr.get_ticker_sector_info(ticker)
            sector = sector_info.get("sector")
            industry = sector_info.get("industry")

            context["sector"] = sector
            context["industry"] = industry

            # Get sector performance (if sector is known)
            if sector:
                perf = sector_mgr.get_sector_performance(sector, rejection_date)

                context["sector_1d_return"] = perf.get("sector_1d_return")
                context["sector_5d_return"] = perf.get("sector_5d_return")
                context["sector_vs_spy"] = perf.get("sector_vs_spy")
                context["sector_rvol"] = perf.get("sector_rvol")

                log.debug(
                    f"sector_context_fetched ticker={ticker} "
                    f"sector={sector} "
                    f"sector_1d_return={context['sector_1d_return']} "
                    f"sector_vs_spy={context['sector_vs_spy']}"
                )
            else:
                log.debug(f"sector_unknown ticker={ticker}")

        except Exception as e:
            log.warning(f"sector_context_failed ticker={ticker} err={e}")

        return context

    def _fetch_outcome_for_timeframe(
        self,
        ticker: str,
        rejection_date: datetime,
        rejection_price: float,
        timeframe: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch outcome data for a specific timeframe.

        Args:
            ticker: Stock ticker
            rejection_date: Date of rejection
            rejection_price: Price at rejection
            timeframe: Timeframe to check (15m, 30m, 1h, etc.)

        Returns:
            Outcome data dict or None if unavailable
        """
        if timeframe not in ALL_TIMEFRAMES:
            return None

        hours = ALL_TIMEFRAMES[timeframe]
        target_date = rejection_date + timedelta(hours=hours)

        # Don't fetch future data
        if target_date > datetime.now(timezone.utc):
            return None

        try:
            # Map timeframe to yfinance interval
            interval_map = {
                "15m": "15m",
                "30m": "30m",
                "1h": "1h",
                "4h": "1h",  # yfinance doesn't have 4h, use 1h and resample
                "1d": "1d",
                "7d": "1d",  # Use daily data
            }

            interval = interval_map.get(timeframe, "1h")

            # Fetch historical data
            ticker_obj = yf.Ticker(ticker)

            # Calculate date range (from rejection to target + buffer)
            start = rejection_date.strftime("%Y-%m-%d")
            end = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

            hist = ticker_obj.history(start=start, end=end, interval=interval)

            if hist is None or hist.empty:
                return None

            # Get price closest to target time
            target_price = None

            # For hourly+ intervals, get the closing price at target time
            if timeframe in ["1d", "7d"]:
                # Use daily close
                target_price = float(hist["Close"].iloc[-1])
            else:
                # For intraday, find closest bar to target time
                hist_index = hist.index

                # Find bar closest to target time
                time_diffs = [
                    (idx, abs((idx - target_date).total_seconds()))
                    for idx in hist_index
                ]
                if time_diffs:
                    closest_idx, _ = min(time_diffs, key=lambda x: x[1])
                    target_price = float(hist.loc[closest_idx, "Close"])

            if target_price is None:
                return None

            # Calculate return percentage - guard against division by zero
            if rejection_price == 0 or rejection_price is None:
                log.warning(
                    f"invalid_rejection_price ticker={ticker} price={rejection_price}"
                )
                return None

            return_pct = ((target_price - rejection_price) / rejection_price) * 100.0

            return {
                "price": target_price,
                "return_pct": round(return_pct, 2),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            log.debug(
                f"bootstrap_outcome_failed ticker={ticker} timeframe={timeframe} err={e}"
            )
            return None

    def _log_rejected_item(
        self,
        item: Dict[str, Any],
        ticker: str,
        price: float,
        rejection_reason: str,
        rejection_ts: str,
        scored: Optional[Any] = None,
    ) -> None:
        """
        Write rejected item to data/rejected_items.jsonl.

        Args:
            item: Original news item
            ticker: Stock ticker
            price: Price at rejection
            rejection_reason: Reason for rejection
            rejection_ts: ISO timestamp
            scored: Classification result with keywords/score/sentiment
        """
        # Extract classification data from scored object
        score = 0.0
        sentiment = 0.0
        keywords = []
        fundamental_data = {}

        if scored is not None:
            try:
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

                # Extract fundamental data if available
                if hasattr(scored, "fundamental_score"):
                    fundamental_data = {
                        "score": getattr(scored, "fundamental_score", None),
                        "float_shares": getattr(
                            scored, "fundamental_float_shares", None
                        ),
                        "short_interest": getattr(
                            scored, "fundamental_short_interest", None
                        ),
                        "float_score": getattr(scored, "fundamental_float_score", None),
                        "si_score": getattr(scored, "fundamental_si_score", None),
                        "float_reason": getattr(
                            scored, "fundamental_float_reason", None
                        ),
                        "si_reason": getattr(scored, "fundamental_si_reason", None),
                    }
                elif isinstance(scored, dict):
                    if "fundamental_score" in scored:
                        fundamental_data = {
                            "score": scored.get("fundamental_score"),
                            "float_shares": scored.get("fundamental_float_shares"),
                            "short_interest": scored.get("fundamental_short_interest"),
                            "float_score": scored.get("fundamental_float_score"),
                            "si_score": scored.get("fundamental_si_score"),
                            "float_reason": scored.get("fundamental_float_reason"),
                            "si_reason": scored.get("fundamental_si_reason"),
                        }

            except Exception as e:
                log.debug(f"keyword_extract_failed ticker={ticker} err={e}")

        rejected_item = {
            "ts": rejection_ts,
            "ticker": ticker,
            "title": item.get("title", ""),
            "link": item.get("link", ""),  # Preserve link for LLM doc fetching
            "source": item.get("source", ""),
            "summary": item.get("summary", ""),  # Include summary for keyword analysis
            "price": price,
            "cls": {
                "score": score,
                "sentiment": sentiment,
                "keywords": keywords,
            },
            "rejected": True,
            "rejection_reason": rejection_reason,
        }

        # Add fundamental data if available
        if fundamental_data:
            rejected_item["fundamental"] = fundamental_data

        try:
            with open(self.rejected_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rejected_item, ensure_ascii=False) + "\n")
        except Exception as e:
            log.error(f"bootstrap_rejected_write_failed ticker={ticker} err={e}")

    def _save_checkpoint(self, date: datetime) -> None:
        """
        Save progress checkpoint.

        Args:
            date: Date to save as checkpoint
        """
        try:
            checkpoint_data = {
                "last_processed_date": date.isoformat(),
                "stats": self.stats,
            }

            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, indent=2)

            log.debug(f"bootstrap_checkpoint_saved date={date.date()}")

        except Exception as e:
            log.error(f"bootstrap_checkpoint_save_failed err={e}")

    def _load_checkpoint(self) -> Optional[datetime]:
        """
        Load last processed date from checkpoint.

        Returns:
            Last processed datetime or None
        """
        if not self.checkpoint_path.exists():
            return None

        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            last_date_str = data.get("last_processed_date")
            if last_date_str:
                return datetime.fromisoformat(last_date_str)

            return None

        except Exception as e:
            log.error(f"bootstrap_checkpoint_load_failed err={e}")
            return None

    # ========================================================================
    # Discord Notification Methods
    # ========================================================================

    def _get_discord_webhook(self) -> Optional[str]:
        """
        Get Discord webhook URL from environment.

        Returns:
            Webhook URL or None if not configured
        """
        webhook = os.getenv("DISCORD_ADMIN_WEBHOOK")
        if not webhook:
            return None

        # Check if notifications are enabled
        enabled = os.getenv("BOOTSTRAP_DISCORD_NOTIFICATIONS", "1").strip().lower()
        if enabled not in ("1", "true", "yes", "on"):
            return None

        return webhook

    def _send_discord_notification(self, embed: Dict[str, Any]) -> bool:
        """
        Send Discord notification with embed.

        Args:
            embed: Discord embed dict

        Returns:
            True if sent successfully
        """
        webhook_url = self._get_discord_webhook()
        if not webhook_url:
            return False

        payload = {
            "username": "Historical Bootstrapper",
            "embeds": [embed],
        }

        try:
            success, status = post_discord_with_backoff(webhook_url, payload)
            if success:
                log.debug("discord_notification_sent")
            else:
                log.warning(f"discord_notification_failed status={status}")
            return success
        except Exception as e:
            log.warning(f"discord_notification_error err={e}")
            return False

    def _build_start_embed(self) -> Dict[str, Any]:
        """Build Discord embed for bootstrap start."""
        return {
            "title": "🚀 Historical Bootstrapper Started",
            "color": 0x3498DB,  # Blue
            "fields": [
                {
                    "name": "Date Range",
                    "value": f"{self.start_date.date()} to {self.end_date.date()}",
                    "inline": False,
                },
                {
                    "name": "Sources",
                    "value": ", ".join(self.sources),
                    "inline": False,
                },
                {
                    "name": "Batch Size",
                    "value": str(self.batch_size),
                    "inline": True,
                },
                {
                    "name": "Resume",
                    "value": "Yes" if self.resume else "No",
                    "inline": True,
                },
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _build_progress_embed(self, elapsed_minutes: float) -> Dict[str, Any]:
        """Build Discord embed for progress update."""
        cache_total = (
            self.stats["cache_hits"]
            + self.stats["disk_cache_hits"]
            + self.stats["cache_misses"]
        )
        cache_hit_rate = (
            (self.stats["cache_hits"] + self.stats["disk_cache_hits"])
            / cache_total
            * 100
            if cache_total > 0
            else 0
        )

        return {
            "title": "⏱️ Bootstrap Progress Update",
            "color": 0xF39C12,  # Orange
            "fields": [
                {
                    "name": "Runtime",
                    "value": f"{elapsed_minutes:.1f} minutes",
                    "inline": True,
                },
                {
                    "name": "Items Processed",
                    "value": f"{self.stats['items_processed']:,}",
                    "inline": True,
                },
                {
                    "name": "Rejections Found",
                    "value": f"{self.stats['rejections_found']:,}",
                    "inline": True,
                },
                {
                    "name": "Outcomes Recorded",
                    "value": f"{self.stats['outcomes_recorded']:,}",
                    "inline": True,
                },
                {
                    "name": "Cache Hit Rate",
                    "value": f"{cache_hit_rate:.1f}%",
                    "inline": True,
                },
                {
                    "name": "Errors",
                    "value": str(self.stats["errors"]),
                    "inline": True,
                },
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _build_completion_embed(self, elapsed_seconds: float) -> Dict[str, Any]:
        """Build Discord embed for bootstrap completion."""
        elapsed_minutes = elapsed_seconds / 60
        cache_total = (
            self.stats["cache_hits"]
            + self.stats["disk_cache_hits"]
            + self.stats["cache_misses"]
        )
        cache_hit_rate = (
            (self.stats["cache_hits"] + self.stats["disk_cache_hits"])
            / cache_total
            * 100
            if cache_total > 0
            else 0
        )

        # Calculate API calls saved via caching
        api_calls_made = self.stats["cache_misses"] + self.stats["bulk_fetches"]
        api_calls_saved = self.stats["cache_hits"] + self.stats["disk_cache_hits"]

        return {
            "title": "✅ Historical Bootstrap Complete",
            "color": 0x2ECC71,  # Green
            "fields": [
                {
                    "name": "Date Range",
                    "value": f"{self.start_date.date()} to {self.end_date.date()}",
                    "inline": False,
                },
                {
                    "name": "Runtime",
                    "value": f"{elapsed_minutes:.1f} minutes",
                    "inline": True,
                },
                {
                    "name": "Items Processed",
                    "value": f"{self.stats['items_processed']:,}",
                    "inline": True,
                },
                {
                    "name": "Rejections Found",
                    "value": f"{self.stats['rejections_found']:,}",
                    "inline": True,
                },
                {
                    "name": "Outcomes Recorded",
                    "value": f"{self.stats['outcomes_recorded']:,}",
                    "inline": True,
                },
                {
                    "name": "Cache Hit Rate",
                    "value": f"{cache_hit_rate:.1f}%",
                    "inline": True,
                },
                {
                    "name": "Bulk Fetches",
                    "value": f"{self.stats['bulk_fetches']:,}",
                    "inline": True,
                },
                {
                    "name": "API Calls Made",
                    "value": f"{api_calls_made:,}",
                    "inline": True,
                },
                {
                    "name": "API Calls Saved",
                    "value": f"{api_calls_saved:,} (via caching)",
                    "inline": True,
                },
                {
                    "name": "Errors",
                    "value": str(self.stats["errors"]),
                    "inline": True,
                },
            ],
            "footer": {"text": "Data ready for MOA analysis"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _build_error_embed(self, error_message: str) -> Dict[str, Any]:
        """Build Discord embed for bootstrap error."""
        return {
            "title": "❌ Historical Bootstrap Error",
            "color": 0xE74C3C,  # Red
            "description": f"```\n{error_message[:1000]}\n```",
            "fields": [
                {
                    "name": "Items Processed (before error)",
                    "value": f"{self.stats['items_processed']:,}",
                    "inline": True,
                },
                {
                    "name": "Rejections Found",
                    "value": f"{self.stats['rejections_found']:,}",
                    "inline": True,
                },
            ],
            "footer": {"text": "Check logs for details. Progress saved to checkpoint."},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _maybe_send_progress_update(self, force: bool = False) -> None:
        """
        Send progress update if enough time has elapsed.

        Args:
            force: Force send regardless of time elapsed
        """
        now = time.time()
        elapsed = now - self._last_progress_time

        if force or elapsed >= self._progress_interval:
            elapsed_minutes = (now - self.stats.get("start_time", now)) / 60
            embed = self._build_progress_embed(elapsed_minutes)
            self._send_discord_notification(embed)
            self._last_progress_time = now


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Historical Data Bootstrapper for MOA system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Bootstrap 6 months with SEC filings only
  python -m catalyst_bot.historical_bootstrapper \\
      --start-date 2024-07-01 \\
      --end-date 2025-01-01 \\
      --sources sec_8k,sec_424b5,sec_fwp

  # Bootstrap with mixed sources (SEC + news)
  python -m catalyst_bot.historical_bootstrapper \\
      --start-date 2024-11-01 \\
      --end-date 2025-01-01 \\
      --sources sec_8k,globenewswire_public

  # Resume from checkpoint
  python -m catalyst_bot.historical_bootstrapper \\
      --start-date 2024-01-01 \\
      --end-date 2025-01-01 \\
      --sources sec_8k \\
      --resume
        """,
    )

    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")

    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")

    parser.add_argument(
        "--sources",
        required=True,
        help="Comma-separated list of sources (e.g., sec_8k,globenewswire_public)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Items to process per batch (default: 100)",
    )

    parser.add_argument(
        "--resume", action="store_true", help="Resume from last checkpoint"
    )

    args = parser.parse_args()

    # Parse sources
    sources = [s.strip() for s in args.sources.split(",")]

    # Validate sources
    valid_sources = set(FEED_URLS.keys())
    invalid = [s for s in sources if s not in valid_sources]
    if invalid:
        print(f"Error: Invalid sources: {', '.join(invalid)}")
        print(f"Valid sources: {', '.join(sorted(valid_sources))}")
        return 1

    # Create bootstrapper
    bootstrapper = HistoricalBootstrapper(
        start_date=args.start_date,
        end_date=args.end_date,
        sources=sources,
        batch_size=args.batch_size,
        resume=args.resume,
    )

    # Run
    print("Starting historical bootstrap...")
    print(f"  Date range: {args.start_date} to {args.end_date}")
    print(f"  Sources: {', '.join(sources)}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Resume: {args.resume}")
    print()

    try:
        stats = bootstrapper.run()

        print("\nBootstrap Complete!")
        print(f"  Feeds fetched: {stats['feeds_fetched']}")
        print(f"  Items processed: {stats['items_processed']}")
        print(f"  Rejections found: {stats['rejections_found']}")
        print(f"  Outcomes recorded: {stats['outcomes_recorded']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Elapsed: {stats['elapsed_seconds']:.1f}s")
        print("\nPhase 2 Cache Statistics:")
        print(f"  Cache hits (memory): {stats['cache_hits']}")
        print(f"  Cache hits (disk): {stats['disk_cache_hits']}")
        print(f"  Cache misses: {stats['cache_misses']}")
        print(f"  Bulk fetches: {stats['bulk_fetches']}")

        # Generate LLM usage report
        print("\n" + "=" * 70)
        print("LLM USAGE REPORT")
        print("=" * 70)
        try:
            monitor = get_monitor()
            summary = monitor.get_daily_stats()
            monitor.print_summary(summary)
        except Exception as e:
            print(f"Failed to generate LLM usage report: {e}")

        return 0

    except KeyboardInterrupt:
        print("\nInterrupted by user. Progress saved to checkpoint.")
        return 130
    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
