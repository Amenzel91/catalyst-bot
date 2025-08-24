"""Discord alert delivery for the catalyst bot.

This module encapsulates the logic for sending richly formatted
alerts to a Discord channel via a webhook. Alerts include an embed
containing key information about the news item along with a
attachment of the generated chart image.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

try:
    from discord_webhook import DiscordEmbed, DiscordWebhook  # type: ignore
except Exception:  # pragma: no cover
    # If the optional discord_webhook dependency is missing, set to None
    DiscordEmbed = None  # type: ignore
    DiscordWebhook = None  # type: ignore

from .config import get_settings
from .logs import log_event
from .models import ScoredItem


def send_alert(
    scored_item: ScoredItem,
    price: Optional[float] = None,
    percent_change: Optional[float] = None,
    volume_ratio: Optional[float] = None,
    chart_relative_path: Optional[str] = None,
) -> None:
    """Send a single alert to Discord.

    Parameters
    ----------
    scored_item : ScoredItem
        The scored news item to alert on.
    price : Optional[float]
        Latest price at alert time.
    percent_change : Optional[float]
        Percentage change from previous close.
    volume_ratio : Optional[float]
        Relative volume (session volume vs 20D average).
    chart_relative_path : Optional[str]
        Relative path to the PNG chart file to attach.
    """
    settings = get_settings()
    webhook_url = settings.discord_webhook_url
    # If the discord_webhook library is unavailable or no webhook URL is configured,
    # skip sending the alert entirely.
    if DiscordWebhook is None or not webhook_url:
        return
    item = scored_item.item

    # Prepare embed
    embed = DiscordEmbed(
        title=f"{item.ticker or 'N/A'}: {item.title}",
        description=f"Source: {item.source_host}",
        color="03b2f8",
    )
    embed.set_timestamp(item.ts_utc.isoformat())
    embed.add_embed_field(name="Sentiment", value=f"{scored_item.sentiment:.2f}")
    embed.add_embed_field(name="Keywords", value=", ".join(scored_item.keyword_hits) or "None")
    embed.add_embed_field(name="Score", value=f"{scored_item.total_score:.2f}")
    if price is not None:
        embed.add_embed_field(name="Price", value=f"${price:.2f}")
    if percent_change is not None:
        embed.add_embed_field(name="% Chg", value=f"{percent_change*100:.2f}%")
    if volume_ratio is not None:
        embed.add_embed_field(name="Vol/Avg", value=f"{volume_ratio:.2f}x")

    # Build webhook
    webhook = DiscordWebhook(url=webhook_url, rate_limit_retry=True)
    webhook.add_embed(embed)

    # Attach chart if available
    if chart_relative_path:
        # Determine absolute path relative to project root
        absolute_path = get_settings().base_dir / chart_relative_path
        try:
            with absolute_path.open("rb") as fh:
                webhook.add_file(fh.read(), filename=Path(chart_relative_path).name)
        except Exception as exc:
            log_event({
                "ts_utc": datetime.utcnow().isoformat(),
                "level": "error",
                "message": "Failed to attach chart",
                "error": str(exc),
                "path": str(absolute_path),
            })

    try:
        response = webhook.execute()
        if response and response.status_code >= 400:
            log_event({
                "ts_utc": datetime.utcnow().isoformat(),
                "level": "error",
                "message": "Webhook returned non‑200 status",
                "status": response.status_code,
                "body": response.content.decode("utf-8", errors="ignore") if response.content else None,
            })
    except Exception as exc:
        log_event({
            "ts_utc": datetime.utcnow().isoformat(),
            "level": "error",
            "message": "Exception sending alert",
            "error": str(exc),
        })