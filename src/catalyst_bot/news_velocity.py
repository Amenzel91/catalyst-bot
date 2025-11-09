"""News Velocity (Momentum) Sentiment Source.

This module tracks news article velocity/momentum as a sentiment indicator.
A sudden spike in article count indicates breaking news, viral catalysts,
or pump attempts - all valuable trading signals.

Key Features:
- Track article count per ticker over time windows: 1h, 4h, 24h
- Calculate velocity: articles_per_hour for each window
- Detect spikes vs sustained coverage
- Deduplicate articles by title similarity
- Lightweight SQLite storage with timestamp tracking

Storage Schema:
    CREATE TABLE article_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        timestamp INTEGER NOT NULL,  -- Unix timestamp
        article_title TEXT,  -- For deduplication
        article_url TEXT,
        source TEXT
    );
    CREATE INDEX idx_ticker_time ON article_history(ticker, timestamp);

Usage:
    from catalyst_bot.news_velocity import NewsVelocityTracker

    tracker = NewsVelocityTracker()

    # Record new article
    tracker.record_article(
        ticker="AAPL",
        title="Apple announces new product",
        url="https://example.com/article",
        source="globenewswire"
    )

    # Get velocity sentiment
    velocity_sentiment = tracker.get_velocity_sentiment(ticker="AAPL")
    # Returns: {
    #     "sentiment": 0.5,  # -1.0 to +1.0 (attention indicator, not directional)
    #     "confidence": 0.70,
    #     "articles_1h": 15,
    #     "articles_4h": 45,
    #     "articles_24h": 120,
    #     "velocity_1h": 15.0,  # articles per hour
    #     "velocity_4h": 11.25,
    #     "velocity_24h": 5.0,
    #     "is_spike": True,  # True if 4h velocity > 3x baseline
    #     "velocity_score": 0.5,
    # }
"""

import hashlib
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .logging_utils import get_logger
from .storage import init_optimized_connection

log = get_logger("news_velocity")


