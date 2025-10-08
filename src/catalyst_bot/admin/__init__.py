"""
Admin Controls Module
=====================

Self-learning admin control system for the Catalyst trading bot.

Features:
- Nightly admin reports with parameter recommendations
- Admin approval/rejection via Discord buttons
- Auto-apply approved parameter changes
- Track performance of parameter changes over time
"""

from .parameter_manager import ParameterManager, get_change_history, rollback_change
from .report_generator import AdminReportGenerator

__all__ = [
    "ParameterManager",
    "AdminReportGenerator",
    "get_change_history",
    "rollback_change",
]
