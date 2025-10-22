"""Temporal Sentiment Tracking - Time-series sentiment analysis and trend detection.

This module provides sentiment tracking capabilities to detect trends, momentum,
and reversals over time. Research shows that sentiment trends predict price
movements better than absolute sentiment values.

Key Features:
- Time-series storage of sentiment scores (SQLite)
- Trend calculation over 1h, 4h, 24h windows
- Sentiment momentum (velocity) calculation
- Reversal detection (>3 std dev spikes)
- Sentiment divergence detection (social vs news)

Storage Schema:
    CREATE TABLE sentiment_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        timestamp INTEGER NOT NULL,  -- Unix timestamp
        sentiment_score REAL NOT NULL,  -- -1.0 to +1.0
        confidence REAL,  -- 0.0 to 1.0
        source TEXT,  -- e.g., 'combined', 'social', 'news'
        metadata TEXT  -- JSON blob for additional data
    );
    CREATE INDEX idx_ticker_time ON sentiment_history(ticker, timestamp);

Usage:
    from catalyst_bot.sentiment_tracking import SentimentTracker

    tracker = SentimentTracker()

    # Record new sentiment
    tracker.record(
        ticker="AAPL",
        sentiment=0.75,
        confidence=0.85,
        source="combined"
    )

    # Get trend analysis
    trends = tracker.get_trends(ticker="AAPL")
    # Returns: {
    #     "trend_1h": 0.15,   # +0.15 increase over 1 hour
    #     "trend_4h": -0.05,  # -0.05 decrease over 4 hours
    #     "trend_24h": 0.30,  # +0.30 increase over 24 hours
    #     "momentum": 0.08,   # Current velocity (change per hour)
    #     "is_reversal": False,  # No >3σ spike detected
    #     "reversal_magnitude": 0.5,  # Std dev units
    # }
"""

import json
import logging
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .logging_utils import get_logger

log = get_logger("sentiment_tracking")


@dataclass
class SentimentTrend:
    """Sentiment trend analysis results."""

    ticker: str
    current_sentiment: float
    confidence: float

    # Trend metrics (change over time windows)
    trend_1h: Optional[float] = None  # Sentiment change over 1 hour
    trend_4h: Optional[float] = None  # Sentiment change over 4 hours
    trend_24h: Optional[float] = None  # Sentiment change over 24 hours

    # Momentum metrics
    momentum: Optional[float] = None  # Velocity (sentiment change per hour)
    acceleration: Optional[float] = None  # Change in velocity

    # Reversal detection
    is_reversal: bool = False  # True if >3σ spike detected
    reversal_magnitude: Optional[float] = None  # Std dev units
    reversal_direction: Optional[str] = None  # "bullish" or "bearish"

    # Statistical metrics
    volatility: Optional[float] = None  # Std dev of recent sentiment
    mean_24h: Optional[float] = None  # 24h average sentiment

    # Data quality
    data_points_1h: int = 0
    data_points_4h: int = 0
    data_points_24h: int = 0


