"""
Admin Nightly Reporter
======================

Sends nightly admin reports to Discord with backtest results, keyword performance,
and interactive buttons for parameter adjustments.

This module is called by the analyzer at the end of each day to deliver
performance summaries to the admin channel.
"""

from __future__ import annotations

import os
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from .admin_controls import (
    build_admin_components,
    build_admin_embed,
    generate_admin_report,
    save_admin_report,
)
from .logging_utils import get_logger

log = get_logger("admin_reporter")


def post_admin_report(
    target_date: Optional[date_cls] = None, webhook_url: Optional[str] = None
) -> bool:
    """
    Generate and post nightly admin report to Discord.

    Parameters
    ----------
    target_date : date, optional
        Date to generate report for. Defaults to yesterday.
    webhook_url : str, optional
        Discord webhook URL. If None, uses DISCORD_ADMIN_WEBHOOK from env.

    Returns
    -------
    bool
        True if report was posted successfully
    """
    # Determine target date (default: yesterday)
    if target_date is None:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    # Check if admin reports are enabled
    if not os.getenv("FEATURE_ADMIN_REPORTS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        log.info("admin_reports_disabled")
        return False

    log.info(f"generating_admin_report date={target_date}")

    try:
        # Generate report
        report = generate_admin_report(target_date)

        # Save report to disk
        save_admin_report(report)

        # Build Discord payload
        embed = build_admin_embed(report)
        report_id = report.date.isoformat()
        components = build_admin_components(report_id)

        # Check if bot token and channel ID are configured (preferred for buttons)
        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        channel_id = os.getenv("DISCORD_ADMIN_CHANNEL_ID")

        if bot_token and channel_id:
            # Use Discord Bot API (supports components/buttons)
            return _post_via_bot_api(
                embed, components, bot_token, channel_id, target_date
            )
        else:
            # Fallback to webhook (no buttons)
            if webhook_url is None:
                webhook_url = os.getenv("DISCORD_ADMIN_WEBHOOK")

            if not webhook_url:
                log.warning("no_admin_webhook_configured")
                return False

            log.warning("bot_token_not_configured using_webhook_without_buttons")
            payload = {
                "username": "Catalyst Admin",
                "embeds": [embed],
                # Note: webhooks don't support components
            }

            response = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            if response.status_code in (200, 204):
                log.info(f"admin_report_posted_via_webhook date={target_date}")
                return True
            else:
                log.warning(
                    f"admin_report_post_failed date={target_date} "
                    f"status={response.status_code} body={response.text[:200]}"
                )
                return False

    except Exception as e:
        log.error(f"admin_report_failed date={target_date} err={e}")
        return False


def _post_via_bot_api(
    embed: dict,
    components: list,
    bot_token: str,
    channel_id: str,
    target_date: date_cls,
) -> bool:
    """
    Post message with components via Discord Bot API.

    Parameters
    ----------
    embed : dict
        Discord embed object
    components : list
        Discord message components (buttons)
    bot_token : str
        Discord bot token
    channel_id : str
        Discord channel ID to post to
    target_date : date
        Report date for logging

    Returns
    -------
    bool
        True if posted successfully
    """
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

    payload = {"embeds": [embed], "components": components}

    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code in (200, 201):
            log.info(f"admin_report_posted_via_bot date={target_date}")
            return True
        else:
            log.warning(
                f"bot_api_post_failed date={target_date} "
                f"status={response.status_code} body={response.text[:200]}"
            )
            return False

    except Exception as e:
        log.error(f"bot_api_post_exception date={target_date} err={e}")
        return False


def should_send_admin_report(now: datetime) -> bool:
    """
    Determine if it's time to send the admin report.

    Admin reports are sent once daily at the configured schedule
    (same as analyzer: ANALYZER_UTC_HOUR:ANALYZER_UTC_MINUTE).

    Parameters
    ----------
    now : datetime
        Current time (timezone aware)

    Returns
    -------
    bool
        True if admin report should be sent now
    """
    # Normalize to UTC
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    # Get schedule from environment (same as analyzer)
    try:
        target_hour = int(os.getenv("ANALYZER_UTC_HOUR", "21"))
        target_minute = int(os.getenv("ANALYZER_UTC_MINUTE", "30"))
    except ValueError:
        target_hour, target_minute = 21, 30

    # Check if we're in the target hour and haven't sent yet today
    now.hour
    now.minute

    # Within 5-minute window of target time
    target_time = now.replace(
        hour=target_hour, minute=target_minute, second=0, microsecond=0
    )
    time_diff = abs((now - target_time).total_seconds())

    # Send if within 5 minutes of target time
    return time_diff <= 300  # 5 minutes


def send_admin_report_if_scheduled(now: Optional[datetime] = None) -> bool:
    """
    Send admin report if it's the scheduled time.

    This function should be called periodically (e.g., every minute) from
    the main runner loop.

    Parameters
    ----------
    now : datetime, optional
        Current time. Defaults to datetime.now(timezone.utc).

    Returns
    -------
    bool
        True if report was sent
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if should_send_admin_report(now):
        log.info("triggering_scheduled_admin_report")
        return post_admin_report()

    return False
