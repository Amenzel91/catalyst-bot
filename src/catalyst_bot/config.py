"""Configuration management for the catalyst bot.

This module centralizes all configuration values used throughout the
application. Values are loaded from environment variables (via a
`.env` file if present) and exposed as module‑level attributes for
convenient access. Reasonable defaults are provided for all values
such that the bot can run in a sandboxed environment without any
secrets. See `.env.example` in the repository root for a full list of
available configuration variables.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    # Fallback no‑op if python‑dotenv is not installed
    def load_dotenv(dotenv_path: Path | None = None) -> None:
        return None


# Load environment variables from a .env file if present. This call is
# idempotent – if the .env file is missing it simply does nothing.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")


def _str_to_bool(value: Optional[str], default: bool = False) -> bool:
    """Convert a string value to a boolean.

    Accepts a variety of common truthy values ("true", "1", "yes") and
    treats all other non‑empty strings as false unless explicit.

    Parameters
    ----------
    value : Optional[str]
        The string to convert.
    default : bool, optional
        The default to return if ``value`` is ``None``.

    Returns
    -------
    bool
    """
    if value is None:
        return default
    return value.strip().lower() in {"true", "1", "yes", "y"}


@dataclass
class Settings:
    """Dataclass encapsulating runtime configuration for the bot."""

    # Discord webhook for sending alerts
    discord_webhook_url: str = os.environ.get("DISCORD_WEBHOOK_URL", "")

    # Alpha Vantage API key
    alphavantage_api_key: str = os.environ.get("ALPHAVANTAGE_API_KEY", "demo")

    # Finviz credentials (optional)
    finviz_email: str = os.environ.get("FINVIZ_EMAIL", "")
    finviz_password: str = os.environ.get("FINVIZ_PASSWORD", "")

    # Finviz Elite auth token. When set, the bot will use the Finviz
    # export endpoints to fetch screener data programmatically. See
    # universe.py for usage. The token is typically a UUID tied to
    # your logged‑in session.
    finviz_auth_token: str = os.environ.get("FINVIZ_AUTH_TOKEN", "")

    # Universe filter
    price_ceiling: float = float(os.environ.get("PRICE_CEILING", 10))
    max_alerts: int = int(os.environ.get("MAX_ALERTS", 5))
    loop_seconds: int = int(os.environ.get("LOOP_SECONDS", 300))
    timezone: str = os.environ.get("TIMEZONE", "America/Chicago")

    # Analyzer configuration
    analyzer_run: str = os.environ.get("ANALYZER_RUN", "EOD").upper()
    analyzer_min_rv: float = float(os.environ.get("ANALYZER_MIN_RV", 1.5))
    analyzer_target_pct: float = float(os.environ.get("ANALYZER_TARGET_PCT", 0.35))

    # Feature flags
    feature_record_only: bool = _str_to_bool(
        os.environ.get("FEATURE_RECORD_ONLY"), default=False
    )
    feature_alerts: bool = _str_to_bool(os.environ.get("FEATURE_ALERTS"), default=True)
    feature_analyzer: bool = _str_to_bool(os.environ.get("FEATURE_ANALYZER"), default=True)
    feature_verbose_logging: bool = _str_to_bool(
        os.environ.get("FEATURE_VERBOSE_LOGGING"), default=False
    )

    # Directories (resolved at runtime)
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    data_dir: Path = field(init=False)
    out_dir: Path = field(init=False)

    # Keyword categories and their static default weights. These are used
    # by the classifier and may be overridden by dynamic weights
    # persisted in ``/data/analyzer/keyword_stats.json``. All keywords
    # should be lowercase for comparison simplicity.
    keyword_categories: Dict[str, List[str]] = field(default_factory=lambda: {
        "fda": ["fda", "clinical", "trial", "phase", "data", "study"],
        "buyback": ["buyback", "repurchase"],
        "upgrade": ["upgrade", "raised", "target", "pt"],
        "partnership": ["partnership", "contract", "deal", "agreement"],
        "guidance": ["guidance", "raises guidance", "outlook"],
        "uplist": ["uplisting", "uplist"],
        "investment": ["investment", "funding", "financing"],
        "grant": ["grant", "award"],
        "launch": ["launch", "clearance", "approval"],
        "merger": ["merger", "acquisition", "m&a"],
    })

    keyword_default_weight: float = 1.0

    # RSS sources and their associated source weights. These weights
    # influence the overall score of an item; heavier weights imply more
    # trusted or timely sources.
    rss_sources: Dict[str, float] = field(default_factory=lambda: {
        "businesswire.com": 1.0,
        "globenewswire.com": 1.0,
        "prnewswire.com": 1.0,
        "accesswire.com": 1.0,
    })

    def __post_init__(self) -> None:
        # Resolve data and output directories relative to the project root
        self.data_dir = self.base_dir / "data"
        self.out_dir = self.base_dir / "out"

        # Ensure directories exist at runtime. These directories are not
        # committed to version control but must exist on disk for the bot
        # to persist its state and artifacts.
        for directory in [
            self.data_dir,
            self.data_dir / "raw",
            self.data_dir / "processed",
            self.data_dir / "logs",
            self.data_dir / "analyzer",
            self.out_dir,
            self.out_dir / "charts",
        ]:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception:
                # Directory creation failures should never stop the bot
                pass


def get_settings() -> Settings:
    """Return a singleton instance of :class:`Settings`.

    This function caches the settings instance on the module to avoid
    reloading environment variables multiple times. Subsequent calls
    return the same instance.
    """
    global _cached_settings
    try:
        return _cached_settings  # type: ignore[name-defined]
    except NameError:
        _cached_settings = Settings()  # type: ignore[assignment]
        return _cached_settings