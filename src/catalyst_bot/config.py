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
    finviz_auth_token: str = os.getenv("FINVIZ_AUTH_TOKEN", "")

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

    # Optional explicit path for analyzer summary markdown to post
    admin_summary_path: Optional[str] = os.getenv("ADMIN_SUMMARY_PATH", None)

    # Misc
    tz: str = os.getenv("TZ", "America/Chicago")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    analyzer_utc_hour: int = int(os.getenv("ANALYZER_UTC_HOUR", "21"))
    analyzer_utc_minute: int = int(os.getenv("ANALYZER_UTC_MINUTE", "30"))

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
