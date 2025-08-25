from dataclasses import dataclass, field
from typing import Dict
from pathlib import Path
import os

def _b(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "y", "on"}

@dataclass
class Settings:
    # Keys / tokens (names expected by older code/tests)
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

    # --- Paths expected by tests/legacy code ---
    # Allow override of project root via env (rare). Default: current working dir.
    project_root: Path = field(default_factory=lambda: Path(os.getenv("PROJECT_ROOT", os.getcwd())).resolve())
    data_dir: Path = field(default_factory=lambda: (Path(os.getenv("DATA_DIR", "data")).resolve()))
    out_dir: Path = field(default_factory=lambda: (Path(os.getenv("OUT_DIR", "out")).resolve()))

    # Expected by tests: a keyword weight table
    keyword_categories: Dict[str, float] = field(default_factory=lambda: {
        # positive
        "fda approval": 3.2,
        "fda clearance": 3.0,
        "phase 3": 2.5,
        "breakthrough": 2.0,
        "contract award": 2.2,
        "strategic partnership": 1.8,
        "uplisting": 1.5,
        # negative
        "offering": -3.0,
        "dilution": -3.2,
        "going concern": -3.0,
    })

    # Back-compat aliases for any newer modules we added elsewhere
    @property
    def alpha_key(self) -> str:
        return self.alphavantage_api_key

    @property
    def finviz_cookie(self) -> str:
        return self.finviz_auth_token

    @property
    def discord_webhook(self) -> str:
        return self.discord_webhook_url

# Singleton settings
SETTINGS = Settings()

# Back-compat accessor used by legacy modules/tests
def get_settings() -> Settings:
    return SETTINGS
