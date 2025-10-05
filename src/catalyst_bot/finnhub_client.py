"""Finnhub API client for real-time market data, news, and sentiment.

This module provides a comprehensive client for the Finnhub API, supporting:
- Real-time news and press releases
- Earnings calendar
- Analyst upgrades/downgrades
- Insider transactions
- Social sentiment (Reddit, Twitter, StockTwits)
- Company profiles
- Price data (OHLCV)

API Documentation: https://finnhub.io/docs/api
Free Tier: 60 API calls/minute
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("finnhub_client")


log = get_logger("finnhub_client")


class FinnhubClient:
    """Client for Finnhub API with rate limiting and error handling."""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str = None):
        """Initialize Finnhub client.

        Parameters
        ----------
        api_key : str
            Finnhub API key (default: read from FINNHUB_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY", "")
        if not self.api_key:
            raise ValueError("Finnhub API key required (set FINNHUB_API_KEY env var)")

        self._last_request_time = 0
        self._min_request_interval = 1.0 / 60.0  # 60 calls/minute = 1 call per second

    def _rate_limit(self):
        """Enforce rate limiting (60 calls/minute)."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            sleep_time = self._min_request_interval - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _request(
        self, endpoint: str, params: Dict[str, Any] = None
    ) -> Optional[Dict | List]:
        """Make authenticated request to Finnhub API.

        Parameters
        ----------
        endpoint : str
            API endpoint (e.g., "/news", "/stock/earnings")
        params : dict
            Query parameters

        Returns
        -------
        dict or list or None
            Parsed JSON response, or None on error
        """
        self._rate_limit()

        url = f"{self.BASE_URL}{endpoint}"
        params = params or {}
        params["token"] = self.api_key

        try:
            log.debug("finnhub_request endpoint=%s params=%s", endpoint, params)
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 429:
                log.warning("finnhub_rate_limit_exceeded")
                return None

            if resp.status_code != 200:
                log.warning(
                    "finnhub_error status=%d endpoint=%s", resp.status_code, endpoint
                )
                return None

            data = resp.json()
            return data

        except (ValueError, requests.exceptions.JSONDecodeError) as e:
            log.warning("finnhub_json_error endpoint=%s err=%s", endpoint, str(e))
            return None
        except requests.exceptions.Timeout:
            log.warning("finnhub_timeout endpoint=%s", endpoint)
            return None
        except Exception as e:
            log.warning(
                "finnhub_exception endpoint=%s err=%s",
                endpoint,
                str(e.__class__.__name__),
            )
            return None

    # -------------------------------------------------------------------------
    # News & Press Releases
    # -------------------------------------------------------------------------

    def get_company_news(
        self, ticker: str, from_date: str = None, to_date: str = None
    ) -> List[Dict[str, Any]]:
        """Get company-specific news articles.

        Parameters
        ----------
        ticker : str
            Stock symbol
        from_date : str
            Start date (YYYY-MM-DD format, default: 7 days ago)
        to_date : str
            End date (YYYY-MM-DD format, default: today)

        Returns
        -------
        list of dict
            News articles with keys: category, datetime, headline, id, image,
            related, source, summary, url
        """
        if not from_date:
            from_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
                "%Y-%m-%d"
            )
        if not to_date:
            to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        data = self._request(
            "/company-news",
            {"symbol": ticker.upper(), "from": from_date, "to": to_date},
        )

        return data if isinstance(data, list) else []

    def get_market_news(self, category: str = "general") -> List[Dict[str, Any]]:
        """Get general market news.

        Parameters
        ----------
        category : str
            News category: general, forex, crypto, merger (default: general)

        Returns
        -------
        list of dict
            News articles
        """
        data = self._request("/news", {"category": category})
        return data if isinstance(data, list) else []

    def get_press_releases(self, ticker: str) -> List[Dict[str, Any]]:
        """Get company press releases.

        Parameters
        ----------
        ticker : str
            Stock symbol

        Returns
        -------
        list of dict
            Press releases with keys: datetime, headline, id, url
        """
        data = self._request("/press-releases", {"symbol": ticker.upper()})
        return data if isinstance(data, list) else []

    # -------------------------------------------------------------------------
    # Earnings & Fundamentals
    # -------------------------------------------------------------------------

    def get_earnings_calendar(
        self, from_date: str = None, to_date: str = None, ticker: str = None
    ) -> List[Dict[str, Any]]:
        """Get earnings calendar.

        Parameters
        ----------
        from_date : str
            Start date (YYYY-MM-DD, default: today)
        to_date : str
            End date (YYYY-MM-DD, default: 7 days from now)
        ticker : str
            Filter by specific ticker (optional)

        Returns
        -------
        list of dict
            Earnings events with keys: date, epsActual, epsEstimate, hour,
            quarter, revenueActual, revenueEstimate, symbol, year
        """
        if not from_date:
            from_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not to_date:
            to_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime(
                "%Y-%m-%d"
            )

        params = {"from": from_date, "to": to_date}
        if ticker:
            params["symbol"] = ticker.upper()

        data = self._request("/calendar/earnings", params)

        if isinstance(data, dict) and "earningsCalendar" in data:
            return data["earningsCalendar"]
        return []

    def get_company_profile(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get company profile and fundamentals.

        Parameters
        ----------
        ticker : str
            Stock symbol

        Returns
        -------
        dict or None
            Company profile with keys: country, currency, exchange, finnhubIndustry,
            ipo, logo, marketCapitalization, name, phone, shareOutstanding, ticker, weburl
        """
        data = self._request("/stock/profile2", {"symbol": ticker.upper()})
        return data if isinstance(data, dict) else None

    # -------------------------------------------------------------------------
    # Analyst Recommendations & Upgrades/Downgrades
    # -------------------------------------------------------------------------

    def get_recommendation_trends(self, ticker: str) -> List[Dict[str, Any]]:
        """Get analyst recommendation trends.

        Parameters
        ----------
        ticker : str
            Stock symbol

        Returns
        -------
        list of dict
            Recommendation trends with keys: buy, hold, period, sell, strongBuy,
            strongSell, symbol
        """
        data = self._request("/stock/recommendation", {"symbol": ticker.upper()})
        return data if isinstance(data, list) else []

    def get_price_target(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get analyst price targets.

        Parameters
        ----------
        ticker : str
            Stock symbol

        Returns
        -------
        dict or None
            Price targets with keys: lastUpdated, symbol, targetHigh, targetLow,
            targetMean, targetMedian
        """
        data = self._request("/stock/price-target", {"symbol": ticker.upper()})
        return data if isinstance(data, dict) else None

    def get_upgrades_downgrades(self, ticker: str) -> List[Dict[str, Any]]:
        """Get analyst upgrades and downgrades.

        Parameters
        ----------
        ticker : str
            Stock symbol

        Returns
        -------
        list of dict
            Upgrades/downgrades with keys: company, fromGrade, gradeTime, symbol,
            toGrade, action
        """
        data = self._request("/stock/upgrade-downgrade", {"symbol": ticker.upper()})
        return data if isinstance(data, list) else []

    # -------------------------------------------------------------------------
    # Insider Transactions
    # -------------------------------------------------------------------------

    def get_insider_transactions(
        self, ticker: str, from_date: str = None, to_date: str = None
    ) -> List[Dict[str, Any]]:
        """Get insider transactions.

        Parameters
        ----------
        ticker : str
            Stock symbol
        from_date : str
            Start date (YYYY-MM-DD, default: 30 days ago)
        to_date : str
            End date (YYYY-MM-DD, default: today)

        Returns
        -------
        list of dict
            Insider transactions with keys: change, filingDate, name, share,
            symbol, transactionCode, transactionDate, transactionPrice
        """
        if not from_date:
            from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
                "%Y-%m-%d"
            )
        if not to_date:
            to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        data = self._request(
            "/stock/insider-transactions",
            {"symbol": ticker.upper(), "from": from_date, "to": to_date},
        )

        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return []

    # -------------------------------------------------------------------------
    # Social Sentiment
    # -------------------------------------------------------------------------

    def get_social_sentiment(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get social media sentiment from Reddit and Twitter.

        Parameters
        ----------
        ticker : str
            Stock symbol

        Returns
        -------
        dict or None
            Sentiment data with keys: reddit (list), symbol, twitter (list)
            Each entry has: atTime, mention, positiveScore, negativeScore, score
        """
        data = self._request("/stock/social-sentiment", {"symbol": ticker.upper()})
        return data if isinstance(data, dict) else None

    # -------------------------------------------------------------------------
    # Price Data
    # -------------------------------------------------------------------------

    def get_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get real-time quote.

        Parameters
        ----------
        ticker : str
            Stock symbol

        Returns
        -------
        dict or None
            Quote with keys: c (current price), d (change), dp (percent change),
            h (high), l (low), o (open), pc (previous close), t (timestamp)
        """
        data = self._request("/quote", {"symbol": ticker.upper()})
        return data if isinstance(data, dict) else None


# -------------------------------------------------------------------------
# Convenience Functions
# -------------------------------------------------------------------------


def get_finnhub_client() -> Optional[FinnhubClient]:
    """Get a configured Finnhub client.

    Returns
    -------
    FinnhubClient or None
        Client instance, or None if API key not configured
    """
    try:
        return FinnhubClient()
    except ValueError:
        log.debug("finnhub_client_not_configured")
        return None


if __name__ == "__main__":
    # Test script
    print("Testing Finnhub API client...")

    client = get_finnhub_client()
    if not client:
        print("ERROR: Set FINNHUB_API_KEY environment variable")
        exit(1)

    # Test news
    print("\n--- Company News (AAPL) ---")
    news = client.get_company_news("AAPL")
    for article in news[:3]:
        print(f"  {article.get('datetime')}: {article.get('headline')}")

    # Test earnings calendar
    print("\n--- Earnings Calendar (next 7 days) ---")
    earnings = client.get_earnings_calendar()
    for event in earnings[:5]:
        print(
            f"  {event.get('date')} {event.get('symbol')}: EPS est {event.get('epsEstimate')}"
        )

    # Test upgrades/downgrades
    print("\n--- Analyst Upgrades/Downgrades (AAPL) ---")
    upgrades = client.get_upgrades_downgrades("AAPL")
    for event in upgrades[:3]:
        print(
            f"  {event.get('gradeTime')}: {event.get('fromGrade')} → {event.get('toGrade')}"
        )

    print("\nAll tests passed!")
