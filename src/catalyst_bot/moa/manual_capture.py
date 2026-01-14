"""
Manual Capture Module for Missed Opportunities.

Monitors a dedicated Discord channel for user-submitted screenshots of
missed stock opportunities. Uses vision LLM to extract catalyst data and
stores it in the MOA database for learning.

Workflow:
1. User posts in #missed-opportunities channel with:
   - Article screenshot (required)
   - Chart screenshot(s) (optional, 5min + daily recommended)
   - Ticker symbol in message text ($TICKER or just TICKER)
2. Bot downloads images and extracts ticker
3. Vision LLM analyzes images to extract:
   - Headline, source, keywords, catalyst type from article
   - Timeframe, pattern, price levels from chart
4. Data is stored in manual_captures table
5. Bot reacts with checkmark and replies with summary

Author: Claude Code (Manual Capture Feature)
Date: 2026-01-08
"""

import asyncio
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_utils import get_logger
from .database import get_connection
from .vision_analyzer import (
    ArticleAnalysis,
    ChartAnalysis,
    analyze_article_image,
    analyze_chart_image,
)

log = get_logger("moa.manual_capture")

# Image storage directory
IMAGE_STORAGE_DIR = Path("data/moa/captures")


# ============================================================================
# Configuration
# ============================================================================


def is_feature_enabled() -> bool:
    """Check if manual capture feature is enabled."""
    return os.getenv("FEATURE_MANUAL_CAPTURE", "0") in ("1", "true", "yes")


def get_capture_channel_id() -> Optional[str]:
    """Get the Discord channel ID for manual captures."""
    return os.getenv("MANUAL_CAPTURE_CHANNEL_ID", "")


# ============================================================================
# Ticker Extraction
# ============================================================================


def extract_ticker_from_text(text: str) -> Optional[str]:
    """
    Extract stock ticker from message text.

    Supports formats:
    - $AAPL
    - AAPL (if 1-5 uppercase letters)
    - $aapl (normalized to uppercase)

    Args:
        text: Message text

    Returns:
        Ticker symbol (uppercase) or None
    """
    # Pattern 1: $TICKER format (most reliable)
    cashtag_match = re.search(r"\$([A-Za-z]{1,5})\b", text)
    if cashtag_match:
        return cashtag_match.group(1).upper()

    # Pattern 2: Standalone uppercase ticker (less reliable)
    # Only match if it's a single word, 1-5 uppercase letters
    words = text.split()
    for word in words:
        # Clean punctuation
        clean_word = re.sub(r"[^\w]", "", word)
        if clean_word.isupper() and 1 <= len(clean_word) <= 5:
            return clean_word

    return None


# ============================================================================
# Image Handling
# ============================================================================


def ensure_storage_dir() -> Path:
    """Ensure image storage directory exists."""
    IMAGE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGE_STORAGE_DIR


async def download_discord_attachment(
    attachment_url: str,
    filename: str,
    message_id: str,
) -> Optional[Path]:
    """
    Download a Discord attachment and save it locally.

    Args:
        attachment_url: Discord CDN URL
        filename: Original filename
        message_id: Discord message ID (for unique naming)

    Returns:
        Path to saved file or None on failure
    """
    try:
        import aiohttp

        storage_dir = ensure_storage_dir()

        # Create unique filename: {message_id}_{original_filename}
        safe_filename = re.sub(r"[^\w.-]", "_", filename)
        save_path = storage_dir / f"{message_id}_{safe_filename}"

        async with aiohttp.ClientSession() as session:
            async with session.get(attachment_url) as response:
                if response.status != 200:
                    log.warning(
                        "attachment_download_failed url=%s status=%d",
                        attachment_url,
                        response.status,
                    )
                    return None

                content = await response.read()

                with open(save_path, "wb") as f:
                    f.write(content)

        log.info("attachment_saved path=%s size=%d", save_path, len(content))
        return save_path

    except Exception as e:
        log.error("attachment_download_error error=%s", e, exc_info=True)
        return None


def classify_image_type(filename: str) -> str:
    """
    Classify image type based on filename hints.

    Returns: 'article', 'chart_5m', 'chart_daily', 'chart', or 'unknown'
    """
    name_lower = filename.lower()

    # Article indicators
    if any(x in name_lower for x in ["article", "news", "headline", "finviz", "pr"]):
        return "article"

    # Chart timeframe indicators
    if any(x in name_lower for x in ["5m", "5min", "5-min", "5 min"]):
        return "chart_5m"
    if any(x in name_lower for x in ["daily", "1d", "day", "1day"]):
        return "chart_daily"
    if any(x in name_lower for x in ["chart", "price", "graph", "candl"]):
        return "chart"

    return "unknown"


