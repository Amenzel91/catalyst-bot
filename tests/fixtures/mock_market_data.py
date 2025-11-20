"""Mock market data provider for testing."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Quote:
    """Market quote data."""

    symbol: str
    bid_price: float
    ask_price: float
    bid_size: int
    ask_size: int
    timestamp: datetime


@dataclass
class Bar:
    """OHLCV bar data."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None


class MockMarketDataProvider:
    """
    Mock market data provider for testing.

    Generates realistic market data without external API calls.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.RandomState(seed)
        self._prices: Dict[str, float] = {
            "AAPL": 175.00,
            "TSLA": 250.00,
            "NVDA": 500.00,
            "SPY": 450.00,
        }
        self._volatility: Dict[str, float] = {
            "AAPL": 0.02,  # 2% daily volatility
            "TSLA": 0.04,  # 4% daily volatility
            "NVDA": 0.035,  # 3.5% daily volatility
            "SPY": 0.01,  # 1% daily volatility
        }

    def get_latest_quote(self, symbol: str) -> Quote:
        """Get latest quote for a symbol."""
        if symbol not in self._prices:
            raise ValueError(f"Unknown symbol: {symbol}")

        mid_price = self._prices[symbol]
        spread = mid_price * 0.0001  # 1 basis point spread

        return Quote(
            symbol=symbol,
            bid_price=mid_price - spread / 2,
            ask_price=mid_price + spread / 2,
            bid_size=self.rng.randint(100, 1000) * 100,
            ask_size=self.rng.randint(100, 1000) * 100,
            timestamp=datetime.now(timezone.utc),
        )

    def get_latest_bar(self, symbol: str) -> Bar:
        """Get latest bar for a symbol."""
        if symbol not in self._prices:
            raise ValueError(f"Unknown symbol: {symbol}")

        close_price = self._prices[symbol]
        volatility = self._volatility.get(symbol, 0.02)

        # Generate realistic OHLC
        open_price = close_price * (1 + self.rng.normal(0, volatility / 4))
        high_price = max(open_price, close_price) * (1 + abs(self.rng.normal(0, volatility / 2)))
        low_price = min(open_price, close_price) * (1 - abs(self.rng.normal(0, volatility / 2)))
        volume = self.rng.randint(10_000_000, 100_000_000)

        return Bar(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=volume,
            vwap=round((high_price + low_price + close_price) / 3, 2),
        )

    def get_historical_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1Day",
    ) -> pd.DataFrame:
        """Get historical bars for a symbol."""
        if symbol not in self._prices:
            raise ValueError(f"Unknown symbol: {symbol}")

        return generate_market_data(
            symbol=symbol,
            days=(end - start).days,
            base_price=self._prices[symbol],
            volatility=self._volatility.get(symbol, 0.02),
            seed=hash(symbol) % 10000,
        )

    def update_price(self, symbol: str, new_price: float):
        """Update the current price for a symbol (for testing)."""
        self._prices[symbol] = new_price

    def simulate_price_movement(self, symbol: str, pct_change: float):
        """Simulate a price movement (for testing)."""
        if symbol in self._prices:
            self._prices[symbol] *= 1 + pct_change


def generate_market_data(
    symbol: str = "AAPL",
    days: int = 30,
    base_price: float = 170.0,
    volatility: float = 0.02,
    trend: float = 0.001,  # Daily trend (0.1% per day by default)
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """
    Generate realistic market data for testing.

    Args:
        symbol: Stock symbol
        days: Number of days of data
        base_price: Starting price
        volatility: Daily volatility (standard deviation of returns)
        trend: Daily trend (mean return)
        seed: Random seed for reproducibility

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random.RandomState(42)

    # Generate dates
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=days, freq="D")

    # Generate returns using GBM (Geometric Brownian Motion)
    returns = rng.normal(trend, volatility, days)
    close_prices = base_price * (1 + returns).cumprod()

    # Generate OHLC from close prices
    open_prices = close_prices * rng.uniform(0.99, 1.01, days)
    high_prices = np.maximum(open_prices, close_prices) * rng.uniform(1.00, 1.03, days)
    low_prices = np.minimum(open_prices, close_prices) * rng.uniform(0.97, 1.00, days)

    # Generate volume (correlated with price changes)
    base_volume = 50_000_000
    volume_volatility = abs(returns) * 2  # Higher volatility = higher volume
    volumes = base_volume * (1 + rng.normal(0, 0.3, days) + volume_volatility)
    volumes = volumes.astype(int)

    df = pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": dates,
            "open": np.round(open_prices, 2),
            "high": np.round(high_prices, 2),
            "low": np.round(low_prices, 2),
            "close": np.round(close_prices, 2),
            "volume": volumes,
        }
    )

    return df


