"""Finnhub news feed integration for Catalyst-Bot.

This module fetches news, press releases, earnings, and analyst events from
Finnhub and formats them for the bot's alert pipeline.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

try:
    from .finnhub_client import get_finnhub_client
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("finnhub_feeds")

    get_finnhub_client = None

log = get_logger("finnhub_feeds")


def fetch_finnhub_news(max_items: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent market news from Finnhub.

    Returns news items formatted for the bot's alert pipeline.

    Parameters
    ----------
    max_items : int
        Maximum number of items to return (default: 50)

    Returns
    -------
    list of dict
        News items with keys: id, title, summary, link, published_parsed,
        source, ticker (if available)
    """
    client = get_finnhub_client()
    if not client:
        log.debug("finnhub_news_fetch_skipped reason=no_client")
        return []

    try:
        # Fetch general market news
        news = client.get_market_news(category="general")

        items = []
        for article in news[:max_items]:
            # Create unique ID from URL
            url = article.get("url", "")
            if not url:
                continue

            item_id = hashlib.md5(url.encode()).hexdigest()[:16]

            # Parse timestamp
            timestamp = article.get("datetime")
            if timestamp:
                published_parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            else:
                published_parsed = datetime.now(timezone.utc)

            item = {
                "id": item_id,
                "title": article.get("headline", ""),
                "summary": article.get("summary", ""),
                "link": url,
                "published_parsed": published_parsed,
                "source": article.get("source", "Finnhub"),
                "ticker": article.get("related", ""),  # Related ticker if available
                "category": article.get("category", ""),
                "image": article.get("image", ""),
            }

            items.append(item)

        log.info("finnhub_news_fetched count=%d", len(items))
        return items

    except Exception as e:
        log.warning("finnhub_news_fetch_error err=%s", str(e))
        return []


def fetch_finnhub_company_news(ticker: str, days: int = 7) -> List[Dict[str, Any]]:
    """Fetch company-specific news from Finnhub.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    days : int
        Number of days to look back (default: 7)

    Returns
    -------
    list of dict
        News items for the ticker
    """
    client = get_finnhub_client()
    if not client:
        return []

    try:
        from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d"
        )
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        news = client.get_company_news(ticker, from_date=from_date, to_date=to_date)

        items = []
        for article in news:
            url = article.get("url", "")
            if not url:
                continue

            item_id = hashlib.md5(url.encode()).hexdigest()[:16]

            timestamp = article.get("datetime")
            if timestamp:
                published_parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            else:
                published_parsed = datetime.now(timezone.utc)

            item = {
                "id": item_id,
                "title": article.get("headline", ""),
                "summary": article.get("summary", ""),
                "link": url,
                "published_parsed": published_parsed,
                "source": article.get("source", "Finnhub"),
                "ticker": ticker,
                "category": article.get("category", ""),
                "image": article.get("image", ""),
            }

            items.append(item)

        log.info("finnhub_company_news_fetched ticker=%s count=%d", ticker, len(items))
        return items

    except Exception as e:
        log.warning("finnhub_company_news_fetch_error ticker=%s err=%s", ticker, str(e))
        return []


