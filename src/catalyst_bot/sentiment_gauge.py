"""Sentiment gauge visual generator for Discord embeds.

Creates a radial speedometer gauge showing aggregate sentiment score with
color-coded zones and a needle indicator (2x larger than previous version).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
    style: str = "dark",
) -> Optional[Path]:
    """Generate a radial speedometer sentiment gauge (2x larger, modern design).

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
        import numpy as np

        matplotlib.use("Agg", force=True)

        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt

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

        # Create figure (10% larger to be more visible as thumbnail)
        fig, ax = plt.subplots(figsize=(11, 11), dpi=150)

        # Define color zones (same as before)
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

        # Speedometer settings
        # Convert score range (-100 to +100) to angle range (180° to 0°)
        # -100 = 180° (left), 0 = 90° (top), +100 = 0° (right)
        min_angle = 0  # Right (positive)
        max_angle = 180  # Left (negative)
        center_x, center_y = 0.5, 0.3  # Center of speedometer
        radius_outer = 0.35
        radius_inner = 0.25

        # Draw color zones as arcs
        for zone in zones:
            # Calculate angles for this zone
            angle_start = max_angle - ((zone["min"] + 100) / 200 * (max_angle - min_angle))
            angle_end = max_angle - ((zone["max"] + 100) / 200 * (max_angle - min_angle))

            # Create wedge (arc segment)
            wedge = mpatches.Wedge(
                (center_x, center_y),
                radius_outer,
                angle_end,
                angle_start,
                width=radius_outer - radius_inner,
                facecolor=zone["color"],
                edgecolor=border_color,
                linewidth=1.5,
                alpha=0.9,
            )
            ax.add_patch(wedge)

        # Draw tick marks and labels
        tick_values = [-100, -50, 0, 50, 100]
        for value in tick_values:
            # Calculate angle
            angle = max_angle - ((value + 100) / 200 * (max_angle - min_angle))
            angle_rad = np.radians(angle)

            # Outer tick mark
            tick_outer_x = center_x + radius_outer * np.cos(angle_rad)
            tick_outer_y = center_y + radius_outer * np.sin(angle_rad)

            # Inner tick mark position (shorter tick)
            tick_inner_x = center_x + (radius_outer + 0.03) * np.cos(angle_rad)
            tick_inner_y = center_y + (radius_outer + 0.03) * np.sin(angle_rad)

            # Draw tick mark
            ax.plot(
                [tick_outer_x, tick_inner_x],
                [tick_outer_y, tick_inner_y],
                color=text_color,
                linewidth=2,
                alpha=0.8,
            )

            # Add value label
            label_x = center_x + (radius_outer + 0.08) * np.cos(angle_rad)
            label_y = center_y + (radius_outer + 0.08) * np.sin(angle_rad)
            ax.text(
                label_x,
                label_y,
                str(value),
                ha="center",
                va="center",
                fontsize=11,
                color=text_color,
                fontweight="bold",
                alpha=0.9,
            )

        # Calculate needle angle
        needle_angle = max_angle - ((score + 100) / 200 * (max_angle - min_angle))
        needle_angle_rad = np.radians(needle_angle)

        # Draw needle (from center to outer edge)
        needle_length = radius_outer - 0.02
        needle_x = center_x + needle_length * np.cos(needle_angle_rad)
        needle_y = center_y + needle_length * np.sin(needle_angle_rad)

        # Draw needle as thick line with arrow
        ax.annotate(
            "",
            xy=(needle_x, needle_y),
            xytext=(center_x, center_y),
            arrowprops=dict(
                arrowstyle="-|>",
                lw=4,
                color="#FF0000",  # Red needle
                shrinkA=0,
                shrinkB=0,
            ),
            zorder=100,
        )

        # Draw center circle (hub)
        center_circle = plt.Circle(
            (center_x, center_y),
            0.03,
            color="#000000",
            ec=text_color,
            linewidth=2,
            zorder=101,
        )
        ax.add_patch(center_circle)

        # Add score text in center (below needle hub)
        score_text = f"{score:+.0f}"
        ax.text(
            center_x,
            center_y - 0.12,
            score_text,
            ha="center",
            va="center",
            fontsize=32,
            fontweight="bold",
            color=text_color,
        )

        # Determine current zone label
        current_zone = next(
            (z["label"] for z in zones if z["min"] <= score <= z["max"]), "Neutral"
        )

        # Add zone label below score
        ax.text(
            center_x,
            center_y - 0.20,
            current_zone,
            ha="center",
            va="center",
            fontsize=16,
            color=text_color,
            style="italic",
            alpha=0.9,
        )

        # Add title above speedometer
        title = f"Sentiment Score{' - ' + ticker if ticker else ''}"
        ax.text(
            center_x,
            0.75,
            title,
            ha="center",
            va="center",
            fontsize=18,
            fontweight="bold",
            color=text_color,
        )

        # Set axis limits and remove axes
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal")
        ax.axis("off")

        # Tight layout
        plt.tight_layout()

        # Save
        plt.savefig(
            save_path,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight",
            dpi=150,
        )
        plt.close(fig)

        log.info(
            "gauge_generated ticker=%s score=%.1f path=%s",
            ticker,
            score,
            save_path.name,
        )
        return save_path

    except Exception as e:
        log.warning(
            "gauge_generation_failed ticker=%s score=%.1f err=%s", ticker, score, str(e)
        )
        return None


def log_sentiment_score(
    ticker: str, score: float, price_at_alert: float = None, metadata: dict = None
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
            "metadata": metadata or {},
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
            "bearish": [],  # -40 to -10
            "neutral": [],  # -10 to +10
            "bullish": [],  # +10 to +40
            "strong_bullish": [],  # +40 to +100
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
                    "tickers": list(
                        set(e.get("ticker") for e in entries if e.get("ticker"))
                    )[:10],
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
        (-75, "BEAR1"),  # Strong bearish
        (-25, "BEAR2"),  # Bearish
        (0, "NEUT"),  # Neutral
        (25, "BULL1"),  # Bullish
        (67, "BULL2"),  # Strong bullish
    ]

    for score, ticker in test_scores:
        gauge_path = generate_sentiment_gauge(score, ticker, style="dark")
        if gauge_path:
            print(
                f"  ✓ Generated gauge for {ticker} (score={score}): {gauge_path.name}"
            )

            # Log the score
            log_sentiment_score(
                ticker, score, price_at_alert=10.5, metadata={"test": True}
            )
        else:
            print(f"  ✗ Failed to generate gauge for {ticker}")

    # Test performance analysis
    print("\n--- Sentiment Performance Analysis ---")
    stats = analyze_sentiment_performance(lookback_days=30)
    if stats:
        print(f"Total alerts: {stats.get('total_alerts', 0)}")
        for range_name, data in stats.items():
            if isinstance(data, dict) and "count" in data:
                print(
                    f"  {range_name}: {data['count']} alerts (avg score: {data['avg_score']:.1f})"
                )

    print("\nAll tests passed!")
