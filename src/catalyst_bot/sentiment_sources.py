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


def _fetch_stocktwits_sentiment(
    ticker: str, api_key: str
) -> Optional[Tuple[float, str, int, Dict[str, Any]]]:
    """Fetch social sentiment from StockTwits.

    StockTwits provides real-time social sentiment from its investor community.
    The API returns recent messages (tweets) for a ticker with explicit
    bullish/bearish labels when authors tag their sentiment. We aggregate
    these labeled messages into a composite score.

    Free tier: 200 calls/hour, no API key required (but recommended for
    higher limits).

    Returns
    -------
    tuple or None
        (score, label, n_messages, details) where score is derived from
        bullish/bearish message ratio, or None on error
    """
    if not ticker:
        return None
    # StockTwits API endpoint for symbol stream
    base_url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker.upper()}.json"
    headers = {}
    # API key is optional but provides higher rate limits when present
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.get(base_url, headers=headers, timeout=8)
    except Exception as e:
        log.debug("stocktwits_sentiment_request error=%s", e.__class__.__name__)
        return None

    if resp.status_code != 200:
        if resp.status_code in (401, 403, 429):
            log.debug(
                "stocktwits_sentiment_http status=%s ticker=%s",
                resp.status_code,
                ticker,
            )
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    messages = data.get("messages") or []
    if not messages:
        return None

    # Count bullish/bearish messages
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0

    for msg in messages:
        entities = msg.get("entities") or {}
        sentiment_obj = entities.get("sentiment")
        if not sentiment_obj:
            neutral_count += 1
            continue

        basic_sentiment = sentiment_obj.get("basic")
        if basic_sentiment == "Bullish":
            bullish_count += 1
        elif basic_sentiment == "Bearish":
            bearish_count += 1
        else:
            neutral_count += 1

    total_labeled = bullish_count + bearish_count
    if total_labeled == 0:
        # No sentiment labels available, treat as neutral
        return 0.0, "Neutral", len(messages), {"provider": "stocktwits"}

    # Calculate sentiment score from bullish/bearish ratio
    # Score range: [-1.0, 1.0]
    score = (bullish_count - bearish_count) / total_labeled
    label = _label_from_score(score)

    details = {
        "n_articles": len(messages),
        "provider": "stocktwits",
        "bullish": bullish_count,
        "bearish": bearish_count,
        "neutral": neutral_count,
    }

    log.debug(
        "stocktwits_sentiment ticker=%s bullish=%d bearish=%d neutral=%d score=%.2f",
        ticker.upper(),
        bullish_count,
        bearish_count,
        neutral_count,
        score,
    )

    return score, label, len(messages), details


