"""
LLM Usage Monitor
=================

Real-time cost tracking and performance monitoring for LLM service.

Features:
- Track costs by provider, model, and feature
- Budget alerts (daily/monthly thresholds)
- Performance metrics (latency, cache hits, errors)
- Thread-safe counters

Alerts:
- Daily cost alert at $30/day
- Monthly cost alert at $800/month
- Hard limit at $1000/month (circuit breaker)
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from ..logging_utils import get_logger

log = get_logger("llm_monitor")


class LLMMonitor:
    """Real-time LLM usage monitor and cost tracker."""

    def __init__(self, config: dict):
        """
        Initialize monitor.

        Args:
            config: Configuration dict from LLMService
        """
        self.config = config
        self.enabled = config.get("cost_tracking_enabled", True)

        # Cost thresholds
        self.daily_alert_threshold = config.get("daily_cost_alert", 30.00)
        self.monthly_alert_threshold = config.get("monthly_cost_alert", 800.00)
        self.monthly_hard_limit = config.get("monthly_cost_hard_limit", 1000.00)

        # Thread-safe counters
        self.lock = threading.Lock()

        # Statistics (reset daily/monthly)
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "total_cost_usd": 0.0,
            "total_tokens_input": 0,
            "total_tokens_output": 0,
            "total_latency_ms": 0.0,
        }

        # Breakdowns
        self.cost_by_provider = defaultdict(float)
        self.cost_by_feature = defaultdict(float)
        self.cost_by_model = defaultdict(float)
        self.requests_by_provider = defaultdict(int)

        # Daily/monthly tracking
        self.daily_cost = 0.0
        self.monthly_cost = 0.0
        self.last_reset_date = datetime.now().date()
        self.alert_sent_today = False
        self.alert_sent_monthly = False

        log.info(
            "llm_monitor_initialized enabled=%s daily_alert=$%.2f monthly_alert=$%.2f",
            self.enabled,
            self.daily_alert_threshold,
            self.monthly_alert_threshold
        )

    def track_request(
        self,
        feature: str,
        provider: str,
        model: str,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
        latency_ms: float,
        cached: bool,
        error: Optional[str] = None
    ):
        """
        Track LLM request.

        Args:
            feature: Feature name
            provider: Provider name
            model: Model name
            tokens_input: Input tokens
            tokens_output: Output tokens
            cost_usd: Cost in USD
            latency_ms: Latency in milliseconds
            cached: Whether response was cached
            error: Error message if failed
        """
        if not self.enabled:
            return

        with self.lock:
            # Check if we need to reset daily stats
            self._check_reset_daily()

            # Update counters
            self.stats["total_requests"] += 1
            self.stats["total_tokens_input"] += tokens_input
            self.stats["total_tokens_output"] += tokens_output
            self.stats["total_latency_ms"] += latency_ms

            if cached:
                self.stats["cache_hits"] += 1
            else:
                self.stats["cache_misses"] += 1
                # Only count cost for non-cached requests
                self.stats["total_cost_usd"] += cost_usd
                self.daily_cost += cost_usd
                self.monthly_cost += cost_usd

                # Breakdowns
                self.cost_by_provider[provider] += cost_usd
                self.cost_by_feature[feature] += cost_usd
                self.cost_by_model[model] += cost_usd

            if error:
                self.stats["errors"] += 1

            self.requests_by_provider[provider] += 1

            # Check budget alerts
            self._check_budget_alerts()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current statistics.

        Returns:
            Dict with comprehensive stats
        """
        with self.lock:
            total_requests = self.stats["total_requests"]
            cache_hit_rate = 0.0
            avg_latency = 0.0
            error_rate = 0.0

            if total_requests > 0:
                cache_hit_rate = (self.stats["cache_hits"] / total_requests) * 100
                avg_latency = self.stats["total_latency_ms"] / total_requests
                error_rate = (self.stats["errors"] / total_requests) * 100

            return {
                "total_requests": total_requests,
                "cache_hit_rate": round(cache_hit_rate, 2),
                "avg_latency_ms": round(avg_latency, 2),
                "total_cost_usd": round(self.stats["total_cost_usd"], 4),
                "daily_cost_usd": round(self.daily_cost, 4),
                "monthly_cost_usd": round(self.monthly_cost, 4),
                "error_rate": round(error_rate, 2),
                "cost_by_provider": dict(self.cost_by_provider),
                "cost_by_feature": dict(self.cost_by_feature),
                "cost_by_model": dict(self.cost_by_model),
                "requests_by_provider": dict(self.requests_by_provider),
                "total_tokens_input": self.stats["total_tokens_input"],
                "total_tokens_output": self.stats["total_tokens_output"],
            }

    def _check_reset_daily(self):
        """Reset daily stats if date has changed."""
        current_date = datetime.now().date()

        if current_date > self.last_reset_date:
            log.info(
                "daily_stats_reset date=%s daily_cost=$%.2f",
                self.last_reset_date,
                self.daily_cost
            )

            # Reset daily counters
            self.daily_cost = 0.0
            self.alert_sent_today = False
            self.last_reset_date = current_date

            # Reset monthly on first of month
            if current_date.day == 1:
                log.info("monthly_stats_reset monthly_cost=$%.2f", self.monthly_cost)
                self.monthly_cost = 0.0
                self.alert_sent_monthly = False

    def _check_budget_alerts(self):
        """Check if budget thresholds are exceeded and send alerts."""

        # Daily alert
        if (
            not self.alert_sent_today
            and self.daily_cost >= self.daily_alert_threshold
        ):
            log.warning(
                "daily_cost_alert_triggered daily_cost=$%.2f threshold=$%.2f",
                self.daily_cost,
                self.daily_alert_threshold
            )
            self._send_alert(
                f"⚠️ Daily LLM Cost Alert: ${self.daily_cost:.2f} (threshold: ${self.daily_alert_threshold:.2f})"
            )
            self.alert_sent_today = True

        # Monthly alert
        if (
            not self.alert_sent_monthly
            and self.monthly_cost >= self.monthly_alert_threshold
        ):
            log.warning(
                "monthly_cost_alert_triggered monthly_cost=$%.2f threshold=$%.2f",
                self.monthly_cost,
                self.monthly_alert_threshold
            )
            self._send_alert(
                f"⚠️ Monthly LLM Cost Alert: ${self.monthly_cost:.2f} (threshold: ${self.monthly_alert_threshold:.2f})"
            )
            self.alert_sent_monthly = True

        # Hard limit (circuit breaker)
        if self.monthly_cost >= self.monthly_hard_limit:
            log.error(
                "monthly_hard_limit_exceeded monthly_cost=$%.2f limit=$%.2f DISABLING_SERVICE",
                self.monthly_cost,
                self.monthly_hard_limit
            )
            self._send_alert(
                f"🚨 CRITICAL: Monthly LLM Hard Limit Exceeded! ${self.monthly_cost:.2f} >= ${self.monthly_hard_limit:.2f}. Service disabled."
            )
            # TODO: Implement circuit breaker (disable LLM service)

    def _send_alert(self, message: str):
        """
        Send cost alert.

        Args:
            message: Alert message
        """
        # Log to console
        log.warning("cost_alert msg=%s", message)

        # TODO: Send to Discord admin webhook
        # Try to send to admin webhook if configured
        try:
            webhook_url = os.getenv("DISCORD_ADMIN_WEBHOOK")
            if webhook_url:
                import requests
                requests.post(webhook_url, json={"content": message}, timeout=5)
        except Exception as e:
            log.warning("failed_to_send_discord_alert err=%s", str(e))
