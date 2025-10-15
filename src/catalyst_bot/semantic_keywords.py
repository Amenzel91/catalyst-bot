"""Semantic keyword extraction using KeyBERT.

This module provides context-aware, semantic keyword extraction to supplement
traditional keyword matching. Uses KeyBERT with sentence transformers to extract
multi-word keyphrases that capture domain-specific concepts.
"""

import logging
import time
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SemanticKeywordExtractor:
    """Extract semantically relevant keywords using KeyBERT.

    KeyBERT uses BERT embeddings to extract keywords and keyphrases that are
    most similar to the document. This provides better context awareness than
    simple word frequency methods.

    Features:
    - Multi-word phrase extraction (unigrams, bigrams, trigrams)
    - Semantic similarity to capture domain concepts
    - Diversity algorithm (MaxSum) to avoid redundant keywords
    - Graceful degradation if KeyBERT unavailable
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize semantic keyword extractor.

        Args:
            model_name: Sentence transformer model to use. Default is fast and lightweight.
        """
        self.model_name = model_name
        self.kw_model: Optional[Any] = None
        self._initialize_model()

    def _initialize_model(self):
        """Lazy load KeyBERT model.

        This method handles import and initialization errors gracefully,
        allowing the system to continue without semantic extraction if
        the library is not available.
        """
        try:
            from keybert import KeyBERT

            logger.info(f"Initializing KeyBERT with model: {self.model_name}")
            start_time = time.time()

            self.kw_model = KeyBERT(model=self.model_name)

            elapsed = time.time() - start_time
            logger.info(f"KeyBERT model initialized successfully in {elapsed:.2f}s")

        except ImportError:
            logger.warning(
                "keybert not installed, semantic extraction disabled. "
                "Install with: pip install keybert"
            )
            self.kw_model = None
        except Exception as e:
            logger.warning(f"Failed to initialize KeyBERT: {e}")
            self.kw_model = None

    def extract_keywords(
        self,
        text: str,
        top_n: int = 5,
        keyphrase_ngram_range: Tuple[int, int] = (1, 3),
        use_maxsum: bool = True,
        diversity: float = 0.5,
        timeout_seconds: float = 5.0,
    ) -> List[str]:
        """Extract top N keywords from text.

        Args:
            text: Input text to extract keywords from
            top_n: Number of keywords to extract
            keyphrase_ngram_range: Range of n-grams (1-3 = unigrams to trigrams)
            use_maxsum: Use MaxSum diversity algorithm for diverse keywords
            diversity: Diversity parameter (0.0-1.0), higher = more diverse
            timeout_seconds: Max time to spend on extraction

        Returns:
            List of keyword strings (without scores)
        """
        if not self.kw_model or not text or not text.strip():
            return []

        try:
            start_time = time.time()

            keywords = self.kw_model.extract_keywords(
                text,
                keyphrase_ngram_range=keyphrase_ngram_range,
                stop_words="english",
                top_n=top_n,
                use_maxsum=use_maxsum,
                diversity=diversity,
                nr_candidates=20,
            )

            elapsed = time.time() - start_time

            # Check timeout
            if elapsed > timeout_seconds:
                logger.warning(
                    f"Keyword extraction took {elapsed:.2f}s (timeout: {timeout_seconds}s)"
                )

            # Extract just the keyword strings (discard scores)
            keyword_list = [kw for kw, score in keywords]

            logger.debug(
                f"Extracted {len(keyword_list)} keywords in {elapsed:.3f}s: {keyword_list}"
            )

            return keyword_list

        except Exception as e:
            logger.debug(f"Keyword extraction failed: {e}")
            return []

    def extract_keywords_with_scores(
        self,
        text: str,
        top_n: int = 5,
        keyphrase_ngram_range: Tuple[int, int] = (1, 3),
        use_maxsum: bool = True,
        diversity: float = 0.5,
    ) -> List[Tuple[str, float]]:
        """Extract keywords with similarity scores.

        Args:
            text: Input text to extract keywords from
            top_n: Number of keywords to extract
            keyphrase_ngram_range: Range of n-grams
            use_maxsum: Use MaxSum diversity algorithm
            diversity: Diversity parameter (0.0-1.0)

        Returns:
            List of (keyword, score) tuples
        """
        if not self.kw_model or not text or not text.strip():
            return []

        try:
            keywords = self.kw_model.extract_keywords(
                text,
                keyphrase_ngram_range=keyphrase_ngram_range,
                stop_words="english",
                top_n=top_n,
                use_maxsum=use_maxsum,
                diversity=diversity,
                nr_candidates=20,
            )

            return keywords

        except Exception as e:
            logger.debug(f"Keyword extraction with scores failed: {e}")
            return []

    def extract_from_feed_item(
        self,
        title: str,
        summary: str,
        top_n: int = 5,
        keyphrase_ngram_range: Tuple[int, int] = (1, 3),
    ) -> List[str]:
        """Extract keywords from RSS feed item (title + summary).

        Combines title and summary with title weighted more heavily
        by including it twice.

        Args:
            title: Feed item title
            summary: Feed item summary/description
            top_n: Number of keywords to extract
            keyphrase_ngram_range: Range of n-grams

        Returns:
            List of extracted keyword strings
        """
        # Weight title more heavily by including it twice
        title_text = title or ""
        summary_text = summary or ""

        text = f"{title_text} {title_text} {summary_text}".strip()

        if not text:
            return []

        return self.extract_keywords(
            text, top_n=top_n, keyphrase_ngram_range=keyphrase_ngram_range
        )

    def is_available(self) -> bool:
        """Check if KeyBERT is available.

        Returns:
            True if KeyBERT model is loaded and ready to use
        """
        return self.kw_model is not None

    def get_model_info(self) -> dict:
        """Get information about the loaded model.

        Returns:
            Dictionary with model information
        """
        return {
            "available": self.is_available(),
            "model_name": self.model_name,
            "backend": "KeyBERT with sentence-transformers",
        }


# Global singleton instance
_semantic_extractor: Optional[SemanticKeywordExtractor] = None


def get_semantic_extractor() -> SemanticKeywordExtractor:
    """Get or create global semantic keyword extractor instance.

    Returns:
        Singleton SemanticKeywordExtractor instance
    """
    global _semantic_extractor

    if _semantic_extractor is None:
        _semantic_extractor = SemanticKeywordExtractor()

    return _semantic_extractor
