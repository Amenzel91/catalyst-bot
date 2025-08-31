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
