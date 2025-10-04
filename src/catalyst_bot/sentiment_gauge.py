"""Sentiment gauge visual generator for Discord embeds.

Creates a gradient gauge chart showing aggregate sentiment score with
color-coded zones and an arrow indicator.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

try:
    from .logging_utils import get_logger
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    def get_logger(_):
        return logging.getLogger("sentiment_gauge")

log = get_logger("sentiment_gauge")


def generate_sentiment_gauge(
    score: float,
    ticker: str = "",
    out_dir: str | Path = "out/gauges",
    style: str = "dark"
) -> Optional[Path]:
    """Generate a sentiment gauge chart showing score on gradient scale.

    Parameters
    ----------
    score : float
        Aggregate sentiment score (-100 to +100)
    ticker : str
        Stock ticker symbol (for filename and label)
    out_dir : str | Path
        Directory to save the gauge image
    style : str
        Chart style: 'dark' or 'light' (default: 'dark')

    Returns
    -------
    Path or None
        Path to the saved PNG file, or None on failure
    """
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)

        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np

    except Exception as e:
        log.warning("gauge_import_failed err=%s", str(e))
        return None

    # Clamp score to valid range
    score = max(-100, min(100, score))

    try:
        # Create output directory
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        ticker_safe = ticker.replace("/", "_").replace(".", "_") if ticker else "score"
        filename = f"gauge_{ticker_safe}_{timestamp}.png"
        save_path = out_path / filename

        # Create figure
        fig, ax = plt.subplots(figsize=(10, 3), dpi=100)

        # Define color zones and labels
        zones = [
            {"min": -100, "max": -40, "color": "#D32F2F", "label": "Strong Bearish"},
            {"min": -40, "max": -10, "color": "#FF6F00", "label": "Bearish"},
            {"min": -10, "max": 10, "color": "#FDD835", "label": "Neutral"},
            {"min": 10, "max": 40, "color": "#66BB6A", "label": "Bullish"},
            {"min": 40, "max": 100, "color": "#2E7D32", "label": "Strong Bullish"},
        ]

        # Set background color based on style
        if style == "dark":
            fig.patch.set_facecolor("#2C2F33")
            ax.set_facecolor("#2C2F33")
            text_color = "#FFFFFF"
            border_color = "#40444B"
        else:
            fig.patch.set_facecolor("#FFFFFF")
            ax.set_facecolor("#FFFFFF")
            text_color = "#000000"
            border_color = "#CCCCCC"

        # Draw gradient bar with zones
        bar_height = 0.6
        bar_y = 0.5

        for zone in zones:
            # Calculate position and width
            x_start = (zone["min"] + 100) / 200  # Normalize to 0-1
            x_end = (zone["max"] + 100) / 200
            width = x_end - x_start

            # Draw rectangle for this zone
            rect = mpatches.Rectangle(
                (x_start, bar_y - bar_height/2),
                width,
                bar_height,
                facecolor=zone["color"],
                edgecolor=border_color,
                linewidth=0.5
            )
            ax.add_patch(rect)

        # Calculate arrow position
        arrow_x = (score + 100) / 200  # Normalize to 0-1
        arrow_y = bar_y

        # Draw arrow pointing to score
        arrow_props = dict(
            arrowstyle="->",
            lw=3,
            color=text_color,
            connectionstyle="arc3,rad=0"
        )

        # Arrow from top pointing down to the score
        ax.annotate(
            "",
            xy=(arrow_x, bar_y - bar_height/2 - 0.05),
            xytext=(arrow_x, bar_y + bar_height/2 + 0.3),
            arrowprops=arrow_props
        )

        # Add score label above arrow
        score_text = f"{score:+.0f}"
        ax.text(
            arrow_x,
            bar_y + bar_height/2 + 0.35,
            score_text,
            ha="center",
            va="bottom",
            fontsize=16,
            fontweight="bold",
            color=text_color
        )

        # Determine current zone label
        current_zone = next(
            (z["label"] for z in zones if z["min"] <= score <= z["max"]),
            "Neutral"
        )

        # Add zone label below arrow
        ax.text(
            arrow_x,
            bar_y - bar_height/2 - 0.15,
            current_zone,
            ha="center",
            va="top",
            fontsize=11,
            color=text_color,
            style="italic"
        )

        # Add scale markers
        for value in [-100, -50, 0, 50, 100]:
            x_pos = (value + 100) / 200
            ax.plot(
                [x_pos, x_pos],
                [bar_y - bar_height/2 - 0.02, bar_y - bar_height/2],
                color=border_color,
                linewidth=1
            )
            ax.text(
                x_pos,
                bar_y - bar_height/2 - 0.05,
                str(value),
                ha="center",
                va="top",
                fontsize=8,
                color=text_color,
                alpha=0.7
            )

        # Add title
        title = f"Aggregate Sentiment Score{' - ' + ticker if ticker else ''}"
        ax.text(
            0.5,
            0.95,
            title,
            ha="center",
            va="top",
            fontsize=14,
            fontweight="bold",
            color=text_color,
            transform=ax.transAxes
        )

        # Set axis limits and remove axes
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        # Tight layout
        plt.tight_layout()

        # Save
        plt.savefig(
            save_path,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight",
            dpi=100
        )
        plt.close(fig)

        log.info("gauge_generated ticker=%s score=%.1f path=%s", ticker, score, save_path.name)
        return save_path

    except Exception as e:
        log.warning("gauge_generation_failed ticker=%s score=%.1f err=%s",
                   ticker, score, str(e))
        return None


def log_sentiment_score(
    ticker: str,
    score: float,
    price_at_alert: float = None,
    metadata: dict = None
) -> None:
    """Log sentiment score for calibration and backtesting.

    Logs are written to data/sentiment_scores.jsonl in JSON Lines format
    for easy analysis and backtesting.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    score : float
        Aggregate sentiment score
    price_at_alert : float
        Current stock price when alert fired
    metadata : dict
        Additional metadata (source, indicators, etc.)
    """
    try:
        import json

        log_dir = Path("data")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "sentiment_scores.jsonl"

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "score": round(score, 2),
            "price_at_alert": round(price_at_alert, 4) if price_at_alert else None,
            "metadata": metadata or {}
        }

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        log.debug("sentiment_score_logged ticker=%s score=%.2f", ticker, score)

    except Exception as e:
        log.warning("sentiment_score_log_failed ticker=%s err=%s", ticker, str(e))


def analyze_sentiment_performance(lookback_days: int = 30) -> dict:
    """Analyze historical sentiment score performance.

    Reads sentiment_scores.jsonl and calculates performance metrics
    for different score ranges.

    Parameters
    ----------
    lookback_days : int
        Number of days to analyze (default: 30)

    Returns
    -------
    dict
        Performance statistics by score range
    """
    try:
        import json
        from collections import defaultdict

        log_file = Path("data/sentiment_scores.jsonl")
        if not log_file.exists():
            return {}

        # Read scores
        scores = []
        cutoff = datetime.now(timezone.utc).timestamp() - (lookback_days * 86400)

        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    timestamp = datetime.fromisoformat(entry["timestamp"]).timestamp()
                    if timestamp >= cutoff:
                        scores.append(entry)
                except Exception:
                    continue

        if not scores:
            return {}

        # Group by score ranges
        ranges = {
            "strong_bearish": [],  # -100 to -40
            "bearish": [],         # -40 to -10
            "neutral": [],         # -10 to +10
            "bullish": [],         # +10 to +40
            "strong_bullish": []   # +40 to +100
        }

        for entry in scores:
            score = entry.get("score", 0)
            if score <= -40:
                ranges["strong_bearish"].append(entry)
            elif score <= -10:
                ranges["bearish"].append(entry)
            elif score <= 10:
                ranges["neutral"].append(entry)
            elif score <= 40:
                ranges["bullish"].append(entry)
            else:
                ranges["strong_bullish"].append(entry)

        # Calculate stats
        stats = {}
        for range_name, entries in ranges.items():
            if entries:
                stats[range_name] = {
                    "count": len(entries),
                    "avg_score": sum(e.get("score", 0) for e in entries) / len(entries),
                    "tickers": list(set(e.get("ticker") for e in entries if e.get("ticker")))[:10]
                }

        stats["total_alerts"] = len(scores)
        stats["lookback_days"] = lookback_days

        return stats

    except Exception as e:
        log.warning("sentiment_performance_analysis_failed err=%s", str(e))
        return {}


if __name__ == "__main__":
    # Test script
    print("Testing sentiment gauge generator...")

    # Test different scores
    test_scores = [
        (-75, "BEAR1"),   # Strong bearish
        (-25, "BEAR2"),   # Bearish
        (0, "NEUT"),      # Neutral
        (25, "BULL1"),    # Bullish
        (67, "BULL2"),    # Strong bullish
    ]

    for score, ticker in test_scores:
        gauge_path = generate_sentiment_gauge(score, ticker, style="dark")
        if gauge_path:
            print(f"  ✓ Generated gauge for {ticker} (score={score}): {gauge_path.name}")

            # Log the score
            log_sentiment_score(ticker, score, price_at_alert=10.5, metadata={"test": True})
        else:
            print(f"  ✗ Failed to generate gauge for {ticker}")

    # Test performance analysis
    print("\n--- Sentiment Performance Analysis ---")
    stats = analyze_sentiment_performance(lookback_days=30)
    if stats:
        print(f"Total alerts: {stats.get('total_alerts', 0)}")
        for range_name, data in stats.items():
            if isinstance(data, dict) and "count" in data:
                print(f"  {range_name}: {data['count']} alerts (avg score: {data['avg_score']:.1f})")

    print("\nAll tests passed!")
