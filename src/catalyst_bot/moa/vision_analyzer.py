"""
Vision Analyzer for Manual Capture Feature.

Uses Gemini vision capabilities to extract structured data from:
- Article screenshots (headline, source, keywords, catalyst type)
- Chart screenshots (timeframe, pattern, price levels, % move)

Author: Claude Code (Manual Capture Feature)
Date: 2026-01-08
"""

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..logging_utils import get_logger

log = get_logger("moa.vision_analyzer")


# ============================================================================
# Data Classes for Vision Analysis Results
# ============================================================================


@dataclass
class ArticleAnalysis:
    """Extracted data from article screenshot."""

    headline: str = ""
    source: str = ""
    timestamp: str = ""
    ticker: str = ""
    catalyst_type: str = ""
    keywords: List[str] = None
    sentiment: str = "neutral"
    confidence: float = 0.0

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


@dataclass
class ChartAnalysis:
    """Extracted data from chart screenshot."""

    timeframe: str = ""
    ticker: str = ""
    pattern: str = ""
    entry_price: Optional[float] = None
    peak_price: Optional[float] = None
    pct_move: Optional[float] = None
    volume_spike: bool = False
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    confidence: float = 0.0


# ============================================================================
# Vision Prompts
# ============================================================================

ARTICLE_ANALYSIS_PROMPT = """Analyze this stock news article screenshot and extract the following information.
Be precise and only extract what you can clearly see in the image.

Extract:
1. HEADLINE: The main title/headline text (exact text visible)
2. SOURCE: News source name (e.g., "GlobeNewswire", "Reuters", "SEC Filing", "Finviz")
3. TIMESTAMP: Any visible date/time (format as seen, e.g., "Jan 8, 2026 10:30 AM")
4. TICKER: Stock symbol if visible (just the symbol, e.g., "AAPL")
5. CATALYST_TYPE: Classify into ONE of these categories based on the content:
   - fda (FDA approval, drug approval, breakthrough designation)
   - clinical (trial results, phase data, study outcomes)
   - earnings (earnings beat, EPS, revenue results)
   - guidance (raised guidance, outlook, forecast)
   - acquisition (M&A, acquisition, merger)
   - partnership (strategic partnership, collaboration, deal)
   - contract (government contract, enterprise deal, award)
   - discovery (oil/gas discovery, mineral find)
   - compliance (Nasdaq compliance, delisting avoided)
   - institutional (13D filing, activist, large stake)
   - crypto (Bitcoin, blockchain, crypto adoption)
   - mining (mining results, feasibility study)
   - other (if none of the above fit)
6. KEYWORDS: List 3-5 key catalyst phrases from the headline/article (e.g., ["FDA approval", "breakthrough therapy"])
7. SENTIMENT: bullish, neutral, or bearish based on the news content

Return ONLY valid JSON in this exact format:
{
    "headline": "...",
    "source": "...",
    "timestamp": "...",
    "ticker": "...",
    "catalyst_type": "...",
    "keywords": ["...", "..."],
    "sentiment": "...",
    "confidence": 0.0 to 1.0
}

If you cannot extract a field clearly, use empty string or empty list. Set confidence based on how clearly you could read the content."""

CHART_ANALYSIS_PROMPT = """Analyze this stock chart screenshot and extract technical information.
Be precise and only report what you can clearly see.

Extract:
1. TIMEFRAME: The chart period shown (e.g., "1min", "5min", "15min", "1hour", "4hour", "daily", "weekly")
   - Look for labels like "1m", "5m", "1H", "1D", etc.
2. TICKER: Stock symbol if visible on the chart
3. PATTERN: The price action pattern you observe. Choose ONE:
   - gap_up (price opened significantly higher than previous close)
   - breakout (price broke above resistance level)
   - spike (sudden sharp upward move)
   - reversal (price changed direction after downtrend)
   - consolidation (price moving sideways in a range)
   - trend_continuation (price continuing existing uptrend)
   - unknown (cannot determine pattern)
4. ENTRY_PRICE: The price at the START of the move (look for the base before the spike)
5. PEAK_PRICE: The highest price visible during/after the move
6. PCT_MOVE: Approximate percentage move from entry to peak
7. VOLUME_SPIKE: Is there a visible volume spike (tall volume bars)? true/false
8. PRICE_LOW: Lowest price visible on the chart
9. PRICE_HIGH: Highest price visible on the chart

Return ONLY valid JSON in this exact format:
{
    "timeframe": "...",
    "ticker": "...",
    "pattern": "...",
    "entry_price": null or number,
    "peak_price": null or number,
    "pct_move": null or number,
    "volume_spike": true or false,
    "price_low": null or number,
    "price_high": null or number,
    "confidence": 0.0 to 1.0
}

If you cannot determine a value, use null. Set confidence based on chart clarity."""


# ============================================================================
# Helper Functions
# ============================================================================


def encode_image_to_base64(image_path: str) -> Optional[str]:
    """
    Encode an image file to base64 string.

    Args:
        image_path: Path to image file (PNG, JPG, WEBP)

    Returns:
        Base64 encoded string or None if failed
    """
    try:
        path = Path(image_path)
        if not path.exists():
            log.warning("image_not_found path=%s", image_path)
            return None

        with open(path, "rb") as f:
            image_data = f.read()

        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        log.warning("image_encode_failed path=%s error=%s", image_path, e)
        return None


