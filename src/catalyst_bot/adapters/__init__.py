"""
Adapters Package

This package contains adapter classes that bridge different parts of the
Catalyst Bot trading system, enabling clean integration between components.
"""

from .signal_adapter import SignalAdapter, SignalAdapterConfig

__all__ = ["SignalAdapter", "SignalAdapterConfig"]
