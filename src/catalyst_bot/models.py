from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class NewsItem:
    source: str
    title: str
    link: str
    id: str
    summary: Optional[str] = None
    ticker: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    @property
    def source_host(self) -> Optional[str]:
        try:
            return urlparse(self.link).netloc.lower()
        except Exception:
            return None

    @classmethod
    def from_feed_dict(cls, d: Dict[str, Any]) -> "NewsItem":
        return cls(
            source=(d.get("source") or "unknown"),
            title=d.get("title") or "",
            link=d.get("link") or d.get("url") or "",
            id=d.get("id") or d.get("guid") or "",
            summary=d.get("summary"),
            ticker=(d.get("ticker") or "").strip() or None,
            raw=d,
        )


@dataclass
class ScoredItem:
    relevance: float
    sentiment: float
    tags: List[str]
    source_weight: float = 1.0

    @property
    def total(self) -> float:
        return self.relevance * self.source_weight


# --- Trade simulation data structures ---


@dataclass
class TradeSimConfig:
    """Configuration for trade simulation.

    Attributes
    ----------
    entry_offsets : list[int]
        Minutes after the alert timestamp at which to enter trades.
    hold_durations : list[int]
        Minutes to hold after entry (e.g. 30, 60, 120).
    slippage_bps : float
        Slippage applied on both entry and exit, expressed in basis points.
    """

    entry_offsets: List[int] = (0, 5, 10)  # immediate, 5m, 10m
    hold_durations: List[int] = (30, 60, 120)  # hold 30m, 1h, 2h
    slippage_bps: float = 5.0


@dataclass
class TradeSimResult:
    """Result of a single trade simulation.

    Stores the NewsItem, entry offset, hold duration and returns dict.
    """

    item: NewsItem
    entry_offset: int
    hold_duration: int
    returns: Dict[str, float]