def get_mime_type(image_path: str) -> str:
    """Get MIME type from file extension."""
    path = Path(image_path)
    ext = path.suffix.lower()

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }

    return mime_types.get(ext, "image/png")


def parse_article_response(response_text: str) -> ArticleAnalysis:
    """
    Parse LLM response into ArticleAnalysis dataclass.

    Args:
        response_text: Raw JSON response from vision LLM

    Returns:
        ArticleAnalysis with extracted data
    """
    try:
        # Try to extract JSON from response (may have markdown code blocks)
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if not json_match:
            log.warning("no_json_in_article_response")
            return ArticleAnalysis()

        data = json.loads(json_match.group())

        return ArticleAnalysis(
            headline=data.get("headline", ""),
            source=data.get("source", ""),
            timestamp=data.get("timestamp", ""),
            ticker=data.get("ticker", "").upper().strip(),
            catalyst_type=data.get("catalyst_type", "other"),
            keywords=data.get("keywords", []),
            sentiment=data.get("sentiment", "neutral"),
            confidence=float(data.get("confidence", 0.0)),
        )
    except json.JSONDecodeError as e:
        log.warning("article_json_parse_failed error=%s", e)
        return ArticleAnalysis()
    except Exception as e:
        log.warning("article_parse_failed error=%s", e)
        return ArticleAnalysis()


def parse_chart_response(response_text: str) -> ChartAnalysis:
    """
    Parse LLM response into ChartAnalysis dataclass.

    Args:
        response_text: Raw JSON response from vision LLM

    Returns:
        ChartAnalysis with extracted data
    """
    try:
        # Try to extract JSON from response
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if not json_match:
            log.warning("no_json_in_chart_response")
            return ChartAnalysis()

        data = json.loads(json_match.group())

        return ChartAnalysis(
            timeframe=data.get("timeframe", ""),
            ticker=data.get("ticker", "").upper().strip() if data.get("ticker") else "",
            pattern=data.get("pattern", "unknown"),
            entry_price=data.get("entry_price"),
            peak_price=data.get("peak_price"),
            pct_move=data.get("pct_move"),
            volume_spike=data.get("volume_spike", False),
            price_low=data.get("price_low"),
            price_high=data.get("price_high"),
            confidence=float(data.get("confidence", 0.0)),
        )
    except json.JSONDecodeError as e:
        log.warning("chart_json_parse_failed error=%s", e)
        return ChartAnalysis()
    except Exception as e:
        log.warning("chart_parse_failed error=%s", e)
        return ChartAnalysis()


# ============================================================================
# Main Analysis Functions
# ============================================================================


async def analyze_article_image(
    image_path: str,
    image_data: Optional[bytes] = None,
) -> ArticleAnalysis:
    """
    Analyze an article screenshot using vision LLM.

    Args:
        image_path: Path to article screenshot
        image_data: Optional raw image bytes (if already loaded)

    Returns:
        ArticleAnalysis with extracted data
    """
    try:
        # Import vision LLM function
        from .vision_llm import call_vision_llm

        # Encode image
        if image_data:
            image_b64 = base64.b64encode(image_data).decode("utf-8")
            mime_type = "image/png"  # Default to PNG for raw bytes
        else:
            image_b64 = encode_image_to_base64(image_path)
            if not image_b64:
                return ArticleAnalysis()
            mime_type = get_mime_type(image_path)

        # Call vision LLM
        response = await call_vision_llm(
            prompt=ARTICLE_ANALYSIS_PROMPT,
            image_base64=image_b64,
            mime_type=mime_type,
        )

        if not response:
            log.warning("article_vision_llm_no_response")
            return ArticleAnalysis()

        # Parse response
        result = parse_article_response(response)
        log.info(
            "article_analyzed ticker=%s catalyst=%s keywords=%s confidence=%.2f",
            result.ticker,
            result.catalyst_type,
            len(result.keywords),
            result.confidence,
        )

        return result

    except Exception as e:
        log.error("article_analysis_failed error=%s", e, exc_info=True)
        return ArticleAnalysis()


async def analyze_chart_image(
    image_path: str,
    image_data: Optional[bytes] = None,
) -> ChartAnalysis:
    """
    Analyze a chart screenshot using vision LLM.

    Args:
        image_path: Path to chart screenshot
        image_data: Optional raw image bytes (if already loaded)

    Returns:
        ChartAnalysis with extracted data
    """
    try:
        # Import vision LLM function
        from .vision_llm import call_vision_llm

        # Encode image
        if image_data:
            image_b64 = base64.b64encode(image_data).decode("utf-8")
            mime_type = "image/png"
        else:
            image_b64 = encode_image_to_base64(image_path)
            if not image_b64:
                return ChartAnalysis()
            mime_type = get_mime_type(image_path)

        # Call vision LLM
        response = await call_vision_llm(
            prompt=CHART_ANALYSIS_PROMPT,
            image_base64=image_b64,
            mime_type=mime_type,
        )

        if not response:
            log.warning("chart_vision_llm_no_response")
            return ChartAnalysis()

        # Parse response
        result = parse_chart_response(response)
        log.info(
            "chart_analyzed timeframe=%s pattern=%s pct_move=%s confidence=%.2f",
            result.timeframe,
            result.pattern,
            result.pct_move,
            result.confidence,
        )

        return result

    except Exception as e:
        log.error("chart_analysis_failed error=%s", e, exc_info=True)
        return ChartAnalysis()
