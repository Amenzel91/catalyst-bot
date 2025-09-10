"""Classification and scoring of news items.

The classifier assigns a numerical score to each news item based on a
combination of sentiment analysis and keyword matches. Dynamic
adjustments derived from the analyzer are applied to keyword
categories to improve precision over time. The result is a
:class:`~catalyst_bot.models.ScoredItem` which encapsulates the
underlying news item along with its sentiment, keyword hits, and total
score.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .ai_adapter import AIEnrichment, get_adapter

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except Exception:  # pragma: no cover
    SentimentIntensityAnalyzer = None  # type: ignore

from .config import get_settings
from .models import NewsItem, ScoredItem

# Initialize a single VADER sentiment analyzer instance if available
if SentimentIntensityAnalyzer is not None:
    _vader = SentimentIntensityAnalyzer()
else:
    _vader = None  # type: ignore


def load_dynamic_keyword_weights(path: Optional[Path] = None) -> Dict[str, float]:
    """Load dynamic keyword weights from a JSON file.

    Parameters
    ----------
    path : Optional[Path]
        Path to the JSON file containing keyword statistics. If
        ``None``, defaults to ``data/analyzer/keyword_stats.json`` in
        the project directory.

    Returns
    -------
    Dict[str, float]
        Mapping of keyword category → weight. Falls back to empty dict
        if the file does not exist or is invalid.
    """
    settings = get_settings()
    if path is None:
        path = settings.data_dir / "analyzer" / "keyword_stats.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        weights = data.get("weights", {})
        # Ensure keys are lowercase strings and values are floats
        return {str(k).lower(): float(v) for k, v in weights.items()}
    except Exception:
        return {}


def classify(
    item: NewsItem, keyword_weights: Optional[Dict[str, float]] = None
) -> ScoredItem:
    """Classify a news item and return a scored representation.

    Combines sentiment, keyword-category hits (with analyzer-provided
    dynamic weights when available), and source weighting.
    """
    settings = get_settings()
    keyword_categories = settings.keyword_categories

    # Sentiment (graceful if VADER unavailable)
    if _vader is not None:
        sentiment_scores = _vader.polarity_scores(item.title)
        sentiment = float(sentiment_scores.get("compound", 0.0))
    else:
        sentiment = 0.0

    # Keyword hits & weights (prefer analyzer dynamic weights)
    title_lower = (item.title or "").lower()
    hits: List[str] = []
    total_keyword_score = 0.0
    dynamic_weights = keyword_weights or load_dynamic_keyword_weights()

    for category, keywords in keyword_categories.items():
        for kw in keywords:
            if kw in title_lower:
                hits.append(category)
                weight = float(
                    dynamic_weights.get(category, settings.keyword_default_weight)
                )
                total_keyword_score += weight
                # Count at most one hit per category
                break

    # Source weight (wrapped to satisfy flake8 line length)
    src_host = (item.source_host or "").lower()
    source_weight = settings.rss_sources.get(src_host, 1.0)

    # Aggregate relevance (keep simple/deterministic)
    relevance = float(total_keyword_score) * float(source_weight)

    # Total score: simple combination that is deterministic and monotonic
    total_score = relevance + sentiment

    # Build ScoredItem first (keep existing behavior), then optionally enrich.
    # Use keyword arguments to ensure fields map correctly and populate
    # keyword_hits explicitly so tests can introspect matched categories.
    scored: ScoredItem | dict
    try:
        scored = ScoredItem(
            relevance=relevance,
            sentiment=sentiment,
            tags=hits,
            source_weight=total_score,
            keyword_hits=hits.copy(),
        )
    except TypeError:
        # Older builds may not accept keyword_hits; fall back to positional args
        try:
            scored = ScoredItem(relevance, sentiment, hits, total_score)
        except Exception:
            # Last resort so pipeline doesn’t die; downstream runner handles dicts too
            scored = {
                "relevance": relevance,
                "sentiment": sentiment,
                "keywords": hits,
                "score": total_score,
            }

    # --- Optional AI enrichment (noop by default via AI_BACKEND=none) -------
    # Adds 'ai_sentiment' into .extra and merges 'ai_tags' into tags.
    try:
        adapter = get_adapter()
        enr: AIEnrichment = adapter.enrich(item.title or "", None)

        # Helper accessors for object-or-dict compatibility
        def _get_tags(obj):
            if isinstance(obj, dict):
                # prefer 'tags', fall back to 'keywords'
                return list(obj.get("tags") or obj.get("keywords") or [])
            return list(getattr(obj, "tags", []) or [])

        def _set_tags(obj, new_tags: List[str]):
            if isinstance(obj, dict):
                obj["tags"] = new_tags
            else:
                try:
                    setattr(obj, "tags", new_tags)
                except Exception:
                    pass

        def _get_extra(obj) -> dict:
            if isinstance(obj, dict):
                obj.setdefault("extra", {})
                return obj["extra"]
            extra = getattr(obj, "extra", None)
            if extra is None:
                try:
                    setattr(obj, "extra", {})
                    extra = getattr(obj, "extra", {})
                except Exception:
                    extra = {}
            return extra

        # Merge tags from AI (deduped)
        if enr.ai_tags:
            cur = set(_get_tags(scored))
            cur.update(enr.ai_tags)
            _set_tags(scored, sorted(cur))

        # Record AI sentiment in 'extra' without overriding numeric 'sentiment'
        if enr.ai_sentiment:
            extra = _get_extra(scored)
            extra["ai_sentiment"] = {
                "label": enr.ai_sentiment.label,
                "score": float(enr.ai_sentiment.score),
            }
    except Exception:
        # Never let enrichment break classification
        pass

    return scored
