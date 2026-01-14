"""
MOA (Missed Opportunities Analyzer) Module.

This module provides real-time tracking of rejected items and their price outcomes
to enable the MOA system to analyze fresh data daily.

Components:
- database.py: SQLite database for rejection tracking
- rejection_recorder.py: Records rejected items during classification
- outcome_tracker.py: Tracks price outcomes at multiple timeframes
- vision_analyzer.py: Vision LLM analysis for article/chart screenshots
- vision_llm.py: Gemini vision API interface
- manual_capture.py: Manual capture processing pipeline
- discord_listener.py: Discord channel listener for manual captures
"""

from .database import init_database, get_db_path
from .rejection_recorder import record_rejection, RejectionEvent
from .outcome_tracker import update_outcome_prices, export_outcomes_to_jsonl

__all__ = [
    "init_database",
    "get_db_path",
    "record_rejection",
    "RejectionEvent",
    "update_outcome_prices",
    "export_outcomes_to_jsonl",
]

# Lazy imports for optional components (to avoid import errors if discord not installed)
def start_manual_capture_listener():
    """Start the Discord listener for manual captures."""
    from .discord_listener import start_listener
    return start_listener()

def stop_manual_capture_listener():
    """Stop the Discord listener."""
    from .discord_listener import stop_listener
    return stop_listener()

def get_manual_capture_stats():
    """Get statistics about manual captures."""
    from .manual_capture import get_capture_stats
    return get_capture_stats()