class SentimentTracker:
    """Tracks sentiment over time and computes trends, momentum, and reversals."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize sentiment tracker with SQLite storage.

        Parameters
        ----------
        db_path : str, optional
            Path to SQLite database file. Defaults to data/sentiment_history.db
        """
        if db_path is None:
            # Default to data directory
            data_dir = Path("data")
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "sentiment_history.db")

        self.db_path = db_path
        self._init_database()
        log.info("sentiment_tracker_initialized db_path=%s", db_path)

    def _init_database(self):
        """Create sentiment_history table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    sentiment_score REAL NOT NULL,
                    confidence REAL,
                    source TEXT,
                    metadata TEXT
                )
            """)

            # Create index for fast ticker+time lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ticker_time
                ON sentiment_history(ticker, timestamp)
            """)

            conn.commit()
            log.debug("sentiment_tracker_db_initialized")

    def record(
        self,
        ticker: str,
        sentiment: float,
        confidence: float = 1.0,
        source: str = "combined",
        metadata: Optional[Dict] = None,
    ) -> None:
        """Record a sentiment data point.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        sentiment : float
            Sentiment score (-1.0 to +1.0)
        confidence : float, optional
            Confidence level (0.0 to 1.0), default 1.0
        source : str, optional
            Source identifier (e.g., 'combined', 'social', 'news')
        metadata : dict, optional
            Additional metadata to store as JSON
        """
        ticker_upper = ticker.upper().strip()
        timestamp = int(datetime.now(timezone.utc).timestamp())

        # Clamp sentiment to valid range
        sentiment = max(-1.0, min(1.0, sentiment))
        confidence = max(0.0, min(1.0, confidence))

        # Serialize metadata
        metadata_json = json.dumps(metadata) if metadata else None

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO sentiment_history
                    (ticker, timestamp, sentiment_score, confidence, source, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (ticker_upper, timestamp, sentiment, confidence, source, metadata_json),
                )
                conn.commit()

            log.debug(
                "sentiment_recorded ticker=%s sentiment=%.3f confidence=%.3f source=%s",
                ticker_upper,
                sentiment,
                confidence,
                source,
            )
        except Exception as e:
            log.error(
                "sentiment_record_error ticker=%s error=%s",
                ticker_upper,
                e.__class__.__name__,
            )

    def get_trends(
        self,
        ticker: str,
        current_sentiment: Optional[float] = None,
        current_confidence: Optional[float] = None,
    ) -> Optional[SentimentTrend]:
        """Calculate sentiment trends and momentum for a ticker.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        current_sentiment : float, optional
            Current sentiment value. If not provided, uses most recent from DB
        current_confidence : float, optional
            Current confidence value

        Returns
        -------
        SentimentTrend or None
            Trend analysis object, or None if insufficient data
        """
        ticker_upper = ticker.upper().strip()
        now = datetime.now(timezone.utc)
        now_ts = int(now.timestamp())

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get historical data points for different time windows
                # 1 hour = 3600s, 4 hours = 14400s, 24 hours = 86400s
                cursor.execute(
                    """
                    SELECT timestamp, sentiment_score, confidence
                    FROM sentiment_history
                    WHERE ticker = ?
                      AND timestamp >= ?
                    ORDER BY timestamp ASC
                    """,
                    (ticker_upper, now_ts - 86400),  # Last 24 hours
                )

                rows = cursor.fetchall()

                if not rows:
                    log.debug("sentiment_trends_no_data ticker=%s", ticker_upper)
                    return None

                # If current sentiment not provided, use most recent from DB
                if current_sentiment is None:
                    cursor.execute(
                        """
                        SELECT sentiment_score, confidence
                        FROM sentiment_history
                        WHERE ticker = ?
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """,
                        (ticker_upper,),
                    )
                    latest = cursor.fetchone()
                    if latest:
                        current_sentiment = latest[0]
                        current_confidence = latest[1] or 1.0
                    else:
                        return None

                if current_confidence is None:
                    current_confidence = 1.0

                # Separate data points by time window
                data_1h = []
                data_4h = []
                data_24h = []

                for ts, sent, conf in rows:
                    age_seconds = now_ts - ts
                    data_24h.append((ts, sent, conf))
                    if age_seconds <= 14400:  # 4 hours
                        data_4h.append((ts, sent, conf))
                    if age_seconds <= 3600:  # 1 hour
                        data_1h.append((ts, sent, conf))

                # Calculate trends (change from oldest to current)
                trend_1h = self._calculate_trend(data_1h, current_sentiment)
                trend_4h = self._calculate_trend(data_4h, current_sentiment)
                trend_24h = self._calculate_trend(data_24h, current_sentiment)

                # Calculate momentum (velocity = change per hour)
                momentum = self._calculate_momentum(data_24h, current_sentiment, now_ts)

                # Calculate acceleration (change in velocity)
                acceleration = self._calculate_acceleration(data_24h, now_ts)

                # Detect reversals (>3σ spikes)
                is_reversal, reversal_magnitude, reversal_direction = \
                    self._detect_reversal(data_24h, current_sentiment)

                # Calculate volatility (std dev of recent sentiment)
                volatility = self._calculate_volatility(data_24h)

                # Calculate 24h mean
                mean_24h = statistics.mean([s for _, s, _ in data_24h]) if data_24h else None

                # Build result
                result = SentimentTrend(
                    ticker=ticker_upper,
                    current_sentiment=current_sentiment,
                    confidence=current_confidence,
                    trend_1h=trend_1h,
                    trend_4h=trend_4h,
                    trend_24h=trend_24h,
                    momentum=momentum,
                    acceleration=acceleration,
                    is_reversal=is_reversal,
                    reversal_magnitude=reversal_magnitude,
                    reversal_direction=reversal_direction,
                    volatility=volatility,
                    mean_24h=mean_24h,
                    data_points_1h=len(data_1h),
                    data_points_4h=len(data_4h),
                    data_points_24h=len(data_24h),
                )

                log.debug(
                    "sentiment_trends_calculated ticker=%s trend_1h=%.3f trend_24h=%.3f "
                    "momentum=%.3f is_reversal=%s",
                    ticker_upper,
                    trend_1h or 0.0,
                    trend_24h or 0.0,
                    momentum or 0.0,
                    is_reversal,
                )

                return result

        except Exception as e:
            log.error(
                "sentiment_trends_error ticker=%s error=%s",
                ticker_upper,
                e.__class__.__name__,
            )
            return None

    def _calculate_trend(
        self,
        data: List[Tuple[int, float, float]],
        current_sentiment: float,
    ) -> Optional[float]:
        """Calculate sentiment trend (change from start to current).

        Returns change in sentiment from oldest data point to current.
        Positive = increasing sentiment, Negative = decreasing sentiment.
        """
        if not data:
            return None

        # Oldest sentiment in this window
        oldest_sentiment = data[0][1]

        # Trend = current - oldest
        trend = current_sentiment - oldest_sentiment
        return trend

    def _calculate_momentum(
        self,
        data: List[Tuple[int, float, float]],
        current_sentiment: float,
        current_ts: int,
    ) -> Optional[float]:
        """Calculate sentiment momentum (velocity = change per hour).

        Uses linear regression slope over the time window to estimate
        rate of sentiment change.
        """
        if len(data) < 2:
            return None

        try:
            # Add current point
            all_data = data + [(current_ts, current_sentiment, 1.0)]

            # Calculate linear regression slope
            # Convert timestamps to hours since oldest point
            oldest_ts = all_data[0][0]
            x_values = [(ts - oldest_ts) / 3600.0 for ts, _, _ in all_data]
            y_values = [sent for _, sent, _ in all_data]

            # Simple linear regression
            n = len(x_values)
            x_mean = sum(x_values) / n
            y_mean = sum(y_values) / n

            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
            denominator = sum((x - x_mean) ** 2 for x in x_values)

            if denominator == 0:
                return None

            slope = numerator / denominator  # Sentiment change per hour
            return slope

        except Exception:
            return None

    def _calculate_acceleration(
        self,
        data: List[Tuple[int, float, float]],
        current_ts: int,
    ) -> Optional[float]:
        """Calculate sentiment acceleration (change in velocity).

        Compares momentum in first half vs second half of time window.
        """
        if len(data) < 4:
            return None

        try:
            # Split data in half
            midpoint = len(data) // 2
            first_half = data[:midpoint]
            second_half = data[midpoint:]

            # Calculate momentum for each half
            momentum_first = self._calculate_momentum(
                first_half, first_half[-1][1], first_half[-1][0]
            )
            momentum_second = self._calculate_momentum(
                second_half, second_half[-1][1], second_half[-1][0]
            )

            if momentum_first is None or momentum_second is None:
                return None

            # Acceleration = change in momentum
            acceleration = momentum_second - momentum_first
            return acceleration

        except Exception:
            return None

    def _detect_reversal(
        self,
        data: List[Tuple[int, float, float]],
        current_sentiment: float,
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Detect sentiment reversals (>3σ spikes).

        Returns (is_reversal, magnitude_in_std_devs, direction)
        where direction is 'bullish' or 'bearish'.
        """
        if len(data) < 5:
            return False, None, None

        try:
            # Calculate mean and std dev of historical data
            sentiments = [s for _, s, _ in data]
            mean = statistics.mean(sentiments)
            std_dev = statistics.stdev(sentiments)

            if std_dev == 0:
                return False, None, None

            # Calculate z-score of current sentiment
            z_score = (current_sentiment - mean) / std_dev

            # Reversal if |z-score| > 3
            is_reversal = abs(z_score) > 3.0
            magnitude = abs(z_score)

            if is_reversal:
                direction = "bullish" if z_score > 0 else "bearish"
            else:
                direction = None

            return is_reversal, magnitude, direction

        except Exception:
            return False, None, None

    def _calculate_volatility(
        self,
        data: List[Tuple[int, float, float]],
    ) -> Optional[float]:
        """Calculate sentiment volatility (standard deviation)."""
        if len(data) < 2:
            return None

        try:
            sentiments = [s for _, s, _ in data]
            return statistics.stdev(sentiments)
        except Exception:
            return None

    def cleanup_old_data(self, days_to_keep: int = 30) -> int:
        """Remove sentiment history older than specified days.

        Parameters
        ----------
        days_to_keep : int, optional
            Number of days of history to retain, default 30

        Returns
        -------
        int
            Number of rows deleted
        """
        cutoff_ts = int(
            (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).timestamp()
        )

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM sentiment_history WHERE timestamp < ?",
                    (cutoff_ts,),
                )
                deleted = cursor.rowcount
                conn.commit()

            log.info("sentiment_history_cleanup deleted=%d days_kept=%d", deleted, days_to_keep)
            return deleted

        except Exception as e:
            log.error("sentiment_cleanup_error error=%s", e.__class__.__name__)
            return 0
