# Narrow deprecation filter for tests only.
# Keeps application logging intact while preventing noisy utcnow warnings during pytest runs.
import warnings


def pytest_configure(config):
    # Suppress only the well-known Python 3.12+ deprecation for datetime.utcnow() in tests.
    warnings.filterwarnings(
        "ignore",
        message=r"datetime\.datetime\.utcnow\(\) is deprecated.*",
        category=DeprecationWarning,
    )
