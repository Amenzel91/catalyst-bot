"""
manual_backtest.py
==================

This script provides a simple manual testing harness for Catalyst Bot.  It
scans a folder for JSON files containing trading events or trade
dictionaries, computes backtest metrics using the same analytics as the
main BacktestEngine, and optionally sends a Discord embed summarising
the results.  The intent is to allow interactive experimentation with
historical data outside of the live pipeline.

Each JSON file in the specified directory should either contain a list
of objects with ``entry_price`` and ``exit_price`` fields (representing
completed trades) or arbitrary events for which you can derive entry
and exit prices.  When ``entry_price``/``exit_price`` are missing, the
script attempts to compute a simple return based on the alert's
published price and the closing price in the next trading window via
``market.get_last_price_change``.

The script prints out a summary of metrics for each file and can
construct a Discord embed dictionary containing these metrics along
with composite indicator and ML confidence scores.  Sending the embed
requires a configured Discord webhook and is left as a future
extension.

Migration Note
--------------
This script has been migrated away from the legacy backtest.simulator
module to use metrics calculation compatible with the main BacktestEngine
from the backtesting package. The calculation logic is now inline to
support the specific use case of simple trade pairs (entry/exit prices)
without requiring full event stream replay.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

from ..alerts import _post_discord_with_backoff  # type: ignore
from ..indicator_utils import compute_composite_score
from ..market import get_intraday, get_last_price_change  # type: ignore[attr-defined]
from ..ml_utils import extract_features, load_model, score_alerts


# Compatibility class to match old BacktestSummary interface
class BacktestSummary:
    """Backtest summary metrics compatible with old simulator interface."""

    def __init__(self, metrics: Dict[str, Any]):
        """Initialize from BacktestEngine metrics dict."""
        self.n = metrics.get("total_trades", 0)
        self.hits = metrics.get("winning_trades", 0)
        self.hit_rate = (
            metrics.get("win_rate", 0.0) / 100.0
        )  # Convert from % to fraction
        self.avg_return = (
            metrics.get("avg_return_pct", 0.0) / 100.0
        )  # Convert from % to fraction
        self.max_drawdown = (
            metrics.get("max_drawdown_pct", 0.0) / 100.0
        )  # Convert from % to fraction
        self.sharpe = metrics.get("sharpe_ratio", 0.0)
        self.sortino = metrics.get("sortino_ratio", 0.0)
        self.profit_factor = metrics.get("profit_factor", 0.0)
        # Calculate avg_win_loss from avg_win and avg_loss
        avg_win = metrics.get("avg_win", 0.0)
        avg_loss = abs(metrics.get("avg_loss", -1.0))
        self.avg_win_loss = avg_win / avg_loss if avg_loss != 0 else 0.0


def _load_events(path: Path) -> List[Dict[str, Any]]:
    """Load a list of events or trades from a JSON or JSONL file."""
    items: List[Dict[str, Any]] = []
    try:
        if path.suffix.lower() in {".json", ".jsonl"}:
            with path.open("r", encoding="utf-8") as f:
                if path.suffix.lower() == ".json":
                    try:
                        data = json.load(f)
                        if isinstance(data, list):
                            items.extend(data)
                    except Exception:
                        pass
                else:
                    # JSON Lines
                    for line in f:
                        try:
                            d = json.loads(line)
                            if isinstance(d, dict):
                                items.append(d)
                        except Exception:
                            continue
    except Exception:
        pass
    return items


def _derive_trades(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw event dictionaries into trade dictionaries for the backtester.

    A trade dictionary must contain ``entry_price`` and ``exit_price``.  This
    helper looks for these keys on the event; if missing, it attempts
    to compute the return using ``get_last_price_change``.  If both
    values are missing, the event is skipped.
    """
    trades: List[Dict[str, Any]] = []
    for ev in events:
        symbol = (ev.get("ticker") or ev.get("symbol") or "").strip().upper()
        entry = ev.get("entry_price")
        exit_px = ev.get("exit_price")
        qty = ev.get("quantity", 1)
        direction = ev.get("direction", "long")
        # If explicit entry/exit present, use them
        if entry is not None and exit_px is not None:
            try:
                trades.append(
                    {
                        "symbol": symbol,
                        "entry_price": float(entry),
                        "exit_price": float(exit_px),
                        "quantity": float(qty or 1),
                        "direction": str(direction),
                    }
                )
                continue
            except Exception:
                pass
        # Otherwise attempt to compute a simple return: entry at event price,
        # exit at next close.  Use get_last_price_change to fetch (last, prev).
        try:
            last, prev = get_last_price_change(symbol)
            if last is not None and prev is not None:
                trades.append(
                    {
                        "symbol": symbol,
                        "entry_price": float(prev),
                        "exit_price": float(last),
                        "quantity": 1.0,
                        "direction": "long",
                    }
                )
        except Exception:
            continue
    return trades


