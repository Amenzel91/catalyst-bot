# src/catalyst_bot/__init__.py
__all__ = []
# Keep this file lean. Avoid importing submodules at import time.
# If you need names for type hints:
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .ticker_resolver import resolve  # or whatever symbols you reference in type hints
