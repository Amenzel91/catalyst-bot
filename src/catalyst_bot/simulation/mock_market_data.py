"""
MockMarketDataFeed - Provides historical prices during simulation.

Replaces live market data API calls with historical data lookup.
Returns price data based on the current simulation clock time.

Usage:
    from catalyst_bot.simulation import SimulationClock
    from catalyst_bot.simulation.mock_market_data import MockMarketDataFeed

    clock = SimulationClock(start_time=..., speed_multiplier=0)
    feed = MockMarketDataFeed(price_bars=historical_data["price_bars"], clock=clock)

    # Get current price (as of simulation time)
    price = feed.get_last_price("AAPL")

    # Get price with previous close
    last, prev_close = feed.get_last_price_snapshot("AAPL")

    # Batch fetch for multiple tickers
    prices = feed.batch_get_prices(["AAPL", "TSLA", "NVDA"])
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .clock import SimulationClock

# Import the global clock provider to get the synchronized clock
from .clock_provider import get_clock as get_global_clock

log = logging.getLogger(__name__)


class MockMarketDataFeed:
    """
    Simulated market data feed using historical data.

    Provides the same interface as the real market data providers,
    but returns historical prices based on the simulation clock.

    The feed indexes price bars by timestamp for O(1) lookup and
    caches the most recent price for each ticker for quick access.
    """

    def __init__(
        self,
        price_bars: Dict[str, List[Dict]],
        clock: "SimulationClock",
    ):
        """
        Initialize with historical price data.

        Args:
            price_bars: Dict mapping ticker -> list of OHLCV bars
                        Each bar should have: timestamp, open, high, low, close, volume
            clock: SimulationClock for time-aware lookups
        """
        self.clock = clock

        # Index price data by timestamp for fast lookup
        # Structure: {ticker: {timestamp: bar_data}}
        self._price_index: Dict[str, Dict[datetime, Dict]] = {}

        # Sorted timestamps per ticker for binary search
        self._sorted_timestamps: Dict[str, List[datetime]] = {}

        # Cache latest prices for quick access
        self._latest_prices: Dict[str, float] = {}
        self._latest_bars: Dict[str, Dict] = {}

        # Load and index the price data
        self._load_price_data(price_bars)

        log.debug(
            f"MockMarketDataFeed initialized with {len(self._price_index)} tickers"
        )

    def _get_current_time(self) -> datetime:
        """
        Get current simulation time, preferring the global clock.

        This ensures MockMarketDataFeed uses the same clock that the runner
        advances via sim_sleep(), solving the dual-clock mismatch issue.

        Returns:
            Current simulation time from the global clock provider,
            falling back to the local clock if global not available.
        """
        # Prefer the global clock (which is advanced by sim_sleep in runner)
        global_clock = get_global_clock()
        if global_clock is not None:
            return global_clock.now()
        # Fallback to local clock (for tests that don't use global provider)
        return self.clock.now()

    def _load_price_data(self, price_bars: Dict[str, List[Dict]]) -> None:
        """
        Index price data by timestamp for fast lookup.

        Args:
            price_bars: Raw price bar data from historical fetch
        """
        for ticker, bars in price_bars.items():
            self._price_index[ticker] = {}
            timestamps = []

            for bar in bars:
                timestamp = self._parse_timestamp(bar.get("timestamp"))
                if timestamp:
                    self._price_index[ticker][timestamp] = bar
                    timestamps.append(timestamp)

            # Sort timestamps for binary search
            self._sorted_timestamps[ticker] = sorted(timestamps)

        log.debug(
            f"Loaded price data for {len(self._price_index)} tickers: "
            f"{list(self._price_index.keys())}"
        )

    def _parse_timestamp(self, ts: Any) -> Optional[datetime]:
        """
        Parse timestamp from various formats.

        Handles: ISO format strings, datetime objects, Unix timestamps.

        Args:
            ts: Timestamp in any supported format

        Returns:
            Parsed datetime or None if parsing fails
        """
        if ts is None:
            return None

        try:
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    return ts.replace(tzinfo=timezone.utc)
                return ts

            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts, tz=timezone.utc)

            if isinstance(ts, str):
                # Handle ISO format with various timezone formats
                ts = ts.replace("Z", "+00:00")
                return datetime.fromisoformat(ts)

        except (ValueError, TypeError) as e:
            log.warning(f"Failed to parse timestamp '{ts}': {e}")

        return None

    def _find_bar_at_time(self, ticker: str, target_time: datetime) -> Optional[Dict]:
        """
        Find the most recent price bar at or before the target time.

        Uses binary search for efficient lookup.

        Args:
            ticker: Stock ticker symbol
            target_time: Target datetime to look up

        Returns:
            Price bar dict or None if no data available
        """
        if ticker not in self._sorted_timestamps:
            return None

        timestamps = self._sorted_timestamps[ticker]
        if not timestamps:
            return None

        # Binary search for the largest timestamp <= target_time
        left, right = 0, len(timestamps) - 1
        result_idx = -1

        while left <= right:
            mid = (left + right) // 2
            if timestamps[mid] <= target_time:
                result_idx = mid
                left = mid + 1
            else:
                right = mid - 1

        if result_idx >= 0:
            timestamp = timestamps[result_idx]
            return self._price_index[ticker].get(timestamp)

        return None

    def get_last_price(self, ticker: str) -> Optional[float]:
        """
        Get the most recent price as of current simulation time.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Last traded price, or None if no data available
        """
        current_time = self._get_current_time()
        bar = self._find_bar_at_time(ticker, current_time)

        if bar:
            price = bar.get("close")
            if price is not None:
                self._latest_prices[ticker] = price
                self._latest_bars[ticker] = bar
                return price

        # Return cached price if available
        return self._latest_prices.get(ticker)

    def get_last_price_snapshot(self, ticker: str) -> Optional[Tuple[float, float]]:
        """
        Get price snapshot with last price and previous close.

        Useful for calculating price change percentage.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Tuple of (last_price, previous_close) or None if unavailable
        """
        current_time = self._get_current_time()
        current_bar = self._find_bar_at_time(ticker, current_time)

        if not current_bar:
            return None

        last_price = current_bar.get("close")
        if last_price is None:
            return None

        # Get previous bar for prev_close
        timestamps = self._sorted_timestamps.get(ticker, [])
        current_idx = -1

        for i, ts in enumerate(timestamps):
            if ts <= current_time:
                current_idx = i
            else:
                break

        if current_idx > 0:
            prev_timestamp = timestamps[current_idx - 1]
            prev_bar = self._price_index[ticker].get(prev_timestamp, {})
            prev_close = prev_bar.get("close", last_price)
        else:
            # No previous bar, use open price as prev_close
            prev_close = current_bar.get("open", last_price)

        return (last_price, prev_close)

    def get_ohlcv(self, ticker: str) -> Optional[Dict]:
        """
        Get current OHLCV bar for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with open, high, low, close, volume or None
        """
        current_time = self._get_current_time()
        bar = self._find_bar_at_time(ticker, current_time)

        if bar:
            self._latest_bars[ticker] = bar

        return bar or self._latest_bars.get(ticker)

    def batch_get_prices(self, tickers: List[str]) -> Dict[str, Tuple[float, float]]:
        """
        Get prices for multiple tickers efficiently.

        Args:
            tickers: List of stock ticker symbols

        Returns:
            Dict mapping ticker -> (last_price, change_pct)
        """
        results = {}

        for ticker in tickers:
            snapshot = self.get_last_price_snapshot(ticker)
            if snapshot:
                last, prev = snapshot
                if prev and prev != 0:
                    change_pct = ((last / prev) - 1) * 100
                else:
                    change_pct = 0.0
                results[ticker] = (last, change_pct)

        return results

    def get_available_tickers(self) -> List[str]:
        """
        Get list of tickers with price data.

        Returns:
            List of ticker symbols
        """
        return list(self._price_index.keys())

    def has_data_for_ticker(self, ticker: str) -> bool:
        """
        Check if price data exists for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            True if data is available
        """
        return ticker in self._price_index and len(self._price_index[ticker]) > 0

    def get_price_range(self, ticker: str) -> Optional[Tuple[datetime, datetime]]:
        """
        Get the time range of available data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Tuple of (earliest_time, latest_time) or None
        """
        timestamps = self._sorted_timestamps.get(ticker, [])
        if timestamps:
            return (timestamps[0], timestamps[-1])
        return None

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the mock feed.

        Returns:
            Dict with feed statistics
        """
        total_bars = sum(len(bars) for bars in self._price_index.values())

        return {
            "tickers": len(self._price_index),
            "total_bars": total_bars,
            "cached_prices": len(self._latest_prices),
            "ticker_list": list(self._price_index.keys()),
        }

    def clear_cache(self) -> None:
        """Clear the latest price cache (for testing)."""
        self._latest_prices.clear()
        self._latest_bars.clear()
