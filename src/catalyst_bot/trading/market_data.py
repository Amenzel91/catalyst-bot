"""
Market Data Feed Module

Provides efficient batch price fetching for position updates with smart caching
and multi-provider fallback support.

Key Features:
- Batch fetching (10-20x faster than sequential)
- Smart caching with configurable TTL (30-60 seconds)
- Fallback to multiple providers (Tiingo, Alpaca, yfinance)
- Integration with existing market.py providers
- Decimal precision for financial calculations
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..config import get_settings
from ..logging_utils import get_logger
from .. import market  # Use existing market providers

logger = get_logger(__name__)


# ============================================================================
# Type Definitions & Cache
# ============================================================================

@dataclass
class PriceQuote:
    """Price quote with metadata."""
    ticker: str
    price: Decimal
    timestamp: datetime
    source: str  # "tiingo", "alpaca", "yfinance", "alpha_vantage"


@dataclass
class MarketDataFeedConfig:
    """Configuration for MarketDataFeed."""
    cache_ttl_seconds: int = 30  # Cache prices for 30 seconds
    max_batch_size: int = 100  # Maximum tickers per batch
    timeout_seconds: float = 10.0  # Overall timeout for batch fetch
    provider_priority: List[str] = field(default_factory=lambda: ["tiingo", "alpaca", "yfinance"])
    use_decimal: bool = True  # Always return Decimal for precision


@dataclass
class CachedPrice:
    """Cached price entry."""
    price: Decimal
    timestamp: datetime
    source: str


# ============================================================================
# Market Data Feed
# ============================================================================

class MarketDataFeed:
    """
    Efficient batch price fetching for position updates.

    Uses existing market.py providers with smart caching:
    - Tiingo IEX API (real-time, requires API key)
    - Alpha Vantage (free tier, limited)
    - yfinance (final fallback, no key required)

    Implements 30-60 second cache to avoid API rate limiting while
    keeping prices fresh for position management.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize market data feed.

        Args:
            config: Optional configuration dictionary
        """
        self.logger = get_logger(__name__)
        settings = get_settings()

        # Parse configuration
        config = config or {}
        self.config = MarketDataFeedConfig(
            cache_ttl_seconds=config.get("cache_ttl_seconds",
                int(getattr(settings, "MARKET_DATA_CACHE_TTL", 30))),
            max_batch_size=config.get("max_batch_size", 100),
            timeout_seconds=config.get("timeout_seconds", 10.0),
            provider_priority=config.get("provider_priority", ["tiingo", "alpaca", "yfinance"]),
        )

        # Cache: ticker -> CachedPrice
        self._price_cache: Dict[str, CachedPrice] = {}
        self._cache_lock = asyncio.Lock()

        # Stats
        self._cache_hits = 0
        self._cache_misses = 0
        self._batch_fetches = 0

        self.logger.info(
            f"Initialized MarketDataFeed (cache_ttl={self.config.cache_ttl_seconds}s, "
            f"batch_size={self.config.max_batch_size})"
        )

    # ========================================================================
    # Public API
    # ========================================================================

    async def get_current_prices(self, tickers: List[str]) -> Dict[str, Decimal]:
        """
        Batch fetch prices for multiple tickers.

        Uses smart caching to avoid redundant API calls. Returns prices
        that are within cache TTL, fetches others from providers.

        Args:
            tickers: List of ticker symbols

        Returns:
            Dictionary mapping ticker -> price (Decimal)
            Missing tickers are omitted from result

        Example:
            >>> feed = MarketDataFeed()
            >>> prices = await feed.get_current_prices(['AAPL', 'MSFT', 'GOOGL'])
            >>> prices
            {'AAPL': Decimal('150.25'), 'MSFT': Decimal('370.50'), 'GOOGL': Decimal('140.00')}
        """
        if not tickers:
            return {}

        # Normalize and validate tickers
        valid_tickers = self._normalize_tickers(tickers)
        if not valid_tickers:
            return {}

        # Check cache first
        cached_tickers = []
        missing_tickers = []

        async with self._cache_lock:
            for ticker in valid_tickers:
                if self._is_cached(ticker):
                    cached_tickers.append(ticker)
                else:
                    missing_tickers.append(ticker)

        # Build result from cache
        result = {}
        for ticker in cached_tickers:
            result[ticker] = self._price_cache[ticker].price
            self._cache_hits += 1

        # Fetch missing tickers
        if missing_tickers:
            fetched_prices = await self._fetch_batch_prices(missing_tickers)
            result.update(fetched_prices)
            self._cache_misses += len(missing_tickers)

            # Update cache with new prices
            async with self._cache_lock:
                for ticker, price in fetched_prices.items():
                    self._price_cache[ticker] = CachedPrice(
                        price=price,
                        timestamp=datetime.now(),
                        source="batch_fetch"
                    )

        self.logger.debug(
            f"get_current_prices tickers={len(valid_tickers)} "
            f"cached={len(cached_tickers)} fetched={len(missing_tickers)} "
            f"cache_hits={self._cache_hits} cache_misses={self._cache_misses}"
        )

        return result

    async def get_price(self, ticker: str) -> Optional[Decimal]:
        """
        Fetch price for a single ticker (convenience method).

        Args:
            ticker: Ticker symbol

        Returns:
            Price as Decimal, or None if unavailable
        """
        prices = await self.get_current_prices([ticker])
        return prices.get(ticker)

    def clear_cache(self) -> None:
        """Clear the price cache (useful for testing)."""
        self._price_cache.clear()
        self.logger.debug("Price cache cleared")

    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache hit/miss stats
        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_pct": round(hit_rate, 2),
            "cached_tickers": len(self._price_cache),
            "batch_fetches": self._batch_fetches,
        }

    # ========================================================================
    # Internal - Caching
    # ========================================================================

    def _is_cached(self, ticker: str) -> bool:
        """
        Check if ticker is in cache and not expired.

        Args:
            ticker: Ticker symbol

        Returns:
            True if cached and valid, False otherwise
        """
        if ticker not in self._price_cache:
            return False

        cached = self._price_cache[ticker]
        age = (datetime.now() - cached.timestamp).total_seconds()

        return age < self.config.cache_ttl_seconds

    def _normalize_tickers(self, tickers: List[str]) -> List[str]:
        """
        Normalize and validate ticker symbols.

        Args:
            tickers: List of ticker symbols (may be lowercase, with spaces, etc)

        Returns:
            List of normalized tickers in uppercase
        """
        normalized = []

        for ticker in tickers:
            if not ticker:
                continue

            # Clean and uppercase
            t = ticker.strip().upper()

            # Remove $ prefix if present (common in social media)
            if t.startswith("$"):
                t = t[1:].strip()

            # Validate ticker (prevent injection)
            if t and len(t) <= 5 and t.isalnum():
                normalized.append(t)
            else:
                self.logger.debug(f"Invalid ticker: {ticker}")

        return normalized

    # ========================================================================
    # Internal - Batch Fetching
    # ========================================================================

    async def _fetch_batch_prices(self, tickers: List[str]) -> Dict[str, Decimal]:
        """
        Fetch prices for batch of tickers using market.py providers.

        Implements provider fallback chain:
        1. batch_get_prices (yfinance batch download - fastest)
        2. get_last_price_change (Tiingo -> Alpha Vantage -> yfinance)

        Args:
            tickers: List of ticker symbols to fetch

        Returns:
            Dictionary mapping ticker -> price (Decimal)
            Missing tickers are omitted
        """
        self._batch_fetches += 1
        result = {}

        try:
            # Use market.batch_get_prices for fast batch download
            self.logger.debug(f"Batch fetching prices for {len(tickers)} tickers")

            try:
                # This uses yfinance batch download (10-20x faster than sequential)
                batch_prices = await asyncio.wait_for(
                    self._run_in_executor(lambda: market.batch_get_prices(tickers)),
                    timeout=self.config.timeout_seconds
                )

                # Extract prices and convert to Decimal
                for ticker, (price, _change) in batch_prices.items():
                    if price is not None:
                        result[ticker] = Decimal(str(price))

                self.logger.debug(
                    f"Batch fetch succeeded: {len(result)}/{len(tickers)} tickers"
                )

                return result

            except asyncio.TimeoutError:
                self.logger.warning(
                    f"Batch fetch timeout after {self.config.timeout_seconds}s, "
                    f"falling back to sequential fetch"
                )
                # Fall through to sequential fetch below

            except Exception as e:
                self.logger.warning(
                    f"Batch fetch failed: {e.__class__.__name__}, "
                    f"falling back to sequential fetch"
                )
                # Fall through to sequential fetch below

            # Fallback: fetch individually with provider chain
            for ticker in tickers:
                if ticker in result:
                    continue  # Already have price

                try:
                    # get_last_price_change uses provider chain (Tiingo -> AV -> yfinance)
                    price, _change = await asyncio.wait_for(
                        self._run_in_executor(
                            lambda t=ticker: market.get_last_price_change(t)
                        ),
                        timeout=self.config.timeout_seconds
                    )

                    if price is not None:
                        result[ticker] = Decimal(str(price))

                except asyncio.TimeoutError:
                    self.logger.debug(
                        f"Timeout fetching price for {ticker}"
                    )

                except Exception as e:
                    self.logger.debug(
                        f"Failed to fetch price for {ticker}: {e.__class__.__name__}"
                    )

            return result

        except Exception as e:
            self.logger.error(
                f"Critical error in batch fetch: {e}",
                exc_info=True
            )
            return {}

    @staticmethod
    async def _run_in_executor(func, *args):
        """
        Run synchronous function in thread pool executor.

        This prevents blocking the async event loop for long-running
        I/O operations like price fetching.

        Args:
            func: Synchronous function to run
            *args: Function arguments

        Returns:
            Result from function
        """
        loop = asyncio.get_running_loop()  # Python 3.10+ safe
        return await loop.run_in_executor(None, func, *args)

    # ========================================================================
    # Stats & Debugging
    # ========================================================================

    def get_status(self) -> Dict:
        """
        Get current feed status.

        Returns:
            Status dictionary with cache and performance info
        """
        cache_size = len(self._price_cache)
        expired = sum(1 for cached in self._price_cache.values()
                     if (datetime.now() - cached.timestamp).total_seconds() >= self.config.cache_ttl_seconds)

        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "initialized": True,
            "cache_size": cache_size,
            "cache_expired": expired,
            "cache_valid": cache_size - expired,
            "cache_ttl_seconds": self.config.cache_ttl_seconds,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_pct": round(hit_rate, 2),
            "batch_fetches": self._batch_fetches,
            "timestamp": datetime.now().isoformat(),
        }


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of MarketDataFeed.
    """

    async def demo():
        """Demo function showing market data feed usage"""

        # Initialize feed
        feed = MarketDataFeed()

        # Fetch single price
        print("Fetching single price...")
        price = await feed.get_price("AAPL")
        print(f"AAPL: ${price}")

        # Batch fetch multiple prices
        print("\nBatch fetching prices...")
        tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]
        prices = await feed.get_current_prices(tickers)

        print(f"\nPrices (cached fetch):")
        for ticker, price in prices.items():
            print(f"  {ticker}: ${price}")

        # Check cache stats
        stats = feed.get_cache_stats()
        print(f"\nCache Stats: {stats}")

        # Fetch again (should hit cache)
        print("\nFetching again (should hit cache)...")
        prices2 = await feed.get_current_prices(tickers)
        stats2 = feed.get_cache_stats()
        print(f"Cache Stats: {stats2}")

        # Get status
        status = feed.get_status()
        print(f"\nFeed Status: {status}")

    # Run demo
    asyncio.run(demo())
