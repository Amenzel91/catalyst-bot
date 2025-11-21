"""
Base Processor Interface
========================

Abstract base class that all document processors must implement.
Ensures consistent interface across different processor types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseProcessor(ABC):
    """
    Abstract base class for document processors.

    All processors should:
    1. Use the unified LLMService for consistency
    2. Return structured results (dataclasses)
    3. Handle errors gracefully
    4. Track costs via feature_name
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize processor.

        Args:
            config: Optional configuration dict
        """
        self.config = config or {}

    @abstractmethod
    async def process(self, *args, **kwargs) -> Any:
        """
        Process document and return structured result.

        Subclasses must implement this method.
        """
        pass
