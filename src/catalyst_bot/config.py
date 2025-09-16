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
    # Use classify.classify() bridge in feeds/analyzer instead of legacy classifier.py
    feature_classifier_unify: bool = _b("FEATURE_CLASSIFIER_UNIFY", False)
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

    # Misc
    tz: str = os.getenv("TZ", "America/Chicago")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    analyzer_utc_hour: int = int(os.getenv("ANALYZER_UTC_HOUR", "21"))
    analyzer_utc_minute: int = int(os.getenv("ANALYZER_UTC_MINUTE", "30"))

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
