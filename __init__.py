# src/catalyst_bot/__init__.py
from __future__ import annotations

__all__ = ["resolve", "resolve_many", "TickerHit"]


def __getattr__(name: str):
    """
    Lazy export to avoid import side effects at package import time.
    This prevents runpy RuntimeWarning when using `python -m catalyst_bot.ticker_resolver`.
    """
    if name in {"resolve", "resolve_many", "TickerHit"}:
        from .ticker_resolver import TickerHit, resolve, resolve_many

        mapping = {
            "resolve": resolve,
            "resolve_many": resolve_many,
            "TickerHit": TickerHit,
        }
        return mapping[name]
    raise AttributeError(name)