# ============================================================================
# Database Operations
# ============================================================================


def save_manual_capture(
    ticker: str,
    discord_user_id: str,
    discord_message_id: str,
    article_analysis: Optional[ArticleAnalysis] = None,
    chart_analysis: Optional[ChartAnalysis] = None,
    article_image_path: Optional[str] = None,
    chart_5m_image_path: Optional[str] = None,
    chart_daily_image_path: Optional[str] = None,
    user_notes: str = "",
    llm_response: str = "",
    was_in_rejected: bool = False,
    rejection_id: Optional[int] = None,
) -> Optional[int]:
    """
    Save a manual capture to the database.

    Args:
        ticker: Stock ticker symbol
        discord_user_id: Discord user ID who submitted
        discord_message_id: Discord message ID
        article_analysis: Extracted article data from vision LLM
        chart_analysis: Extracted chart data from vision LLM
        article_image_path: Path to saved article screenshot
        chart_5m_image_path: Path to saved 5m chart screenshot
        chart_daily_image_path: Path to saved daily chart screenshot
        user_notes: User's message text
        llm_response: Raw LLM response JSON
        was_in_rejected: True if ticker was found in rejected_items
        rejection_id: ID from rejected_items if was_in_rejected is True

    Returns:
        Record ID or None on failure
    """
    try:
        now = datetime.now(timezone.utc)

        # Combine data from article and chart analysis
        headline = article_analysis.headline if article_analysis else ""
        source = article_analysis.source if article_analysis else ""
        timestamp = article_analysis.timestamp if article_analysis else ""
        catalyst_type = article_analysis.catalyst_type if article_analysis else ""
        keywords = json.dumps(article_analysis.keywords) if article_analysis else "[]"
        sentiment = article_analysis.sentiment if article_analysis else "neutral"

        chart_timeframe = chart_analysis.timeframe if chart_analysis else ""
        chart_pattern = chart_analysis.pattern if chart_analysis else ""
        entry_price = chart_analysis.entry_price if chart_analysis else None
        peak_price = chart_analysis.peak_price if chart_analysis else None
        pct_move = chart_analysis.pct_move if chart_analysis else None
        volume_spike = chart_analysis.volume_spike if chart_analysis else False

        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO manual_captures (
                    ticker, submitted_at, discord_user_id, discord_message_id,
                    headline, source, article_timestamp, catalyst_type, keywords, sentiment,
                    chart_timeframe, chart_pattern, entry_price, peak_price, pct_move, volume_spike,
                    article_image_path, chart_5m_image_path, chart_daily_image_path,
                    user_notes, processed, llm_response,
                    was_in_rejected, rejection_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker.upper(),
                    now.isoformat(),
                    discord_user_id,
                    discord_message_id,
                    headline,
                    source,
                    timestamp,
                    catalyst_type,
                    keywords,
                    sentiment,
                    chart_timeframe,
                    chart_pattern,
                    entry_price,
                    peak_price,
                    pct_move,
                    volume_spike,
                    str(article_image_path) if article_image_path else None,
                    str(chart_5m_image_path) if chart_5m_image_path else None,
                    str(chart_daily_image_path) if chart_daily_image_path else None,
                    user_notes,
                    True,  # processed
                    llm_response,
                    was_in_rejected,
                    rejection_id,
                ),
            )
            conn.commit()
            record_id = cursor.lastrowid

        log.info(
            "manual_capture_saved id=%d ticker=%s catalyst=%s",
            record_id,
            ticker,
            catalyst_type,
        )
        return record_id

    except sqlite3.IntegrityError:
        log.warning("manual_capture_duplicate ticker=%s message=%s", ticker, discord_message_id)
        return None
    except Exception as e:
        log.error("manual_capture_save_failed error=%s", e, exc_info=True)
        return None


