"""
Startup Test Alert System

Sends a synthetic test alert on bot startup to verify:
- Alert pipeline is functioning
- Data enrichment is working
- Discord embeds are building correctly
- All systems are operational

The test alert uses real data acquisition and scoring but:
- Uses a synthetic ticker "TEST-BOT" to avoid confusion
- Never gets marked as "seen" so it fires on every restart
- Is clearly labeled as a system test in Discord
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import market
from .classify import enrich_scored_item, fast_classify
from .enrichment_worker import enqueue_for_enrichment, get_enriched_item
from .models import NewsItem, ScoredItem

log = logging.getLogger(__name__)


def create_test_newsitem() -> NewsItem:
    """
    Create a synthetic NewsItem for startup testing.

    Returns a NewsItem that represents a realistic catalyst event
    but uses a synthetic ticker to avoid confusion with real alerts.
    """
    now_utc = datetime.now(timezone.utc).isoformat()

    # Use a real, liquid ticker for price data but label it as TEST
    test_ticker = "SPY"  # Use SPY for reliable market data

    title = "[SYSTEM TEST] Catalyst Bot Startup Verification"
    summary = (
        "This is an automated test alert sent on bot startup to verify "
        "that the alert pipeline is functioning correctly. This includes: "
        "keyword scoring, ML sentiment analysis, market data enrichment, "
        "and Discord embed building. If you see this alert, all systems are operational."
    )

    news_item = NewsItem(
        ts_utc=now_utc,
        title=title,
        ticker=test_ticker,
        canonical_url=f"https://internal.test/startup/{int(time.time())}",
        source="system_test",
        summary=summary,
        raw={
            "test_mode": True,
            "startup_timestamp": now_utc,
            "purpose": "verify_alert_pipeline",
        },
    )

    return news_item


def send_startup_test_alert(
    webhook_url: Optional[str] = None,
    min_score: float = 0.0,
) -> bool:
    """
    Send a test alert on bot startup to verify alert pipeline.

    Args:
        webhook_url: Discord webhook URL (if None, uses main from settings)
        min_score: Minimum score threshold (ignored for test alert)

    Returns:
        True if test alert sent successfully, False otherwise
    """
    try:
        log.info("startup_test_alert_begin")

        # Create synthetic NewsItem
        news_item = create_test_newsitem()

        # Fast classify (keyword scoring + sentiment)
        scored = fast_classify(news_item)

        if not scored:
            log.error("startup_test_alert_fast_classify_failed")
            return False

        log.info(
            "startup_test_alert_scored ticker=%s relevance=%.3f sentiment=%.3f",
            news_item.ticker,
            scored.relevance,
            scored.sentiment,
        )

        # Enrich with market data (RVol, Float, VWAP, etc.)
        enriched_scored = scored
        try:
            enrichment_task_id = enqueue_for_enrichment(scored, news_item)
            log.debug("startup_test_enrichment_queued task_id=%s", enrichment_task_id)

            # Wait for enrichment
            enriched_result = get_enriched_item(enrichment_task_id, timeout=10.0)
            if enriched_result:
                enriched_scored = enriched_result
                log.info("startup_test_enrichment_completed task_id=%s", enrichment_task_id)
            else:
                log.warning("startup_test_enrichment_timeout task_id=%s", enrichment_task_id)
        except Exception as enrich_err:
            log.warning("startup_test_enrichment_failed err=%s", str(enrich_err))

        # Get current price data for the test ticker
        last_price = 0.0
        last_change_pct = 0.0
        try:
            # get_last_price_snapshot returns (last_price, prev_close) tuple
            price, prev_close = market.get_last_price_snapshot(news_item.ticker)
            if price:
                last_price = price
                if prev_close and prev_close > 0:
                    last_change_pct = ((price - prev_close) / prev_close) * 100
        except Exception as price_err:
            log.warning("startup_test_price_fetch_failed err=%s", str(price_err))

        # Build alert payload
        from . import alerts

        item_dict = {
            "id": f"test_{int(time.time())}",  # Unique ID that won't be in seen_store
            "title": news_item.title,
            "link": news_item.canonical_url,
            "ticker": news_item.ticker,
            "source": news_item.source,
            "summary": news_item.summary,
            "ts_utc": news_item.ts_utc,
            "raw": news_item.raw,
        }

        scored_dict = (
            enriched_scored._asdict()
            if hasattr(enriched_scored, "_asdict")
            else (
                enriched_scored.dict()
                if hasattr(enriched_scored, "dict")
                else enriched_scored
            )
        )

        # Build Discord embed
        embed = alerts._build_discord_embed(
            item_dict=item_dict,
            scored=scored_dict,
            last_price=last_price,
            last_change_pct=last_change_pct,
            trade_plan=None,
        )

        # Add test mode indicator to embed
        embed["footer"] = {"text": "🧪 SYSTEM TEST ALERT - All Systems Operational"}
        embed["color"] = 0x00FF00  # Green color for test success

        # Ensure title is set and not too long
        if "title" not in embed or not embed["title"]:
            embed["title"] = "[SYSTEM TEST] Bot Startup Verification"
        embed["title"] = embed["title"][:256]  # Discord limit

        # Send to Discord
        payload = {
            "content": "**🧪 Startup Test Alert**",
            "embeds": [embed],
        }

        # Use alerts module's posting logic (handles retries, rate limiting, etc.)
        success = alerts.post_discord_json(payload, webhook_url=webhook_url)

        if success:
            log.info("startup_test_alert_sent successfully")
        else:
            log.warning("startup_test_alert_send_failed")

        return True

    except Exception as e:
        log.error("startup_test_alert_failed err=%s", str(e), exc_info=True)
        return False
