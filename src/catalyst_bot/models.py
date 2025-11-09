from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    from dateutil import parser as _dtparse  # type: ignore
except Exception:
    _dtparse = None


class NewsItem:
    """
    Canonical news atom used across analyzer/tradesim/backtests.
    Accepts either `ts_utc` or `ts` to specify the timestamp (as a
    datetime or ISO string), plus optional `title`, `canonical_url`/`link`,
    `source_host`, `source`, `summary`, `ticker`, and `id`. Unknown
    keyword arguments are ignored. The timestamp is always stored as
    an aware UTC datetime in `ts_utc`. `link` and `canonical_url`
    are treated as aliases. If `source_host` is not provided, it is
    derived from the URL. The `source` defaults to the provided
    source, then `source_host`, then "unknown".
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[no-redef]
        # parse timestamp
        ts_val = kwargs.pop("ts_utc", None) or kwargs.pop("ts", None)
        if ts_val is None:
            raise TypeError("NewsItem requires 'ts_utc' or 'ts' argument")
        if isinstance(ts_val, datetime):
            ts_dt = ts_val
        elif isinstance(ts_val, str):
            if _dtparse is None:
                raise TypeError("NewsItem requires dateutil for string timestamps")
            try:
                ts_dt = _dtparse.isoparse(ts_val)  # type: ignore[attr-defined]
            except Exception:
                # fallback: ISO parsing of Z -> +00:00
                ts_dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
        else:
            raise TypeError("NewsItem timestamp must be datetime or ISO string")
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)
        else:
            ts_dt = ts_dt.astimezone(timezone.utc)
        self.ts_utc: datetime = ts_dt

        self.title: str = kwargs.pop("title", "") or ""

        # link/canonical_url alias
        url = kwargs.pop("canonical_url", None) or kwargs.pop("link", None) or ""
        self.canonical_url: str = url
        self.link: str = url

        self.summary: Optional[str] = kwargs.pop("summary", None)

        tval = kwargs.pop("ticker", None)
        if isinstance(tval, str):
            self.ticker: Optional[str] = tval.strip().upper() or None
        else:
            self.ticker = None

        self.raw: Optional[Dict[str, Any]] = kwargs.pop("raw", None)

        id_val = kwargs.pop("id", None)
        self.id: str = id_val or self.link or self.title

        src_host_val = kwargs.pop("source_host", None)
        src_val = kwargs.pop("source", None)
        if src_host_val:
            try:
                self._source_host: Optional[str] = (
                    str(src_host_val).strip().lower() or None
                )
            except Exception:
                self._source_host = None
        else:
            host = None
            try:
                parsed = urlparse(self.link)
                host = parsed.hostname or parsed.netloc
            except Exception:
                host = None
            self._source_host = host.lower() if isinstance(host, str) and host else None
        if src_val:
            self.source: str = str(src_val)
        else:
            self.source = self._source_host or "unknown"

        # discard any remaining kwargs silently
        for _ in list(kwargs.keys()):
            kwargs.pop(_, None)

    @property
    def source_host(self) -> Optional[str]:
        return self._source_host

    @classmethod
    def from_feed_dict(cls, d: Dict[str, Any]) -> "NewsItem":
        """
        Build a NewsItem from a feed/event dictionary. Recognizes common
        timestamp keys ('ts', 'timestamp', 'ts_utc', 'published', 'time').
        Defaults to the current UTC time when no timestamp field is present.
        """
        ts_val = (
            d.get("ts")
            or d.get("timestamp")
            or d.get("ts_utc")
            or d.get("published")
            or d.get("time")
        )
        if not ts_val:
            ts_val = datetime.now(timezone.utc)
        return cls(
            ts_utc=ts_val,
            title=d.get("title") or "",
            canonical_url=d.get("canonical_url") or d.get("link") or d.get("url") or "",
            source_host=d.get("source") or d.get("source_host"),
            ticker=(d.get("ticker") or "").strip() or None,
            summary=d.get("summary"),
            raw=d,
        )


@dataclass
class ScoredItem:
    relevance: float
    sentiment: float
    tags: List[str]
    # Weight applied to relevance; historically tests passed the total score here.
    source_weight: float = 1.0
    # Explicit list of keyword/category hits. Tests rely on this field.
    keyword_hits: List[str] = None  # type: ignore
    # Enrichment tracking fields
    enriched: bool = False
    enrichment_timestamp: Optional[float] = None

    def __post_init__(self) -> None:
        # Ensure keyword_hits is an empty list if not provided
        if self.keyword_hits is None:
            self.keyword_hits = []

    @property
    def total(self) -> float:
        """
        Total score combining relevance and source weight.

        Historically this returned relevance * source_weight. Sentiment is not
        included in this property.
        """
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
