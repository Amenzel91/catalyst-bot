"""
LLM Usage Monitor
==================

Real-time tracking of LLM API usage, costs, and rate limits.

Features:
- Per-provider token counting (input/output)
- Cost calculation based on current pricing
- Daily/monthly aggregates
- Rate limit monitoring
- Cost alerts and warnings
- Persistent logging to JSON

Environment Variables:
* ``LLM_COST_ALERT_DAILY`` – Daily cost alert threshold (default: $5.00)
* ``LLM_COST_ALERT_MONTHLY`` – Monthly cost alert threshold (default: $50.00)
* ``LLM_USAGE_LOG_PATH`` – Custom path for usage log (default: data/logs/llm_usage.jsonl)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_logger = logging.getLogger(__name__)


@dataclass
class LLMUsageEvent:
    """Single LLM API call event."""

    timestamp: str  # ISO 8601 UTC
    provider: str  # "gemini", "anthropic", "local", "ollama"
    model: str  # e.g., "gemini-2.5-flash", "claude-3-haiku"
    operation: str  # e.g., "sec_keyword_extraction", "sentiment_analysis"

    # Token usage
    input_tokens: int
    output_tokens: int
    total_tokens: int

    # Cost (USD)
    input_cost: float
    output_cost: float
    total_cost: float

    # Metadata
    success: bool
    error: Optional[str] = None
    article_length: Optional[int] = None  # chars
    ticker: Optional[str] = None


@dataclass
class ProviderStats:
    """Aggregate statistics for a single provider."""

    provider: str
    model: str

    # Request counts
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Token usage
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0

    # Costs
    total_input_cost: float = 0.0
    total_output_cost: float = 0.0
    total_cost: float = 0.0

    # Rate limits
    requests_last_hour: int = 0
    requests_last_day: int = 0


@dataclass
class UsageSummary:
    """Complete usage summary across all providers."""

    period_start: str  # ISO 8601 UTC
    period_end: str  # ISO 8601 UTC

    # Per-provider stats
    gemini: ProviderStats
    anthropic: ProviderStats
    local: ProviderStats

    # Overall totals
    total_requests: int
    total_tokens: int
    total_cost: float

    # Cost breakdown
    cost_by_provider: Dict[str, float]
    cost_by_operation: Dict[str, float]


# Current Pricing (as of 2025-01)
# Source: https://ai.google.dev/pricing, https://www.anthropic.com/pricing
PRICING = {
    "gemini": {
        "gemini-2.5-flash": {
            "input": 0.000_000_15,  # $0.15 per 1M tokens
            "output": 0.000_000_60,  # $0.60 per 1M tokens
        },
        "gemini-2.0-flash-lite": {  # Agent 2: Add Flash-Lite pricing
            "input": 0.000_000_02,  # $0.02 per 1M tokens
            "output": 0.000_000_10,  # $0.10 per 1M tokens
        },
        "gemini-1.5-flash": {
            "input": 0.000_000_075,  # $0.075 per 1M tokens
            "output": 0.000_000_30,  # $0.30 per 1M tokens
        },
    },
    "anthropic": {
        "claude-3-haiku-20240307": {
            "input": 0.000_000_25,  # $0.25 per 1M tokens
            "output": 0.000_001_25,  # $1.25 per 1M tokens
        },
        "claude-3-5-sonnet-20241022": {
            "input": 0.000_003_00,  # $3.00 per 1M tokens
            "output": 0.000_015_00,  # $15.00 per 1M tokens
        },
    },
    "local": {
        "mistral": {"input": 0.0, "output": 0.0},  # FREE
    },
}


class LLMUsageMonitor:
    """
    Centralized LLM usage tracker.

    Logs all LLM API calls to a JSONL file and provides real-time statistics.
    Automatically calculates costs and warns when approaching budgets.
    """

    def __init__(self, log_path: Optional[Path] = None):
        """
        Initialize usage monitor.

        Agent 4: Enhanced with real-time cost tracking and model availability flags.

        Args:
            log_path: Path to JSONL log file. If None, uses data/logs/llm_usage.jsonl
        """
        import os

        # Determine log path
        if log_path is None:
            custom_path = os.getenv("LLM_USAGE_LOG_PATH")
            if custom_path:
                self.log_path = Path(custom_path)
            else:
                # Default to data/logs/llm_usage.jsonl
                from .config import get_settings
                settings = get_settings()
                self.log_path = settings.data_dir / "logs" / "llm_usage.jsonl"
        else:
            self.log_path = log_path

        # Ensure directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Alert thresholds (USD)
        self.daily_alert_threshold = float(os.getenv("LLM_COST_ALERT_DAILY", "5.00"))
        self.monthly_alert_threshold = float(os.getenv("LLM_COST_ALERT_MONTHLY", "50.00"))

        # Agent 4: Real-time cost accumulator (resets daily)
        self.realtime_cost_today = 0.0
        self.last_reset_day: Optional[str] = None

        # Agent 4: Model availability flags (for cost control)
        self.model_availability = {
            "gemini-2.0-flash-lite": True,
            "gemini-2.5-flash": True,
            "gemini-2.5-pro": True,
            "anthropic": True,
        }

        _logger.info(
            "llm_usage_monitor_initialized log_path=%s daily_alert=$%.2f monthly_alert=$%.2f",
            self.log_path,
            self.daily_alert_threshold,
            self.monthly_alert_threshold,
        )

    def log_usage(
        self,
        provider: str,
        model: str,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        success: bool = True,
        error: Optional[str] = None,
        article_length: Optional[int] = None,
        ticker: Optional[str] = None,
    ) -> LLMUsageEvent:
        """
        Log a single LLM API call.

        Args:
            provider: "gemini", "anthropic", "local"
            model: Model name (e.g., "gemini-2.5-flash")
            operation: Operation type (e.g., "sec_keyword_extraction")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            success: Whether the call succeeded
            error: Error message if failed
            article_length: Article length in characters
            ticker: Stock ticker if applicable

        Returns:
            LLMUsageEvent with calculated costs
        """
        # Calculate costs
        pricing = PRICING.get(provider, {}).get(model, {"input": 0.0, "output": 0.0})
        input_cost = input_tokens * pricing["input"]
        output_cost = output_tokens * pricing["output"]
        total_cost = input_cost + output_cost

        # Create event
        event = LLMUsageEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=provider,
            model=model,
            operation=operation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            success=success,
            error=error,
            article_length=article_length,
            ticker=ticker,
        )

        # Write to log file
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event)) + "\n")
        except Exception as e:
            _logger.warning("llm_usage_log_write_failed err=%s", str(e))

        # Log to console
        _logger.info(
            "llm_usage provider=%s model=%s operation=%s "
            "input_tokens=%d output_tokens=%d cost=$%.6f success=%s",
            provider,
            model,
            operation,
            input_tokens,
            output_tokens,
            total_cost,
            success,
        )

        # Agent 4: Update real-time cost accumulator
        self._update_realtime_cost(total_cost)

        # Check for cost alerts
        self._check_alerts()

        return event

    def _update_realtime_cost(self, cost: float) -> None:
        """
        Update real-time cost accumulator.

        Agent 4: Tracks costs in-memory for instant threshold checks.
        Resets daily at midnight UTC.
        """
        from datetime import datetime, timezone

        # Get current day (YYYY-MM-DD)
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        # Check if new day (reset accumulator)
        if self.last_reset_day != today:
            self.realtime_cost_today = 0.0
            self.last_reset_day = today
            _logger.info("llm_cost_accumulator_reset date=%s", today)

        # Add cost to accumulator
        self.realtime_cost_today += cost

    def check_cost_threshold(self, threshold_name: str = "warn") -> bool:
        """
        Check if real-time cost has exceeded a threshold.

        Agent 4: Instant threshold check without reading log file.

        Parameters
        ----------
        threshold_name : str
            Threshold to check: "warn", "crit", or "emergency"

        Returns
        -------
        bool
            True if threshold exceeded
        """
        from .config import get_settings
        settings = get_settings()

        thresholds = {
            "warn": getattr(settings, "llm_cost_alert_warn", 5.0),
            "crit": getattr(settings, "llm_cost_alert_crit", 10.0),
            "emergency": getattr(settings, "llm_cost_alert_emergency", 20.0),
        }

        threshold_value = thresholds.get(threshold_name, 5.0)
        return self.realtime_cost_today >= threshold_value

    def disable_model(self, model_name: str) -> None:
        """
        Disable a model to prevent further usage.

        Agent 4: Cost control mechanism - prevents expensive model usage
        when thresholds are exceeded.

        Parameters
        ----------
        model_name : str
            Model to disable (e.g., "gemini-2.5-pro", "anthropic")
        """
        if model_name in self.model_availability:
            self.model_availability[model_name] = False
            _logger.warning(
                "llm_model_disabled model=%s reason=cost_threshold",
                model_name,
            )

    def enable_model(self, model_name: str) -> None:
        """
        Re-enable a previously disabled model.

        Agent 4: Manual override to re-enable models after cost review.

        Parameters
        ----------
        model_name : str
            Model to enable (e.g., "gemini-2.5-pro", "anthropic")
        """
        if model_name in self.model_availability:
            self.model_availability[model_name] = True
            _logger.info(
                "llm_model_enabled model=%s",
                model_name,
            )

    def is_model_available(self, model_name: str) -> bool:
        """
        Check if a model is available for use.

        Agent 4: Used by llm_hybrid.py to honor cost-based disabling.

        Parameters
        ----------
        model_name : str
            Model to check

        Returns
        -------
        bool
            True if model is available
        """
        return self.model_availability.get(model_name, True)

    def get_stats(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> UsageSummary:
        """
        Get usage statistics for a time period.

        Args:
            since: Start time (UTC). If None, uses beginning of today.
            until: End time (UTC). If None, uses current time.

        Returns:
            UsageSummary with aggregated statistics
        """
        # Default time range: today
        if since is None:
            now = datetime.now(timezone.utc)
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if until is None:
            until = datetime.now(timezone.utc)

        # Initialize provider stats
        stats_by_provider: Dict[str, ProviderStats] = {
            "gemini": ProviderStats(provider="gemini", model="gemini-2.5-flash"),
            "anthropic": ProviderStats(provider="anthropic", model="claude-3-haiku"),
            "local": ProviderStats(provider="local", model="mistral"),
        }

        cost_by_operation: Dict[str, float] = {}
        total_requests = 0
        total_tokens = 0
        total_cost = 0.0

        # Read and process log file
        if not self.log_path.exists():
            _logger.debug("llm_usage_log_not_found path=%s", self.log_path)
        else:
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            event_data = json.loads(line.strip())
                            event_time = datetime.fromisoformat(event_data["timestamp"])

                            # Filter by time range
                            if event_time < since or event_time > until:
                                continue

                            provider = event_data["provider"]
                            operation = event_data["operation"]

                            # Update provider stats
                            if provider in stats_by_provider:
                                pstats = stats_by_provider[provider]
                                pstats.total_requests += 1
                                if event_data["success"]:
                                    pstats.successful_requests += 1
                                else:
                                    pstats.failed_requests += 1

                                pstats.total_input_tokens += event_data["input_tokens"]
                                pstats.total_output_tokens += event_data["output_tokens"]
                                pstats.total_tokens += event_data["total_tokens"]

                                pstats.total_input_cost += event_data["input_cost"]
                                pstats.total_output_cost += event_data["output_cost"]
                                pstats.total_cost += event_data["total_cost"]

                            # Update operation costs
                            cost_by_operation[operation] = (
                                cost_by_operation.get(operation, 0.0) + event_data["total_cost"]
                            )

                            # Update totals
                            total_requests += 1
                            total_tokens += event_data["total_tokens"]
                            total_cost += event_data["total_cost"]

                        except (json.JSONDecodeError, KeyError, ValueError) as e:
                            _logger.debug("llm_usage_parse_error line=%s err=%s", line[:50], str(e))
            except Exception as e:
                _logger.warning("llm_usage_log_read_failed err=%s", str(e))

        # Build cost_by_provider
        cost_by_provider = {
            provider: pstats.total_cost
            for provider, pstats in stats_by_provider.items()
        }

        return UsageSummary(
            period_start=since.isoformat(),
            period_end=until.isoformat(),
            gemini=stats_by_provider["gemini"],
            anthropic=stats_by_provider["anthropic"],
            local=stats_by_provider["local"],
            total_requests=total_requests,
            total_tokens=total_tokens,
            total_cost=total_cost,
            cost_by_provider=cost_by_provider,
            cost_by_operation=cost_by_operation,
        )

    def get_daily_stats(self) -> UsageSummary:
        """Get stats for today (UTC)."""
        now = datetime.now(timezone.utc)
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_stats(since=since, until=now)

    def get_monthly_stats(self) -> UsageSummary:
        """Get stats for current month (UTC)."""
        now = datetime.now(timezone.utc)
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return self.get_stats(since=since, until=now)

    def _check_alerts(self) -> None:
        """
        Check if usage has exceeded alert thresholds.

        Agent 4: Multi-tier cost monitoring with automatic model disabling.
        """
        # Check daily threshold
        daily_stats = self.get_daily_stats()

        # Agent 4: Multi-tier alerting (warn/crit/emergency)
        from .config import get_settings
        settings = get_settings()

        warn_threshold = getattr(settings, "llm_cost_alert_warn", 5.0)
        crit_threshold = getattr(settings, "llm_cost_alert_crit", 10.0)
        emergency_threshold = getattr(settings, "llm_cost_alert_emergency", 20.0)

        daily_cost = daily_stats.total_cost

        if daily_cost >= emergency_threshold:
            _logger.critical(
                "llm_cost_alert_EMERGENCY cost=$%.2f threshold=$%.2f providers=%s - DISABLING EXPENSIVE MODELS",
                daily_cost,
                emergency_threshold,
                {k: f"${v:.2f}" for k, v in daily_stats.cost_by_provider.items()},
            )
            # Agent 4: Disable Pro and Anthropic models
            self.disable_model("gemini-2.5-pro")
            self.disable_model("anthropic")

        elif daily_cost >= crit_threshold:
            _logger.error(
                "llm_cost_alert_CRITICAL cost=$%.2f threshold=$%.2f providers=%s - DISABLING PRO MODEL",
                daily_cost,
                crit_threshold,
                {k: f"${v:.2f}" for k, v in daily_stats.cost_by_provider.items()},
            )
            # Agent 4: Disable Pro model only
            self.disable_model("gemini-2.5-pro")

        elif daily_cost >= warn_threshold:
            _logger.warning(
                "llm_cost_alert_WARN cost=$%.2f threshold=$%.2f providers=%s",
                daily_cost,
                warn_threshold,
                {k: f"${v:.2f}" for k, v in daily_stats.cost_by_provider.items()},
            )

        # Check monthly threshold (legacy compatibility)
        monthly_stats = self.get_monthly_stats()
        if monthly_stats.total_cost >= self.monthly_alert_threshold:
            _logger.warning(
                "llm_monthly_cost_alert cost=$%.2f threshold=$%.2f providers=%s",
                monthly_stats.total_cost,
                self.monthly_alert_threshold,
                {k: f"${v:.2f}" for k, v in monthly_stats.cost_by_provider.items()},
            )

    def print_summary(self, summary: UsageSummary) -> None:
        """Print a formatted usage summary to console."""
        print("\n" + "=" * 70)
        print("LLM USAGE SUMMARY")
        print("=" * 70)
        print(f"Period: {summary.period_start} to {summary.period_end}")
        print(f"Total Requests: {summary.total_requests}")
        print(f"Total Tokens: {summary.total_tokens:,}")
        print(f"Total Cost: ${summary.total_cost:.4f}")

        print("\n" + "-" * 70)
        print("COST BY PROVIDER:")
        print("-" * 70)
        for provider, cost in summary.cost_by_provider.items():
            if cost > 0:
                pstats = getattr(summary, provider)
                print(f"{provider.capitalize():15s} ${cost:8.4f}  "
                      f"({pstats.total_requests} requests, "
                      f"{pstats.total_tokens:,} tokens)")

        print("\n" + "-" * 70)
        print("COST BY OPERATION:")
        print("-" * 70)
        # Sort by cost descending
        sorted_ops = sorted(
            summary.cost_by_operation.items(),
            key=lambda x: x[1],
            reverse=True
        )
        for operation, cost in sorted_ops[:10]:  # Top 10
            print(f"{operation:30s} ${cost:8.4f}")

        print("\n" + "-" * 70)
        print("PROVIDER DETAILS:")
        print("-" * 70)

        for provider in ["gemini", "anthropic", "local"]:
            pstats = getattr(summary, provider)
            if pstats.total_requests > 0:
                print(f"\n{provider.upper()} ({pstats.model}):")
                print(f"  Requests: {pstats.total_requests} "
                      f"(OK:{pstats.successful_requests} FAIL:{pstats.failed_requests})")
                print(f"  Tokens:   {pstats.total_tokens:,} "
                      f"(in: {pstats.total_input_tokens:,}, out: {pstats.total_output_tokens:,})")
                print(f"  Cost:     ${pstats.total_cost:.4f} "
                      f"(in: ${pstats.total_input_cost:.4f}, out: ${pstats.total_output_cost:.4f})")

        print("\n" + "=" * 70 + "\n")


# Global monitor instance (lazy initialization)
_monitor: Optional[LLMUsageMonitor] = None


def get_monitor() -> LLMUsageMonitor:
    """Get or create the global usage monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = LLMUsageMonitor()
    return _monitor


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Uses rough approximation: ~4 chars per token.
    Add 5% margin for safety.

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    return int(len(text) / 4 * 1.05)