def check_ticker_in_rejected(ticker: str, lookback_hours: int = 48) -> Optional[int]:
    """
    Check if a ticker was in our rejected items recently.

    Args:
        ticker: Ticker symbol
        lookback_hours: How far back to check

    Returns:
        Rejection ID if found, None otherwise
    """
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id FROM rejected_items
                WHERE ticker = ?
                AND rejected_at > datetime('now', ? || ' hours')
                ORDER BY rejected_at DESC
                LIMIT 1
                """,
                (ticker.upper(), f"-{lookback_hours}"),
            )
            row = cursor.fetchone()
            return row["id"] if row else None
    except Exception as e:
        log.warning("check_rejected_failed ticker=%s error=%s", ticker, e)
        return None


# ============================================================================
# Processing Pipeline
# ============================================================================


async def process_capture_submission(
    message_id: str,
    user_id: str,
    message_text: str,
    attachments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Process a manual capture submission from Discord.

    Args:
        message_id: Discord message ID
        user_id: Discord user ID
        message_text: Message content
        attachments: List of attachment dicts with {url, filename, content_type}

    Returns:
        Dict with processing results
    """
    result = {
        "success": False,
        "ticker": None,
        "article_analysis": None,
        "chart_analysis": None,
        "record_id": None,
        "error": None,
        "was_rejected": False,
    }

    try:
        # Step 1: Extract ticker from message
        ticker = extract_ticker_from_text(message_text)

        # Step 2: Filter image attachments
        image_attachments = [
            a
            for a in attachments
            if a.get("content_type", "").startswith("image/")
        ]

        if not image_attachments:
            result["error"] = "No image attachments found"
            log.warning("no_images message=%s", message_id)
            return result

        # Step 3: Download and classify images
        article_path = None
        chart_5m_path = None
        chart_daily_path = None
        generic_chart_path = None

        for attachment in image_attachments:
            url = attachment.get("url", "")
            filename = attachment.get("filename", "image.png")

            # Download
            local_path = await download_discord_attachment(url, filename, message_id)
            if not local_path:
                continue

            # Classify
            img_type = classify_image_type(filename)

            if img_type == "article":
                article_path = local_path
            elif img_type == "chart_5m":
                chart_5m_path = local_path
            elif img_type == "chart_daily":
                chart_daily_path = local_path
            elif img_type == "chart":
                generic_chart_path = local_path
            else:
                # If we don't have an article yet, assume first image is article
                if not article_path:
                    article_path = local_path
                elif not chart_5m_path:
                    chart_5m_path = local_path
                elif not chart_daily_path:
                    chart_daily_path = local_path

        # Use generic chart if specific ones not found
        if not chart_5m_path and generic_chart_path:
            chart_5m_path = generic_chart_path

        # Step 4: Analyze article image (required)
        article_analysis = None
        if article_path:
            article_analysis = await analyze_article_image(str(article_path))
            result["article_analysis"] = article_analysis

            # Use ticker from article if not in message
            if not ticker and article_analysis.ticker:
                ticker = article_analysis.ticker

        if not ticker:
            result["error"] = "Could not determine ticker. Please include $TICKER in your message."
            log.warning("no_ticker message=%s", message_id)
            return result

        result["ticker"] = ticker

        # Step 5: Analyze chart image(s)
        chart_analysis = None
        if chart_5m_path:
            chart_analysis = await analyze_chart_image(str(chart_5m_path))
            result["chart_analysis"] = chart_analysis

        # Also analyze daily chart if present (for additional context)
        if chart_daily_path:
            daily_analysis = await analyze_chart_image(str(chart_daily_path))
            # Merge daily analysis into chart_analysis if we got better data
            if daily_analysis and chart_analysis:
                if not chart_analysis.pct_move and daily_analysis.pct_move:
                    chart_analysis.pct_move = daily_analysis.pct_move

        # Step 6: Check if ticker was in rejected items
        rejection_id = check_ticker_in_rejected(ticker)
        result["was_rejected"] = rejection_id is not None

        # Step 7: Save to database
        llm_response = json.dumps({
            "article": vars(article_analysis) if article_analysis else None,
            "chart": vars(chart_analysis) if chart_analysis else None,
        })

        record_id = save_manual_capture(
            ticker=ticker,
            discord_user_id=user_id,
            discord_message_id=message_id,
            article_analysis=article_analysis,
            chart_analysis=chart_analysis,
            article_image_path=str(article_path) if article_path else None,
            chart_5m_image_path=str(chart_5m_path) if chart_5m_path else None,
            chart_daily_image_path=str(chart_daily_path) if chart_daily_path else None,
            user_notes=message_text,
            llm_response=llm_response,
            was_in_rejected=rejection_id is not None,
            rejection_id=rejection_id,
        )

        if record_id:
            result["success"] = True
            result["record_id"] = record_id
            log.info(
                "capture_processed ticker=%s catalyst=%s keywords=%d was_rejected=%s",
                ticker,
                article_analysis.catalyst_type if article_analysis else "unknown",
                len(article_analysis.keywords) if article_analysis else 0,
                result["was_rejected"],
            )
        else:
            result["error"] = "Failed to save capture to database"

        return result

    except Exception as e:
        log.error("capture_processing_failed message=%s error=%s", message_id, e, exc_info=True)
        result["error"] = str(e)
        return result