def fetch_finnhub_earnings_calendar(days_ahead: int = 7) -> List[Dict[str, Any]]:
    """Fetch upcoming earnings from Finnhub.

    Parameters
    ----------
    days_ahead : int
        Number of days to look ahead (default: 7)

    Returns
    -------
    list of dict
        Earnings events formatted as news items
    """
    client = get_finnhub_client()
    if not client:
        return []

    try:
        from_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        to_date = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime(
            "%Y-%m-%d"
        )

        earnings = client.get_earnings_calendar(from_date=from_date, to_date=to_date)

        items = []
        for event in earnings:
            ticker = event.get("symbol", "")
            date = event.get("date", "")
            if not ticker or not date:
                continue

            # Create unique ID
            item_id = hashlib.md5(f"{ticker}_{date}_earnings".encode()).hexdigest()[:16]

            # Parse date
            try:
                published_parsed = datetime.strptime(date, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except Exception:
                published_parsed = datetime.now(timezone.utc)

            eps_estimate = event.get("epsEstimate")
            revenue_estimate = event.get("revenueEstimate")
            hour = event.get("hour", "")

            title = (
                f"{ticker} Earnings {hour.upper()}" if hour else f"{ticker} Earnings"
            )
            summary = f"Earnings Date: {date}"

            if eps_estimate:
                summary += f" | EPS Est: ${eps_estimate}"
            if revenue_estimate:
                summary += f" | Revenue Est: ${revenue_estimate/1e6:.1f}M"

            item = {
                "id": item_id,
                "title": title,
                "summary": summary,
                "link": f"https://finnhub.io/quote/{ticker}",
                "published_parsed": published_parsed,
                "source": "Finnhub Earnings",
                "ticker": ticker,
                "category": "earnings",
                "event_type": "earnings",
                "eps_estimate": eps_estimate,
                "revenue_estimate": revenue_estimate,
                "hour": hour,
            }

            items.append(item)

        log.info("finnhub_earnings_fetched count=%d", len(items))
        return items

    except Exception as e:
        log.warning("finnhub_earnings_fetch_error err=%s", str(e))
        return []


def fetch_finnhub_upgrades_downgrades() -> List[Dict[str, Any]]:
    """Fetch recent analyst upgrades/downgrades from Finnhub.

    Note: This requires checking specific tickers. To get broad coverage,
    you would need to iterate through a watchlist.

    Returns
    -------
    list of dict
        Upgrade/downgrade events formatted as news items
    """
    client = get_finnhub_client()
    if not client:
        return []

    # Get watchlist tickers to check for upgrades/downgrades
    try:
        from .watchlist import load_watchlist_set

        watchlist = load_watchlist_set()
    except Exception:
        log.debug("finnhub_upgrades_no_watchlist")
        return []

    items = []
    checked = 0

    for ticker in list(watchlist)[:50]:  # Limit to first 50 to avoid rate limits
        try:
            upgrades = client.get_upgrades_downgrades(ticker)

            for event in upgrades[:5]:  # Last 5 events per ticker
                grade_time = event.get("gradeTime", "")
                if not grade_time:
                    continue

                # Only show recent events (last 7 days)
                try:
                    event_time = datetime.strptime(
                        grade_time, "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - event_time).days > 7:
                        continue
                except Exception:
                    continue

                from_grade = event.get("fromGrade", "")
                to_grade = event.get("toGrade", "")
                company = event.get("company", "")
                action = event.get("action", "")

                # Create unique ID
                item_id = hashlib.md5(
                    f"{ticker}_{grade_time}_{to_grade}".encode()
                ).hexdigest()[:16]

                title = (
                    f"{ticker} {action}: {from_grade} → {to_grade}"
                    if action
                    else f"{ticker} Rated {to_grade}"
                )
                summary = f"Analyst: {company}" if company else ""

                item = {
                    "id": item_id,
                    "title": title,
                    "summary": summary,
                    "link": f"https://finnhub.io/quote/{ticker}",
                    "published_parsed": event_time,
                    "source": "Finnhub Analyst",
                    "ticker": ticker,
                    "category": "analyst",
                    "event_type": (
                        "upgrade"
                        if "upgrade" in action.lower()
                        else "downgrade" if "downgrade" in action.lower() else "rating"
                    ),
                    "from_grade": from_grade,
                    "to_grade": to_grade,
                    "analyst_company": company,
                }

                items.append(item)

            checked += 1

        except Exception as e:
            log.debug(
                "finnhub_upgrades_error ticker=%s err=%s",
                ticker,
                str(e.__class__.__name__),
            )

    log.info(
        "finnhub_upgrades_fetched tickers_checked=%d events=%d", checked, len(items)
    )
    return items


def is_finnhub_enabled() -> bool:
    """Check if Finnhub integration is enabled.

    Returns
    -------
    bool
        True if FINNHUB_API_KEY is set and FEATURE_FINNHUB_NEWS is enabled
    """
    if not os.getenv("FINNHUB_API_KEY"):
        return False

    feature_flag = os.getenv("FEATURE_FINNHUB_NEWS", "1").strip().lower()
    return feature_flag in ("1", "true", "yes", "on")


if __name__ == "__main__":
    # Test script
    print("Testing Finnhub feeds...")

    if not os.getenv("FINNHUB_API_KEY"):
        print("ERROR: Set FINNHUB_API_KEY environment variable")
        exit(1)

    print("\n--- Market News ---")
    news = fetch_finnhub_news(max_items=5)
    for item in news:
        print(f"  {item['title'][:60]}... ({item['source']})")

    print("\n--- Earnings Calendar ---")
    earnings = fetch_finnhub_earnings_calendar(days_ahead=7)
    for item in earnings[:5]:
        print(f"  {item['title']}: {item['summary']}")

    print("\nAll tests passed!")
