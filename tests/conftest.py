# Narrow deprecation filter for tests only.
# Keeps application logging intact while preventing noisy utcnow warnings during pytest runs.
import sys
import types
import warnings

import pytest


def pytest_configure(config):
    # Suppress only the well-known Python 3.12+ deprecation for datetime.utcnow() in tests.
    warnings.filterwarnings(
        "ignore",
        message=r"datetime\.datetime\.utcnow\(\) is deprecated.*",
        category=DeprecationWarning,
    )


@pytest.fixture(autouse=True, scope="session")
def _stub_feedparser_module():
    """
    Ensure catalyst_bot.feeds imports without external dependency.
    We inject a minimal 'feedparser' module whose parse() returns an object
    with an empty 'entries' list by default. Individual tests can monkeypatch
    parse() to return custom entries.
    """
    if "feedparser" not in sys.modules:
        m = types.SimpleNamespace()

        def _parse(_text):
            class _R:
                pass

            _R.entries = []
            return _R

        m.parse = _parse
        sys.modules["feedparser"] = m
    yield
