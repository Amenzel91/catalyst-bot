"""Pluggable news sentiment providers and aggregator for Catalyst‑Bot.

This module defines lightweight adapters for several external news‑based
sentiment services and a helper function to combine their outputs into a
single score and label.  Providers are enabled via feature flags and API
keys declared in the environment.  When no external provider returns a
score or the feature is disabled, the aggregator returns ``None`` and
callers should fall back to local sentiment.  All network errors are
swallowed to ensure the pipeline continues uninterrupted.

Each provider returns a tuple of ``(score, label, n_articles, details)``
where ``score`` is a float in the range ``[-1, 1]``, ``label`` is one
of ``"Bullish"``, ``"Neutral"`` or ``"Bearish"``, ``n_articles`` is the
number of articles considered and ``details`` is an optional mapping of
provider‑specific diagnostics.  The aggregator computes a weighted mean
using per‑provider weights defined in :class:`~catalyst_bot.config.Settings`.
When the total number of articles across providers is below
``sentiment_min_articles`` the combined sentiment is considered
insufficiently supported and ``None`` is returned.

Phase 1 of the Sentiment Source Patch focuses on the Alpha Vantage
``NEWS_SENTIMENT`` endpoint and includes placeholders for Marketaux,
StockNewsAPI and Finnhub.  Additional providers can be added by
implementing a fetch helper that returns the above tuple signature and
registering it in ``_PROVIDERS`` below.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from .config import get_settings
from .logging_utils import get_logger

# Initialise a module‑level logger.  Use a short name to avoid deep
# hierarchies in JSON logs.
log = get_logger("sentiment_sources")


def _safe_float(val: Any) -> Optional[float]:
    """Attempt to convert ``val`` to a float.  Return ``None`` when not
    convertible or out of expected range.  Accepts values like strings or
    numbers and ignores exceptions quietly.
    """
    if val is None:
        return None
    try:
        f = float(val)
        # Clamp extreme values into [-1, 1] to avoid skew from mis‑scaled
        # inputs.  Some APIs return scores outside the expected range.
        if f > 1.0:
            return 1.0
        if f < -1.0:
            return -1.0
        return f
    except Exception:
        return None


def _label_from_score(score: float) -> str:
    """Map a continuous sentiment score to a discrete label.

    Uses simple cut‑offs: scores ≥ 0.05 → ``"Bullish"``, scores ≤ −0.05
    → ``"Bearish"``, otherwise ``"Neutral"``.  The thresholds are
    intentionally symmetric around zero to avoid misclassifying mild
    fluctuations.
    """
    try:
        s = float(score)
    except Exception:
        s = 0.0
    if s >= 0.05:
        return "Bullish"
    if s <= -0.05:
        return "Bearish"
    return "Neutral"


def _majority_label(labels: Iterable[str]) -> str:
    """Return the most common label in ``labels`` or ``Neutral`` when tied.
    Ignores falsy entries.  When no labels are provided, returns
    ``Neutral``.
    """
    counts: Dict[str, int] = {}
    for lbl in labels:
        if not lbl:
            continue
        counts[lbl] = counts.get(lbl, 0) + 1
    if not counts:
        return "Neutral"
    # Return the label with the highest count; in case of ties,
    # ``sorted`` guarantees deterministic order.
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _fetch_alpha_sentiment(
    ticker: str, api_key: str
) -> Optional[Tuple[float, str, int, Dict[str, Any]]]:
    """Fetch sentiment from Alpha Vantage's NEWS_SENTIMENT endpoint.

    Returns a tuple (score, label, n_articles, details) or ``None`` on
    error.  Scores are averaged over the ``ticker_sentiment`` scores for
    the requested ticker when available, or fall back to
    ``overall_sentiment_score``.
    """
    if not api_key or not ticker:
        return None
    # Compose the query.  We request the latest articles and limit to a
    # modest number to avoid hitting the API rate limit.  Alpha Vantage
    # supports up to 200 items, but 50 is sufficient for sentiment.
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker.upper(),
        "sort": "LATEST",
        "limit": "50",
        "apikey": api_key,
    }
    try:
        resp = requests.get(
            "https://www.alphavantage.co/query", params=params, timeout=8
        )
    except Exception as e:
        log.debug("alpha_sentiment_request error=%s", e.__class__.__name__)
        return None
    # Handle non‑success HTTP responses gracefully; treat 401/429 as a
    # transient failure and do not propagate exceptions.  We do not retry
    # here as the bot loops frequently and subsequent cycles will reattempt.
    if resp.status_code != 200:
        if resp.status_code in (401, 403, 429):
            log.debug(
                "alpha_sentiment_http status=%s ticker=%s", resp.status_code, ticker
            )
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    feed = data.get("feed") or []
    scores: List[float] = []
    labels: List[str] = []
    for entry in feed:
        # Each entry contains either a ticker_sentiment array or overall values.
        try:
            # ticker_sentiment is a list of dicts keyed by ticker symbol.  We
            # pick the first matching record for our ticker.
            ts_list = entry.get("ticker_sentiment") or []
            ts_score = None
            ts_label = None
            for ts in ts_list:
                try:
                    sym = (ts.get("ticker") or ts.get("ticker_symbol") or "").upper()
                except Exception:
                    sym = ""
                if sym == ticker.upper():
                    ts_score = _safe_float(ts.get("ticker_sentiment_score"))
                    ts_label = ts.get("ticker_sentiment_label") or ts.get(
                        "ticker_sentiment_code"
                    )
                    break
            score = ts_score
            label = ts_label
            # Fall back to overall sentiment when ticker_sentiment is absent
            if score is None:
                score = _safe_float(entry.get("overall_sentiment_score"))
                label = entry.get("overall_sentiment_label")
            if score is None:
                continue
            scores.append(score)
            labels.append(label or _label_from_score(score))
        except Exception:
            continue
    if not scores:
        return None
    avg = sum(scores) / float(len(scores))
    final_label = _majority_label(labels) or _label_from_score(avg)
    details: Dict[str, Any] = {
        "n_articles": len(scores),
        "provider": "alpha",
    }
    return avg, final_label, len(scores), details


def _fetch_marketaux_sentiment(
    ticker: str, api_key: str
) -> Optional[Tuple[float, str, int, Dict[str, Any]]]:
    """Fetch sentiment for ``ticker`` using the Marketaux API.

    The endpoint returns a list of news articles with entity sentiment scores
    under ``data > entities > sentiment_score``.  When no scores are
    present or an error occurs, ``None`` is returned.
    """
    if not api_key or not ticker:
        return None
    base_url = "https://api.marketaux.com/v1/news/all"
    params = {
        "symbols": ticker.upper(),
        "filter_entities": "true",
        "language": "en",
        "limit": "50",
        "api_token": api_key,
    }
    try:
        resp = requests.get(base_url, params=params, timeout=8)
    except Exception as e:
        log.debug("marketaux_sentiment_request error=%s", e.__class__.__name__)
        return None
    if resp.status_code != 200:
        if resp.status_code in (401, 403, 429):
            log.debug(
                "marketaux_sentiment_http status=%s ticker=%s", resp.status_code, ticker
            )
        return None
    try:
        data = resp.json()  # type: ignore[call-arg]
    except Exception:
        return None
    articles = data.get("data") or []
    scores: List[float] = []
    labels: List[str] = []
    for art in articles:
        ents = art.get("entities") or []
        for ent in ents:
            try:
                sym = (ent.get("symbol") or ent.get("ticker") or "").upper()
            except Exception:
                sym = ""
            if sym != ticker.upper():
                continue
            score = _safe_float(ent.get("sentiment_score"))
            if score is None:
                continue
            scores.append(score)
            labels.append(_label_from_score(score))
    if not scores:
        return None
    avg = sum(scores) / float(len(scores))
    final_label = _majority_label(labels) or _label_from_score(avg)
    details = {
        "n_articles": len(scores),
        "provider": "marketaux",
    }
    return avg, final_label, len(scores), details


def _fetch_stocknews_sentiment(
    ticker: str, api_key: str
) -> Optional[Tuple[float, str, int, Dict[str, Any]]]:
    """Fetch sentiment from StockNewsAPI.

    This helper attempts to call the StockNewsAPI endpoint and parse a
    sentiment score from returned items.  Because the public API does not
    document a formal sentiment field, we search for numeric fields named
    ``sentiment``, ``sentiment_score`` or similar on each article.  When
    no scores are found, ``None`` is returned.
    """
    if not api_key or not ticker:
        return None
    # Construct a simple request.  StockNewsAPI exposes multiple
    # categories/endpoints; here we hit the generic query with tickers.
    base_url = "https://stocknewsapi.com/api/v1"
    params = {
        "tickers": ticker.upper(),
        "items": "50",
        "token": api_key,
    }
    try:
        resp = requests.get(base_url, params=params, timeout=8)
    except Exception as e:
        log.debug("stocknews_sentiment_request error=%s", e.__class__.__name__)
        return None
    if resp.status_code != 200:
        if resp.status_code in (401, 403, 429):
            log.debug(
                "stocknews_sentiment_http status=%s ticker=%s", resp.status_code, ticker
            )
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    # Many StockNewsAPI responses nest articles under a 'data' key; fall back
    # to 'articles' when absent.
    items = data.get("data") or data.get("articles") or []
    scores: List[float] = []
    labels: List[str] = []
    for art in items:
        # Search a handful of common keys for sentiment values.
        score = None
        for key in ("sentiment", "sentiment_score", "sentimentScore", "score"):
            if key in art:
                score = _safe_float(art.get(key))
                if score is not None:
                    break
        if score is None:
            # Some APIs embed sentiment under nested structures; scan values.
            try:
                for v in art.values():
                    if isinstance(v, (int, float)):
                        # Limit to plausible ranges
                        f = _safe_float(v)
                        if f is not None:
                            score = f
                            break
                    elif isinstance(v, dict):
                        for vv in v.values():
                            f = _safe_float(vv)
                            if f is not None:
                                score = f
                                break
                    if score is not None:
                        break
            except Exception:
                pass
        if score is None:
            continue
        scores.append(score)
        labels.append(_label_from_score(score))
    if not scores:
        return None
    avg = sum(scores) / float(len(scores))
    final_label = _majority_label(labels) or _label_from_score(avg)
    details = {
        "n_articles": len(scores),
        "provider": "stocknews",
    }
    return avg, final_label, len(scores), details


def _fetch_finnhub_sentiment(
    ticker: str, api_key: str
) -> Optional[Tuple[float, str, int, Dict[str, Any]]]:
    """Fetch sentiment from Finnhub.

    Finnhub provides a news sentiment endpoint keyed by symbol.  The
    response contains aggregated bullish/bearish counts and sentiment
    score.  We parse ``sentimentScore`` or derive a score from the
    bullish/bearish percentages.  When the API key is blank or an error
    occurs, ``None`` is returned.
    """
    if not api_key or not ticker:
        return None
    base_url = "https://finnhub.io/api/v1/news-sentiment"
    params = {
        "symbol": ticker.upper(),
        "token": api_key,
    }
    try:
        resp = requests.get(base_url, params=params, timeout=8)
    except Exception as e:
        log.debug("finnhub_sentiment_request error=%s", e.__class__.__name__)
        return None
    if resp.status_code != 200:
        if resp.status_code in (401, 403, 429):
            log.debug(
                "finnhub_sentiment_http status=%s ticker=%s", resp.status_code, ticker
            )
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    # The API returns keys like 'sentiment', 'buzz' and 'companyNewsSentiment'.
    score = None
    # Some versions expose an overall sentimentScore
    score = _safe_float(data.get("sentimentScore") or data.get("score"))
    if score is None:
        # Derive from bullish/bearish percentages when available
        try:
            bullish = float(data.get("bullishPercent"))
            bearish = float(data.get("bearishPercent"))
            # Convert percentage difference into a symmetric [-1, 1] score
            if bullish + bearish > 0:
                score = (bullish - bearish) / (bullish + bearish)
        except Exception:
            pass
    if score is None:
        return None
    label = _label_from_score(score)
    details = {
        "n_articles": 1,
        "provider": "finnhub",
    }
    return score, label, 1, details


# Mapping of provider identifiers to their fetch functions.
#
# NEWS/SENTIMENT PROVIDER PRIORITY STRATEGY:
# ===========================================
# The order of entries reflects the preferred sequence in which providers
# will be queried for news sentiment data:
#
# 1. PRIMARY: Finnhub (FREE tier, 60 calls/min)
#    - Excellent news coverage and sentiment analysis
#    - Company news, analyst ratings, earnings calendars
#    - No cost, generous rate limits
#
# 2. BACKUP: Alpha Vantage (uses existing subscription)
#    - News sentiment endpoint available
#    - Already subscribed for price data
#
# 3. BACKUP: Marketaux (requires separate API key)
# 4. BACKUP: StockNewsAPI (requires separate API key)
#
# Additional providers can be appended here in future patches.
_PROVIDERS = {
    "finnhub": _fetch_finnhub_sentiment,  # PRIMARY for news/sentiment
    "alpha": _fetch_alpha_sentiment,  # BACKUP (existing subscription)
    "marketaux": _fetch_marketaux_sentiment,  # BACKUP (optional)
    "stocknews": _fetch_stocknews_sentiment,  # BACKUP (optional)
}


def get_combined_sentiment_for_ticker(
    ticker: str, headlines: Optional[List[str]] = None
) -> Optional[Tuple[float, str, Dict[str, Any]]]:
    """Return an aggregated sentiment score, label and per‑provider details.

    NEWS/SENTIMENT PROVIDER PRIORITY STRATEGY:
    ==========================================
    This function implements a prioritized fallback chain for news sentiment:

    1. PRIMARY: Finnhub (FREE tier, 60 calls/min)
       - Excellent news coverage and analyst sentiment
       - Company news, earnings calendars, upgrades/downgrades
       - No cost, generous rate limits
       - Requires: FEATURE_FINNHUB_SENTIMENT=1, FINNHUB_API_KEY

    2. BACKUP: Alpha Vantage News Sentiment
       - Uses existing subscription (already paying for price data)
       - Falls back when Finnhub unavailable
       - Requires: FEATURE_ALPHA_SENTIMENT=1, ALPHAVANTAGE_API_KEY

    3. BACKUP: Marketaux (optional, requires separate API key)
    4. BACKUP: StockNewsAPI (optional, requires separate API key)

    The helper consults each enabled provider in turn.  Providers are
    enabled based on feature flags and the presence of API keys.  The
    returned tuple has the form ``(score, label, details)`` where
    ``score`` is a float (or ``None``), ``label`` is one of
    ``"Bullish"``, ``"Neutral"`` or ``"Bearish"``, and ``details`` is a
    mapping keyed by provider name containing the individual results.  When
    no provider returns a score or the total number of contributing
    articles is below ``sentiment_min_articles``, the function returns
    ``None``.

    Provider usage is logged with role designation (PRIMARY/BACKUP) for
    debugging and monitoring.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol to fetch sentiment for
    headlines : list of str, optional
        Reserved for future use (e.g. for providers that accept raw text
        rather than a ticker). Currently ignored.

    Returns
    -------
    tuple of (float, str, dict) or None
        (score, label, provider_details) where score is in range [-1, 1],
        label is one of "Bullish"/"Neutral"/"Bearish", and provider_details
        contains individual provider results. Returns None if insufficient data.
    """
    if not ticker:
        return None
    # Load runtime settings lazily to allow env overrides during tests.
    try:
        settings = get_settings()
    except Exception:
        settings = None
    # Check global feature flag
    if settings:
        enabled = getattr(settings, "feature_news_sentiment", False)
    else:
        enabled = os.getenv("FEATURE_NEWS_SENTIMENT", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if not enabled:
        return None
    ticker_upper = ticker.upper().strip()
    # Determine active providers based on per‑provider flags and keys
    provider_results: Dict[str, Dict[str, Any]] = {}
    total_articles = 0
    weighted_sum = 0.0
    total_weight = 0.0
    # Provider iteration order; adhere to keys in _PROVIDERS
    for name, fetch_fn in _PROVIDERS.items():
        # Determine feature flag name and weight/key attributes on settings
        flag_attr = f"feature_{name}_sentiment"
        weight_attr = f"sentiment_weight_{name}"
        key_attr = f"{name}_api_key"
        # Finnhub uses finnhub_api_key; handle special case
        if name == "alpha":
            # Alpha uses existing alphavantage_api_key; weight attr still correct
            key_val = (
                getattr(settings, "alphavantage_api_key", "")
                if settings
                else os.getenv("ALPHAVANTAGE_API_KEY", "")
            )
        else:
            key_val = (
                getattr(settings, key_attr, "")
                if settings
                else os.getenv(key_attr.upper(), "")
            )
        # Flag gating; default false when missing
        flag_val = (
            getattr(settings, flag_attr, False)
            if settings
            else os.getenv(flag_attr.upper(), "0").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        if not flag_val:
            continue
        if not key_val:
            continue
        try:
            # Reload the provider function from globals to ensure monkeypatched
            # functions are invoked.  `_PROVIDERS` is initialised at module
            # import time and holds references to the original fetchers; when
            # tests monkeypatch the fetch helpers, the mapping still points
            # at the old functions.  To accommodate this, lookup the current
            # implementation by name via globals().  Fallback to the
            # original mapping when not found.
            impl = globals().get(getattr(fetch_fn, "__name__", ""), fetch_fn)
            res = impl(ticker_upper, key_val)  # type: ignore[arg-type]
        except Exception:
            res = None
        if not res:
            continue
        score, label, n_articles, details = res
        if n_articles <= 0:
            continue
        provider_results[name] = {
            "score": score,
            "label": label,
            "n_articles": n_articles,
        }
        # Log provider usage with role designation
        role = "PRIMARY" if name == "finnhub" else "BACKUP"
        log.info(
            "sentiment_provider provider=%s ticker=%s role=%s score=%.2f label=%s n_articles=%d",
            name,
            ticker_upper,
            role,
            score,
            label,
            n_articles,
        )
        total_articles += n_articles
        try:
            weight = (
                float(getattr(settings, weight_attr, 0.0))
                if settings
                else float(os.getenv(weight_attr.upper(), "0") or 0.0)
            )
        except Exception:
            weight = 0.0
        weighted_sum += score * weight
        total_weight += weight

    # ---------------------------------------------------------------
    # Include SEC filings sentiment when enabled
    #
    # When the SEC digester feature is on and a lookback window exists,
    # incorporate the aggregated SEC score into the combined sentiment.
    # The weight is configured via SENTIMENT_WEIGHT_SEC.  We use the
    # number of recent filings as the article count.  Errors are
    # swallowed to avoid disrupting the main sentiment pipeline.
    try:
        from .sec_digester import (
            get_combined_sentiment as _get_sec_sent,  # type: ignore
        )
        from .sec_digester import get_recent_filings as _get_sec_recs
    except Exception:
        _get_sec_sent = None  # type: ignore
        _get_sec_recs = None  # type: ignore
    try:
        sec_enabled = False
        if settings:
            sec_enabled = getattr(settings, "feature_sec_digester", False)
        else:
            sec_enabled = os.getenv("FEATURE_SEC_DIGESTER", "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if sec_enabled and _get_sec_sent and _get_sec_recs:
            sec_score, sec_label = _get_sec_sent(ticker_upper)
            if sec_score is not None:
                try:
                    n_recs = len(_get_sec_recs(ticker_upper) or [])
                except Exception:
                    n_recs = 0
                # Only include when at least one filing exists
                if n_recs > 0:
                    provider_results["sec"] = {
                        "score": sec_score,
                        "label": sec_label,
                        "n_articles": n_recs,
                    }
                    try:
                        w_sec = float(
                            getattr(settings, "sentiment_weight_sec", 0.0)
                            if settings
                            else os.getenv("SENTIMENT_WEIGHT_SEC", "0") or 0.0
                        )
                    except Exception:
                        w_sec = 0.0
                    if w_sec and w_sec != 0.0:
                        weighted_sum += sec_score * w_sec
                        total_weight += w_sec
                        total_articles += n_recs
    except Exception:
        pass

    # ---------------------------------------------------------------
    # Include earnings sentiment when enabled
    #
    # The earnings module supplies a single score per ticker derived from
    # the most recent EPS surprise (past earnings) or 0.0 for upcoming
    # reports.  We treat each earnings sentiment as one “article” for
    # purposes of the minimum article threshold.  Errors are swallowed
    # quietly; the pipeline continues even when the provider fails.
    try:
        from .earnings import get_earnings_sentiment as _get_earn_sent  # type: ignore
    except Exception:
        _get_earn_sent = None  # type: ignore
    try:
        earn_enabled = False
        if settings:
            earn_enabled = getattr(settings, "feature_earnings_alerts", False)
        else:
            earn_enabled = os.getenv(
                "FEATURE_EARNINGS_ALERTS", "0"
            ).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if earn_enabled and _get_earn_sent is not None:
            earn_score, earn_label, earn_details = _get_earn_sent(ticker_upper)
            if earn_score is not None:
                # treat as single article
                provider_results["earnings"] = {
                    "score": earn_score,
                    "label": earn_label,
                    "n_articles": 1,
                }
                try:
                    w_earn = float(
                        getattr(settings, "sentiment_weight_earnings", 0.0)
                        if settings
                        else os.getenv("SENTIMENT_WEIGHT_EARNINGS", "0") or 0.0
                    )
                except Exception:
                    w_earn = 0.0
                if w_earn and w_earn != 0.0:
                    weighted_sum += earn_score * w_earn
                    total_weight += w_earn
                    total_articles += 1
    except Exception:
        pass
    # Insufficient data
    min_articles = (
        getattr(settings, "sentiment_min_articles", 0)
        if settings
        else int(os.getenv("SENTIMENT_MIN_ARTICLES", "0") or 0)
    )
    if total_articles < max(1, min_articles) or total_weight <= 0.0:
        return None
    combined_score = weighted_sum / total_weight
    combined_label = _label_from_score(combined_score)
    return combined_score, combined_label, provider_results
