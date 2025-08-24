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
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def classify(item: NewsItem, keyword_weights: Optional[Dict[str, float]] = None) -> ScoredItem:
    """Classify a news item and return a scored representation.

    The scoring formula combines sentiment, keyword hits, and source
    weighting into a single metric used for ranking. Category weights
    may be dynamically adjusted by the analyzer via ``keyword_weights``.

    Parameters
    ----------
    item : NewsItem
        The news item to score.
    keyword_weights : Optional[Dict[str, float]]
        Optional dynamic weights by category. If provided, these
        override the static defaults from configuration.
    """
    settings = get_settings()
    keyword_categories = settings.keyword_categories
    # Compute sentiment using VADER
    if _vader is not None:
        sentiment_scores = _vader.polarity_scores(item.title)
        sentiment = sentiment_scores.get("compound", 0.0)
    else:
        sentiment = 0.0

    # Determine keyword hits and accumulate weight
    title_lower = item.title.lower()
    hits: List[str] = []
    total_keyword_score = 0.0
    dynamic_weights = keyword_weights or load_dynamic_keyword_weights()
    for category, keywords in keyword_categories.items():
        for kw in keywords:
            if kw in title_lower:
                hits.append(category)
                # Use dynamic weight if available, else default
                weight = dynamic_weights.get(category, settings.keyword_default_weight)
                total_keyword_score += weight
                break  # Count each category at most once

    # Compute source weight
    source_weight = settings.rss_sources.get(item.source_host.lower(), 1.0)

    # Aggregate the final score. We use a simple linear combination:
    #   total_score = sentiment_weight * sentiment + keyword_weight * total_keyword_score + source_weight
    # Sentiment is scaled to [0,1] by mapping [-1,1] → [0,1]
    sentiment_norm = (sentiment + 1.0) / 2.0
    # We give keyword_score a higher influence because catalyst keywords are more
    # predictive than sentiment alone.
    total_score = 0.4 * sentiment_norm + 0.5 * total_keyword_score + 0.1 * source_weight

    return ScoredItem(
        item=item,
        sentiment=sentiment,
        keyword_hits=hits,
        source_weight=source_weight,
        total_score=total_score,
    )