"""
Backtesting Engine
==================

Main backtesting engine that replays historical alerts with realistic
trading simulation, tracks performance, and generates reports.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from ..logging_utils import get_logger
from .analytics import (
    analyze_catalyst_performance,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_returns_series,
    calculate_sharpe_ratio,
    calculate_win_rate,
)
from .portfolio import ClosedTrade, Portfolio, Position
from .trade_simulator import PennyStockTradeSimulator

log = get_logger("backtesting.engine")


class LRUCache:
    """
    Simple LRU (Least Recently Used) cache implementation.

    Prevents unbounded memory growth by evicting least recently used items
    when cache reaches max_size. Critical for long-running backtests.
    """

    def __init__(self, max_size: int = 50):
        """
        Initialize LRU cache.

        Parameters
        ----------
        max_size : int
            Maximum number of items to cache (default: 50)
        """
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size

    def get(self, key: str) -> Optional[pd.DataFrame]:
        """
        Get item from cache and mark as recently used.

        Parameters
        ----------
        key : str
            Cache key

        Returns
        -------
        pd.DataFrame or None
            Cached value or None if not found
        """
        if key not in self.cache:
            return None

        # Move to end (mark as recently used)
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: str, value: pd.DataFrame) -> None:
        """
        Add item to cache, evicting oldest if necessary.

        Parameters
        ----------
        key : str
            Cache key
        value : pd.DataFrame
            Value to cache
        """
        if key in self.cache:
            # Update existing key and move to end
            self.cache.move_to_end(key)

        self.cache[key] = value

        # Evict oldest item if over max_size
        if len(self.cache) > self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            log.debug("lru_cache_evicted key=%s", oldest_key)

    def __contains__(self, key: str) -> bool:
        """Check if key exists in cache."""
        return key in self.cache

    def clear(self) -> None:
        """Clear all items from cache."""
        self.cache.clear()


class BacktestEngine:
    """
    Main backtesting engine that:
    1. Replays historical alerts from events.jsonl or database
    2. Simulates trades with realistic constraints
    3. Tracks performance over time
    4. Generates comprehensive reports
    """

    def __init__(
        self,
        start_date: str,
        end_date: str,
        initial_capital: float = 10000.0,
        strategy_params: Optional[Dict] = None,
        data_source: str = "data/events.jsonl",
        data_filter: Optional[Callable] = None,
    ):
        """
        Initialize backtest engine.

        Parameters
        ----------
        start_date : str
            Start date (YYYY-MM-DD)
        end_date : str
            End date (YYYY-MM-DD)
        initial_capital : float
            Starting capital
        strategy_params : dict, optional
            Strategy parameters:
            - min_score: Minimum relevance score (default: 0.25)
            - min_sentiment: Minimum sentiment (default: None)
            - take_profit_pct: Take profit % (default: 0.20)
            - stop_loss_pct: Stop loss % (default: 0.10)
            - max_hold_hours: Max hold time in hours (default: 24)
            - position_size_pct: Position size % (default: 0.10)
            - max_daily_volume_pct: Max % of daily volume (default: 0.05)
        data_source : str, optional
            Path to historical events data file (default: "data/events.jsonl")
        data_filter : callable, optional
            Optional filter function to apply to loaded alerts.
            Function should accept an alert dict and return True to keep it.
        """
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        self.initial_capital = initial_capital
        self.data_source = data_source
        self.data_filter = data_filter

        # Default strategy params
        self.strategy_params = {
            "min_score": 0.25,
            "min_sentiment": None,
            "take_profit_pct": 0.20,
            "stop_loss_pct": 0.10,
            "max_hold_hours": 24,
            "position_size_pct": 0.10,
            "max_daily_volume_pct": 0.05,
            "required_catalysts": [],  # e.g., ['earnings', 'fda_approval']
        }

        if strategy_params:
            self.strategy_params.update(strategy_params)

        # Initialize simulator and portfolio
        self.simulator = PennyStockTradeSimulator(
            initial_capital=initial_capital,
            position_size_pct=self.strategy_params["position_size_pct"],
            max_daily_volume_pct=self.strategy_params["max_daily_volume_pct"],
        )
        self.portfolio = Portfolio(initial_capital=initial_capital)

        # LRU cache to reduce API calls and prevent OOM in long backtests
        self.price_cache = LRUCache(max_size=50)

        log.info(
            "backtest_engine_initialized start=%s end=%s capital=%.2f params=%s",
            start_date,
            end_date,
            initial_capital,
            self.strategy_params,
        )

    def load_historical_alerts(self) -> List[Dict]:
        """
        Load alerts from configured data source filtered by date range.

        Returns
        -------
        list of dict
            Historical alerts within date range
        """
        alerts = []

        # Load from configured data source
        events_path = Path(self.data_source)
        if not events_path.exists():
            log.warning("events_file_not_found path=%s", events_path)
            return []

        log.info("loading_historical_alerts path=%s", events_path)

        try:
            with open(events_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)

                        # Parse timestamp
                        ts_str = event.get("ts") or event.get("timestamp")
                        if not ts_str:
                            continue

                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

                        # Filter by date range
                        if not (self.start_date <= ts <= self.end_date):
                            continue

                        # Skip if no ticker
                        ticker = event.get("ticker")
                        if not ticker:
                            continue

                        alerts.append(event)

                    except Exception as e:
                        log.debug("failed_to_parse_event error=%s", str(e))
                        continue

        except Exception as e:
            log.error("failed_to_load_events path=%s error=%s", events_path, str(e))
            return []

        # Apply custom data filter if provided
        if self.data_filter is not None:
            original_count = len(alerts)
            alerts = [alert for alert in alerts if self.data_filter(alert)]
            log.info(
                "data_filter_applied original=%d filtered=%d",
                original_count,
                len(alerts),
            )

        log.info(
            "historical_alerts_loaded count=%d start=%s end=%s",
            len(alerts),
            self.start_date.strftime("%Y-%m-%d"),
            self.end_date.strftime("%Y-%m-%d"),
        )

        return alerts

    def prefetch_bulk_price_data(
        self, tickers: List[str], start: datetime, end: datetime
    ) -> Dict[str, pd.DataFrame]:
        """
        Bulk fetch price data for multiple tickers in parallel using Tiingo.

        Uses ThreadPoolExecutor to fetch multiple tickers concurrently.
        Falls back to yfinance if Tiingo is not available.

        Parameters
        ----------
        tickers : list of str
            List of ticker symbols to fetch
        start : datetime
            Start datetime
        end : datetime
            End datetime

        Returns
        -------
        dict
            Dict mapping ticker -> price DataFrame
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from ..config import get_settings

        settings = get_settings()
        tiingo_api_key = settings.tiingo_api_key

        price_cache_dict = {}

        def fetch_ticker_tiingo(ticker):
            """Fetch single ticker from Tiingo."""
            try:
                import requests

                url = f"https://api.tiingo.com/iex/{ticker}/prices"
                params = {
                    "startDate": start.strftime("%Y-%m-%d"),
                    "endDate": end.strftime("%Y-%m-%d"),
                    "resampleFreq": "1hour",
                    "token": tiingo_api_key,
                }
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                # Convert to DataFrame
                df = pd.DataFrame(data)
                if "date" in df.columns and not df.empty:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")
                    df = df.rename(
                        columns={
                            "close": "Close",
                            "open": "Open",
                            "high": "High",
                            "low": "Low",
                            "volume": "Volume",
                        }
                    )
                    return ticker, df

                return ticker, None

            except Exception as e:
                log.debug("tiingo_fetch_failed ticker=%s error=%s", ticker, str(e))
                return ticker, None

        # Use ThreadPoolExecutor for parallel fetching
        if tiingo_api_key:
            log.info(
                "prefetching_price_data_tiingo tickers=%d start=%s end=%s",
                len(tickers),
                start.date(),
                end.date(),
            )
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_ticker = {
                    executor.submit(fetch_ticker_tiingo, ticker): ticker
                    for ticker in tickers
                }
                for future in as_completed(future_to_ticker):
                    ticker, df = future.result()
                    if df is not None:
                        price_cache_dict[ticker] = df

        log.info(
            "prefetch_complete cached=%d of %d tickers",
            len(price_cache_dict),
            len(tickers),
        )
        return price_cache_dict

    def load_price_data(
        self, ticker: str, start: datetime, end: datetime
    ) -> Optional[pd.DataFrame]:
        """
        Load historical price data for ticker.

        Uses yfinance for simplicity. In production, you might use Tiingo or
        cached data.

        Parameters
        ----------
        ticker : str
            Stock ticker
        start : datetime
            Start date
        end : datetime
            End date

        Returns
        -------
        pd.DataFrame or None
            Price data with columns: Open, High, Low, Close, Volume
        """
        # Check if we have prefetched data
        if hasattr(self, "prefetch_cache") and ticker in self.prefetch_cache:
            return self.prefetch_cache[ticker]

        cache_key = f"{ticker}_{start.date()}_{end.date()}"

        # Check LRU cache first
        cached_data = self.price_cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            import yfinance as yf

            # Download data
            df = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval="15m",  # 15-minute data for more granular intraday tracking
                progress=False,
            )

            if df.empty:
                log.warning(
                    "no_price_data ticker=%s start=%s end=%s",
                    ticker,
                    start.date(),
                    end.date(),
                )
                return None

            # Store in LRU cache (auto-evicts oldest if full)
            self.price_cache.set(cache_key, df)

            log.debug(
                "price_data_loaded ticker=%s rows=%d start=%s end=%s",
                ticker,
                len(df),
                start.date(),
                end.date(),
            )

            return df

        except Exception as e:
            log.warning("price_data_load_failed ticker=%s error=%s", ticker, str(e))
            return None

    def get_price_at_time(self, ticker: str, timestamp: datetime) -> Optional[float]:
        """
        Get price at a specific time.

        Parameters
        ----------
        ticker : str
            Stock ticker
        timestamp : datetime
            Target timestamp

        Returns
        -------
        float or None
            Price at that time
        """
        # Load data for a window around the timestamp
        start = timestamp - timedelta(days=2)
        end = timestamp + timedelta(days=2)

        df = self.load_price_data(ticker, start, end)
        if df is None or df.empty:
            return None

        try:
            # Find closest timestamp
            df_idx = pd.to_datetime(df.index)
            target_ts = pd.Timestamp(timestamp, tz=timezone.utc)

            # Get closest row
            closest_idx = df_idx.searchsorted(target_ts)
            if closest_idx >= len(df):
                closest_idx = len(df) - 1

            price = df.iloc[closest_idx]["Close"]
            return float(price)

        except Exception as e:
            log.debug(
                "get_price_failed ticker=%s ts=%s error=%s", ticker, timestamp, str(e)
            )
            return None

    def apply_entry_strategy(self, alert: Dict) -> bool:
        """
        Determine if alert meets entry criteria.

        Parameters
        ----------
        alert : dict
            Alert data

        Returns
        -------
        bool
            True if should enter trade
        """
        # Check minimum score
        score = alert.get("cls", {}).get("score", 0.0)
        if score < self.strategy_params["min_score"]:
            return False

        # Check minimum sentiment (if specified)
        min_sentiment = self.strategy_params.get("min_sentiment")
        if min_sentiment is not None:
            sentiment = alert.get("cls", {}).get("sentiment", 0.0)
            if sentiment < min_sentiment:
                return False

        # Check required catalysts (if specified)
        required_catalysts = self.strategy_params.get("required_catalysts", [])
        if required_catalysts:
            keywords = alert.get("cls", {}).get("keywords", [])
            if not any(cat in keywords for cat in required_catalysts):
                return False

        return True

    def apply_exit_strategy(
        self, position: Position, current_price: float, elapsed_hours: float
    ) -> Tuple[bool, str]:
        """
        Determine if position should be exited.

        Exit rules:
        - Take profit: +X% gain (configurable)
        - Stop loss: -X% loss (configurable)
        - Time exit: Max hold hours

        Parameters
        ----------
        position : Position
            Open position
        current_price : float
            Current market price
        elapsed_hours : float
            Hours since entry

        Returns
        -------
        tuple
            (should_exit: bool, reason: str)
        """
        # Calculate current P&L %
        pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100

        # Take profit
        take_profit = self.strategy_params["take_profit_pct"] * 100
        if pnl_pct >= take_profit:
            return True, "take_profit"

        # Stop loss
        stop_loss = self.strategy_params["stop_loss_pct"] * 100
        if pnl_pct <= -stop_loss:
            return True, "stop_loss"

        # Time exit
        max_hold = self.strategy_params["max_hold_hours"]
        if elapsed_hours >= max_hold:
            return True, "time_exit"

        return False, ""

    def run_backtest(self) -> Dict:
        """
        Main backtest loop.

        Returns
        -------
        dict
            {
                'trades': List[Dict],
                'equity_curve': List[Tuple[timestamp, value]],
                'metrics': {
                    'total_return_pct': float,
                    'win_rate': float,
                    'sharpe_ratio': float,
                    'max_drawdown_pct': float,
                    'profit_factor': float,
                    'total_trades': int,
                    'avg_hold_time_hours': float,
                    ...
                }
            }
        """
        log.info(
            "starting_backtest start=%s end=%s",
            self.start_date.date(),
            self.end_date.date(),
        )

        # Load historical alerts
        alerts = self.load_historical_alerts()
        if not alerts:
            log.warning("no_alerts_found - backtest_aborted")
            return {
                "trades": [],
                "equity_curve": [],
                "metrics": self.portfolio.get_performance_metrics(),
            }

        # Sort alerts by timestamp
        alerts.sort(key=lambda a: a.get("ts", "") or a.get("timestamp", ""))

        # Extract unique tickers and prefetch price data in bulk
        unique_tickers = list(
            set(
                alert.get("ticker", "").upper()
                for alert in alerts
                if alert.get("ticker")
            )
        )
        if unique_tickers:
            log.info("extracting_unique_tickers count=%d", len(unique_tickers))
            # Add buffer to date range for price lookups
            prefetch_start = self.start_date - timedelta(days=2)
            prefetch_end = self.end_date + timedelta(days=2)
            self.prefetch_cache = self.prefetch_bulk_price_data(
                unique_tickers, prefetch_start, prefetch_end
            )
        else:
            self.prefetch_cache = {}

        # Process each alert
        for alert in alerts:
            ticker = alert.get("ticker", "").upper()
            ts_str = alert.get("ts") or alert.get("timestamp")
            alert_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

            # Check entry criteria
            if not self.apply_entry_strategy(alert):
                log.debug(
                    "entry_rejected ticker=%s score=%.2f",
                    ticker,
                    alert.get("cls", {}).get("score", 0),
                )
                continue

            # Get entry price
            entry_price = self.get_price_at_time(ticker, alert_time)
            if entry_price is None:
                log.debug("no_entry_price ticker=%s - skipping", ticker)
                continue

            # Skip if already have position in this ticker
            if ticker in self.portfolio.positions:
                log.debug("position_exists ticker=%s - skipping", ticker)
                continue

            # Execute entry trade
            trade_result = self.simulator.execute_trade(
                ticker=ticker,
                action="buy",
                price=entry_price,
                volume=None,  # Would need to fetch volume data
                timestamp=int(alert_time.timestamp()),
                available_capital=self.portfolio.cash,
            )

            if not trade_result.executed:
                log.debug(
                    "trade_not_executed ticker=%s reason=%s",
                    ticker,
                    trade_result.reason,
                )
                continue

            # Open position
            success = self.portfolio.open_position(
                ticker=ticker,
                shares=trade_result.shares,
                entry_price=trade_result.fill_price,
                entry_time=int(alert_time.timestamp()),
                alert_data={
                    "score": alert.get("cls", {}).get("score", 0.0),
                    "sentiment": alert.get("cls", {}).get("sentiment", 0.0),
                    "keywords": alert.get("cls", {}).get("keywords", []),
                    "catalyst_type": self._get_catalyst_type(alert),
                    "source": alert.get("source", "unknown"),
                },
                commission=trade_result.commission,
            )

            if success:
                log.info(
                    "position_opened ticker=%s shares=%d entry=%.4f score=%.2f",
                    ticker,
                    trade_result.shares,
                    trade_result.fill_price,
                    alert.get("cls", {}).get("score", 0),
                )

        # Monitor and exit positions
        self._monitor_positions()

        # Calculate final metrics
        final_metrics = self._calculate_final_metrics()

        # Prepare results
        trades_data = [
            self._trade_to_dict(trade) for trade in self.portfolio.closed_trades
        ]

        results = {
            "trades": trades_data,
            "equity_curve": self.portfolio.equity_curve,
            "metrics": final_metrics,
            "strategy_params": self.strategy_params,
            "backtest_period": {
                "start": self.start_date.strftime("%Y-%m-%d"),
                "end": self.end_date.strftime("%Y-%m-%d"),
            },
        }

        log.info(
            "backtest_complete trades=%d return=%.2f%% sharpe=%.2f win_rate=%.1f%%",
            final_metrics["total_trades"],
            final_metrics["total_return_pct"],
            final_metrics.get("sharpe_ratio", 0),
            final_metrics["win_rate"],
        )

        return results

    def _monitor_positions(self) -> None:
        """
        Monitor open positions and exit based on strategy.

        This simulates monitoring positions over time and exiting when
        conditions are met.
        """
        # Create a timeline of hourly checks
        current_time = self.start_date
        end_time = self.end_date + timedelta(days=1)  # Add buffer for final exits

        while current_time <= end_time:
            # Check each open position
            tickers_to_close = []

            for ticker, position in list(self.portfolio.positions.items()):
                # Calculate elapsed time
                elapsed_hours = (
                    current_time.timestamp() - position.entry_time
                ) / 3600.0

                # Get current price
                current_price = self.get_price_at_time(ticker, current_time)
                if current_price is None:
                    continue

                # Check exit conditions
                should_exit, exit_reason = self.apply_exit_strategy(
                    position, current_price, elapsed_hours
                )

                if should_exit:
                    tickers_to_close.append((ticker, current_price, exit_reason))

            # Close positions
            for ticker, exit_price, exit_reason in tickers_to_close:
                self.portfolio.close_position(
                    ticker=ticker,
                    exit_price=exit_price,
                    exit_time=int(current_time.timestamp()),
                    exit_reason=exit_reason,
                )

            # Record equity point
            current_prices = {
                ticker: self.get_price_at_time(ticker, current_time) or pos.entry_price
                for ticker, pos in self.portfolio.positions.items()
            }
            self.portfolio.record_equity_point(
                int(current_time.timestamp()), current_prices
            )

            # Move to next 15-minute interval (more granular monitoring)
            current_time += timedelta(minutes=15)

    def _get_catalyst_type(self, alert: Dict) -> str:
        """Extract catalyst type from alert keywords."""
        keywords = alert.get("cls", {}).get("keywords", [])

        # Map common keywords to catalyst types
        catalyst_map = {
            "fda": ["fda", "approval", "clearance"],
            "clinical": ["phase", "trial", "study"],
            "partnership": ["partnership", "collaboration", "agreement"],
            "earnings": ["earnings", "revenue", "profit"],
            "sec_filing": ["8-k", "10-k", "10-q", "s-1"],
        }

        for catalyst_type, catalyst_keywords in catalyst_map.items():
            if any(
                kw.lower() in " ".join(keywords).lower() for kw in catalyst_keywords
            ):
                return catalyst_type

        return "other"

    def _calculate_final_metrics(self) -> Dict:
        """Calculate final performance metrics."""
        base_metrics = self.portfolio.get_performance_metrics()

        # Calculate Sharpe ratio
        if len(self.portfolio.equity_curve) > 1:
            returns = calculate_returns_series(self.portfolio.equity_curve)
            sharpe = calculate_sharpe_ratio(returns)
            base_metrics["sharpe_ratio"] = sharpe
        else:
            base_metrics["sharpe_ratio"] = 0.0

        # Calculate max drawdown details
        drawdown_info = calculate_max_drawdown(self.portfolio.equity_curve)
        base_metrics["max_drawdown_details"] = drawdown_info

        # Win rate breakdown
        trades_data = [self._trade_to_dict(t) for t in self.portfolio.closed_trades]
        win_rate_info = calculate_win_rate(trades_data)
        base_metrics["win_rate_details"] = win_rate_info

        # Profit factor
        profit_factor = calculate_profit_factor(trades_data)
        base_metrics["profit_factor"] = profit_factor

        # Catalyst performance
        catalyst_perf = analyze_catalyst_performance(trades_data)
        base_metrics["catalyst_performance"] = catalyst_perf

        return base_metrics

    def _trade_to_dict(self, trade: ClosedTrade) -> Dict:
        """Convert ClosedTrade to dict."""
        return {
            "ticker": trade.ticker,
            "shares": trade.shares,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
            "profit": trade.profit,
            "profit_pct": trade.profit_pct,
            "hold_time_hours": trade.hold_time_hours,
            "exit_reason": trade.exit_reason,
            "alert_data": trade.alert_data,
            "commission": trade.commission,
        }