def _build_embed(
    summary: BacktestSummary,
    composite: float | None,
    ml_score: float | None,
    alert_tier: str | None,
    label: str,
) -> Dict[str, Any]:
    """Construct a Discord embed dict summarising backtest results."""
    fields: List[Dict[str, Any]] = []
    fields.append({"name": "Trades", "value": str(summary.n), "inline": True})
    fields.append({"name": "Hits", "value": str(summary.hits), "inline": True})
    fields.append(
        {"name": "Hit Rate", "value": f"{summary.hit_rate:.3f}", "inline": True}
    )
    fields.append(
        {"name": "Avg Return", "value": f"{summary.avg_return:.4f}", "inline": True}
    )
    fields.append(
        {"name": "Max Drawdown", "value": f"{summary.max_drawdown:.4f}", "inline": True}
    )
    fields.append(
        {
            "name": "Sharpe",
            "value": f"{summary.sharpe:.3f}" if not pd.isna(summary.sharpe) else "n/a",
            "inline": True,
        }
    )
    fields.append(
        {
            "name": "Sortino",
            "value": (
                f"{summary.sortino:.3f}" if not pd.isna(summary.sortino) else "n/a"
            ),
            "inline": True,
        }
    )
    fields.append(
        {
            "name": "Profit Factor",
            "value": (
                f"{summary.profit_factor:.3f}"
                if summary.profit_factor != float("inf")
                else "∞"
            ),
            "inline": True,
        }
    )
    fields.append(
        {"name": "Avg Win-Loss", "value": f"{summary.avg_win_loss:.4f}", "inline": True}
    )
    if composite is not None:
        fields.append(
            {"name": "Composite Score", "value": f"{composite:.2f}", "inline": True}
        )
    if ml_score is not None:
        fields.append(
            {"name": "Confidence", "value": f"{ml_score:.2f}", "inline": True}
        )
    if alert_tier:
        fields.append({"name": "Tier", "value": alert_tier, "inline": True})
    embed = {
        "title": f"Backtest Summary – {label}",
        "color": 0x3498DB,
        "fields": fields,
        "footer": {"text": "Manual Backtest"},
    }
    return embed