class NewsVelocityTracker:
    """Tracks news article velocity over time and calculates sentiment."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize news velocity tracker with SQLite storage.

        Parameters
        ----------
        db_path : str, optional
            Path to SQLite database file. Defaults to data/news_velocity.db
        """
        if db_path is None:
            # Default to data directory
            data_dir = Path("data")
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "news_velocity.db")

        self.db_path = db_path
        self._init_database()
        log.info("news_velocity_tracker_initialized db_path=%s", db_path)

    def _init_database(self):
        """Create article_history table if it doesn't exist."""
        from .storage import init_optimized_connection

        with init_optimized_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Create table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS article_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    article_title TEXT,
                    article_url TEXT,
                    source TEXT,
                    title_hash TEXT
                )
            """)

            # Create index for fast ticker+time lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ticker_time
                ON article_history(ticker, timestamp)
            """)

            # Create index for deduplication
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_title_hash
                ON article_history(title_hash)
            """)

            conn.commit()
            log.debug("news_velocity_db_initialized")

    def _title_similarity_hash(self, title: str) -> str:
        """Generate similarity hash for deduplication.

        Normalizes title by removing special chars, lowercasing, and
        hashing to detect near-duplicates.
        """
        import re

        # Normalize: lowercase, remove special chars, collapse whitespace
        normalized = re.sub(r"[^\w\s]", "", title.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()

        # Hash normalized title
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def record_article(
        self,
        ticker: str,
        title: str,
        url: Optional[str] = None,
        source: Optional[str] = None,
    ) -> bool:
        """Record a news article for velocity tracking.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        title : str
            Article title (used for deduplication)
        url : str, optional
            Article URL
        source : str, optional
            Source identifier (e.g., 'globenewswire', 'businesswire')

        Returns
        -------
        bool
            True if article was recorded, False if duplicate
        """
        ticker_upper = ticker.upper().strip()
        timestamp = int(datetime.now(timezone.utc).timestamp())

        # Calculate title hash for deduplication
        title_hash = self._title_similarity_hash(title)

        try:
            with init_optimized_connection(self.db_path) as conn:
                cursor = conn.cursor()

                # Check for duplicate within last 24 hours
                cursor.execute(
                    """
                    SELECT id FROM article_history
                    WHERE title_hash = ?
                      AND timestamp >= ?
                    LIMIT 1
                    """,
                    (title_hash, timestamp - 86400),  # 24 hours
                )

                if cursor.fetchone():
                    log.debug(
                        "article_duplicate_skipped ticker=%s title_prefix=%s",
                        ticker_upper,
                        title[:50],
                    )
                    return False

                # Insert article
                cursor.execute(
                    """
                    INSERT INTO article_history
                    (ticker, timestamp, article_title, article_url, source, title_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (ticker_upper, timestamp, title, url, source, title_hash),
                )
                conn.commit()

                log.debug(
                    "article_recorded ticker=%s source=%s title_prefix=%s",
                    ticker_upper,
                    source or "unknown",
                    title[:50],
                )
                return True

        except Exception as e:
            log.error(
                "article_record_error ticker=%s error=%s",
                ticker_upper,
                e.__class__.__name__,
            )
            return False

    def get_velocity_sentiment(
        self,
        ticker: str,
        baseline_articles_per_day: float = 5.0,
    ) -> Optional[Dict]:
        """Calculate velocity sentiment for a ticker.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        baseline_articles_per_day : float, optional
            Expected baseline articles per day (default: 5.0)

        Returns
        -------
        dict or None
            Velocity sentiment data, or None if insufficient data
        """
        ticker_upper = ticker.upper().strip()
        now = datetime.now(timezone.utc)
        now_ts = int(now.timestamp())

        try:
            with init_optimized_connection(self.db_path) as conn:
                cursor = conn.cursor()

                # Get article counts for different time windows
                # 1 hour = 3600s, 4 hours = 14400s, 24 hours = 86400s
                time_windows = {
                    "1h": 3600,
                    "4h": 14400,
                    "24h": 86400,
                }

                article_counts = {}
                for window_name, window_seconds in time_windows.items():
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM article_history
                        WHERE ticker = ?
                          AND timestamp >= ?
                        """,
                        (ticker_upper, now_ts - window_seconds),
                    )
                    count = cursor.fetchone()[0]
                    article_counts[window_name] = count

                # Extract counts
                articles_1h = article_counts["1h"]
                articles_4h = article_counts["4h"]
                articles_24h = article_counts["24h"]

                # Calculate velocities (articles per hour)
                velocity_1h = articles_1h  # Already per hour
                velocity_4h = articles_4h / 4.0
                velocity_24h = articles_24h / 24.0

                # Calculate baseline hourly rate
                baseline_hourly = baseline_articles_per_day / 24.0

                # Calculate velocity score based on thresholds
                sentiment = 0.0
                velocity_score = 0.0

                # Threshold-based sentiment (attention indicator)
                if articles_1h > 50:
                    sentiment = 0.7  # Extreme attention - potential pump
                    velocity_score = 0.7
                elif articles_1h > 20:
                    sentiment = 0.5  # Viral catalyst
                    velocity_score = 0.5
                elif articles_1h > 10:
                    sentiment = 0.3  # High media attention
                    velocity_score = 0.3
                else:
                    # Scale linearly for lower counts
                    sentiment = min(0.3, articles_1h / 10.0 * 0.3)
                    velocity_score = sentiment

                # Check for sustained coverage (4h velocity vs baseline)
                # Only flag as spike if we have significant 4h data AND velocity is high
                is_spike = False
                if articles_4h >= 15 and velocity_4h > (baseline_hourly * 3):
                    # Sustained spike over 4 hours (15+ articles AND >3x baseline)
                    is_spike = True
                    # Add bonus to sentiment
                    sentiment = min(1.0, sentiment + 0.2)
                    velocity_score = min(1.0, velocity_score + 0.2)

                # Confidence based on data availability
                # Higher confidence with more data points
                if articles_24h >= 10:
                    confidence = 0.70
                elif articles_24h >= 5:
                    confidence = 0.60
                elif articles_24h >= 2:
                    confidence = 0.50
                else:
                    confidence = 0.40

                result = {
                    "sentiment": sentiment,
                    "confidence": confidence,
                    "articles_1h": articles_1h,
                    "articles_4h": articles_4h,
                    "articles_24h": articles_24h,
                    "velocity_1h": velocity_1h,
                    "velocity_4h": velocity_4h,
                    "velocity_24h": velocity_24h,
                    "is_spike": is_spike,
                    "velocity_score": velocity_score,
                    "baseline_hourly": baseline_hourly,
                }

                log.debug(
                    "velocity_sentiment_calculated ticker=%s articles_1h=%d "
                    "articles_4h=%d articles_24h=%d sentiment=%.3f is_spike=%s",
                    ticker_upper,
                    articles_1h,
                    articles_4h,
                    articles_24h,
                    sentiment,
                    is_spike,
                )

                return result

        except Exception as e:
            log.error(
                "velocity_sentiment_error ticker=%s error=%s",
                ticker_upper,
                e.__class__.__name__,
            )
            return None

    def cleanup_old_data(self, days_to_keep: int = 7) -> int:
        """Remove article history older than specified days.

        Parameters
        ----------
        days_to_keep : int, optional
            Number of days of history to retain, default 7

        Returns
        -------
        int
            Number of rows deleted
        """
        cutoff_ts = int(
            (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).timestamp()
        )

        try:
            with init_optimized_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM article_history WHERE timestamp < ?",
                    (cutoff_ts,),
                )
                deleted = cursor.rowcount
                conn.commit()

            log.info("article_history_cleanup deleted=%d days_kept=%d", deleted, days_to_keep)
            return deleted

        except Exception as e:
            log.error("article_cleanup_error error=%s", e.__class__.__name__)
            return 0

    def get_stats(self) -> Dict:
        """Get statistics about tracked articles.

        Returns
        -------
        dict
            Statistics including total articles, tickers tracked, etc.
        """
        try:
            with init_optimized_connection(self.db_path) as conn:
                cursor = conn.cursor()

                # Total articles
                cursor.execute("SELECT COUNT(*) FROM article_history")
                total_articles = cursor.fetchone()[0]

                # Unique tickers
                cursor.execute("SELECT COUNT(DISTINCT ticker) FROM article_history")
                unique_tickers = cursor.fetchone()[0]

                # Articles in last 24h
                now_ts = int(datetime.now(timezone.utc).timestamp())
                cursor.execute(
                    "SELECT COUNT(*) FROM article_history WHERE timestamp >= ?",
                    (now_ts - 86400,),
                )
                articles_24h = cursor.fetchone()[0]

                return {
                    "total_articles": total_articles,
                    "unique_tickers": unique_tickers,
                    "articles_24h": articles_24h,
                }

        except Exception as e:
            log.error("stats_error error=%s", e.__class__.__name__)
            return {
                "total_articles": 0,
                "unique_tickers": 0,
                "articles_24h": 0,
            }


# Global singleton instance
_tracker = None


def get_tracker() -> NewsVelocityTracker:
    """Get global news velocity tracker instance (singleton)."""
    global _tracker
    if _tracker is None:
        _tracker = NewsVelocityTracker()
    return _tracker
