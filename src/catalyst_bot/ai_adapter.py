from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

# Public interface ------------------------------------------------------------


@dataclass(frozen=True)
class AISentiment:
    label: str  # "positive" | "neutral" | "negative"
    score: float  # in [-1.0, 1.0]


@dataclass(frozen=True)
class AIEnrichment:
    ai_sentiment: Optional[AISentiment] = None
    ai_tags: Optional[List[str]] = None
    proposed_keywords: Optional[List[Dict]] = None  # [{category, weight, phrases: []}]


class AIAdapter(Protocol):
    def enrich(self, title: str, body: str | None = None) -> AIEnrichment: ...


# Backends --------------------------------------------------------------------


class _NoneAdapter:
    def enrich(self, title: str, body: str | None = None) -> AIEnrichment:
        return AIEnrichment()


class _MockAdapter:
    """
    Deterministic heuristic "AI" for tests / offline runs.
    - Looks for lightweight biotech/FDA/upgrade cues
    - Emits neutral defaults otherwise
    Never calls external services.
    """

    POS = {"beats", "approved", "approval", "upgrade", "raises", "surge", "record"}
    NEG = {"delay", "halts", "reject", "rejects", "fraud", "down", "misses", "recall"}
    FDA = {"fda", "phase 3", "phase iii", "pdufa"}

    def enrich(self, title: str, body: str | None = None) -> AIEnrichment:
        text = f"{title} {(body or '')}".lower()
        tags: List[str] = []
        label = "neutral"
        score = 0.0
        if any(tok in text for tok in self.FDA):
            tags.append("fda")
        if any(tok in text for tok in self.POS):
            label, score = "positive", 0.4
        if any(tok in text for tok in self.NEG):
            # let negative override to be conservative
            label, score = "negative", -0.4
        return AIEnrichment(
            ai_sentiment=AISentiment(label=label, score=score),
            ai_tags=sorted(set(tags)) or None,
            proposed_keywords=None,
        )


# Factory ---------------------------------------------------------------------


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on"}


def get_adapter() -> AIAdapter:
    """
    Choose adapter by env. Defaults to no-op:
      AI_BACKEND=none|mock
    Future: support 'chatgpt'/'gemini' backends; secrets must never be logged.
    """
    name = (os.getenv("AI_BACKEND") or "none").strip().lower()
    if name == "mock":
        return _MockAdapter()
    return _NoneAdapter()
