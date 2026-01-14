"""
Vision LLM Interface for Manual Capture Feature.

Provides Gemini vision API calls for analyzing images.
Uses the same cost-efficient model as text analysis (gemini-2.5-flash).

Author: Claude Code (Manual Capture Feature)
Date: 2026-01-08
"""

import asyncio
import os
from typing import Optional

from ..logging_utils import get_logger

log = get_logger("moa.vision_llm")

# Check Gemini availability
try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None


# Vision model - use same Flash model for cost efficiency
# Gemini Flash supports vision at same price as text
VISION_MODEL = "gemini-2.5-flash"


def _init_gemini() -> bool:
    """Initialize Gemini API if not already done."""
    if not GEMINI_AVAILABLE:
        log.warning("gemini_not_available for vision")
        return False

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("gemini_api_key_not_set for vision")
        return False

    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        log.warning("gemini_init_failed error=%s", e)
        return False


async def call_vision_llm(
    prompt: str,
    image_base64: str,
    mime_type: str = "image/png",
    model: str = VISION_MODEL,
) -> Optional[str]:
    """
    Call Gemini vision API with an image.

    Args:
        prompt: Text prompt for analysis
        image_base64: Base64-encoded image data
        mime_type: Image MIME type (image/png, image/jpeg, image/webp)
        model: Gemini model to use (default: gemini-2.5-flash)

    Returns:
        LLM response text or None on failure
    """
    if not _init_gemini():
        return None

    try:
        # Create model instance
        gemini_model = genai.GenerativeModel(model)

        # Build multimodal content
        # Gemini accepts: [text, {"mime_type": "image/png", "data": base64_str}]
        content = [
            prompt,
            {
                "mime_type": mime_type,
                "data": image_base64,
            },
        ]

        # Call API (synchronous, run in thread pool)
        response = await asyncio.to_thread(
            gemini_model.generate_content, content
        )

        if response and hasattr(response, "text"):
            result = response.text.strip()

            # Log usage
            log.info(
                "vision_llm_success model=%s response_len=%d",
                model,
                len(result),
            )

            return result
        else:
            log.warning("vision_llm_empty_response model=%s", model)
            return None

    except Exception as e:
        log.error("vision_llm_failed model=%s error=%s", model, e, exc_info=True)
        return None


async def analyze_multiple_images(
    prompt: str,
    images: list,
    model: str = VISION_MODEL,
) -> Optional[str]:
    """
    Analyze multiple images in a single request.

    Args:
        prompt: Text prompt for analysis
        images: List of dicts with {"base64": str, "mime_type": str}
        model: Gemini model to use

    Returns:
        LLM response text or None on failure
    """
    if not _init_gemini():
        return None

    if not images:
        log.warning("no_images_provided")
        return None

    try:
        gemini_model = genai.GenerativeModel(model)

        # Build multimodal content with multiple images
        content = [prompt]

        for img in images:
            content.append({
                "mime_type": img.get("mime_type", "image/png"),
                "data": img.get("base64", ""),
            })

        # Call API
        response = await asyncio.to_thread(
            gemini_model.generate_content, content
        )

        if response and hasattr(response, "text"):
            result = response.text.strip()
            log.info(
                "vision_llm_multi_success model=%s images=%d response_len=%d",
                model,
                len(images),
                len(result),
            )
            return result
        else:
            log.warning("vision_llm_multi_empty_response model=%s", model)
            return None

    except Exception as e:
        log.error("vision_llm_multi_failed model=%s error=%s", model, e, exc_info=True)
        return None
