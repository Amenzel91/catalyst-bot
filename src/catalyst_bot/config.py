import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


def _env_float_opt(name: str) -> Optional[float]:
    """
    Read an optional float from env. Returns None if unset, blank, or non-numeric.
    """
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "" or raw.lower() in {"none", "null"} or raw.startswith("#"):
        return None
    try:
        return float(raw)
    except Exception:
        return None


def _b(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


@dataclass
class Settings:
    # Keys / tokens
    alphavantage_api_key: str = os.getenv("ALPHAVANTAGE_API_KEY", "")
    # Use FINVIZ_AUTH_TOKEN primarily, falling back to FINVIZ_ELITE_AUTH for
    # backward compatibility.  Some older deployments still refer to the
    # token as FINVIZ_ELITE_AUTH; check both so the value propagates to
    # settings.finviz_auth_token.  Note that feeds.py also explicitly
    # falls back to FINVIZ_ELITE_AUTH when pulling news.
    finviz_auth_token: str = (
        os.getenv("FINVIZ_AUTH_TOKEN") or os.getenv("FINVIZ_ELITE_AUTH") or ""
    )

    # --- Phase‑C: Tiingo support ---
    # API key used to access the Tiingo real‑time quote endpoint. When this value
    # is non‑empty and FEATURE_TIINGO is enabled, the bot will prefer Tiingo for
    # last price/previous close snapshots before falling back to other providers.
    tiingo_api_key: str = os.getenv("TIINGO_API_KEY", "")

    # Feature flag to enable Tiingo as the primary price provider. Defaults to
    # false. When true and a TIINGO_API_KEY is set, get_last_price_snapshot()
    # will query Tiingo before Alpha Vantage and yfinance.
    feature_tiingo: bool = _b("FEATURE_TIINGO", False)

    # --- Phase‑C: FMP sentiment support ---
    # API key used to access the Financial Modeling Prep sentiment RSS endpoint.  When
    # non‑empty, it will be appended as a query parameter to the RSS URL.  This
    # field is optional because the free sentiment feed does not require a key,
    # but future premium tiers may.  Set via FMP_API_KEY in your environment.
    fmp_api_key: str = os.getenv("FMP_API_KEY", "")

    # Feature flag to enable parsing and attaching FMP sentiment scores.  When
    # true, the bot will fetch the Stock News Sentiment RSS feed from
    # Financial Modeling Prep on each cycle and merge the returned sentiment
    # values into events by canonicalised link.  Defaults to false.  Use
    # FEATURE_FMP_SENTIMENT=1 to enable.
    feature_fmp_sentiment: bool = _b("FEATURE_FMP_SENTIMENT", False)

    # --- Phase‑C: Finviz news export CSV support ---
    # Optional URL for exporting Finviz aggregated news as CSV.  If provided,
    # the bot will fetch this URL when FEATURE_FINVIZ_NEWS_EXPORT=1 and merge
    # the resulting rows into the event stream.  Rows should be in CSV format
    # with at least Title, Source, Date, Url and Category columns.  Because
    # Finviz does not include tickers in the news export feed, events will be
    # created without a ticker unless one can be inferred from the title.
    finviz_news_export_url: str = os.getenv("FINVIZ_NEWS_EXPORT_URL", "")

    # Feature flag to enable the Finviz news export feed.  When true and a
    # FINVIZ_NEWS_EXPORT_URL is set, fetch_pr_feeds() will attempt to pull
    # rows from the export URL and convert them to events.  Defaults to false.
    feature_finviz_news_export: bool = _b("FEATURE_FINVIZ_NEWS_EXPORT", False)

    # --- Phase‑C: Earnings calendar support ---
    # Path to a cached earnings calendar CSV pulled from Alpha Vantage.  This file
    # is refreshed by the jobs/earnings_pull.py script.  The analyzer will read
    # this file to annotate events occurring on or near earnings dates.  Use
    # EARNINGS_CALENDAR_CACHE in your environment to override; defaults to
    # ``data/earnings_calendar.csv``.
    earnings_calendar_cache: str = os.getenv(
        "EARNINGS_CALENDAR_CACHE", "data/earnings_calendar.csv"
    )

    # ----------------------------------------------------------------------
    # Phase‑C Patch 6: Provider chooser & Alpaca telemetry
    #
    # The market_provider_order determines the order in which the bot will
    # attempt to fetch last/prev prices.  It is a comma‑separated list of
    # provider identifiers.  Recognised values include:
    #
    #   - ``tiingo``: Use the Tiingo IEX API when FEATURE_TIINGO=1 and a
    #     TIINGO_API_KEY is set.
    #   - ``av`` or ``alpha``: Use Alpha Vantage’s GLOBAL_QUOTE endpoint when an
    #     ALPHAVANTAGE_API_KEY is present and MARKET_SKIP_ALPHA is not set.
    #   - ``yf`` or ``yahoo``: Use the yfinance fallback.  This uses fast_info
    #     and history() to derive last and previous close values.
    #
    # The default order is ``tiingo,av,yf``.  You can override this by setting
    # MARKET_PROVIDER_ORDER in the environment (e.g. "av,yf" to skip Tiingo).
    market_provider_order: str = os.getenv("MARKET_PROVIDER_ORDER", "tiingo,av,yf")

    # Enable Alpaca IEX streaming after a headline.  When true, the runner
    # subscribes to the Alpaca websocket feed for tickers in alerts for a
    # short period after sending the alert.  This can provide more up‑to‑date
    # price information.  Requires ALPACA_API_KEY and ALPACA_SECRET.
    feature_alpaca_stream: bool = _b("FEATURE_ALPACA_STREAM", False)

    # Alpaca API credentials.  Only used when FEATURE_ALPACA_STREAM is true.
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret: str = os.getenv("ALPACA_SECRET", "")

    # Number of seconds to sample Alpaca stream after a headline.  The
    # subscription will be active for this duration to capture any immediate
    # price moves.  Defaults to 0 (disabled) when FEATURE_ALPACA_STREAM is off.
    # You can override via STREAM_SAMPLE_WINDOW_SEC.
    stream_sample_window_sec: int = 0
    try:
        _stream_sec = int((os.getenv("STREAM_SAMPLE_WINDOW_SEC") or "0").strip() or "0")
        if _stream_sec > 0:
            stream_sample_window_sec = _stream_sec
    except Exception:
        # leave as zero when invalid
        pass

    # --- Phase‑C: Watchlist support ---
    # Path to the CSV file containing watchlist tickers. The file should
    # contain a column named ``ticker`` (case insensitive), and may include
    # optional columns like ``rationale`` or ``weight``. Defaults to
    # ``data/watchlist.csv`` relative to the project root. Use the
    # WATCHLIST_CSV environment variable to override.
    watchlist_csv: str = os.getenv("WATCHLIST_CSV", "data/watchlist.csv")

    # Feature flag to enable watchlist pre‑gating. When true, the bot will
    # load the watchlist from ``watchlist_csv`` once per cycle and bypass the
    # price ceiling filter for events whose ticker is on the watchlist. In
    # future patches this flag may also enable preferential classification
    # weighting for watchlisted tickers. Defaults to false.
    feature_watchlist: bool = _b("FEATURE_WATCHLIST", False)

    # -- Wave‑3: Screener boost support --
    # Path to the Finviz screener CSV used to boost tickers.  When
    # feature_screener_boost is enabled, this file will be loaded once per
    # cycle and tickers appearing in it will bypass the price ceiling
    # filter just like the static watchlist.  The CSV is expected to have
    # a column named "Ticker" (case insensitive) but will fall back to
    # using the first column if the standard header is missing.  Defaults
    # to ``data/finviz.csv`` relative to the project root.  Override via
    # the SCREENER_CSV environment variable.
    screener_csv: str = os.getenv("SCREENER_CSV", "data/finviz.csv")

    # Feature flag to enable screener boost.  When true, the bot will
    # combine the tickers loaded from the file specified by ``screener_csv``
    # with the static watchlist (if feature_watchlist is also enabled) and
    # treat them as one unified watchlist.  Tickers on this combined set
    # bypass the price ceiling filter during feed processing.  This flag
    # does not modify classification weights; it only affects gating.  It
    # defaults to false.
    feature_screener_boost: bool = _b("FEATURE_SCREENER_BOOST", False)

    # Helpers
    def _env_first(*names: str) -> str:
        import os

        for n in names:
            v = os.getenv(n)
            if v and v.strip():
                return v.strip()
        return ""

    # Primary Discord webhook (support several common names)
    discord_webhook_url: str = _env_first(
        "DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK", "ALERT_WEBHOOK"
    )
    # Back-compat aliases (so getattr(settings, "...") keeps working)
    webhook_url: str = discord_webhook_url
    discord_webhook: str = discord_webhook_url

    # Optional admin/dev webhook (ops / heartbeat)
    admin_webhook_url: Optional[str] = (
        _env_first("DISCORD_ADMIN_WEBHOOK", "ADMIN_WEBHOOK") or None
    )

    # Feature flags
    feature_heartbeat: bool = bool(int(os.getenv("FEATURE_HEARTBEAT", "1")))

    # Behavior / thresholds
    price_ceiling: Optional[float] = _env_float_opt("PRICE_CEILING")
    loop_seconds: int = int(os.getenv("LOOP_SECONDS", "60"))

    # Feature flags
    feature_record_only: bool = _b("FEATURE_RECORD_ONLY", False)
    feature_alerts: bool = _b("FEATURE_ALERTS", True)
    feature_verbose_logging: bool = _b("FEATURE_VERBOSE_LOGGING", True)

    # --- Phase-B feature flags (default: OFF) ---
    # Use classify.classify() bridge in feeds/analyzer instead of the legacy
    # classifier.py.  Enabling this flag unifies classification logic across
    # modules and paves the way for removal of ``classifier.py`` in a future
    # release.  Default to True so the new classifier is used out of the box.
    feature_classifier_unify: bool = _b("FEATURE_CLASSIFIER_UNIFY", True)
    # Post analyzer summary markdown to admin webhook via alerts helper
    feature_admin_embed: bool = _b("FEATURE_ADMIN_EMBED", False)
    # Add intraday indicators (VWAP/RSI14) into alert embeds
    feature_indicators: bool = _b("FEATURE_INDICATORS", False)

    # --- Phase-C Patch 7: Rich alert charts ---
    # When enabled, the bot will generate an intraday candlestick chart for each
    # alert and attach it to the Discord embed.  Charts are created via
    # catalyst_bot.charts.render_intraday_chart() and are only rendered when
    # Matplotlib/mplfinance are available (see charts.CHARTS_OK).  By default
    # this flag is off.  Use FEATURE_RICH_ALERTS=1 to turn on chart rendering.
    feature_rich_alerts: bool = _b("FEATURE_RICH_ALERTS", False)

    # --- Quick win: Finviz chart fallback ---
    # When enabled and rich alerts are disabled or charts are unavailable, the
    # bot will embed a static daily candlestick chart from Finviz for the
    # primary ticker on each alert.  This uses Finviz’s public chart API
    # (charts2.finviz.com) and does not require any additional credentials.
    # To enable, set FEATURE_FINVIZ_CHART=1 in your environment.
    feature_finviz_chart: bool = _b("FEATURE_FINVIZ_CHART", False)

    # --- Momentum & QuickChart features ---
    # When FEATURE_QUICKCHART is enabled, the bot will render intraday
    # candlestick charts using the QuickChart API.  A Chart.js config
    # is generated on the fly and passed to the API, which returns a
    # hosted PNG image.  This avoids embedding large base64 payloads
    # in Discord messages.  If disabled, the bot falls back to local
    # chart rendering (FEATURE_RICH_ALERTS) or Finviz static charts.
    feature_quickchart: bool = _b("FEATURE_QUICKCHART", False)

    # Base URL for the QuickChart API.  Override this via the
    # QUICKCHART_BASE_URL environment variable to point to a self‑hosted
    # QuickChart server (e.g. ``http://localhost:3400/chart``).  When
    # unspecified, the bot uses the hosted ``https://quickchart.io/chart``
    # endpoint.  This variable should include the ``/chart`` path.
    quickchart_base_url: str = os.getenv(
        "QUICKCHART_BASE_URL", "https://quickchart.io/chart"
    )

    # When FEATURE_MOMENTUM_INDICATORS is enabled (in addition to
    # FEATURE_INDICATORS), the bot will compute MACD, EMA crossovers
    # and VWAP deltas from intraday data and include these metrics in
    # alert embeds.  The additional indicators provide traders with
    # context about momentum and trend strength.  Defaults to false.
    feature_momentum_indicators: bool = _b("FEATURE_MOMENTUM_INDICATORS", False)

    # When FEATURE_LOCAL_SENTIMENT is enabled, a fallback sentiment
    # score will be computed using the VADER sentiment analyser for each
    # headline.  This score will be displayed in the alert embed
    # alongside any FMP sentiment value (when available).  Defaults to
    # false.
    feature_local_sentiment: bool = _b("FEATURE_LOCAL_SENTIMENT", False)

    # --- Phase‑D: External news sentiment sources ---
    # When enabled, the bot will fetch news‑based sentiment signals from
    # external providers (Alpha Vantage News Sentiment, Marketaux,
    # StockNewsAPI and Finnhub) and aggregate them into a combined score.
    # The aggregated score and discrete label are attached to each event as
    # ``sentiment_ext_score`` and ``sentiment_ext_label``.  When this flag is
    # off the external providers are skipped entirely.  Defaults to false.
    feature_news_sentiment: bool = _b("FEATURE_NEWS_SENTIMENT", False)
    # Per‑provider switches.  These allow fine‑grained control over which
    # external feeds are consulted.  When a provider flag is false or the
    # corresponding API key is blank, that provider will be ignored.
    feature_alpha_sentiment: bool = _b("FEATURE_ALPHA_SENTIMENT", False)
    feature_marketaux_sentiment: bool = _b("FEATURE_MARKETAUX_SENTIMENT", False)
    feature_stocknews_sentiment: bool = _b("FEATURE_STOCKNEWS_SENTIMENT", False)
    feature_finnhub_sentiment: bool = _b("FEATURE_FINNHUB_SENTIMENT", False)

    # API keys for optional sentiment providers.  The Alpha Vantage key
    # (ALPHAVANTAGE_API_KEY) defined above is reused for the news sentiment
    # endpoint.  These additional keys are read here for completeness.
    marketaux_api_key: str = os.getenv("MARKETAUX_API_KEY", "")
    stocknews_api_key: str = os.getenv("STOCKNEWS_API_KEY", "")
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")

    # Weights used when combining sentiment scores from multiple providers.
    # Values should sum to 1.0, but no assumptions are made; the aggregator
    # will normalise weights across providers that return a score.  Defaults
    # allocate 0.4 to Alpha Vantage and 0.3 each to Marketaux and
    # StockNewsAPI.  Finnhub is disabled by default (weight ignored when
    # provider disabled).
    sentiment_weight_alpha: float = float(
        os.getenv("SENTIMENT_WEIGHT_ALPHA", "0.4").strip() or "0.4"
    )
    sentiment_weight_marketaux: float = float(
        os.getenv("SENTIMENT_WEIGHT_MARKETAUX", "0.3").strip() or "0.3"
    )
    sentiment_weight_stocknews: float = float(
        os.getenv("SENTIMENT_WEIGHT_STOCKNEWS", "0.3").strip() or "0.3"
    )
    sentiment_weight_finnhub: float = float(
        os.getenv("SENTIMENT_WEIGHT_FINNHUB", "0").strip() or "0"
    )

    # Minimum total article count required across all providers before a
    # combined sentiment score is considered valid.  When the sum of
    # ``n_articles`` returned by the providers is less than this value, the
    # aggregator returns ``None`` for score and label, and events fall
    # back to local sentiment only.  Defaults to 2 to avoid single‑item
    # noise dominating the signal.
    sentiment_min_articles: int = int(
        os.getenv("SENTIMENT_MIN_ARTICLES", "1").strip() or "1"
    )

    # --- Patch‑6: Analyst signals ---
    # When enabled, the bot will fetch consensus analyst price targets
    # and compute the implied return relative to the last price for each
    # ticker.  The return is classified as Bullish, Neutral or Bearish
    # depending on the ANALYST_RETURN_THRESHOLD.  Use
    # FEATURE_ANALYST_SIGNALS=1 to enable.
    feature_analyst_signals: bool = _b("FEATURE_ANALYST_SIGNALS", False)
    # Percentage threshold used to determine bullish/bearish classification.
    # A value of 10.0 means the implied return must be ≥ +10% to be
    # considered Bullish and ≤ −10% to be considered Bearish.  Values in
    # between are Neutral.
    analyst_return_threshold: float = float(
        os.getenv("ANALYST_RETURN_THRESHOLD", "10.0").strip() or "10.0"
    )
    # Provider used to fetch analyst signals.  Supported values:
    # ``fmp`` – Financial Modeling Prep API (requires FMP_API_KEY or
    # ANALYST_API_KEY).  ``yahoo`` – yfinance (no key required).  Defaults
    # to ``fmp`` when unset.
    analyst_provider: str = os.getenv("ANALYST_PROVIDER", "fmp").strip() or "fmp"
    # Optional API key for the chosen provider.  When blank and
    # provider=fmp, the bot falls back to FMP_API_KEY.  Ignored for yahoo.
    analyst_api_key: str = os.getenv("ANALYST_API_KEY", "").strip()

    # --- Patch‑2: Breakout scanner flags and thresholds ---
    # When enabled, the bot will proactively scan for breakout
    # candidates using Finviz Elite’s screener export.  The scanner
    # looks for sub‑$10 tickers with unusually high volume and new highs.
    # Use FEATURE_BREAKOUT_SCANNER=1 to activate.
    feature_breakout_scanner: bool = _b("FEATURE_BREAKOUT_SCANNER", False)
    # Minimum average daily volume (shares) for breakout scanner; values
    # should be specified as plain integers (e.g. 300000).  Defaults to
    # 300000 shares.  Use BREAKOUT_MIN_AVG_VOL to override.
    breakout_min_avg_vol: float = float(
        os.getenv("BREAKOUT_MIN_AVG_VOL", "300000").strip() or 300000
    )
    # Minimum relative volume threshold.  Values greater than 1 indicate
    # above‑average trading activity.  Defaults to 1.5.  Use
    # BREAKOUT_MIN_RELVOL to override.
    breakout_min_relvol: float = float(
        os.getenv("BREAKOUT_MIN_RELVOL", "1.5").strip() or 1.5
    )

    # --- Patch‑5: Watchlist cascade and 52‑week low scanner ---
    # When enabled, the bot maintains a stateful watchlist where tickers
    # transition from HOT to WARM to COOL over time.  The state and
    # timestamps are persisted to ``watchlist_state_file``.  Use
    # FEATURE_WATCHLIST_CASCADE=1 to turn on this behaviour.
    feature_watchlist_cascade: bool = _b("FEATURE_WATCHLIST_CASCADE", False)
    # Durations (in days) for each state before demotion.  HOT tickers
    # become WARM after watchlist_hot_days; WARM tickers become COOL
    # after watchlist_hot_days + watchlist_warm_days.  COOL tickers
    # remain COOL indefinitely.  Defaults: 7/21/60 days.
    watchlist_hot_days: int = int(os.getenv("WATCHLIST_HOT_DAYS", "7") or "7")
    watchlist_warm_days: int = int(os.getenv("WATCHLIST_WARM_DAYS", "21") or "21")
    watchlist_cool_days: int = int(os.getenv("WATCHLIST_COOL_DAYS", "60") or "60")
    # Path to the JSON file used to persist watchlist cascade state.  If
    # relative, it is resolved relative to the project root.  Defaults
    # to ``data/watchlist_state.json``.  Use WATCHLIST_STATE_FILE to
    # override.
    watchlist_state_file: str = os.getenv(
        "WATCHLIST_STATE_FILE", "data/watchlist_state.json"
    )

    # Flag to enable the 52‑week low scanner.  When true, the bot
    # proactively scans for tickers trading near their 52‑week lows and
    # adds them to the watchlist cascade.  Defaults to false.
    feature_52w_low_scanner: bool = _b("FEATURE_52W_LOW_SCANNER", False)
    # Distance from the 52‑week low (percentage) considered "near".  A
    # value of 5 means the price is within 5% above the 52‑week low.
    # Defaults to 5.
    low_distance_pct: float = float(os.getenv("LOW_DISTANCE_PCT", "5") or "5")
    # Minimum average daily volume required for 52‑week low scanner.  Use
    # LOW_MIN_AVG_VOL=300000 to require at least 300k shares.  Defaults
    # to 300k shares.
    low_min_avg_vol: float = float(os.getenv("LOW_MIN_AVG_VOL", "300000") or "300000")

    # -------------------------------------------------------------------
    # Patch‑Wave‑1: Bullishness gauge and sentiment logging
    #
    # When enabled, the bot will compute a single combined "bullishness" score
    # by aggregating multiple sentiment inputs (local sentiment, external
    # news sentiment, SEC filings, analyst signals and earnings surprises).
    # The combined score is normalised to the range [‑1, 1] and classified
    # as Bullish, Neutral or Bearish.  The result is displayed in alerts
    # when FEATURE_BULLISHNESS_GAUGE is turned on.  Set this flag via
    # FEATURE_BULLISHNESS_GAUGE=1 in your environment.  Defaults to off.
    feature_bullishness_gauge: bool = _b("FEATURE_BULLISHNESS_GAUGE", False)

    # When enabled, the bot will emit a JSONL log for each event capturing
    # the individual sentiment components (local, external, SEC, analyst and
    # earnings) as well as the final combined score.  Logs are written to
    # ``data/sentiment_logs/YYYY‑MM‑DD.jsonl`` relative to ``data_dir``.
    # Use FEATURE_SENTIMENT_LOGGING=1 to enable.  Defaults to off.
    feature_sentiment_logging: bool = _b("FEATURE_SENTIMENT_LOGGING", False)

    # Comma‑separated list of exchange codes that are allowed during feed
    # ingestion.  Tickers whose headlines specify an exchange not in this
    # list will be dropped before price/volatility filtering.  Valid
    # values include NASDAQ, NYSE, AMEX and OTCMKTS variants.  Values are
    # compared case‑insensitively.  The default whitelist allows
    # Nasdaq, NYSE and AMEX listings while filtering out OTC/Pink sheet
    # symbols.  Example: ``ALLOWED_EXCHANGES=nasdaq,nyse,amex``.
    allowed_exchanges: str = os.getenv("ALLOWED_EXCHANGES", "nasdaq,nyse,amex")

    # Weights applied when combining different sentiment sources into the
    # bullishness gauge.  Each weight should be a non‑negative float.  The
    # aggregator will normalise weights across sources that return a
    # non‑null score.  You can adjust these values to tune the relative
    # influence of each component.  When a weight is zero, that component
    # is excluded from the combined score.  The defaults favour the
    # local VADER sentiment and external news sentiment while giving
    # modest weight to SEC filings, analyst signals and earnings surprises.
    sentiment_weight_local: float = float(
        os.getenv("SENTIMENT_WEIGHT_LOCAL", "0.4") or "0.4"
    )
    sentiment_weight_ext: float = float(
        os.getenv("SENTIMENT_WEIGHT_EXT", "0.3") or "0.3"
    )
    # sentiment_weight_sec already defined further down; reused by gauge
    sentiment_weight_analyst: float = float(
        os.getenv("SENTIMENT_WEIGHT_ANALYST", "0.1") or "0.1"
    )
    # sentiment_weight_earnings defined in Patch‑6 section is reused

    # --- Phase-C Patch 8: Admin digest & approval loop ---
    # When this flag is enabled, the analyzer will write pending plan files
    # and expect a manual approval before promoting weight adjustments.
    # Pending plans are written via ``approval.write_pending_plan`` and
    # promoted via ``approval.promote_if_approved``.  Use
    # FEATURE_APPROVAL_LOOP=1 to enable the file-based approval workflow.
    feature_approval_loop: bool = _b("FEATURE_APPROVAL_LOOP", False)

    # Directory where approval marker files live.  When the approval loop
    # feature is on, a plan will only be promoted once a file named
    # ``<planId>.approved`` exists in this directory.  Override via
    # APPROVAL_DIR in your environment.  Defaults to ``out/approvals``.
    approval_dir: str = os.getenv("APPROVAL_DIR", "out/approvals")

    # Optional explicit path for analyzer summary markdown to post
    admin_summary_path: Optional[str] = os.getenv("ADMIN_SUMMARY_PATH", None)

    # --- WAVE 0.0 Phase 2: Market Hours Detection ---
    # Enable market hours detection and adaptive cycling.  When this flag is
    # enabled, the bot will adjust cycle times and feature availability based
    # on the current market status (pre-market, regular, after-hours, closed).
    # Use FEATURE_MARKET_HOURS_DETECTION=1 to enable.
    feature_market_hours_detection: bool = _b("FEATURE_MARKET_HOURS_DETECTION", False)

    # Process priority for Windows.  Valid values: IDLE, BELOW_NORMAL, NORMAL,
    # ABOVE_NORMAL, HIGH, REALTIME.  Defaults to BELOW_NORMAL to reduce
    # CPU contention with other applications.  Use BOT_PROCESS_PRIORITY to
    # override.  On non-Windows platforms this setting is ignored.
    bot_process_priority: str = os.getenv("BOT_PROCESS_PRIORITY", "BELOW_NORMAL")

    # Minimum interval (in seconds) between LLM classification calls.  This
    # throttle prevents excessive API requests during high-volume periods.
    # Defaults to 3 seconds.
    llm_min_interval_sec: int = int(os.getenv("LLM_MIN_INTERVAL_SEC", "3") or "3")

    # Minimum interval (in seconds) between chart generation calls.  This
    # throttle prevents excessive rendering during high-volume periods.
    # Defaults to 2 seconds.
    chart_min_interval_sec: int = int(os.getenv("CHART_MIN_INTERVAL_SEC", "2") or "2")

    # Cycle time (in seconds) when market is open (9:30 AM - 4:00 PM ET).
    # Defaults to 60 seconds.
    market_open_cycle_sec: int = int(os.getenv("MARKET_OPEN_CYCLE_SEC", "60") or "60")

    # Cycle time (in seconds) during extended hours (pre-market 4:00-9:30 AM,
    # after-hours 4:00-8:00 PM ET).  Defaults to 90 seconds.
    extended_hours_cycle_sec: int = int(
        os.getenv("EXTENDED_HOURS_CYCLE_SEC", "90") or "90"
    )

    # Cycle time (in seconds) when market is closed (8:00 PM - 4:00 AM ET,
    # weekends, holidays).  Defaults to 180 seconds.
    market_closed_cycle_sec: int = int(
        os.getenv("MARKET_CLOSED_CYCLE_SEC", "180") or "180"
    )

    # Number of hours before market open to start the pre-open warmup period.
    # During warmup, features are gradually enabled.  Defaults to 2 hours.
    preopen_warmup_hours: int = int(os.getenv("PREOPEN_WARMUP_HOURS", "2") or "2")

    # Feature toggles for market closed periods.  When set to 1, the
    # corresponding feature will be disabled when the market is closed.
    closed_disable_llm: bool = _b("CLOSED_DISABLE_LLM", True)
    closed_disable_charts: bool = _b("CLOSED_DISABLE_CHARTS", True)
    closed_disable_breakout: bool = _b("CLOSED_DISABLE_BREAKOUT", True)

    # Misc
    tz: str = os.getenv("TZ", "America/Chicago")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    analyzer_utc_hour: int = int(os.getenv("ANALYZER_UTC_HOUR", "21"))
    analyzer_utc_minute: int = int(os.getenv("ANALYZER_UTC_MINUTE", "30"))

    # --- Phase‑D: SEC filings digester ---
    # Feature flag to enable classification and aggregation of SEC filings.
    # When on, the bot will run the sec_digester to classify 8‑K/424B5/FWP/13D/G
    # events as Bullish/Neutral/Bearish and attach recent filings context to
    # news events.  Defaults to off.  Use FEATURE_SEC_DIGESTER=1 to enable.
    feature_sec_digester: bool = _b("FEATURE_SEC_DIGESTER", False)
    # Number of days to look back when aggregating SEC filings for sentiment.
    # Older filings are dropped from the cache automatically.  Defaults to 7.
    sec_lookback_days: int = int(os.getenv("SEC_LOOKBACK_DAYS", "7") or "7")
    # Weight of SEC sentiment in the combined sentiment gauge.  When non‑zero
    # and the SEC digester is enabled, the sentiment aggregator will include
    # the SEC score using this weight.  Defaults to 0.2.
    sentiment_weight_sec: float = float(
        os.getenv("SENTIMENT_WEIGHT_SEC", "0.2") or "0.2"
    )

    # --- Patch‑6: Earnings alerts ---
    # Enable earnings alerts and sentiment integration.  When this flag is
    # enabled, the bot will fetch the next scheduled earnings announcement
    # and the most recent EPS estimate/actual via the configured provider
    # (currently ``yfinance``).  Upcoming earnings are attached to events
    # when they fall within the lookahead window.  Past earnings surprises
    # contribute to the sentiment gauge via the weight below.  Defaults to
    # off.  Set FEATURE_EARNINGS_ALERTS=1 to enable.
    feature_earnings_alerts: bool = _b("FEATURE_EARNINGS_ALERTS", False)
    # Number of days ahead to consider upcoming earnings for alerting and
    # sentiment.  Earnings further in the future will not be attached.  For
    # example, a value of 14 means that earnings scheduled within the next
    # two weeks are considered.  Defaults to 14 days.
    earnings_lookahead_days: int = int(
        os.getenv("EARNINGS_LOOKAHEAD_DAYS", "14") or "14"
    )
    # Weight of earnings sentiment in the combined sentiment gauge.  When
    # non‑zero and earnings alerts are enabled, the sentiment aggregator will
    # include the earnings score using this weight.  A modest default of
    # 0.1 gives earnings surprises some influence without overwhelming other
    # signals.
    sentiment_weight_earnings: float = float(
        os.getenv("SENTIMENT_WEIGHT_EARNINGS", "0.1") or "0.1"
    )

    # --- Wave‑4: Options scanner support ---
    # Enable the options sentiment scanner.  When this flag is set, the bot
    # will call :func:`catalyst_bot.options_scanner.scan_options` for each
    # ticker and, if a score is returned, combine it into the bullishness
    # gauge.  Defaults to False.
    feature_options_scanner: bool = _b("FEATURE_OPTIONS_SCANNER", False)
    # Weight of the options sentiment in the combined bullishness gauge.
    # When non‑zero and a sentiment score is present on the event, this
    # component will contribute to the weighted average.  Defaults to 0.0.
    sentiment_weight_options: float = float(
        os.getenv("SENTIMENT_WEIGHT_OPTIONS", "0") or "0"
    )
    # Optional thresholds for unusual options activity.  These values are
    # currently unused by the stub implementation but are defined here for
    # future provider integrations.
    options_volume_threshold: float = float(
        os.getenv("OPTIONS_VOLUME_THRESHOLD", "0") or "0"
    )
    options_min_premium: float = float(os.getenv("OPTIONS_MIN_PREMIUM", "0") or "0")

    # --- Wave‑4: Sector/session and auto analyzer feature flags ---
    # These flags mirror values defined in ``config_extras.py``.  Exposing
    # them on ``Settings`` allows existing code to continue using
    # ``getattr(settings, ...)`` without importing the extras module.
    feature_sector_info: bool = _b("FEATURE_SECTOR_INFO", False)
    feature_market_time: bool = _b("FEATURE_MARKET_TIME", False)
    feature_sector_relax: bool = _b("FEATURE_SECTOR_RELAX", False)

    # Wave‑4: auto analyzer and log reporter flags.  When
    # ``feature_auto_analyzer`` is true, the runner will invoke the
    # analyzer at configured times.  When ``feature_log_reporter`` is true,
    # the runner will emit periodic log summaries.  Defaults to False for
    # both to preserve backward compatibility.
    feature_auto_analyzer: bool = _b("FEATURE_AUTO_ANALYZER", False)

    # --- Trade simulation analysis ---
    # Enable trade simulation analysis in the daily analyzer.  When this
    # flag is true, the analyzer will invoke the backtest simulator for
    # each event processed and surface high‑level performance metrics
    # such as top gainers and losers in the daily report.  Because
    # simulation requires fetching historical intraday data, it can be
    # computationally expensive and is therefore disabled by default.
    # Set FEATURE_TRADE_SIM_ANALYSIS=1 to enable.
    feature_trade_sim_analysis: bool = _b("FEATURE_TRADE_SIM_ANALYSIS", False)

    # Number of top gainers and losers to display when trade simulation
    # analysis is enabled.  A lower number produces a more concise
    # report.  Defaults to 5.
    trade_sim_top_n: int = int(os.getenv("TRADE_SIM_TOP_N", "5") or "5")

    # Directory containing scraped historical event files for offline
    # backtesting and simulation.  The historical backtest CLI scans
    # this directory for ``*.jsonl`` files and analyses them via the
    # backtest simulator.  Ensure the directory exists or the CLI will
    # produce no output.  Defaults to ``data/historical``.
    historical_data_dir: str = os.getenv("HISTORICAL_DATA_DIR", "data/historical")
    feature_log_reporter: bool = _b("FEATURE_LOG_REPORTER", False)

    # --- Wave‑5: LLM classification and sentiment support ---
    # Enable the LLM news classifier.  When this flag is set the bot will
    # invoke the local LLM via :mod:`catalyst_bot.llm_classifier` to
    # classify news headlines and summaries.  The classification
    # returns catalyst tags, relevance, sentiment and a rationale
    # which are merged into each event.  Defaults to false to avoid
    # incurring network or compute overhead when disabled.
    feature_llm_classifier: bool = _b("FEATURE_LLM_CLASSIFIER", False)

    # URL of the LLM API endpoint.  Must include the path to the
    # ``/api/generate`` method when using Ollama.  Used by
    # :mod:`catalyst_bot.llm_client`.  Defaults to ``http://localhost:11434/api/generate``.
    llm_endpoint_url: str = os.getenv(
        "LLM_ENDPOINT_URL", "http://localhost:11434/api/generate"
    )

    # Name of the local model to call.  Used by
    # :mod:`catalyst_bot.llm_client`.  Defaults to ``"mistral"``.
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "mistral")

    # Timeout (in seconds) for the LLM API request.  A shorter timeout
    # prevents the ingest pipeline from stalling on long‑running
    # requests.  Defaults to 15 seconds.
    llm_timeout_secs: float = float(os.getenv("LLM_TIMEOUT_SECS", "15") or "15")

    # --- Liquidity filtering ---
    # Minimum last price threshold for tickers.  When greater than zero, any
    # ticker whose last traded price falls below this value will be skipped
    # during feed ingestion.  Use this to suppress alerts on highly illiquid
    # penny stocks while still allowing reasonably priced symbols.  Set
    # PRICE_FLOOR in your environment, e.g. ``PRICE_FLOOR=1.00`` to ignore
    # tickers trading below $1.  Defaults to 0 (disabled).
    price_floor: float = float(os.getenv("PRICE_FLOOR", "0") or "0")

    # --- Phase‑C Patch 9: Plain logging mode ---
    # When this flag is enabled (LOG_PLAIN=1), the bot will emit human‑readable
    # one‑line logs to the console.  The log messages will include a timestamp,
    # coloured log level, logger name and message along with any extra fields
    # appended to the log record.  Structured JSON logs will still be
    # written to a rotating file under ``data/logs`` for ingestion by
    # downstream systems.  By default this feature is disabled to preserve
    # the compact JSON console format.  Set LOG_PLAIN=1 in your environment
    # to enable readable console logs.
    log_plain: bool = _b("LOG_PLAIN", False)

    # --- WAVE 1.2: Real-Time Breakout Feedback Loop ---
    # Enable the feedback loop system that tracks alert performance and
    # auto-adjusts keyword weights based on real outcomes. When enabled,
    # the bot will record each alert to a database, monitor price/volume
    # changes at 15m/1h/4h/1d intervals, score outcomes, and generate
    # keyword weight recommendations. Set FEATURE_FEEDBACK_LOOP=1 to enable.
    feature_feedback_loop: bool = _b("FEATURE_FEEDBACK_LOOP", False)

    # Interval in seconds for the price tracking background task. The
    # tracker queries current prices and volumes for all active alerts
    # and updates the database. Defaults to 900 seconds (15 minutes).
    feedback_tracking_interval: int = int(
        os.getenv("FEEDBACK_TRACKING_INTERVAL", "900")
    )

    # When enabled, keyword weight adjustments are applied automatically
    # to the dynamic weights file. When disabled (default), recommendations
    # are sent to the admin channel for manual review. Set
    # FEEDBACK_AUTO_ADJUST=1 to enable automatic adjustments.
    feedback_auto_adjust: bool = _b("FEEDBACK_AUTO_ADJUST", False)

    # Minimum number of alerts required for a keyword before its weight
    # will be adjusted. This prevents premature adjustments based on
    # insufficient data. Defaults to 20 alerts.
    feedback_min_samples: int = int(os.getenv("FEEDBACK_MIN_SAMPLES", "20"))

    # Enable weekly performance reports. When enabled, the bot will
    # generate and send a comprehensive weekly report to the admin
    # channel at the configured day/time. Set FEEDBACK_WEEKLY_REPORT=1
    # to enable.
    feature_feedback_weekly_report: bool = _b("FEEDBACK_WEEKLY_REPORT", False)

    # Day of week for weekly reports (0=Monday, 6=Sunday). Defaults to
    # Sunday (6).
    feedback_weekly_report_day: int = int(os.getenv("FEEDBACK_WEEKLY_REPORT_DAY", "6"))

    # Hour (UTC) for weekly reports. Defaults to 23 (11 PM UTC).
    feedback_weekly_report_hour: int = int(
        os.getenv("FEEDBACK_WEEKLY_REPORT_HOUR", "23")
    )

    # Path to the feedback database. Defaults to data/feedback/alert_performance.db
    feedback_db_path: str = os.getenv(
        "FEEDBACK_DB_PATH", "data/feedback/alert_performance.db"
    )

    # --- WAVE 0.1: Smart Earnings Scorer ---
    feature_earnings_scorer: bool = _b("FEATURE_EARNINGS_SCORER", True)
    earnings_beat_threshold_high: float = float(
        os.getenv("EARNINGS_BEAT_THRESHOLD_HIGH", "0.10")
    )
    earnings_beat_threshold_low: float = float(
        os.getenv("EARNINGS_BEAT_THRESHOLD_LOW", "0.05")
    )
    earnings_sentiment_beat_high: float = float(
        os.getenv("EARNINGS_SENTIMENT_BEAT_HIGH", "0.85")
    )
    earnings_sentiment_beat_low: float = float(
        os.getenv("EARNINGS_SENTIMENT_BEAT_LOW", "0.50")
    )
    earnings_sentiment_miss: float = float(
        os.getenv("EARNINGS_SENTIMENT_MISS", "-0.60")
    )

    # --- WAVE 2.1: Chart Generation Optimization ---
    # Note: feature_quickchart and quickchart_base_url already defined above (lines 240, 247)
    quickchart_url: str = os.getenv("QUICKCHART_URL", "http://localhost:3400")
    quickchart_api_key: str = os.getenv("QUICKCHART_API_KEY", "")
    chart_cache_enabled: bool = _b("CHART_CACHE_ENABLED", True)
    chart_cache_db_path: str = os.getenv("CHART_CACHE_DB_PATH", "data/chart_cache.db")
    chart_cache_1d_ttl: int = int(os.getenv("CHART_CACHE_1D_TTL", "60"))
    chart_cache_5d_ttl: int = int(os.getenv("CHART_CACHE_5D_TTL", "300"))
    chart_cache_1m_ttl: int = int(os.getenv("CHART_CACHE_1M_TTL", "900"))
    chart_cache_3m_ttl: int = int(os.getenv("CHART_CACHE_3M_TTL", "3600"))
    chart_parallel_max_workers: int = int(os.getenv("CHART_PARALLEL_MAX_WORKERS", "3"))
    quickchart_shorten_threshold: int = int(
        os.getenv("QUICKCHART_SHORTEN_THRESHOLD", "3500")
    )

    # --- WAVE 2.2: GPU Usage Fine-Tuning ---
    sentiment_model_name: str = os.getenv("SENTIMENT_MODEL_NAME", "finbert")
    sentiment_batch_size: int = int(os.getenv("SENTIMENT_BATCH_SIZE", "10"))
    gpu_memory_cleanup: bool = _b("GPU_MEMORY_CLEANUP", True)
    gpu_profiling_enabled: bool = _b("GPU_PROFILING_ENABLED", False)
    gpu_max_utilization_warn: int = int(os.getenv("GPU_MAX_UTILIZATION_WARN", "90"))
    gpu_max_temperature_c: int = int(os.getenv("GPU_MAX_TEMPERATURE_C", "85"))
    gpu_min_free_vram_mb: int = int(os.getenv("GPU_MIN_FREE_VRAM_MB", "500"))
    feature_cuda_streams: bool = _b("FEATURE_CUDA_STREAMS", False)
    feature_adaptive_sentiment: bool = _b("FEATURE_ADAPTIVE_SENTIMENT", False)
    sentiment_model_open: str = os.getenv("SENTIMENT_MODEL_OPEN", "distilbert")
    sentiment_model_closed: str = os.getenv("SENTIMENT_MODEL_CLOSED", "vader")

    # --- WAVE 2.2+: Sentiment Aggregation Weights ---
    # Weights for combining multiple sentiment sources
    # Note: sentiment_weight_earnings already defined above (line 550)
    # Redefining here for aggregation-specific weights
    sentiment_weight_ml: float = float(os.getenv("SENTIMENT_WEIGHT_ML", "0.25"))
    sentiment_weight_vader_agg: float = float(
        os.getenv("SENTIMENT_WEIGHT_VADER", "0.25")
    )
    sentiment_weight_llm: float = float(os.getenv("SENTIMENT_WEIGHT_LLM", "0.15"))

    # Feature flag for ML sentiment models (FinBERT/DistilBERT)
    feature_ml_sentiment: bool = _b("FEATURE_ML_SENTIMENT", True)

    # --- WAVE 2.3: 24/7 Deployment Infrastructure ---
    health_check_enabled: bool = _b("HEALTH_CHECK_ENABLED", True)
    health_check_port: int = int(os.getenv("HEALTH_CHECK_PORT", "8080"))
    feature_health_endpoint: bool = _b("FEATURE_HEALTH_ENDPOINT", True)
    watchdog_enabled: bool = _b("WATCHDOG_ENABLED", False)
    watchdog_check_interval: int = int(os.getenv("WATCHDOG_CHECK_INTERVAL", "60"))
    watchdog_restart_on_freeze: bool = _b("WATCHDOG_RESTART_ON_FREEZE", True)
    watchdog_freeze_threshold: int = int(os.getenv("WATCHDOG_FREEZE_THRESHOLD", "300"))
    watchdog_max_restarts: int = int(os.getenv("WATCHDOG_MAX_RESTARTS", "3"))
    deployment_env: str = os.getenv("DEPLOYMENT_ENV", "development")
    log_rotation_days: int = int(os.getenv("LOG_ROTATION_DAYS", "7"))
    admin_alert_webhook: str = os.getenv("ADMIN_ALERT_WEBHOOK", "")

    # --- WAVE 3.1: Advanced Chart Indicators ---
    chart_show_bollinger: bool = _b("CHART_SHOW_BOLLINGER", True)
    chart_show_fibonacci: bool = _b("CHART_SHOW_FIBONACCI", True)
    chart_show_support_resistance: bool = _b("CHART_SHOW_SUPPORT_RESISTANCE", True)
    chart_show_volume_profile: bool = _b("CHART_SHOW_VOLUME_PROFILE", False)
    chart_mtf_analysis: bool = _b("CHART_MTF_ANALYSIS", True)
    chart_bollinger_period: int = int(os.getenv("CHART_BOLLINGER_PERIOD", "20"))
    chart_bollinger_std: float = float(os.getenv("CHART_BOLLINGER_STD", "2.0"))
    chart_fibonacci_lookback: int = int(os.getenv("CHART_FIBONACCI_LOOKBACK", "20"))
    chart_sr_sensitivity: float = float(os.getenv("CHART_SR_SENSITIVITY", "0.02"))
    chart_sr_max_levels: int = int(os.getenv("CHART_SR_MAX_LEVELS", "5"))
    chart_sr_min_touches: int = int(os.getenv("CHART_SR_MIN_TOUCHES", "2"))
    chart_volume_bins: int = int(os.getenv("CHART_VOLUME_BINS", "20"))
    chart_show_poc: bool = _b("CHART_SHOW_POC", True)
    chart_show_value_area: bool = _b("CHART_SHOW_VALUE_AREA", True)
    chart_default_indicators: str = os.getenv(
        "CHART_DEFAULT_INDICATORS", "bollinger,sr"
    )
    indicator_cache_enabled: bool = _b("INDICATOR_CACHE_ENABLED", True)
    indicator_cache_ttl_sec: int = int(os.getenv("INDICATOR_CACHE_TTL_SEC", "300"))
    indicator_cache_max_size: int = int(os.getenv("INDICATOR_CACHE_MAX_SIZE", "1000"))

    # --- WAVE 7.1: Discord Slash Commands & Embeds ---
    discord_application_id: str = os.getenv("DISCORD_APPLICATION_ID", "")
    discord_guild_id: str = os.getenv("DISCORD_GUILD_ID", "")
    feature_slash_commands: bool = _b("FEATURE_SLASH_COMMANDS", True)
    slash_command_cooldown: int = int(os.getenv("SLASH_COMMAND_COOLDOWN", "3"))
    watchlist_max_size: int = int(os.getenv("WATCHLIST_MAX_SIZE", "50"))
    watchlist_dm_notifications: bool = _b("WATCHLIST_DM_NOTIFICATIONS", False)

    # --- WAVE ALPHA Agent 2: LLM Batching Enhancement ---
    # Batch size for LLM processing (items per batch)
    mistral_batch_size: int = int(os.getenv("MISTRAL_BATCH_SIZE", "5"))
    # Delay in seconds between LLM batches
    mistral_batch_delay: float = float(os.getenv("MISTRAL_BATCH_DELAY", "2.0"))
    # Minimum prescale score (from VADER + keywords) to qualify for LLM
    mistral_min_prescale: float = float(os.getenv("MISTRAL_MIN_PRESCALE", "0.20"))

    # --- WAVE 1.3: Backtesting Engine ---
    # Backtesting engine for validating strategies with historical data
    backtest_initial_capital: float = float(
        os.getenv("BACKTEST_INITIAL_CAPITAL", "10000.0")
    )
    backtest_position_size_pct: float = float(
        os.getenv("BACKTEST_POSITION_SIZE_PCT", "0.10")
    )
    backtest_max_volume_pct: float = float(os.getenv("BACKTEST_MAX_VOLUME_PCT", "0.05"))
    backtest_slippage_model: str = os.getenv(
        "BACKTEST_SLIPPAGE_MODEL", "adaptive"
    )  # fixed, adaptive, volume_based
    backtest_take_profit_pct: float = float(
        os.getenv("BACKTEST_TAKE_PROFIT_PCT", "0.20")
    )
    backtest_stop_loss_pct: float = float(os.getenv("BACKTEST_STOP_LOSS_PCT", "0.10"))
    backtest_max_hold_hours: int = int(os.getenv("BACKTEST_MAX_HOLD_HOURS", "24"))
    backtest_risk_free_rate: float = float(os.getenv("BACKTEST_RISK_FREE_RATE", "0.02"))

    # Paths (tests expect Path fields)
    project_root: Path = field(
        default_factory=lambda: Path(os.getenv("PROJECT_ROOT", os.getcwd())).resolve()
    )
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DATA_DIR", "data")).resolve()
    )
    out_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OUT_DIR", "out")).resolve()
    )

    # Default keyword weight if analyzer doesn't provide a dynamic override
    keyword_default_weight: float = float(os.getenv("KEYWORD_DEFAULT_WEIGHT", "1.0"))

    # Tests expect: dict[str, list[str]] (categories → keyword phrases)
    keyword_categories: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "fda": [
                "fda approval",
                "fda clearance",
                "510(k)",
                "de novo",
            ],
            "clinical": [
                "phase 3",
                "phase iii",
                "phase 2",
                "phase ii",
                "breakthrough",
                "fast track",
                "orphan drug",
            ],
            "partnership": [
                "contract award",
                "strategic partnership",
                "collaboration",
                "distribution agreement",
            ],
            "uplisting": [
                "uplisting",
                "listed on nasdaq",
                "transfer to nasdaq",
            ],
            "dilution": [
                "offering",
                "registered direct",
                "atm offering",
                "dilution",
            ],
            "going_concern": [
                "going concern",
            ],
        }
    )

    # Per-source weight map (lowercase hosts) — used by classify()
    rss_sources: Dict[str, float] = field(
        default_factory=lambda: {
            "businesswire.com": 1.2,
            "globenewswire.com": 1.1,
            "prnewswire.com": 1.1,
            "accesswire.com": 1.0,
        }
    )

    # Back-compat aliases for other modules
    @property
    def alpha_key(self) -> str:
        return self.alphavantage_api_key

    @property
    def finviz_cookie(self) -> str:
        return self.finviz_auth_token


SETTINGS = Settings()


def get_settings() -> Settings:
    return SETTINGS