def _fetch_reddit_sentiment(
    ticker: str, api_key: str
) -> Optional[Tuple[float, str, int, Dict[str, Any]]]:
    """Fetch social sentiment from Reddit using PRAW library.

    Searches relevant subreddits (wallstreetbets, stocks, pennystocks) for
    recent mentions of the ticker and analyzes sentiment using VADER.
    Reddit's API requires authentication via client_id:client_secret format
    in the api_key parameter.

    Free tier: 60 requests/minute per OAuth client

    Parameters
    ----------
    ticker : str
        Stock ticker symbol to search for
    api_key : str
        Reddit credentials in format "client_id:client_secret:user_agent"
        Example: "abc123:def456:catalyst-bot/1.0"

    Returns
    -------
    tuple or None
        (score, label, n_posts, details) where score is VADER compound
        sentiment averaged across matching posts, or None on error
    """
    if not ticker or not api_key:
        return None

    # Parse Reddit credentials from api_key
    try:
        parts = api_key.split(":")
        if len(parts) < 3:
            log.debug("reddit_sentiment_invalid_key format must be client_id:client_secret:user_agent")
            return None
        client_id = parts[0]
        client_secret = parts[1]
        user_agent = ":".join(parts[2:])  # User agent may contain colons
    except Exception as e:
        log.debug("reddit_sentiment_key_parse_error error=%s", e.__class__.__name__)
        return None

    # Import PRAW dynamically to avoid requiring it if Reddit sentiment is disabled
    try:
        import praw  # type: ignore
    except ImportError:
        log.debug("reddit_sentiment_praw_not_installed install via: pip install praw")
        return None

    # Import VADER for sentiment analysis
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        vader = SentimentIntensityAnalyzer()
    except ImportError:
        log.debug("reddit_sentiment_vader_not_available")
        return None

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
    except Exception as e:
        log.debug("reddit_sentiment_init_error error=%s", e.__class__.__name__)
        return None

    # Subreddits to search (focused on trading and penny stocks)
    subreddits = ["wallstreetbets", "stocks", "pennystocks", "StockMarket"]
    ticker_upper = ticker.upper()

    # Search for ticker mentions across subreddits
    # Use "$TICKER" format common in trading subreddits
    search_queries = [
        f"${ticker_upper}",
        ticker_upper,
        f"${ticker_upper} OR {ticker_upper}",
    ]

    scores: List[float] = []
    post_count = 0

    try:
        for subreddit_name in subreddits:
            try:
                subreddit = reddit.subreddit(subreddit_name)

                # Search recent posts (limit to avoid rate limits)
                # Use first search query (most specific)
                for submission in subreddit.search(
                    search_queries[0], time_filter="day", limit=10
                ):
                    post_count += 1

                    # Analyze title + selftext sentiment
                    text = f"{submission.title} {submission.selftext}"
                    sentiment = vader.polarity_scores(text)
                    compound = sentiment.get("compound", 0.0)
                    scores.append(compound)

                    # Also check top comments for additional context
                    try:
                        submission.comments.replace_more(limit=0)
                        for comment in list(submission.comments)[:3]:  # Top 3 comments
                            comment_sentiment = vader.polarity_scores(comment.body)
                            scores.append(comment_sentiment.get("compound", 0.0))
                    except Exception:
                        pass  # Comment loading can fail, continue

            except Exception as e:
                log.debug(
                    "reddit_sentiment_subreddit_error subreddit=%s error=%s",
                    subreddit_name,
                    e.__class__.__name__,
                )
                continue
    except Exception as e:
        log.debug("reddit_sentiment_search_error error=%s", e.__class__.__name__)
        return None

    if not scores:
        return None

    # Average sentiment across all posts and comments
    avg_score = sum(scores) / len(scores)
    label = _label_from_score(avg_score)

    details = {
        "n_articles": post_count,
        "provider": "reddit",
        "n_sentiment_items": len(scores),
        "subreddits": subreddits,
    }

    log.debug(
        "reddit_sentiment ticker=%s posts=%d sentiment_items=%d score=%.2f",
        ticker_upper,
        post_count,
        len(scores),
        avg_score,
    )

    return avg_score, label, post_count, details


