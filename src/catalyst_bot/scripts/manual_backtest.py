"""
manual_backtest.py
==================

This script provides a simple manual testing harness for Catalyst Bot.  It
scans a folder for JSON files containing trading events or trade
dictionaries, runs backtests on them using the bot’s backtesting engine,
computes performance metrics and indicator scores, and optionally sends
a Discord embed summarising the results.  The intent is to allow
interactive experimentation with historical data outside of the live
pipeline.

Each JSON file in the specified directory should either contain a list
of objects with ``entry_price`` and ``exit_price`` fields (representing
completed trades) or arbitrary events for which you can derive entry
and exit prices.  When ``entry_price``/``exit_price`` are missing, the
script attempts to compute a simple return based on the alert’s
published price and the closing price in the next trading window via
``market.get_last_price_change``.

The script prints out a summary of metrics for each file and can
construct a Discord embed dictionary containing these metrics along
with composite indicator and ML confidence scores.  Sending the embed
requires a configured Discord webhook and is left as a future
extension.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from ..backtest.simulator import simulate_trades
from ..backtest.metrics import summarize_returns, BacktestSummary
from ..indicator_utils import compute_composite_score
from ..ml_utils import extract_features, load_model, score_alerts
from ..market import get_intraday, get_last_price_change  # type: ignore[attr-defined]
from ..alerts import _post_discord_with_backoff  # type: ignore


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


def _build_embed(summary: BacktestSummary, composite: float | None, ml_score: float | None, alert_tier: str | None, label: str) -> Dict[str, Any]:
    """Construct a Discord embed dict summarising backtest results."""
    fields: List[Dict[str, Any]] = []
    fields.append({"name": "Trades", "value": str(summary.n), "inline": True})
    fields.append({"name": "Hits", "value": str(summary.hits), "inline": True})
    fields.append({"name": "Hit Rate", "value": f"{summary.hit_rate:.3f}", "inline": True})
    fields.append({"name": "Avg Return", "value": f"{summary.avg_return:.4f}", "inline": True})
    fields.append({"name": "Max Drawdown", "value": f"{summary.max_drawdown:.4f}", "inline": True})
    fields.append({"name": "Sharpe", "value": f"{summary.sharpe:.3f}" if not pd.isna(summary.sharpe) else "n/a", "inline": True})
    fields.append({"name": "Sortino", "value": f"{summary.sortino:.3f}" if not pd.isna(summary.sortino) else "n/a", "inline": True})
    fields.append({"name": "Profit Factor", "value": f"{summary.profit_factor:.3f}" if summary.profit_factor != float('inf') else "∞", "inline": True})
    fields.append({"name": "Avg Win-Loss", "value": f"{summary.avg_win_loss:.4f}", "inline": True})
    if composite is not None:
        fields.append({"name": "Composite Score", "value": f"{composite:.2f}", "inline": True})
    if ml_score is not None:
        fields.append({"name": "Confidence", "value": f"{ml_score:.2f}", "inline": True})
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
    """Run backtests on all JSON/JSONL files in the directory and return embeds."""
    embeds: List[Dict[str, Any]] = []
    path = Path(dir_path)
    if not path.exists() or not path.is_dir():
        raise NotADirectoryError(f"Directory not found: {dir_path}")
    for file in sorted(path.iterdir()):
        if file.suffix.lower() not in {".json", ".jsonl"}:
            continue
        events = _load_events(file)
        trades = _derive_trades(events)
        # Commission/slippage from env or defaults
        commission = float(os.getenv("BACKTEST_COMMISSION", "0.0") or 0.0)
        slippage = float(os.getenv("BACKTEST_SLIPPAGE", "0.0") or 0.0)
        try:
            results_df, summary = simulate_trades(trades, commission=commission, slippage=slippage)
        except Exception:
            # If simulation fails, summarise manually using returns only
            rets = [((t.get("exit_price") or 0) - (t.get("entry_price") or 0)) / (t.get("entry_price") or 1) for t in trades]
            summary = summarize_returns(rets)
        # Compute composite indicator and ML score for the entire dataset
        comp_score = None
        ml_score = None
        alert_tier = None
        try:
            # Use the first ticker and compute composite on intraday data
            if events:
                sym = (events[0].get("ticker") or events[0].get("symbol") or "").strip().upper()
                if sym:
                    intraday = get_intraday(sym, interval="5min", output_size="compact")
                    if intraday is not None:
                        comp_score = compute_composite_score(intraday)
            # ML confidence using dummy model on aggregate
            if comp_score is not None:
                features_df, _ = extract_features([
                    {
                        "price_change": summary.avg_return,
                        "sentiment_score": summary.avg_return,
                        "indicator_score": comp_score,
                    }
                ])
                model_path = os.getenv("ML_MODEL_PATH", "data/models/trade_classifier.pkl")
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