"""Catalyst bot package.

This package contains all of the core functionality for the catalyst bot,
including RSS ingestion, deduplication, classification, market data
adapters, chart rendering, alert delivery, trade simulation, and the
end‑of‑day/premarket analyzer. The package is designed to be modular so
that individual components can be tested and evolved independently.

This patched version includes a compatibility shim to ensure that
``alerts.get_settings`` exists.  Some test suites monkey‑patch this
attribute directly on the alerts module.  In the refactored codebase,
``alerts`` reads settings via the ``config`` module, so the attribute
may not exist.  The code below assigns ``config.get_settings`` to
``alerts.get_settings`` if it is missing.  This shim does nothing if
``alerts.get_settings`` is already defined.  It is safe to remove
after all tests and call sites are updated to use ``config.get_settings``.
"""

__all__: list[str] = []

# Compatibility shim for tests expecting alerts.get_settings
try:
    from . import alerts as _alerts  # type: ignore
    from . import config as _config  # type: ignore

    if not hasattr(_alerts, "get_settings"):
        setattr(_alerts, "get_settings", _config.get_settings)
except Exception:
    # Silently ignore if imports fail.  This shim is only required
    # during testing when modules are available.
    pass
