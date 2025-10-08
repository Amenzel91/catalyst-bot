"""
Backtest Report Generator
==========================

Generate comprehensive backtest reports in multiple formats
(Markdown, HTML, JSON, Discord embed).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logging_utils import get_logger

log = get_logger("backtesting.reports")


def generate_backtest_report(
    results: Dict, output_format: str = "markdown", output_path: Optional[str] = None
) -> str:
    """
    Generate comprehensive backtest report.

    Parameters
    ----------
    results : dict
        Backtest results from BacktestEngine.run_backtest()
    output_format : str
        Format: 'markdown', 'html', 'json', 'discord_embed'
    output_path : str, optional
        Path to save report (if None, returns string)

    Returns
    -------
    str
        Report content or path to saved file
    """
    if output_format == "markdown":
        content = _generate_markdown_report(results)
    elif output_format == "html":
        content = _generate_html_report(results)
    elif output_format == "json":
        content = json.dumps(results, indent=2)
    elif output_format == "discord_embed":
        content = _generate_discord_embed(results)
    else:
        raise ValueError(f"Unknown format: {output_format}")

    # Save to file if path provided
    if output_path:
        Path(output_path).write_text(content, encoding="utf-8")
        log.info("report_saved path=%s format=%s", output_path, output_format)
        return output_path

    return content


def _generate_markdown_report(results: Dict) -> str:
    """Generate Markdown backtest report."""
    metrics = results["metrics"]
    trades = results["trades"]
    params = results["strategy_params"]
    period = results["backtest_period"]

    lines = []
    lines.append("# Backtest Report")
    lines.append("")
    lines.append(f"**Period:** {period['start']} to {period['end']}")
    lines.append(
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Total Return:** {metrics['total_return_pct']:.2f}%")
    lines.append(f"- **Sharpe Ratio:** {metrics.get('sharpe_ratio', 0):.2f}")
    lines.append(f"- **Win Rate:** {metrics['win_rate']:.1f}%")
    lines.append(f"- **Max Drawdown:** {metrics['max_drawdown_pct']:.2f}%")
    lines.append(f"- **Profit Factor:** {metrics.get('profit_factor', 0):.2f}")
    lines.append(f"- **Total Trades:** {metrics['total_trades']}")
    lines.append("")

    # Strategy Parameters
    lines.append("## Strategy Parameters")
    lines.append("")
    for param, value in params.items():
        lines.append(f"- **{param}:** {value}")
    lines.append("")

    # Trade Statistics
    lines.append("## Trade Statistics")
    lines.append("")
    lines.append(f"- **Winning Trades:** {metrics['winning_trades']}")
    lines.append(f"- **Losing Trades:** {metrics['losing_trades']}")
    lines.append(f"- **Average Win:** {metrics['avg_win']:.2f}%")
    lines.append(f"- **Average Loss:** {metrics['avg_loss']:.2f}%")
    lines.append(f"- **Average Hold Time:** {metrics['avg_hold_time_hours']:.1f} hours")
    lines.append("")

    # Performance by Catalyst
    if "catalyst_performance" in metrics and metrics["catalyst_performance"]:
        lines.append("## Performance by Catalyst Type")
        lines.append("")
        lines.append(
            "| Catalyst | Trades | Win Rate | Avg Return | Profit Factor | Avg Hold (hrs) |"
        )
        lines.append(
            "|----------|--------|----------|------------|---------------|----------------|"
        )

        for catalyst, perf in metrics["catalyst_performance"].items():
            lines.append(
                f"| {catalyst} | {perf['total_trades']} | {perf['win_rate']*100:.1f}% | "
                f"{perf['avg_return']:.2f}% | {perf['profit_factor']:.2f} | "
                f"{perf['avg_hold_hours']:.1f} |"
            )
        lines.append("")

    # Win Rate Details
    if "win_rate_details" in metrics:
        wr_details = metrics["win_rate_details"]

        lines.append("## Win Rate by Score Range")
        lines.append("")
        lines.append("| Score Range | Win Rate |")
        lines.append("|-------------|----------|")
        for score_range, wr in wr_details.get("by_score_range", {}).items():
            lines.append(f"| {score_range} | {wr*100:.1f}% |")
        lines.append("")

    # Best and Worst Trades
    if trades:
        lines.append("## Best Trades (Top 5)")
        lines.append("")
        lines.append("| Ticker | Entry | Exit | Profit % | Hold Time | Exit Reason |")
        lines.append("|--------|-------|------|----------|-----------|-------------|")

        best_trades = sorted(trades, key=lambda t: t["profit_pct"], reverse=True)[:5]
        for trade in best_trades:
            lines.append(
                f"| {trade['ticker']} | ${trade['entry_price']:.2f} | "
                f"${trade['exit_price']:.2f} | {trade['profit_pct']:.2f}% | "
                f"{trade['hold_time_hours']:.1f}h | {trade['exit_reason']} |"
            )
        lines.append("")

        lines.append("## Worst Trades (Bottom 5)")
        lines.append("")
        lines.append("| Ticker | Entry | Exit | Profit % | Hold Time | Exit Reason |")
        lines.append("|--------|-------|------|----------|-----------|-------------|")

        worst_trades = sorted(trades, key=lambda t: t["profit_pct"])[:5]
        for trade in worst_trades:
            lines.append(
                f"| {trade['ticker']} | ${trade['entry_price']:.2f} | "
                f"${trade['exit_price']:.2f} | {trade['profit_pct']:.2f}% | "
                f"{trade['hold_time_hours']:.1f}h | {trade['exit_reason']} |"
            )
        lines.append("")

    # Max Drawdown Details
    if "max_drawdown_details" in metrics:
        dd = metrics["max_drawdown_details"]
        lines.append("## Maximum Drawdown")
        lines.append("")
        lines.append(f"- **Drawdown:** {dd['max_drawdown_pct']:.2f}%")
        lines.append(f"- **Peak Value:** ${dd['peak_value']:.2f}")
        lines.append(f"- **Trough Value:** ${dd['trough_value']:.2f}")
        lines.append(f"- **Peak Date:** {dd['peak_date']}")
        lines.append(f"- **Trough Date:** {dd['trough_date']}")
        lines.append(f"- **Recovery Date:** {dd['recovery_date'] or 'Not recovered'}")
        lines.append(
            f"- **Drawdown Duration:** {dd['drawdown_duration_days']:.1f} days"
        )
        lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    lines.append(_generate_recommendations(metrics, params))
    lines.append("")

    return "\n".join(lines)


def _generate_html_report(results: Dict) -> str:
    """Generate HTML backtest report."""
    md_content = _generate_markdown_report(results)

    # Simple markdown to HTML conversion
    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "  <meta charset='utf-8'>",
        "  <title>Backtest Report</title>",
        "  <style>",
        "    body { font-family: Arial, sans-serif; margin: 40px; }",
        "    table { border-collapse: collapse; width: 100%; margin: 20px 0; }",
        "    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
        "    th { background-color: #4CAF50; color: white; }",
        "    h1 { color: #333; }",
        "    h2 { color: #666; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }",
        "  </style>",
        "</head>",
        "<body>",
    ]

    # Convert markdown to HTML (basic conversion)
    for line in md_content.split("\n"):
        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            html_lines.append(f"<li>{line[2:]}</li>")
        elif line.startswith("|"):
            # Table row (simplified - just wrap in <p>)
            html_lines.append(f"<p>{line}</p>")
        else:
            html_lines.append(f"<p>{line}</p>")

    html_lines.append("</body>")
    html_lines.append("</html>")

    return "\n".join(html_lines)


def _generate_discord_embed(results: Dict) -> str:
    """Generate Discord embed JSON for backtest report."""
    metrics = results["metrics"]
    period = results["backtest_period"]

    # Discord embed format
    embed = {
        "title": "Backtest Report",
        "description": f"Period: {period['start']} to {period['end']}",
        "color": 0x00FF00 if metrics["total_return_pct"] > 0 else 0xFF0000,
        "fields": [
            {
                "name": "Total Return",
                "value": f"{metrics['total_return_pct']:.2f}%",
                "inline": True,
            },
            {
                "name": "Sharpe Ratio",
                "value": f"{metrics.get('sharpe_ratio', 0):.2f}",
                "inline": True,
            },
            {
                "name": "Win Rate",
                "value": f"{metrics['win_rate']:.1f}%",
                "inline": True,
            },
            {
                "name": "Max Drawdown",
                "value": f"{metrics['max_drawdown_pct']:.2f}%",
                "inline": True,
            },
            {
                "name": "Profit Factor",
                "value": f"{metrics.get('profit_factor', 0):.2f}",
                "inline": True,
            },
            {
                "name": "Total Trades",
                "value": str(metrics["total_trades"]),
                "inline": True,
            },
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return json.dumps({"embeds": [embed]}, indent=2)


def _generate_recommendations(metrics: Dict, params: Dict) -> str:
    """Generate recommendations based on backtest results."""
    recommendations = []

    # Win rate recommendations
    win_rate = metrics["win_rate"]
    if win_rate < 40:
        recommendations.append(
            "- **Low Win Rate:** Consider increasing `min_score` threshold to filter out lower-quality alerts."  # noqa: E501
        )
    elif win_rate > 70:
        recommendations.append(
            "- **High Win Rate:** Good signal quality. Consider increasing position size or reducing `min_score` to capture more opportunities."  # noqa: E501
        )

    # Sharpe ratio recommendations
    sharpe = metrics.get("sharpe_ratio", 0)
    if sharpe < 1.0:
        recommendations.append(
            "- **Low Sharpe Ratio:** Risk-adjusted returns are poor. Consider tighter stop losses or stricter entry criteria."  # noqa: E501
        )
    elif sharpe > 2.0:
        recommendations.append(
            "- **Excellent Sharpe Ratio:** Strategy shows strong risk-adjusted performance."
        )

    # Max drawdown recommendations
    max_dd = metrics["max_drawdown_pct"]
    if max_dd > 20:
        recommendations.append(
            "- **High Drawdown:** Consider reducing `position_size_pct` or implementing tighter `stop_loss_pct`."  # noqa: E501
        )

    # Profit factor recommendations
    pf = metrics.get("profit_factor", 0)
    if pf < 1.5:
        recommendations.append(
            "- **Low Profit Factor:** Average wins are not significantly larger than average losses. "  # noqa: E501
            "Consider adjusting `take_profit_pct` and `stop_loss_pct` to improve win/loss ratio."
        )

    # Hold time recommendations
    avg_hold = metrics.get("avg_hold_time_hours", 0)
    max_hold = params.get("max_hold_hours", 24)
    if avg_hold > max_hold * 0.8:
        recommendations.append(
            "- **Long Hold Times:** Most positions are held near max_hold_hours. "
            "Consider extending `max_hold_hours` or adjusting exit criteria."
        )

    if not recommendations:
        recommendations.append(
            "- **Overall:** Strategy performance looks solid. Continue monitoring."
        )

    return "\n".join(recommendations)


def create_equity_curve_chart(equity_curve: List[Tuple[int, float]]) -> str:
    """
    Generate equity curve chart URL using QuickChart.

    Parameters
    ----------
    equity_curve : list of tuple
        List of (timestamp, equity_value) tuples

    Returns
    -------
    str
        QuickChart URL for the equity curve
    """
    if not equity_curve:
        return ""

    # Prepare data
    timestamps = [
        datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        for ts, _ in equity_curve
    ]
    values = [val for _, val in equity_curve]

    # QuickChart config
    chart_config = {
        "type": "line",
        "data": {
            "labels": timestamps,
            "datasets": [
                {
                    "label": "Equity",
                    "data": values,
                    "borderColor": "rgb(75, 192, 192)",
                    "backgroundColor": "rgba(75, 192, 192, 0.2)",
                    "fill": True,
                }
            ],
        },
        "options": {
            "title": {"display": True, "text": "Equity Curve"},
            "scales": {
                "xAxes": [{"display": True}],
                "yAxes": [{"display": True, "ticks": {"beginAtZero": False}}],
            },
        },
    }

    import urllib.parse

    chart_json = json.dumps(chart_config)
    url = f"https://quickchart.io/chart?c={urllib.parse.quote(chart_json)}"

    return url


def create_drawdown_chart(equity_curve: List[Tuple[int, float]]) -> str:
    """
    Generate drawdown chart.

    Parameters
    ----------
    equity_curve : list of tuple
        List of (timestamp, equity_value) tuples

    Returns
    -------
    str
        QuickChart URL for drawdown chart
    """
    if not equity_curve or len(equity_curve) < 2:
        return ""

    # Calculate drawdown series
    peak = equity_curve[0][1]
    drawdowns = []
    timestamps = []

    for ts, value in equity_curve:
        if value > peak:
            peak = value

        dd_pct = ((peak - value) / peak) * 100 if peak > 0 else 0
        drawdowns.append(-dd_pct)  # Negative for chart
        timestamps.append(
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        )

    # QuickChart config
    chart_config = {
        "type": "line",
        "data": {
            "labels": timestamps,
            "datasets": [
                {
                    "label": "Drawdown %",
                    "data": drawdowns,
                    "borderColor": "rgb(255, 99, 132)",
                    "backgroundColor": "rgba(255, 99, 132, 0.2)",
                    "fill": True,
                }
            ],
        },
        "options": {
            "title": {"display": True, "text": "Drawdown Chart"},
            "scales": {
                "xAxes": [{"display": True}],
                "yAxes": [{"display": True}],
            },
        },
    }

    import urllib.parse

    chart_json = json.dumps(chart_config)
    url = f"https://quickchart.io/chart?c={urllib.parse.quote(chart_json)}"

    return url


def export_trades_to_csv(trades: List[Dict], output_path: str) -> None:
    """
    Export trade log to CSV for external analysis.

    Parameters
    ----------
    trades : list of dict
        List of closed trades
    output_path : str
        Path to save CSV file
    """
    if not trades:
        log.warning("no_trades_to_export")
        return

    # Define CSV columns
    fieldnames = [
        "ticker",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "shares",
        "profit",
        "profit_pct",
        "hold_time_hours",
        "exit_reason",
        "score",
        "sentiment",
        "catalyst_type",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for trade in trades:
            row = {
                "ticker": trade["ticker"],
                "entry_time": datetime.fromtimestamp(
                    trade["entry_time"], tz=timezone.utc
                ).isoformat(),
                "exit_time": datetime.fromtimestamp(
                    trade["exit_time"], tz=timezone.utc
                ).isoformat(),
                "entry_price": trade["entry_price"],
                "exit_price": trade["exit_price"],
                "shares": trade["shares"],
                "profit": trade["profit"],
                "profit_pct": trade["profit_pct"],
                "hold_time_hours": trade["hold_time_hours"],
                "exit_reason": trade["exit_reason"],
                "score": trade["alert_data"].get("score", 0),
                "sentiment": trade["alert_data"].get("sentiment", 0),
                "catalyst_type": trade["alert_data"].get("catalyst_type", "unknown"),
            }
            writer.writerow(row)

    log.info("trades_exported path=%s count=%d", output_path, len(trades))