def _fetch_analyst_recommendations(
    ticker: str, api_key: str
) -> Optional[Tuple[float, str, int, Dict[str, Any]]]:
    """Fetch analyst recommendations from Finnhub.

    Analyst ratings and upgrades trigger institutional buying and are a strong
    bullish signal. This function retrieves consensus analyst recommendations
    (buy/hold/sell counts) and detects recent changes (upgrades/downgrades).

    The Finnhub API provides historical recommendation trends with timestamps,
    allowing us to weight recent changes more heavily than older data.

    Free tier: 60 calls/minute

    Sentiment Calculation
    ---------------------
    Net recommendation score is calculated as:
        score = (strongBuy * 1.0 + buy * 0.5 - sell * 0.5 - strongSell * 1.0) / total_analysts

    Normalized to [-1, 1] range. Recent changes (last 7-30 days) receive
    additional sentiment boosts/penalties:
        - Upgrade in last 7 days: +0.4 sentiment boost
        - Initiated coverage with Buy: +0.3 boost
        - Downgrade in last 7 days: -0.4 sentiment penalty

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    api_key : str
        Finnhub API key

    Returns
    -------
    tuple or None
        (score, label, n_recommendations, details) where score is in [-1, 1],
        label is "Bullish"/"Neutral"/"Bearish", n_recommendations is the
        total number of analyst ratings considered, and details contains
        consensus breakdown and recent changes. Returns None on error.
    """
    if not api_key or not ticker:
        return None

    base_url = "https://finnhub.io/api/v1/stock/recommendation"
    params = {
        "symbol": ticker.upper(),
        "token": api_key,
    }

    try:
        resp = requests.get(base_url, params=params, timeout=8)
    except Exception as e:
        log.debug("analyst_recommendations_request error=%s", e.__class__.__name__)
        return None

    if resp.status_code != 200:
        if resp.status_code in (401, 403, 429):
            log.debug(
                "analyst_recommendations_http status=%s ticker=%s",
                resp.status_code,
                ticker,
            )
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    if not data or not isinstance(data, list):
        return None

    # Finnhub returns list of recommendation snapshots ordered by period (most recent first)
    # Each snapshot contains: {period, strongBuy, buy, hold, sell, strongSell}
    # We prioritize the most recent data (first item) but also detect recent changes

    if len(data) == 0:
        return None

    # Get most recent recommendation snapshot
    latest = data[0]
    try:
        strong_buy = int(latest.get("strongBuy") or 0)
        buy = int(latest.get("buy") or 0)
        hold = int(latest.get("hold") or 0)
        sell = int(latest.get("sell") or 0)
        strong_sell = int(latest.get("strongSell") or 0)
    except (ValueError, TypeError):
        return None

    total_analysts = strong_buy + buy + hold + sell + strong_sell
    if total_analysts == 0:
        return None

    # Calculate base sentiment score from consensus
    # Formula: (strongBuy * 1.0 + buy * 0.5 - sell * 0.5 - strongSell * 1.0) / total
    numerator = (strong_buy * 1.0) + (buy * 0.5) - (sell * 0.5) - (strong_sell * 1.0)
    base_score = numerator / float(total_analysts)

    # Clamp to [-1, 1] range
    base_score = max(-1.0, min(1.0, base_score))

    # Detect recent changes (upgrades/downgrades) by comparing recent snapshots
    # Look at last 30 days of data to identify trends
    import datetime

    recent_upgrade = False
    recent_downgrade = False
    recent_initiation = False

    try:
        now = datetime.datetime.utcnow()
        # Parse period field (format: "YYYY-MM-DD" or "YYYY-MM-01")
        for i in range(min(len(data), 6)):  # Check last 6 months of data
            snapshot = data[i]
            period_str = snapshot.get("period")
            if not period_str:
                continue

            try:
                # Parse period date
                period_date = datetime.datetime.strptime(period_str, "%Y-%m-%d")
                days_ago = (now - period_date).days

                # Only consider data from last 30 days for recent changes
                if days_ago > 30:
                    continue

                # Compare with previous snapshot (if available)
                if i + 1 < len(data):
                    prev = data[i + 1]
                    prev_strong_buy = int(prev.get("strongBuy") or 0)
                    prev_buy = int(prev.get("buy") or 0)
                    prev_sell = int(prev.get("sell") or 0)
                    prev_strong_sell = int(prev.get("strongSell") or 0)

                    curr_strong_buy = int(snapshot.get("strongBuy") or 0)
                    curr_buy = int(snapshot.get("buy") or 0)
                    curr_sell = int(snapshot.get("sell") or 0)
                    curr_strong_sell = int(snapshot.get("strongSell") or 0)

                    # Detect upgrade: increase in buy ratings or decrease in sell ratings
                    if (
                        curr_strong_buy > prev_strong_buy
                        or curr_buy > prev_buy
                        or curr_sell < prev_sell
                        or curr_strong_sell < prev_strong_sell
                    ):
                        if days_ago <= 7:
                            recent_upgrade = True

                    # Detect downgrade: decrease in buy ratings or increase in sell ratings
                    if (
                        curr_strong_buy < prev_strong_buy
                        or curr_buy < prev_buy
                        or curr_sell > prev_sell
                        or curr_strong_sell > prev_strong_sell
                    ):
                        if days_ago <= 7:
                            recent_downgrade = True
                else:
                    # First snapshot with coverage - check if it's a recent initiation with Buy
                    if days_ago <= 7 and (strong_buy > 0 or buy > 0):
                        recent_initiation = True

            except (ValueError, TypeError):
                continue
    except Exception:
        pass

    # Apply sentiment boosts/penalties based on recent changes
    sentiment_adjustment = 0.0

    if recent_upgrade:
        sentiment_adjustment += 0.4  # Upgrade in last 7 days
    if recent_initiation:
        sentiment_adjustment += 0.3  # Initiated coverage with Buy
    if recent_downgrade:
        sentiment_adjustment -= 0.4  # Downgrade in last 7 days

    # Calculate final sentiment with adjustments
    final_score = base_score + sentiment_adjustment
    final_score = max(-1.0, min(1.0, final_score))  # Clamp again

    # Determine label
    label = _label_from_score(final_score)

    # Build details dictionary
    details = {
        "n_articles": 1,  # Treat as single consensus data point
        "provider": "analyst",
        "strong_buy": strong_buy,
        "buy": buy,
        "hold": hold,
        "sell": sell,
        "strong_sell": strong_sell,
        "total_analysts": total_analysts,
        "consensus": "Buy" if strong_buy + buy > sell + strong_sell else "Hold" if strong_buy + buy == sell + strong_sell else "Sell",
        "recent_upgrade": recent_upgrade,
        "recent_downgrade": recent_downgrade,
        "recent_initiation": recent_initiation,
        "base_score": base_score,
        "sentiment_adjustment": sentiment_adjustment,
    }

    log.debug(
        "analyst_recommendations ticker=%s total=%d strongBuy=%d buy=%d hold=%d sell=%d strongSell=%d score=%.2f",
        ticker.upper(),
        total_analysts,
        strong_buy,
        buy,
        hold,
        sell,
        strong_sell,
        final_score,
    )

    return final_score, label, 1, details


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
# 2. INSTITUTIONAL SENTIMENT: Analyst Recommendations (FREE via Finnhub)
#    - Consensus analyst ratings (buy/hold/sell counts)
#    - Recent upgrades/downgrades detection
#    - Institutional sentiment indicator
#    - Weight: 0.10 (moderate influence)
#
# 3. SOCIAL SENTIMENT: StockTwits + Reddit (FREE tiers)
#    - StockTwits: 200 calls/hour, real-time investor sentiment
#    - Reddit: 60 req/min, community discussion analysis
#    - Complements news with social/retail sentiment
#    - Research shows social divergence creates 15% larger moves
#
# 4. BACKUP: Alpha Vantage (uses existing subscription)
#    - News sentiment endpoint available
#    - Already subscribed for price data
#
# 5. BACKUP: Marketaux (requires separate API key)
# 6. BACKUP: StockNewsAPI (requires separate API key)
#
# Additional providers can be appended here in future patches.
_PROVIDERS = {
    "finnhub": _fetch_finnhub_sentiment,  # PRIMARY for news/sentiment
    "analyst": _fetch_analyst_recommendations,  # INSTITUTIONAL sentiment (Finnhub)
    "stocktwits": _fetch_stocktwits_sentiment,  # SOCIAL sentiment (free)
    "reddit": _fetch_reddit_sentiment,  # SOCIAL sentiment (free)
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
