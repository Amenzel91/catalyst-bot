"""Catalyst bot package.

This package contains all of the core functionality for the catalyst bot,
including RSS ingestion, deduplication, classification, market data
adapters, chart rendering, alert delivery, trade simulation, and the
end‑of‑day/premarket analyzer. The package is designed to be modular so
that individual components can be tested and evolved independently.
"""

# When importing submodules via ``from catalyst_bot import alerts`` or similar,
# Python will look for attributes on this package.  Out of the box this
# ``__init__`` only defines an empty ``__all__``, so the import would fail
# with ``AttributeError``.  To support the test suite and callers that
# expect to import submodules directly from the package (e.g. ``from
# catalyst_bot import alerts, config``), implement a module-level
# ``__getattr__`` that dynamically imports the requested submodule on
# demand.  This preserves backwards compatibility while keeping the
# namespace clean.  Only submodules that actually exist under this
# package will be imported; otherwise an AttributeError is raised.
# Do not define a static ``__all__`` here.  When ``__all__`` is present,
# ``from catalyst_bot import alerts`` will only succeed if ``alerts`` is
# explicitly listed in ``__all__``.  Because we implement a dynamic
# ``__getattr__`` to load submodules on demand, defining an empty
# ``__all__`` prevents Python from delegating to ``__getattr__`` during
# import.  By omitting ``__all__``, ``from catalyst_bot import alerts``
# triggers ``__getattr__`` for unknown names, allowing the submodule to
# be imported lazily and cached on this package.

# Intentionally do not set ``__all__``.  The dynamic loader in
# ``__getattr__`` will handle unknown attribute accesses.

import importlib
from types import ModuleType
from typing import Any


def __getattr__(name: str) -> Any:
    """Dynamically load submodules as attributes of the ``catalyst_bot`` package.

    This function is invoked when an attribute lookup on this module
    (``catalyst_bot``) fails.  If the attribute name matches a valid
    submodule in this package, that submodule is imported and returned.
    Otherwise, an ``AttributeError`` is raised as usual.

    Examples
    --------
    >>> from catalyst_bot import alerts, config
    >>> alerts  # resolves to catalyst_bot.alerts module
    <module 'catalyst_bot.alerts' ...>

    >>> from catalyst_bot import nonexistent
    Traceback (most recent call last):
        ...
    AttributeError: module 'catalyst_bot' has no attribute 'nonexistent'
    """
    try:
        # Attempt to import ``catalyst_bot.<name>``.  If the module exists,
        # return it; otherwise import_module will raise ModuleNotFoundError,
        # which we catch below and convert to AttributeError.
        module: ModuleType = importlib.import_module(f".{name}", __name__)
    except ModuleNotFoundError as exc:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'") from exc
    # Cache the loaded module on this package so future lookups don't
    # re-import it.
    globals()[name] = module
    return module


# -----------------------------------------------------------------------------
# Compatibility shim for test fixtures
#
# Some test suites expect to patch ``alerts.get_settings`` directly.  In
# previous versions of the code, ``alerts.py`` imported ``get_settings``
# directly from ``config``.  Since that import has been removed in favor of
# accessing settings via the ``config`` module (to support monkey‑patching in
# tests), the ``alerts`` module may no longer define ``get_settings``.  To
# preserve backward compatibility and allow fixtures to monkey‑patch the
# function, assign ``config.get_settings`` onto the ``alerts`` module when it
# is missing.  This is done here in ``__init__`` so that it runs whenever
# ``catalyst_bot`` is imported.
try:
    from . import alerts as _alerts  # type: ignore
    from . import config as _config  # type: ignore

    # Only set the alias if it does not already exist on alerts
    if not hasattr(_alerts, "get_settings"):
        setattr(_alerts, "get_settings", _config.get_settings)
except Exception:
    # If either module fails to import, silently skip; the alias is only
    # needed for testing and will not affect runtime behaviour.
    pass
