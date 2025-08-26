"""Adaptive keyword weighting for the catalyst bot.

This module manages the dynamic adjustment of keyword category weights
based on analyzer results. The adjustment algorithm is intentionally
simple in this implementation: it preserves the static default
weights from configuration but ensures that a ``keyword_stats.json``
file exists for the classifier to consume. A more sophisticated
implementation could examine each trade simulation result to
incrementally boost or diminish weights per category.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List

from .config import get_settings
from .models import TradeSimResult


def update_keyword_stats(trade_results: List[TradeSimResult], date_str: str) -> None:
    """Update the dynamic keyword weights based on trade outcomes.

    This stub implementation writes out a file with the default
    keyword weights if it does not already exist. In a future
    iteration it could use ``trade_results`` to adjust weights.

    Parameters
    ----------
    trade_results : List[TradeSimResult]
        Results from the trade simulator (unused in stub).
    date_str : str
        The date string in YYYYMMDD format used for naming outputs.
    """
    settings = get_settings()
    analyzer_dir = settings.data_dir / "analyzer"
    analyzer_dir.mkdir(parents=True, exist_ok=True)
    stats_file = analyzer_dir / "keyword_stats.json"
    # Load existing stats if present
    existing: Dict[str, any] = {}
    if stats_file.exists():
        try:
            existing = json.loads(stats_file.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    # Prepare weights from configuration
    weights: Dict[str, float] = existing.get("weights", {})
    if not weights:
        for category in settings.keyword_categories:
            weights[category] = settings.keyword_default_weight
    # Write updated stats
    stats = {
        "last_updated": datetime.utcnow().isoformat(),
        "weights": weights,
    }
    try:
        stats_file.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    except Exception:
        pass