def generate_intraday_data(
    symbol: str = "AAPL",
    date: Optional[datetime] = None,
    interval_minutes: int = 5,
    base_price: float = 175.0,
    volatility: float = 0.001,  # Intraday volatility per interval
) -> pd.DataFrame:
    """
    Generate intraday minute-level data for testing.

    Args:
        symbol: Stock symbol
        date: Date for the data (default: today)
        interval_minutes: Interval in minutes (1, 5, 15, 60)
        base_price: Starting price
        volatility: Volatility per interval

    Returns:
        DataFrame with intraday OHLCV data
    """
    if date is None:
        date = datetime.now(timezone.utc).date()

    # Market hours: 9:30 AM - 4:00 PM ET (6.5 hours = 390 minutes)
    market_open = datetime.combine(date, datetime.min.time().replace(hour=13, minute=30))
    market_open = market_open.replace(tzinfo=timezone.utc)

    num_intervals = 390 // interval_minutes

    timestamps = [
        market_open + timedelta(minutes=i * interval_minutes) for i in range(num_intervals)
    ]

    rng = np.random.RandomState(42)
    returns = rng.normal(0, volatility, num_intervals)
    close_prices = base_price * (1 + returns).cumprod()

    open_prices = np.concatenate([[base_price], close_prices[:-1]])
    high_prices = np.maximum(open_prices, close_prices) * rng.uniform(1.000, 1.002, num_intervals)
    low_prices = np.minimum(open_prices, close_prices) * rng.uniform(0.998, 1.000, num_intervals)

    volumes = rng.randint(10_000, 500_000, num_intervals)

    df = pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": timestamps,
            "open": np.round(open_prices, 2),
            "high": np.round(high_prices, 2),
            "low": np.round(low_prices, 2),
            "close": np.round(close_prices, 2),
            "volume": volumes,
        }
    )

    return df


def generate_quote_stream(
    symbol: str = "AAPL",
    num_quotes: int = 100,
    base_price: float = 175.0,
    spread_bps: float = 1.0,  # Spread in basis points
) -> List[Quote]:
    """
    Generate a stream of quotes for testing real-time updates.

    Args:
        symbol: Stock symbol
        num_quotes: Number of quotes to generate
        base_price: Starting mid price
        spread_bps: Bid-ask spread in basis points

    Returns:
        List of Quote objects
    """
    rng = np.random.RandomState(42)
    quotes = []

    current_price = base_price
    spread = base_price * (spread_bps / 10000)

    for i in range(num_quotes):
        # Random walk for mid price
        price_change = rng.normal(0, 0.001) * current_price
        current_price += price_change

        # Generate quote
        quote = Quote(
            symbol=symbol,
            bid_price=round(current_price - spread / 2, 2),
            ask_price=round(current_price + spread / 2, 2),
            bid_size=rng.randint(100, 1000) * 100,
            ask_size=rng.randint(100, 1000) * 100,
            timestamp=datetime.now(timezone.utc) + timedelta(seconds=i),
        )
        quotes.append(quote)

    return quotes
