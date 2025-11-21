"""
Document Processors
===================

Specialized processors for different document types that use the unified LLM service.

Processors:
- sec_processor: SEC filing analysis (8-K, 10-Q, 10-K, etc.)
- sentiment_processor: News sentiment analysis (future)
- news_processor: General news classification (future)

All processors use the centralized LLMService for consistency and cost tracking.
"""

from .base import BaseProcessor
from .sec_processor import SECProcessor, SECAnalysisResult

__all__ = ["BaseProcessor", "SECProcessor", "SECAnalysisResult"]