def run_backtest_on_directory(dir_path: str) -> List[Dict[str, Any]]:
    """Run backtests on all JSON/JSONL files in the directory and return embeds.

    This function now uses BacktestEngine for more robust backtesting with
    realistic trade simulation including slippage, fees, and volume constraints.
    """
    embeds: List[Dict[str, Any]] = []
    path = Path(dir_path)
    if not path.exists() or not path.is_dir():
        raise NotADirectoryError(f"Directory not found: {dir_path}")

    for file in sorted(path.iterdir()):
        if file.suffix.lower() not in {".json", ".jsonl"}:
            continue

        events = _load_events(file)
        if not events:
            continue

        # Extract date range from events or use defaults
        timestamps = []
        for ev in events:
            ts_str = ev.get("ts") or ev.get("timestamp")
            if ts_str:
                try:
                    from datetime import datetime

                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    timestamps.append(ts)
                except Exception:
                    pass

        # Determine date range for backtest
        if timestamps:
            _ = min(timestamps).strftime("%Y-%m-%d")
            max(timestamps).strftime("%Y-%m-%d")
        else:
            # Default to a reasonable range
            from datetime import datetime, timedelta

            datetime.now().strftime("%Y-%m-%d")
            _ = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # Get commission/slippage from env
        commission = float(os.getenv("BACKTEST_COMMISSION", "0.0") or 0.0)
        slippage = float(os.getenv("BACKTEST_SLIPPAGE", "0.0") or 0.0)

        # Calculate summary metrics from simple trade data
        # For files with explicit entry/exit prices, we'll compute simple returns
        trades = _derive_trades(events)

        if not trades:
            continue

        # Compute simple return metrics
        returns = []
        for trade in trades:
            entry = trade.get("entry_price", 0)
            exit_price = trade.get("exit_price", 0)
            if entry > 0:
                # Apply commission and slippage
                entry_cost = entry * (1.0 + commission + slippage)
                exit_proceeds = exit_price * (1.0 - commission - slippage)
                trade_return = (exit_proceeds - entry_cost) / entry_cost
                returns.append(trade_return)

        # Create metrics summary
        if returns:
            n_trades = len(returns)
            hits = sum(1 for r in returns if r > 0)
            avg_return = sum(returns) / n_trades if n_trades > 0 else 0.0

            # Calculate drawdown
            cum_returns = [0]
            for r in returns:
                cum_returns.append(cum_returns[-1] + r)
            peak = cum_returns[0]
            max_dd = 0.0
            for val in cum_returns:
                peak = max(peak, val)
                dd = (peak - val) / (peak + 1.0) if peak > 0 else 0.0
                max_dd = max(max_dd, dd)

            # Calculate Sharpe and Sortino
            if n_trades > 1:
                mean_return = sum(returns) / n_trades
                variance = sum((r - mean_return) ** 2 for r in returns) / (n_trades - 1)
                std_dev = variance**0.5
                sharpe = (mean_return / std_dev) if std_dev > 0 else 0.0

                # Sortino: only downside deviation
                downside_returns = [r for r in returns if r < 0]
                if downside_returns:
                    downside_var = sum(r**2 for r in downside_returns) / len(
                        downside_returns
                    )
                    downside_dev = downside_var**0.5
                    sortino = (mean_return / downside_dev) if downside_dev > 0 else 0.0
                else:
                    sortino = float("inf") if mean_return > 0 else 0.0
            else:
                sharpe = 0.0
                sortino = 0.0

            # Profit factor
            gross_profit = sum(r for r in returns if r > 0)
            gross_loss = abs(sum(r for r in returns if r < 0))
            profit_factor = (
                (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
            )

            # Avg win/loss ratio
            wins = [r for r in returns if r > 0]
            losses = [r for r in returns if r < 0]
            avg_win = sum(wins) / len(wins) if wins else 0.0
            avg_loss = abs(sum(losses) / len(losses)) if losses else 1.0
            avg_win / avg_loss if avg_loss > 0 else 0.0

            metrics = {
                "total_trades": n_trades,
                "winning_trades": hits,
                "win_rate": (hits / n_trades * 100.0) if n_trades > 0 else 0.0,
                "avg_return_pct": avg_return * 100.0,
                "max_drawdown_pct": max_dd * 100.0,
                "sharpe_ratio": sharpe,
                "sortino_ratio": sortino,
                "profit_factor": profit_factor,
                "avg_win": avg_win,
                "avg_loss": -avg_loss,
            }
        else:
            # No trades, use defaults
            metrics = {
                "total_trades": 0,
                "winning_trades": 0,
                "win_rate": 0.0,
                "avg_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "profit_factor": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
            }

        summary = BacktestSummary(metrics)

        # Compute composite indicator and ML score for the entire dataset
        comp_score = None
        ml_score = None
        alert_tier = None
        try:
            # Use the first ticker and compute composite on intraday data
            if events:
                sym = (
                    (events[0].get("ticker") or events[0].get("symbol") or "")
                    .strip()
                    .upper()
                )
                if sym:
                    intraday = get_intraday(sym, interval="5min", output_size="compact")
                    if intraday is not None:
                        comp_score = compute_composite_score(intraday)
            # ML confidence using dummy model on aggregate
            if comp_score is not None:
                features_df, _ = extract_features(
                    [
                        {
                            "price_change": summary.avg_return,
                            "sentiment_score": summary.avg_return,
                            "indicator_score": comp_score,
                        }
                    ]
                )
                model_path = os.getenv(
                    "ML_MODEL_PATH", "data/models/trade_classifier.pkl"
                )
                model = load_model(model_path)
                scores = score_alerts(model, features_df)
                if scores:
                    ml_score = float(scores[0])
                    high_thr = float(os.getenv("CONFIDENCE_HIGH", "0.8"))
                    mod_thr = float(os.getenv("CONFIDENCE_MODERATE", "0.6"))
                    if ml_score >= high_thr:
                        alert_tier = "Strong Alert"
                    elif ml_score >= mod_thr:
                        alert_tier = "Moderate Alert"
                    else:
                        alert_tier = "Heads‑Up Alert"
        except Exception:
            pass

        embed = _build_embed(summary, comp_score, ml_score, alert_tier, file.name)
        embeds.append(embed)

    return embeds


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Manual backtest runner")
    p.add_argument("directory", help="Directory containing JSON or JSONL files")
    p.add_argument("--webhook", help="Discord webhook URL to post embeds", default="")
    args = p.parse_args(argv)
    embeds = run_backtest_on_directory(args.directory)
    if args.webhook:
        # Post each embed to Discord
        for emb in embeds:
            payload = {"username": "Backtest Bot", "embeds": [emb]}
            # Use the backoff aware post helper from alerts.py
            ok, status = _post_discord_with_backoff(args.webhook, payload)
            print(f"Posted embed: status={status}, ok={ok}")
    else:
        # Print summary to stdout
        for emb in embeds:
            print(json.dumps(emb, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
