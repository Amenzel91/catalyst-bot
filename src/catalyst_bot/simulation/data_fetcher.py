"""
HistoricalDataFetcher - Reconstruct a trading day from APIs.

Fetches:
- Intraday price data (5-minute bars)
- News articles published that day
- SEC filings from that day
- Market metadata (float, volume, etc.)

Usage:
    from catalyst_bot.simulation import HistoricalDataFetcher

    fetcher = HistoricalDataFetcher(cache_dir=Path("data/simulation_cache"))

    # Fetch all data for a specific day
    data = await fetcher.fetch_day(
        date=datetime(2024, 11, 12, tzinfo=timezone.utc),
        tickers=["AAPL", "TSLA", "NVDA"]  # Optional: limit to specific tickers
    )
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Use simulation-aware time when available
try:
    from ..time_utils import now as sim_now
except ImportError:
    # Fallback if not running as part of catalyst_bot
    def sim_now():
        return datetime.now(timezone.utc)


log = logging.getLogger(__name__)


class HistoricalDataFetcher:
    """
    Fetch and cache historical trading data for simulation.

    Supports multiple data sources with automatic caching.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        price_source: str = "tiingo",
        news_source: str = "finnhub",
    ):
        """
        Initialize the data fetcher.

        Args:
            cache_dir: Directory to store cached data
            price_source: Price data source ("tiingo", "yfinance", "cached")
            news_source: News source ("finnhub", "cached")
        """
        self.cache_dir = Path(cache_dir or "data/simulation_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.price_source = price_source
        self.news_source = news_source

    def _cache_key(self, date_str: str, tickers: Optional[List[str]] = None) -> str:
        """Generate a unique cache key for the data request."""
        key_parts = [date_str, self.price_source, self.news_source]
        if tickers:
            key_parts.append("-".join(sorted(tickers)[:10]))  # Limit for filename

        key_str = "_".join(key_parts)
        key_hash = hashlib.md5(key_str.encode()).hexdigest()[:8]
        return f"{date_str}_{key_hash}"

    async def fetch_day(
        self,
        date: datetime,
        tickers: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Fetch all data for a trading day.

        Args:
            date: The trading day to fetch
            tickers: Optional list of tickers to focus on (extracts from news if None)
            use_cache: Whether to use cached data if available

        Returns:
            Complete data package for simulation replay:
            {
                "date": "2024-11-12",
                "price_bars": {"AAPL": [...], "TSLA": [...]},
                "news_items": [...],
                "sec_filings": [...],
                "metadata": {...}
            }
        """
        date_str = date.strftime("%Y-%m-%d")
        cache_key = self._cache_key(date_str, tickers)
        cache_file = self.cache_dir / f"{cache_key}.json"

        # Check cache first - try exact match, then fallback to any file for this date
        if use_cache:
            # Try exact hash match first
            if cache_file.exists():
                log.info(f"Loading cached simulation data for {date_str}")
                try:
                    with open(cache_file) as f:
                        return json.load(f)
                except json.JSONDecodeError:
                    log.warning(f"Cache file corrupted, refetching: {cache_file}")
            else:
                # Fallback: find any cache file for this date
                date_pattern = f"{date_str}_*.json"
                matching_files = sorted(self.cache_dir.glob(date_pattern))
                if matching_files:
                    fallback_file = matching_files[
                        -1
                    ]  # Use most recent (last alphabetically)
                    log.info(
                        f"Loading fallback cache file for {date_str}: {fallback_file.name}"
                    )
                    try:
                        with open(fallback_file) as f:
                            return json.load(f)
                    except json.JSONDecodeError:
                        log.warning(f"Fallback cache corrupted: {fallback_file}")

        log.info(f"Fetching historical data for {date_str}")

        # Initialize data structure
        data = {
            "date": date_str,
            "fetched_at": sim_now().isoformat(),
            "price_bars": {},
            "news_items": [],
            "sec_filings": [],
            "ticker_metadata": {},
            "metadata": {
                "price_source": self.price_source,
                "news_source": self.news_source,
            },
        }

        # 1. Fetch news items for the day
        data["news_items"] = await self._fetch_news(date)
        log.info(f"Fetched {len(data['news_items'])} news items")

        # 2. Extract tickers from news if not provided
        if tickers is None:
            tickers = self._extract_tickers_from_news(data["news_items"])
            log.info(f"Extracted {len(tickers)} tickers from news")

        # 3. Fetch SEC filings
        data["sec_filings"] = await self._fetch_sec_filings(date)
        log.info(f"Fetched {len(data['sec_filings'])} SEC filings")

        # 4. Extract additional tickers from SEC filings
        sec_tickers = self._extract_tickers_from_sec(data["sec_filings"])
        all_tickers = list(set(tickers) | set(sec_tickers))
        log.info(f"Total unique tickers: {len(all_tickers)}")

        # 5. Fetch price data for all tickers
        data["price_bars"] = await self._fetch_prices(date, all_tickers)
        log.info(f"Fetched price data for {len(data['price_bars'])} tickers")

        # 6. Fetch metadata for tickers (optional, non-critical)
        try:
            data["ticker_metadata"] = await self._fetch_ticker_metadata(all_tickers)
        except Exception as e:
            log.warning(f"Failed to fetch ticker metadata: {e}")
            data["ticker_metadata"] = {}

        # Cache the data
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
            log.info(f"Cached simulation data to {cache_file}")
        except Exception as e:
            log.warning(f"Failed to cache data: {e}")

        return data

    def _extract_tickers_from_news(self, news_items: List[Dict]) -> List[str]:
        """Extract unique tickers mentioned in news items."""
        tickers: Set[str] = set()

        for item in news_items:
            # Check related_tickers field
            related = item.get("related_tickers", [])
            if isinstance(related, str):
                related = [t.strip() for t in related.split(",") if t.strip()]
            tickers.update(related)

            # Check ticker field
            ticker = item.get("ticker")
            if ticker and ticker != "N/A":
                tickers.add(ticker)

        # Filter out invalid tickers
        valid_tickers = [
            t for t in tickers if t and len(t) <= 5 and t.isalpha() and t.isupper()
        ]

        return sorted(valid_tickers)

    def _extract_tickers_from_sec(self, sec_filings: List[Dict]) -> List[str]:
        """Extract unique tickers from SEC filings."""
        tickers: Set[str] = set()

        for filing in sec_filings:
            ticker = filing.get("ticker")
            if ticker and ticker != "N/A" and len(ticker) <= 5:
                tickers.add(ticker.upper())

        return sorted(tickers)

    async def _fetch_news(self, date: datetime) -> List[Dict]:
        """Fetch news articles from the specified day."""
        news_items = []

        if self.news_source == "finnhub":
            news_items = await self._fetch_finnhub_news(date)
        elif self.news_source == "cached":
            news_items = self._load_cached_news(date)
        else:
            log.warning(f"Unknown news source: {self.news_source}")

        # Sort by timestamp
        news_items.sort(key=lambda x: x.get("timestamp", ""))

        return news_items

    async def _fetch_finnhub_news(self, date: datetime) -> List[Dict]:
        """Fetch news from Finnhub API for a specific date."""
        try:
            import finnhub
        except ImportError:
            log.warning("Finnhub package not installed")
            return []

        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key:
            log.warning("FINNHUB_API_KEY not set")
            return []

        date_str = date.strftime("%Y-%m-%d")
        next_day = (date + timedelta(days=1)).strftime("%Y-%m-%d")

        try:
            client = finnhub.Client(api_key=api_key)
            news = client.general_news("general", _from=date_str, to=next_day)

            items = []
            for article in news:
                timestamp = article.get("datetime", 0)
                if timestamp:
                    ts_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                else:
                    ts_dt = date.replace(hour=12, tzinfo=timezone.utc)

                related = article.get("related", "")
                if isinstance(related, str):
                    related = [t.strip() for t in related.split(",") if t.strip()]

                items.append(
                    {
                        "id": f"finnhub_{article.get('id', '')}",
                        "timestamp": ts_dt.isoformat(),
                        "title": article.get("headline", ""),
                        "summary": article.get("summary", ""),
                        "source": article.get("source", "finnhub"),
                        "url": article.get("url", ""),
                        "related_tickers": related,
                        "category": article.get("category", ""),
                    }
                )

            return items

        except Exception as e:
            log.error(f"Failed to fetch Finnhub news: {e}")
            return []

    def _load_cached_news(self, date: datetime) -> List[Dict]:
        """Load news from a pre-cached JSONL file."""
        date_str = date.strftime("%Y-%m-%d")
        cached_file = self.cache_dir / f"news_{date_str}.jsonl"

        if not cached_file.exists():
            log.warning(f"No cached news file for {date_str}")
            return []

        items = []
        with open(cached_file) as f:
            for line in f:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return items

    async def _fetch_prices(
        self, date: datetime, tickers: List[str]
    ) -> Dict[str, List[Dict]]:
        """Fetch intraday price bars for all tickers."""
        price_bars = {}

        # Batch fetch with concurrency limit
        semaphore = asyncio.Semaphore(5)

        async def fetch_one(ticker: str) -> tuple:
            async with semaphore:
                bars = await self._fetch_ticker_bars(ticker, date)
                return ticker, bars

        tasks = [fetch_one(ticker) for ticker in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                continue
            ticker, bars = result
            if bars:
                price_bars[ticker] = bars

        return price_bars

    async def _fetch_ticker_bars(self, ticker: str, date: datetime) -> List[Dict]:
        """Fetch intraday bars for a single ticker."""
        if self.price_source == "tiingo":
            return await self._fetch_tiingo_bars(ticker, date)
        elif self.price_source == "yfinance":
            return await self._fetch_yfinance_bars(ticker, date)
        elif self.price_source == "cached":
            return self._load_cached_bars(ticker, date)
        else:
            return []

    async def _fetch_tiingo_bars(self, ticker: str, date: datetime) -> List[Dict]:
        """Fetch from Tiingo IEX API."""
        try:
            import aiohttp
        except ImportError:
            log.warning("aiohttp not installed")
            return []

        api_key = os.getenv("TIINGO_API_KEY")
        if not api_key:
            return []

        date_str = date.strftime("%Y-%m-%d")
        url = f"https://api.tiingo.com/iex/{ticker}/prices"
        params = {
            "startDate": date_str,
            "endDate": date_str,
            "resampleFreq": "5min",
            "token": api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        return []

                    data = await resp.json()

                    bars = []
                    for bar in data:
                        bars.append(
                            {
                                "timestamp": bar.get("date"),
                                "open": bar.get("open"),
                                "high": bar.get("high"),
                                "low": bar.get("low"),
                                "close": bar.get("close"),
                                "volume": bar.get("volume"),
                            }
                        )

                    return bars

        except Exception as e:
            log.debug(f"Tiingo fetch failed for {ticker}: {e}")
            return []

    async def _fetch_yfinance_bars(self, ticker: str, date: datetime) -> List[Dict]:
        """Fetch from yfinance (runs in executor to avoid blocking)."""
        try:
            import yfinance as yf
        except ImportError:
            log.warning("yfinance not installed")
            return []

        date_str = date.strftime("%Y-%m-%d")
        next_day = (date + timedelta(days=1)).strftime("%Y-%m-%d")

        def _download():
            try:
                df = yf.download(
                    ticker,
                    start=date_str,
                    end=next_day,
                    interval="5m",
                    progress=False,
                )

                if df.empty:
                    return []

                bars = []
                for timestamp, row in df.iterrows():
                    bars.append(
                        {
                            "timestamp": timestamp.isoformat(),
                            "open": float(row["Open"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                            "close": float(row["Close"]),
                            "volume": int(row["Volume"]),
                        }
                    )

                return bars

            except Exception as e:
                log.debug(f"yfinance fetch failed for {ticker}: {e}")
                return []

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _download)

    def _load_cached_bars(self, ticker: str, date: datetime) -> List[Dict]:
        """Load price bars from cached file."""
        date_str = date.strftime("%Y-%m-%d")
        cached_file = self.cache_dir / f"prices_{date_str}_{ticker}.json"

        if not cached_file.exists():
            return []

        try:
            with open(cached_file) as f:
                return json.load(f)
        except Exception:
            return []

    async def _fetch_sec_filings(self, date: datetime) -> List[Dict]:
        """Fetch SEC filings from the specified day."""
        # Try to load from cached sec_events.jsonl if available
        date_str = date.strftime("%Y-%m-%d")

        # Check for cached SEC filings
        cached_file = self.cache_dir / f"sec_{date_str}.jsonl"
        if cached_file.exists():
            filings = []
            with open(cached_file) as f:
                for line in f:
                    try:
                        filings.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return filings

        # For now, return empty - SEC data typically comes from RSS feeds
        # which would need to be cached during actual trading days
        log.debug(f"No cached SEC filings for {date_str}")
        return []

    async def _fetch_ticker_metadata(self, tickers: List[str]) -> Dict[str, Dict]:
        """Fetch metadata (float, avg volume, sector) for tickers.

        Integrates with the existing float_data module for comprehensive
        ticker metadata including float shares, average volume, and sector.
        """
        metadata = {}

        # Try to import float_data module
        try:
            from ..float_data import get_float_data
        except ImportError:
            log.debug("float_data module not available, returning empty metadata")
            for ticker in tickers:
                metadata[ticker] = {
                    "ticker": ticker,
                    "float": None,
                    "avg_volume": None,
                    "sector": None,
                }
            return metadata

        # Fetch metadata for each ticker with concurrency limit
        semaphore = asyncio.Semaphore(3)  # Limit concurrent API calls

        async def fetch_one(ticker: str) -> tuple:
            async with semaphore:
                loop = asyncio.get_event_loop()
                try:
                    data = await loop.run_in_executor(None, get_float_data, ticker)
                    return ticker, data
                except Exception as e:
                    log.debug(f"Failed to fetch metadata for {ticker}: {e}")
                    return ticker, None

        tasks = [fetch_one(ticker) for ticker in tickers[:50]]  # Limit to 50 tickers
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                continue
            ticker, data = result
            if data:
                metadata[ticker] = {
                    "ticker": ticker,
                    "float": data.get("float_shares"),
                    "avg_volume": data.get("avg_vol_10d"),
                    "sector": data.get("sector"),
                    "market_cap": data.get("market_cap"),
                    "short_float_pct": data.get("short_float_pct"),
                }
            else:
                metadata[ticker] = {
                    "ticker": ticker,
                    "float": None,
                    "avg_volume": None,
                    "sector": None,
                }

        return metadata

    def get_cached_dates(self) -> List[str]:
        """Get list of dates that have cached data."""
        dates = set()
        for f in self.cache_dir.glob("*.json"):
            # Extract date from filename (YYYY-MM-DD_hash.json)
            name = f.stem
            if len(name) >= 10 and name[4] == "-" and name[7] == "-":
                dates.add(name[:10])

        return sorted(dates)

    def clear_cache(self, date: Optional[datetime] = None) -> int:
        """
        Clear cached data.

        Args:
            date: If provided, only clear cache for this date.
                  If None, clear all cache.

        Returns:
            Number of files deleted
        """
        deleted = 0

        if date:
            date_str = date.strftime("%Y-%m-%d")
            pattern = f"{date_str}_*.json"
        else:
            pattern = "*.json"

        for f in self.cache_dir.glob(pattern):
            try:
                f.unlink()
                deleted += 1
            except Exception as e:
                log.warning(f"Failed to delete {f}: {e}")

        return deleted
