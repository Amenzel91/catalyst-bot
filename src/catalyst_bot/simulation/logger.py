"""
SimulationLogger - Dual-format logging for simulation analysis.

Outputs:
- JSONL file: Machine-readable, structured events for LLM analysis
- Markdown file: Human-readable summary report

Usage:
    from catalyst_bot.simulation import SimulationLogger

    logger = SimulationLogger(
        run_id="sim_abc123",
        log_dir=Path("data/logs/simulation"),
        simulation_date="2024-11-12"
    )

    # Log events during simulation
    logger.log_alert(ticker="AAPL", headline="...", ...)
    logger.log_trade(ticker="AAPL", side="buy", ...)

    # Finalize report
    logger.finalize(portfolio_stats={...})
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


log = logging.getLogger(__name__)


class Severity(Enum):
    """Severity levels for simulation events."""

    CRITICAL = "CRITICAL"  # Breaks simulation or requires immediate attention
    WARNING = "WARNING"  # Unexpected behavior but continues
    NOTICE = "NOTICE"  # Informational, worth noting


class SimulationLogger:
    """
    Dual-format logger for simulation runs.

    Creates:
    - {run_id}.jsonl: Line-by-line JSON events
    - {run_id}.md: Human-readable markdown summary
    """

    def __init__(
        self,
        run_id: str,
        log_dir: Path,
        simulation_date: str,
    ):
        """
        Initialize the simulation logger.

        Args:
            run_id: Unique identifier for this simulation run
            log_dir: Directory to write log files
            simulation_date: Date being simulated (YYYY-MM-DD)
        """
        self.run_id = run_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.simulation_date = simulation_date

        # File paths
        self.jsonl_path = self.log_dir / f"{run_id}.jsonl"
        self.md_path = self.log_dir / f"{run_id}.md"

        # Tracking for summary
        self.events: List[Dict] = []
        self.alerts_fired: List[Dict] = []
        self.trades_executed: List[Dict] = []
        self.warnings: List[Dict] = []
        self.errors: List[Dict] = []
        self.skipped_tickers: List[Dict] = []
        self.price_updates: int = 0
        self.news_events: int = 0
        self.sec_events: int = 0

        # Timestamps
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None

        # Initialize files
        self._init_files()

    def _init_files(self) -> None:
        """Initialize log files with headers."""
        # Write markdown header
        with open(self.md_path, "w") as f:
            f.write(f"# Simulation Report: {self.run_id}\n\n")
            f.write(f"**Date Simulated:** {self.simulation_date}\n")
            f.write(f"**Run Started:** {self.start_time.isoformat()}\n\n")
            f.write("---\n\n")

        # Create empty JSONL file
        with open(self.jsonl_path, "w") as f:
            pass  # Just create the file

    def log_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        severity: Optional[Severity] = None,
        sim_time: Optional[datetime] = None,
    ) -> None:
        """
        Log a simulation event.

        Args:
            event_type: Type of event (alert, trade, skip, error, etc.)
            data: Event data
            severity: Optional severity level
            sim_time: Simulation time when event occurred
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sim_time": sim_time.isoformat() if sim_time else None,
            "run_id": self.run_id,
            "event_type": event_type,
            "severity": severity.value if severity else None,
            **data,
        }

        # Write to JSONL
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(event, cls=DateTimeEncoder) + "\n")

        # Track for summary
        self.events.append(event)

        if event_type == "alert":
            self.alerts_fired.append(event)
        elif event_type == "trade":
            self.trades_executed.append(event)
        elif event_type == "skip":
            self.skipped_tickers.append(event)
        elif event_type == "price_update":
            self.price_updates += 1
        elif event_type == "news":
            self.news_events += 1
        elif event_type == "sec_filing":
            self.sec_events += 1
        elif severity == Severity.WARNING:
            self.warnings.append(event)
        elif severity == Severity.CRITICAL:
            self.errors.append(event)

    def log_alert(
        self,
        ticker: str,
        title: Optional[str] = None,
        headline: Optional[str] = None,
        classification: Optional[str] = None,
        confidence: Optional[float] = None,
        sim_time: Optional[datetime] = None,
        score: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Log an alert that was fired.

        Accepts either 'title' or 'headline' for the alert text.
        """
        # Use title if headline not provided (alerts.py uses title=)
        alert_headline = headline or title or ""

        self.log_event(
            "alert",
            {
                "ticker": ticker,
                "headline": alert_headline,
                "classification": classification or "unknown",
                "confidence": confidence or 0.0,
                "score": score,
                **kwargs,
            },
            sim_time=sim_time,
        )

    def log_trade(
        self,
        ticker: str,
        side: str,
        quantity: int,
        price: float,
        sim_time: datetime,
        order_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log a trade execution."""
        self.log_event(
            "trade",
            {
                "ticker": ticker,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_id": order_id,
                **kwargs,
            },
            sim_time=sim_time,
        )

    def log_skip(
        self,
        ticker: str,
        reason: str,
        sim_time: Optional[datetime] = None,
    ) -> None:
        """Log a skipped ticker with reason."""
        self.log_event(
            "skip",
            {"ticker": ticker, "reason": reason},
            severity=Severity.WARNING,
            sim_time=sim_time,
        )

    def log_price_update(
        self,
        ticker: str,
        price: float,
        volume: Optional[int] = None,
        sim_time: Optional[datetime] = None,
    ) -> None:
        """Log a price update event."""
        self.log_event(
            "price_update",
            {"ticker": ticker, "price": price, "volume": volume},
            sim_time=sim_time,
        )

    def log_news(
        self,
        news_id: str,
        title: str,
        ticker: Optional[str] = None,
        sim_time: Optional[datetime] = None,
    ) -> None:
        """Log a news event."""
        self.log_event(
            "news",
            {"news_id": news_id, "title": title[:100], "ticker": ticker},
            sim_time=sim_time,
        )

    def log_sec_filing(
        self,
        ticker: str,
        form_type: str,
        sim_time: Optional[datetime] = None,
    ) -> None:
        """Log an SEC filing event."""
        self.log_event(
            "sec_filing",
            {"ticker": ticker, "form_type": form_type},
            sim_time=sim_time,
        )

    def log_warning(self, message: str, context: Optional[Dict] = None) -> None:
        """Log a warning."""
        self.log_event(
            "warning",
            {"message": message, **(context or {})},
            severity=Severity.WARNING,
        )

    def log_error(self, message: str, context: Optional[Dict] = None) -> None:
        """Log a critical error."""
        self.log_event(
            "error",
            {"message": message, **(context or {})},
            severity=Severity.CRITICAL,
        )

    def log_info(self, message: str, context: Optional[Dict] = None) -> None:
        """Log an informational event."""
        self.log_event(
            "info",
            {"message": message, **(context or {})},
            severity=Severity.NOTICE,
        )

    def finalize(self, portfolio_stats: Dict[str, Any]) -> None:
        """Write final summary to markdown file."""
        self.end_time = datetime.now(timezone.utc)
        duration = (self.end_time - self.start_time).total_seconds()

        with open(self.md_path, "a") as f:
            # Quick Glance Section
            f.write("## Quick Glance\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Duration | {duration:.1f}s |\n")
            f.write(f"| Events Processed | {len(self.events)} |\n")
            f.write(f"| Price Updates | {self.price_updates} |\n")
            f.write(f"| News Events | {self.news_events} |\n")
            f.write(f"| SEC Filings | {self.sec_events} |\n")
            f.write(f"| Alerts Fired | {len(self.alerts_fired)} |\n")
            f.write(f"| Trades Executed | {len(self.trades_executed)} |\n")
            f.write(f"| Tickers Skipped | {len(self.skipped_tickers)} |\n")
            f.write(f"| Warnings | {len(self.warnings)} |\n")
            f.write(f"| Errors | {len(self.errors)} |\n")
            f.write("\n")

            # Errors Section (if any)
            if self.errors:
                f.write("## Errors (CRITICAL)\n\n")
                for error in self.errors:
                    f.write(f"- **{error.get('message', 'Unknown error')}**\n")
                    ctx = {
                        k: v
                        for k, v in error.items()
                        if k
                        not in (
                            "message",
                            "timestamp",
                            "sim_time",
                            "run_id",
                            "event_type",
                            "severity",
                        )
                    }
                    if ctx:
                        f.write(f"  - Context: `{ctx}`\n")
                f.write("\n")

            # Warnings Section (if any)
            if self.warnings:
                f.write("## Warnings\n\n")
                for warning in self.warnings[:20]:  # Limit to 20
                    f.write(f"- {warning.get('message', 'Unknown warning')}\n")
                if len(self.warnings) > 20:
                    f.write(f"- ... and {len(self.warnings) - 20} more\n")
                f.write("\n")

            # Skipped Tickers
            if self.skipped_tickers:
                f.write("## Skipped Tickers\n\n")
                reasons: Dict[str, int] = {}
                for skip in self.skipped_tickers:
                    reason = skip.get("reason", "Unknown")
                    reasons[reason] = reasons.get(reason, 0) + 1

                f.write("| Reason | Count |\n")
                f.write("|--------|-------|\n")
                for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                    f.write(f"| {reason} | {count} |\n")
                f.write("\n")

            # Alerts Summary
            if self.alerts_fired:
                f.write("## Alerts Fired\n\n")
                f.write("| Time | Ticker | Classification | Score | Headline |\n")
                f.write("|------|--------|----------------|-------|----------|\n")
                for alert in self.alerts_fired[:50]:  # Limit to 50
                    sim_time = alert.get("sim_time", "")
                    if sim_time and len(sim_time) > 11:
                        sim_time = sim_time[11:19]  # Extract HH:MM:SS
                    headline = alert.get("headline", "")[:40]
                    score = alert.get("score", "")
                    score_str = (
                        f"{score:.1f}" if isinstance(score, (int, float)) else ""
                    )
                    f.write(
                        f"| {sim_time} | {alert.get('ticker', '')} | "
                        f"{alert.get('classification', '')} | {score_str} | "
                        f"{headline}... |\n"
                    )
                if len(self.alerts_fired) > 50:
                    f.write(f"\n*... and {len(self.alerts_fired) - 50} more alerts*\n")
                f.write("\n")

            # Trades Summary
            if self.trades_executed:
                f.write("## Trades Executed\n\n")
                f.write("| Time | Ticker | Side | Qty | Price |\n")
                f.write("|------|--------|------|-----|-------|\n")
                for trade in self.trades_executed[:50]:
                    sim_time = trade.get("sim_time", "")
                    if sim_time and len(sim_time) > 11:
                        sim_time = sim_time[11:19]
                    f.write(
                        f"| {sim_time} | {trade.get('ticker', '')} | "
                        f"{trade.get('side', '')} | {trade.get('quantity', '')} | "
                        f"${trade.get('price', 0):.2f} |\n"
                    )
                f.write("\n")

            # Portfolio Summary
            f.write("## Portfolio Summary\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(
                f"| Starting Cash | ${portfolio_stats.get('starting_cash', 0):,.2f} |\n"
            )
            f.write(
                f"| Final Value | ${portfolio_stats.get('total_value', 0):,.2f} |\n"
            )
            total_return = portfolio_stats.get("total_return", 0)
            return_pct = portfolio_stats.get("total_return_pct", 0)
            f.write(f"| Return | ${total_return:,.2f} ({return_pct:.2f}%) |\n")
            f.write(f"| Total Trades | {portfolio_stats.get('total_trades', 0)} |\n")
            f.write(f"| Win Rate | {portfolio_stats.get('win_rate', 0):.1f}% |\n")
            f.write(
                f"| Max Drawdown | {portfolio_stats.get('max_drawdown_pct', 0):.2f}% |\n"
            )
            f.write("\n")

            f.write("---\n")
            f.write(f"*Report generated at {self.end_time.isoformat()}*\n")

        log.info(f"Simulation report written to {self.md_path}")

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of logged events."""
        return {
            "run_id": self.run_id,
            "simulation_date": self.simulation_date,
            "total_events": len(self.events),
            "price_updates": self.price_updates,
            "news_events": self.news_events,
            "sec_events": self.sec_events,
            "alerts_fired": len(self.alerts_fired),
            "trades_executed": len(self.trades_executed),
            "tickers_skipped": len(self.skipped_tickers),
            "warnings": len(self.warnings),
            "errors": len(self.errors),
        }