# ============================================================================
# Discord Response Formatting
# ============================================================================


def format_confirmation_message(result: Dict[str, Any]) -> str:
    """
    Format a confirmation message for Discord.

    Args:
        result: Processing result dict

    Returns:
        Formatted message string
    """
    if not result.get("success"):
        return f"Failed to process capture: {result.get('error', 'Unknown error')}"

    ticker = result.get("ticker", "???")
    article = result.get("article_analysis")
    chart = result.get("chart_analysis")

    lines = [f"**Missed Opportunity Captured: ${ticker}**", ""]

    if article:
        lines.append(f"**Headline:** {article.headline[:100]}{'...' if len(article.headline) > 100 else ''}")
        lines.append(f"**Source:** {article.source}")
        lines.append(f"**Catalyst Type:** {article.catalyst_type.upper()}")
        if article.keywords:
            lines.append(f"**Keywords:** {', '.join(article.keywords[:5])}")
        lines.append(f"**Sentiment:** {article.sentiment}")
        lines.append("")

    if chart:
        lines.append(f"**Chart Pattern:** {chart.pattern}")
        if chart.timeframe:
            lines.append(f"**Timeframe:** {chart.timeframe}")
        if chart.pct_move:
            lines.append(f"**Est. Move:** +{chart.pct_move:.1f}%")
        if chart.entry_price and chart.peak_price:
            lines.append(f"**Price Range:** ${chart.entry_price:.2f} → ${chart.peak_price:.2f}")
        if chart.volume_spike:
            lines.append("**Volume:** Spike confirmed")
        lines.append("")

    if result.get("was_rejected"):
        lines.append("*Note: This ticker was in our rejected items - good catch!*")

    lines.append("Added to MOA learning database.")

    return "\n".join(lines)


# ============================================================================
# Statistics
# ============================================================================


def get_capture_stats() -> Dict[str, Any]:
    """Get statistics about manual captures."""
    try:
        with get_connection() as conn:
            stats = {}

            # Total captures
            cursor = conn.execute("SELECT COUNT(*) FROM manual_captures")
            stats["total_captures"] = cursor.fetchone()[0]

            # Captures by catalyst type
            cursor = conn.execute(
                """
                SELECT catalyst_type, COUNT(*) as count
                FROM manual_captures
                WHERE catalyst_type IS NOT NULL AND catalyst_type != ''
                GROUP BY catalyst_type
                ORDER BY count DESC
                LIMIT 10
                """
            )
            stats["by_catalyst"] = {row[0]: row[1] for row in cursor.fetchall()}

            # Average pct_move
            cursor = conn.execute(
                """
                SELECT AVG(pct_move) FROM manual_captures
                WHERE pct_move IS NOT NULL
                """
            )
            avg = cursor.fetchone()[0]
            stats["avg_pct_move"] = round(avg, 2) if avg else 0

            # Top keywords
            cursor = conn.execute(
                """
                SELECT keywords FROM manual_captures
                WHERE keywords IS NOT NULL AND keywords != '[]'
                """
            )
            all_keywords = {}
            for row in cursor.fetchall():
                try:
                    keywords = json.loads(row[0])
                    for kw in keywords:
                        kw_lower = kw.lower()
                        all_keywords[kw_lower] = all_keywords.get(kw_lower, 0) + 1
                except Exception:
                    pass

            # Sort by frequency
            sorted_kw = sorted(all_keywords.items(), key=lambda x: x[1], reverse=True)
            stats["top_keywords"] = dict(sorted_kw[:20])

            # Was rejected rate
            cursor = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN was_in_rejected = 1 THEN 1 ELSE 0 END) as rejected_count,
                    COUNT(*) as total
                FROM manual_captures
                """
            )
            row = cursor.fetchone()
            if row and row[1] > 0:
                stats["was_rejected_rate"] = round((row[0] or 0) / row[1] * 100, 1)
            else:
                stats["was_rejected_rate"] = 0

            return stats

    except Exception as e:
        log.warning("get_capture_stats_failed error=%s", e)
        return {"error": str(e)}
