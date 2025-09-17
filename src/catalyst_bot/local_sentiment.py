"""Local sentiment analysis fallback for Catalyst‑Bot.

This module implements a lightweight sentiment analyser that can be used when
external feeds (e.g. FMP sentiment) are unavailable.  The primary helper,
``score_text()``, attempts to compute a sentiment score in the range
[-1.0, 1.0] for a given headline.  When the VADER sentiment analyser is
available, it is used to obtain a more nuanced polarity score.  If VADER
cannot be imported, a simple keyword lexicon approach is used as a
fallback.

The ``attach_local_sentiment`` function can be used to augment a list of
event dictionaries in‑place.  It looks up each item’s title under a
configurable key (default ``title``) and attaches two new keys:

* ``sentiment_local`` — a float in the range [-1.0, 1.0] representing the
  estimated sentiment of the text.
* ``sentiment_local_label`` — one of ``"Bullish"``, ``"Neutral"`` or
  ``"Bearish"`` based on simple thresholds.

The thresholds and lexicon were selected to provide a reasonable proxy
without introducing heavy dependencies.  You can adjust the keyword lists
or sentiment cut‑offs if desired.
"""

from __future__ import annotations

from typing import Iterable, MutableMapping, Optional

__all__ = ["score_text", "attach_local_sentiment"]


def _simple_lexicon_score(text: str) -> float:
    """Compute a rudimentary sentiment score based on keyword matches.

    The algorithm scans the input for known positive and negative words and
    returns a score proportional to the difference between positive and
    negative counts.  Scores are normalised to the range [-1, 1].  This
    helper is only used when the VADER analyser is unavailable.
    """
    if not text:
        return 0.0
    # Define a minimal lexicon of bullish/bearish words.  The lists are not
    # exhaustive but cover common sentiment cues found in headlines.
    positives = {
        "beat",
        "surge",
        "up",
        "soars",
        "gain",
        "gains",
        "positive",
        "bullish",
        "record",
        "outperform",
        "profit",
    }
    negatives = {
        "miss",
        "fall",
        "drop",
        "down",
        "loss",
        "losses",
        "negative",
        "bearish",
        "decline",
        "warns",
        "warning",
    }
    t = (text or "").lower()
    pos_hits = sum(1 for w in positives if w in t)
    neg_hits = sum(1 for w in negatives if w in t)
    if pos_hits == 0 and neg_hits == 0:
        return 0.0
    score = float(pos_hits - neg_hits) / float(pos_hits + neg_hits)
    # Clamp to [-1, 1]
    return max(-1.0, min(1.0, score))


def score_text(text: str) -> float:
    """Return a sentiment polarity score in the range [-1, 1] for ``text``.

    Uses the VADER sentiment analyser when available.  If VADER is not
    installed, a keyword lexicon fallback is used.  Errors are swallowed
    and treated as neutral.
    """
    if not text:
        return 0.0
    # Try VADER first; catch all exceptions from the import and call.
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        analyzer = SentimentIntensityAnalyzer()
        s = analyzer.polarity_scores(text or "")
        return float(s.get("compound", 0.0))
    except Exception:
        # Fallback: simple lexicon approach
        try:
            return _simple_lexicon_score(text)
        except Exception:
            return 0.0


def _label_from_score(score: float) -> str:
    """Return a discrete sentiment label for a continuous score."""
    try:
        s = float(score)
    except Exception:
        s = 0.0
    if s >= 0.05:
        return "Bullish"
    if s <= -0.05:
        return "Bearish"
    return "Neutral"


def attach_local_sentiment(
    items: Iterable[MutableMapping[str, object]], text_key: str = "title"
) -> None:
    """Attach local sentiment to each mapping in ``items`` in‑place.

    For every item that has a non‑empty ``text_key`` value, compute a
    sentiment score using :func:`score_text` and add two new keys:

    * ``sentiment_local`` — float polarity score in [-1, 1]
    * ``sentiment_local_label`` — discrete label (Bullish/Neutral/Bearish)

    Any exceptions are caught and ignored; the function continues for the
    remaining items.
    """
    for item in items:
        try:
            text_obj: Optional[str] = item.get(text_key)  # type: ignore
        except Exception:
            text_obj = None
        if not text_obj:
            # Leave missing or blank titles untouched
            continue
        try:
            score = score_text(str(text_obj))
            label = _label_from_score(score)
            # Attach into the mapping; avoid overwriting existing keys if present
            if "sentiment_local" not in item:
                item["sentiment_local"] = score  # type: ignore
            if "sentiment_local_label" not in item:
                item["sentiment_local_label"] = label  # type: ignore
        except Exception:
            # Do not let a single failure abort other attachments
            continue
