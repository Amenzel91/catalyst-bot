"""Data models used throughout the catalyst bot.

These dataclasses define the structure of the data passed between
modules. Keeping them in a central location helps to enforce type
consistency and facilitates easier refactoring in the future.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional


@dataclass
class NewsItem:
    """Represents a canonicalized news item or press release."""

    ts_utc: datetime  # timestamp in UTC when the news was published
    title: str  # cleaned headline
    canonical_url: str  # URL for the canonical version of the release
    source_host: str  # host/domain where the release originated
    ticker: Optional[str] = None  # associated stock ticker, if any
    raw_text: Optional[str] = None  # raw body text of the release, if available


@dataclass
class ScoredItem:
    """Represents a news item after classification/scoring."""

    item: NewsItem  # underlying news item
    sentiment: float  # VADER compound sentiment score (-1 to 1)
    keyword_hits: List[str]  # list of keyword categories that matched
    source_weight: float  # weight associated with the source host
    total_score: float  # aggregate score used for ranking


@dataclass
class TradeSimConfig:
    """Configuration parameters for the intraday trade simulator."""

    position_size: float = 500.0  # dollars deployed per trade
    slippage_bps: float = 5.0  # slippage in basis points (0.01%)
    entry_offsets: List[int] = field(default_factory=lambda: [0, 5, 15, 30])  # minutes after news
    hold_durations: List[int] = field(
        default_factory=lambda: [5, 15, 30, 60, 120, 240]  # minutes to hold
    )


@dataclass
class TradeSimResult:
    """Results of a single trade simulation for a news item."""

    item: NewsItem
    entry_offset: int  # minutes after news for entry
    hold_duration: int  # minutes held
    returns: Dict[str, float]  # keys: best/mid/worst, values: pct returns


@dataclass
class AnalyzerSummary:
    """Summary of analyzer run for a given date."""

    date: str
    metrics: Dict[str, float]  # aggregated metrics (e.g., hit rates, confusion matrix)
    keyword_stats: Dict[str, Dict[str, float]]  # updated keyword weights and hit rates