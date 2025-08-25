from dataclasses import dataclass
import os

def _b(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "y", "on"}

@dataclass(frozen=True)
class Settings:
    # API keys / tokens
    alpha_key: str = os.getenv("ALPHAVANTAGE_API_KEY", "")
    finviz_cookie: str = os.getenv("FINVIZ_AUTH_TOKEN", "")
    discord_webhook: str = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Behavior / thresholds
    price_ceiling: float = float(os.getenv("PRICE_CEILING", "10"))
    loop_seconds: int = int(os.getenv("LOOP_SECONDS", "60"))

    # Feature flags
    feature_record_only: bool = _b("FEATURE_RECORD_ONLY", False)
    feature_alerts: bool = _b("FEATURE_ALERTS", True)
    feature_verbose: bool = _b("FEATURE_VERBOSE_LOGGING", True)

    # Misc
    tz: str = os.getenv("TZ", "America/Chicago")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

# Modern access
SETTINGS = Settings()

# Back-compat shim expected by existing modules/tests
def get_settings() -> Settings:
    """
    Backwards-compatible accessor so legacy code can do:
        from catalyst_bot.config import get_settings
        settings = get_settings()
    """
    return SETTINGS
