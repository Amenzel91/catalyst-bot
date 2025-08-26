import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


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
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Behavior / thresholds
    price_ceiling: float = float(os.getenv("PRICE_CEILING", "10"))
    loop_seconds: int = int(os.getenv("LOOP_SECONDS", "60"))

    # Feature flags
    feature_record_only: bool = _b("FEATURE_RECORD_ONLY", False)
    feature_alerts: bool = _b("FEATURE_ALERTS", True)
    feature_verbose_logging: bool = _b("FEATURE_VERBOSE_LOGGING", True)

    # Misc
    tz: str = os.getenv("TZ", "America/Chicago")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

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

    @property
    def discord_webhook(self) -> str:
        return self.discord_webhook_url


SETTINGS = Settings()


def get_settings() -> Settings:
    return SETTINGS
