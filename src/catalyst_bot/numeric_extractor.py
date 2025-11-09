"""Numeric value extractor for SEC filings with Pydantic validation.

This module extracts structured numeric data from SEC filing text:
- Revenue ($XXM/B format)
- EPS (earnings per share)
- Margins (XX% format)
- Guidance ranges (Q1 2025, FY2025)
- Year-over-year comparisons

All extracted values are validated using Pydantic schemas to ensure type safety
and data integrity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field, field_validator

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("numeric_extractor")


log = get_logger("numeric_extractor")


# ============================================================================
# Pydantic Models
# ============================================================================


class RevenueData(BaseModel):
    """Validated revenue data model."""

    value: float = Field(..., gt=0, description="Revenue value in USD")
    unit: str = Field(..., pattern="^(thousands|millions|billions)$")
    period: Optional[str] = Field(None, description="Q1 2025, FY2024, etc.")
    yoy_change_pct: Optional[float] = Field(None, description="Year-over-year % change")

    def to_usd(self) -> float:
        """Convert to USD regardless of unit."""
        multipliers = {"thousands": 1_000, "millions": 1_000_000, "billions": 1_000_000_000}
        return self.value * multipliers[self.unit]

    def __str__(self) -> str:
        """Human-readable string."""
        unit_short = {"thousands": "K", "millions": "M", "billions": "B"}[self.unit]
        yoy = f" ({self.yoy_change_pct:+.1f}% YoY)" if self.yoy_change_pct else ""
        return f"${self.value:.1f}{unit_short}{yoy}"


class EPSData(BaseModel):
    """Validated earnings per share data model."""

    value: float = Field(..., description="EPS value in USD")
    period: Optional[str] = Field(None, description="Q1 2025, FY2024, etc.")
    is_gaap: bool = Field(True, description="True if GAAP, False if non-GAAP")
    yoy_change_pct: Optional[float] = Field(None, description="Year-over-year % change")

    def __str__(self) -> str:
        """Human-readable string."""
        gaap_label = "GAAP" if self.is_gaap else "Non-GAAP"
        yoy = f" ({self.yoy_change_pct:+.1f}% YoY)" if self.yoy_change_pct else ""
        return f"${self.value:.2f} {gaap_label}{yoy}"


class MarginData(BaseModel):
    """Validated margin data model (gross, operating, net)."""

    margin_type: str = Field(..., pattern="^(gross|operating|net|ebitda)$")
    value: float = Field(..., ge=0, le=100, description="Margin percentage 0-100")
    period: Optional[str] = Field(None)

    def __str__(self) -> str:
        """Human-readable string."""
        return f"{self.margin_type.capitalize()} Margin: {self.value:.1f}%"


class GuidanceRange(BaseModel):
    """Validated guidance range model."""

    metric: str = Field(..., description="revenue, eps, etc.")
    low: float = Field(..., gt=0, description="Low end of range")
    high: float = Field(..., gt=0, description="High end of range")
    unit: Optional[str] = Field(None, pattern="^(thousands|millions|billions)?$")
    period: str = Field(..., description="Q1 2025, FY2025, etc.")

    @field_validator("high")
    @classmethod
    def high_must_exceed_low(cls, v: float, info) -> float:
        """Ensure high end exceeds low end."""
        if "low" in info.data and v <= info.data["low"]:
            raise ValueError("high must exceed low")
        return v

    def __str__(self) -> str:
        """Human-readable string."""
        unit_str = ""
        if self.unit:
            unit_short = {"thousands": "K", "millions": "M", "billions": "B"}[self.unit]
            unit_str = f"{unit_short}"
        return f"{self.metric.upper()} {self.period}: ${self.low:.1f}{unit_str} - ${self.high:.1f}{unit_str}"


class NumericMetrics(BaseModel):
    """Container for all extracted numeric metrics."""

    revenue: list[RevenueData] = Field(default_factory=list)
    eps: list[EPSData] = Field(default_factory=list)
    margins: list[MarginData] = Field(default_factory=list)
    guidance: list[GuidanceRange] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """Check if no metrics were extracted."""
        return not (self.revenue or self.eps or self.margins or self.guidance)

    def summary(self) -> str:
        """Generate human-readable summary."""
        parts = []
        if self.revenue:
            parts.append(f"Revenue: {self.revenue[0]}")
        if self.eps:
            parts.append(f"EPS: {self.eps[0]}")
        if self.margins:
            parts.append(str(self.margins[0]))
        if self.guidance:
            parts.append(f"Guidance: {self.guidance[0]}")
        return " | ".join(parts) if parts else "No metrics extracted"


# ============================================================================
# Extraction Patterns
# ============================================================================

# Revenue patterns: "$150M", "$1.5B", "$150 million"
REVENUE_PATTERNS = [
    re.compile(
        r"\$\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B)(?:\s+in\s+revenue)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"revenue\s+of\s+\$\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B)",
        re.IGNORECASE,
    ),
    re.compile(
        r"revenues?\s+(?:was|were|of)?\s*\$\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B)",
        re.IGNORECASE,
    ),
]

# EPS patterns: "$0.50 per share", "EPS of $1.25"
EPS_PATTERNS = [
    re.compile(
        r"\$\s*(\d+\.\d+)\s+(?:per share|eps)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:earnings|eps)\s+(?:per share\s+)?(?:of|was|were)?\s*\$\s*(\d+\.\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:diluted\s+)?eps\s+of\s+\$\s*(\d+\.\d+)",
        re.IGNORECASE,
    ),
]

# Margin patterns: "gross margin of 45%", "operating margin: 20%"
MARGIN_PATTERNS = [
    re.compile(
        r"(gross|operating|net|ebitda)\s+margin\s+(?:of|:)?\s*(\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
]

# Guidance patterns: "$150M to $175M", "$1.50 - $1.75"
GUIDANCE_PATTERNS = [
    re.compile(
        r"(?:guidance|expects?|forecasts?|anticipates?)\s+.*?\$\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B)?\s+to\s+\$\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\$\s*(\d+\.\d+)\s*(?:to|-)\s*\$\s*(\d+\.\d+)\s+per\s+share",
        re.IGNORECASE,
    ),
]

# YoY change patterns: "up 25%", "increased 30% year-over-year"
YOY_PATTERNS = [
    re.compile(
        r"(?:up|increased?|rose)\s+(\d+(?:\.\d+)?)\s*%\s+(?:year-over-year|yoy|from)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:down|decreased?|fell)\s+(\d+(?:\.\d+)?)\s*%\s+(?:year-over-year|yoy|from)",
        re.IGNORECASE,
    ),
]

# Period patterns: "Q1 2025", "FY2024", "fiscal year 2024"
PERIOD_PATTERNS = [
    re.compile(r"(Q[1-4]\s+\d{4})", re.IGNORECASE),
    re.compile(r"(FY\s*\d{4})", re.IGNORECASE),
    re.compile(r"fiscal year\s+(\d{4})", re.IGNORECASE),
]


# ============================================================================
# Extraction Functions
# ============================================================================


def extract_revenue(text: str) -> list[RevenueData]:
    """Extract revenue data from text.

    Parameters
    ----------
    text : str
        Filing text to extract from

    Returns
    -------
    list[RevenueData]
        List of validated revenue data objects
    """
    revenues = []

    for pattern in REVENUE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                value = float(match.group(1))
                unit_raw = match.group(2).lower()

                # Normalize unit
                if unit_raw in ("m", "million"):
                    unit = "millions"
                elif unit_raw in ("b", "billion"):
                    unit = "billions"
                else:
                    continue

                # Try to extract period
                period = _extract_period_near_match(text, match.start(), match.end())

                # Try to extract YoY
                yoy_change = _extract_yoy_near_match(text, match.start(), match.end())

                revenue = RevenueData(
                    value=value,
                    unit=unit,
                    period=period,
                    yoy_change_pct=yoy_change,
                )
                revenues.append(revenue)
                log.debug(f"Extracted revenue: {revenue}")

            except Exception as e:
                log.warning(f"Failed to parse revenue from match: {e}")
                continue

    return revenues


def extract_eps(text: str) -> list[EPSData]:
    """Extract EPS data from text.

    Parameters
    ----------
    text : str
        Filing text to extract from

    Returns
    -------
    list[EPSData]
        List of validated EPS data objects
    """
    eps_list = []

    for pattern in EPS_PATTERNS:
        for match in pattern.finditer(text):
            try:
                value = float(match.group(1))

                # Determine if GAAP or non-GAAP
                context = text[max(0, match.start() - 50) : match.end() + 50].lower()
                is_gaap = "non-gaap" not in context and "adjusted" not in context

                # Try to extract period
                period = _extract_period_near_match(text, match.start(), match.end())

                # Try to extract YoY
                yoy_change = _extract_yoy_near_match(text, match.start(), match.end())

                eps = EPSData(
                    value=value,
                    period=period,
                    is_gaap=is_gaap,
                    yoy_change_pct=yoy_change,
                )
                eps_list.append(eps)
                log.debug(f"Extracted EPS: {eps}")

            except Exception as e:
                log.warning(f"Failed to parse EPS from match: {e}")
                continue

    return eps_list


def extract_margins(text: str) -> list[MarginData]:
    """Extract margin data from text.

    Parameters
    ----------
    text : str
        Filing text to extract from

    Returns
    -------
    list[MarginData]
        List of validated margin data objects
    """
    margins = []

    for pattern in MARGIN_PATTERNS:
        for match in pattern.finditer(text):
            try:
                margin_type = match.group(1).lower()
                value = float(match.group(2))

                # Try to extract period
                period = _extract_period_near_match(text, match.start(), match.end())

                margin = MarginData(
                    margin_type=margin_type,
                    value=value,
                    period=period,
                )
                margins.append(margin)
                log.debug(f"Extracted margin: {margin}")

            except Exception as e:
                log.warning(f"Failed to parse margin from match: {e}")
                continue

    return margins


def extract_guidance(text: str) -> list[GuidanceRange]:
    """Extract guidance ranges from text.

    Parameters
    ----------
    text : str
        Filing text to extract from

    Returns
    -------
    list[GuidanceRange]
        List of validated guidance range objects
    """
    guidance_list = []

    for pattern in GUIDANCE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                # Determine if revenue or EPS guidance
                context = text[max(0, match.start() - 100) : match.start()].lower()

                if "per share" in match.group(0).lower() or "eps" in context:
                    # EPS guidance
                    low = float(match.group(1))
                    high = float(match.group(2))
                    metric = "eps"
                    unit = None
                else:
                    # Revenue guidance
                    low = float(match.group(1))
                    high = float(match.group(3))
                    unit_raw = match.group(2) or match.group(4)
                    metric = "revenue"

                    # Normalize unit
                    if unit_raw:
                        unit_raw = unit_raw.lower()
                        if unit_raw in ("m", "million"):
                            unit = "millions"
                        elif unit_raw in ("b", "billion"):
                            unit = "billions"
                        else:
                            unit = None
                    else:
                        unit = None

                # Extract period (required for guidance)
                period = _extract_period_near_match(text, match.start(), match.end())
                if not period:
                    # Try forward context (guidance usually mentions period after)
                    forward_context = text[match.end() : match.end() + 100]
                    period_match = PERIOD_PATTERNS[0].search(forward_context)
                    if period_match:
                        period = period_match.group(1)
                    else:
                        period = "Unknown Period"

                guidance = GuidanceRange(
                    metric=metric,
                    low=low,
                    high=high,
                    unit=unit,
                    period=period,
                )
                guidance_list.append(guidance)
                log.debug(f"Extracted guidance: {guidance}")

            except Exception as e:
                log.warning(f"Failed to parse guidance from match: {e}")
                continue

    return guidance_list


def extract_all_metrics(text: str) -> NumericMetrics:
    """Extract all numeric metrics from filing text.

    Parameters
    ----------
    text : str
        Filing text to extract from

    Returns
    -------
    NumericMetrics
        Container with all extracted metrics
    """
    if not text:
        log.warning("extract_all_metrics called with empty text")
        return NumericMetrics()

    metrics = NumericMetrics(
        revenue=extract_revenue(text),
        eps=extract_eps(text),
        margins=extract_margins(text),
        guidance=extract_guidance(text),
    )

    log.info(
        f"Extracted metrics: {len(metrics.revenue)} revenue, "
        f"{len(metrics.eps)} EPS, {len(metrics.margins)} margins, "
        f"{len(metrics.guidance)} guidance"
    )

    return metrics


# ============================================================================
# Helper Functions
# ============================================================================


def _extract_period_near_match(text: str, start: int, end: int, window: int = 100) -> Optional[str]:
    """Extract period (Q1 2025, FY2024) near a match."""
    # Search backward first (period usually comes before numbers)
    context_before = text[max(0, start - window) : start]
    for pattern in PERIOD_PATTERNS:
        match = pattern.search(context_before)
        if match:
            return match.group(1)

    # Then search forward
    context_after = text[end : end + window]
    for pattern in PERIOD_PATTERNS:
        match = pattern.search(context_after)
        if match:
            return match.group(1)

    return None


def _extract_yoy_near_match(text: str, start: int, end: int, window: int = 100) -> Optional[float]:
    """Extract year-over-year percentage change near a match."""
    context = text[end : end + window]

    for pattern in YOY_PATTERNS:
        match = pattern.search(context)
        if match:
            pct = float(match.group(1))
            # Check if it's a decrease (negative)
            if "down" in match.group(0).lower() or "decreas" in match.group(0).lower():
                pct = -pct
            return pct

    return None
