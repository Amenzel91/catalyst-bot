"""Sample trading alerts for testing."""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def create_sample_alert(
    ticker: str = "AAPL",
    signal_type: str = "breakout",
    score: float = 8.0,
    price: float = 175.00,
    catalyst: str = "earnings_beat",
    **kwargs,
) -> Dict[str, Any]:
    """
    Create a sample trading alert for testing.

    Args:
        ticker: Stock symbol
        signal_type: Type of signal (breakout, earnings, insider_buying, etc.)
        score: Alert score (0-10)
        price: Current price
        catalyst: Catalyst type
        **kwargs: Additional metadata fields

    Returns:
        Dictionary representing a trading alert
    """
    metadata = {
        "rvol": kwargs.get("rvol", 2.5),
        "atr": kwargs.get("atr", 4.50),
        "volume": kwargs.get("volume", 52000000),
        "sentiment_score": kwargs.get("sentiment_score", 0.6),
    }

    # Merge any additional metadata
    metadata.update(kwargs.get("metadata", {}))

    alert = {
        "id": kwargs.get("id", f"alert-{uuid.uuid4()}"),
        "ticker": ticker,
        "signal_type": signal_type,
        "score": score,
        "price": price,
        "timestamp": kwargs.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "catalyst": catalyst,
        "metadata": metadata,
    }

    return alert


def create_breakout_alert(
    ticker: str = "TSLA",
    score: float = 9.0,
    price: float = 250.00,
    **kwargs,
) -> Dict[str, Any]:
    """Create a breakout pattern alert."""
    return create_sample_alert(
        ticker=ticker,
        signal_type="breakout",
        score=score,
        price=price,
        catalyst="technical_breakout",
        rvol=kwargs.get("rvol", 3.5),
        atr=kwargs.get("atr", 8.0),
        volume=kwargs.get("volume", 125000000),
        sentiment_score=kwargs.get("sentiment_score", 0.7),
        metadata={
            "pattern": "ascending_triangle",
            "resistance_breaks": 3,
            "volume_surge": True,
            **kwargs.get("metadata", {}),
        },
    )


def create_earnings_alert(
    ticker: str = "NVDA",
    score: float = 8.5,
    price: float = 500.00,
    beat_type: str = "revenue_eps",
    **kwargs,
) -> Dict[str, Any]:
    """Create an earnings alert."""
    return create_sample_alert(
        ticker=ticker,
        signal_type="earnings",
        score=score,
        price=price,
        catalyst="earnings_beat",
        rvol=kwargs.get("rvol", 4.0),
        atr=kwargs.get("atr", 15.0),
        volume=kwargs.get("volume", 200000000),
        sentiment_score=kwargs.get("sentiment_score", 0.85),
        metadata={
            "beat_type": beat_type,
            "eps_surprise": 0.15,  # 15% beat
            "revenue_surprise": 0.08,  # 8% beat
            "guidance": "raised",
            **kwargs.get("metadata", {}),
        },
    )


def create_insider_buying_alert(
    ticker: str = "AAPL",
    score: float = 7.5,
    price: float = 175.00,
    **kwargs,
) -> Dict[str, Any]:
    """Create an insider buying alert."""
    return create_sample_alert(
        ticker=ticker,
        signal_type="insider_buying",
        score=score,
        price=price,
        catalyst="insider_buying",
        rvol=kwargs.get("rvol", 1.8),
        atr=kwargs.get("atr", 4.0),
        volume=kwargs.get("volume", 45000000),
        sentiment_score=kwargs.get("sentiment_score", 0.65),
        metadata={
            "insider_role": "CEO",
            "shares_purchased": 100000,
            "purchase_value": 17500000,
            "filing_type": "Form 4",
            **kwargs.get("metadata", {}),
        },
    )


def create_analyst_upgrade_alert(
    ticker: str = "MSFT",
    score: float = 7.0,
    price: float = 380.00,
    **kwargs,
) -> Dict[str, Any]:
    """Create an analyst upgrade alert."""
    return create_sample_alert(
        ticker=ticker,
        signal_type="analyst_upgrade",
        score=score,
        price=price,
        catalyst="analyst_upgrade",
        rvol=kwargs.get("rvol", 1.5),
        atr=kwargs.get("atr", 6.5),
        volume=kwargs.get("volume", 35000000),
        sentiment_score=kwargs.get("sentiment_score", 0.70),
        metadata={
            "analyst_firm": "Goldman Sachs",
            "old_rating": "Neutral",
            "new_rating": "Buy",
            "old_target": 350,
            "new_target": 420,
            **kwargs.get("metadata", {}),
        },
    )


def create_merger_acquisition_alert(
    ticker: str = "ADBE",
    score: float = 8.0,
    price: float = 550.00,
    **kwargs,
) -> Dict[str, Any]:
    """Create a merger/acquisition alert."""
    return create_sample_alert(
        ticker=ticker,
        signal_type="merger_acquisition",
        score=score,
        price=price,
        catalyst="merger_announcement",
        rvol=kwargs.get("rvol", 5.0),
        atr=kwargs.get("atr", 20.0),
        volume=kwargs.get("volume", 150000000),
        sentiment_score=kwargs.get("sentiment_score", 0.80),
        metadata={
            "deal_type": "acquisition",
            "target_company": "Figma",
            "deal_value": 20000000000,  # $20B
            "expected_close": "Q2 2025",
            **kwargs.get("metadata", {}),
        },
    )


def create_low_score_alert(
    ticker: str = "XYZ",
    score: float = 3.0,
    price: float = 25.00,
    **kwargs,
) -> Dict[str, Any]:
    """Create a low-score alert (should not trigger trades)."""
    return create_sample_alert(
        ticker=ticker,
        signal_type="weak_signal",
        score=score,
        price=price,
        catalyst="minor_news",
        rvol=kwargs.get("rvol", 1.1),
        atr=kwargs.get("atr", 1.0),
        volume=kwargs.get("volume", 5000000),
        sentiment_score=kwargs.get("sentiment_score", 0.2),
        metadata={
            "reason": "low_conviction",
            **kwargs.get("metadata", {}),
        },
    )


def create_multiple_alerts(count: int = 5, **kwargs) -> list[Dict[str, Any]]:
    """
    Create multiple alerts for testing.

    Args:
        count: Number of alerts to create
        **kwargs: Common parameters for all alerts

    Returns:
        List of alert dictionaries
    """
    alert_types = [
        ("AAPL", "breakout", 8.5, 175.00),
        ("TSLA", "earnings", 9.0, 250.00),
        ("NVDA", "insider_buying", 7.5, 500.00),
        ("MSFT", "analyst_upgrade", 7.0, 380.00),
        ("GOOGL", "breakout", 8.0, 140.00),
    ]

    alerts = []
    for i in range(min(count, len(alert_types))):
        ticker, signal_type, score, price = alert_types[i]
        alert = create_sample_alert(
            ticker=ticker,
            signal_type=signal_type,
            score=score,
            price=price,
            **kwargs,
        )
        alerts.append(alert)

    return alerts
