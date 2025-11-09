"""RAG (Retrieval-Augmented Generation) system for SEC filing Q&A.

This module provides vector search and LLM-powered question answering for SEC filings,
enabling "Dig Deeper" functionality where users can ask follow-up questions about
filings and get contextual answers.

Key Features:
- FAISS vector store for fast semantic search
- Filing text chunking (512 tokens per chunk)
- Embedding generation using sentence-transformers
- LLM-powered Q&A with retrieved context
- Per-ticker indexing with metadata filtering

Environment Variables:
- RAG_ENABLED: Enable RAG system (default: true)
- RAG_VECTOR_DB: Vector database backend (faiss or chromadb, default: faiss)
- RAG_INDEX_PATH: Path to index storage (default: data/rag_index/)
- RAG_MAX_CONTEXT_CHUNKS: Max chunks to retrieve (default: 3)
- RAG_ANSWER_MAX_TOKENS: Max LLM response length (default: 150)

Example:
    >>> rag = SECFilingRAG()
    >>> rag.index_filing(filing, summary="...", keywords=["earnings", "revenue_beat"])
    >>> results = rag.search("What were the revenue projections?", ticker="AAPL")
    >>> answer = await rag.answer_question("What were the revenue projections?", "AAPL")
    >>> print(answer)
    "The company projected Q2 2025 revenue of $150M-$175M, up from prior guidance..."

References:
- FAISS: https://github.com/facebookresearch/faiss
- Sentence Transformers: https://www.sbert.net/
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer

    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None
    np = None
    SentenceTransformer = None

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("rag_system")


log = get_logger("rag_system")


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_INDEX_PATH = "data/rag_index/"
DEFAULT_CHUNK_SIZE = 512  # tokens
DEFAULT_CHUNK_OVERLAP = 50  # tokens
DEFAULT_MAX_CONTEXT_CHUNKS = 3
DEFAULT_ANSWER_MAX_TOKENS = 150
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 384-dimensional embeddings


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class FilingChunk:
    """A chunk of filing text with metadata."""

    chunk_id: str  # MD5 hash of ticker + filing_url + chunk_index
    ticker: str
    filing_type: str
    filing_url: str
    filed_at: datetime
    chunk_index: int  # 0-based chunk number
    text: str  # Chunk content
    embedding: Optional[np.ndarray] = None
    metadata: dict = field(default_factory=dict)  # summary, keywords, etc.

    def to_dict(self) -> dict:
        """Serialize to dictionary (for storage)."""
        return {
            "chunk_id": self.chunk_id,
            "ticker": self.ticker,
            "filing_type": self.filing_type,
            "filing_url": self.filing_url,
            "filed_at": self.filed_at.isoformat(),
            "chunk_index": self.chunk_index,
            "text": self.text,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FilingChunk:
        """Deserialize from dictionary."""
        data["filed_at"] = datetime.fromisoformat(data["filed_at"])
        return cls(**data)


@dataclass
class SearchResult:
    """A search result with similarity score."""

    chunk: FilingChunk
    similarity: float  # 0.0-1.0 (cosine similarity)
    rank: int  # 1-based ranking


# ============================================================================
# Text Chunking
# ============================================================================


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """
    Split text into overlapping chunks.

    Parameters
    ----------
    text : str
        Text to chunk
    chunk_size : int
        Target chunk size in tokens (approximate, uses word splitting)
    overlap : int
        Overlap between chunks in tokens

    Returns
    -------
    list[str]
        List of text chunks

    Examples
    --------
    >>> text = "This is a long document. " * 1000
    >>> chunks = chunk_text(text, chunk_size=100, overlap=20)
    >>> len(chunks)
    ~10-15
    """
    # Approximate tokens as words (simple heuristic)
    words = text.split()

    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))

        # Move start forward by (chunk_size - overlap) for next chunk
        start += chunk_size - overlap

    return chunks


# ============================================================================
# RAG System
# ============================================================================


class SECFilingRAG:
    """RAG system for SEC filing question answering."""

    def __init__(
        self,
        index_path: Optional[str] = None,
        embedding_model: str = EMBEDDING_MODEL,
    ):
        """
        Initialize RAG system.

        Parameters
        ----------
        index_path : str, optional
            Path to store index (default: data/rag_index/)
        embedding_model : str
            Sentence-transformers model name

        Raises
        ------
        ImportError
            If FAISS or sentence-transformers not available
        """
        if not FAISS_AVAILABLE:
            raise ImportError(
                "FAISS and sentence-transformers required for RAG system. "
                "Install with: pip install faiss-cpu sentence-transformers"
            )

        self.index_path = Path(index_path or os.getenv("RAG_INDEX_PATH", DEFAULT_INDEX_PATH))
        self.index_path.mkdir(parents=True, exist_ok=True)

        # Initialize sentence transformer for embeddings
        log.info(f"Loading embedding model: {embedding_model}")
        self.encoder = SentenceTransformer(embedding_model)
        self.embedding_dim = self.encoder.get_sentence_embedding_dimension()

        # Initialize FAISS index
        self.index = self._load_or_create_index()

        # Metadata storage (chunk_id -> FilingChunk)
        self.chunks: dict[str, FilingChunk] = self._load_chunks()

        log.info(
            f"RAG system initialized: {len(self.chunks)} chunks indexed, "
            f"embedding_dim={self.embedding_dim}"
        )

    def _load_or_create_index(self) -> faiss.Index:
        """Load existing FAISS index or create new one."""
        index_file = self.index_path / "faiss.index"

        if index_file.exists():
            try:
                index = faiss.read_index(str(index_file))
                log.info(f"Loaded existing FAISS index: {index.ntotal} vectors")
                return index
            except Exception as e:
                log.warning(f"Failed to load index: {e}, creating new one")

        # Create new index (Inner Product for cosine similarity with normalized vectors)
        index = faiss.IndexFlatIP(self.embedding_dim)
        log.info(f"Created new FAISS index (dim={self.embedding_dim})")
        return index

    def _load_chunks(self) -> dict[str, FilingChunk]:
        """Load chunk metadata from disk."""
        chunks_file = self.index_path / "chunks.pkl"

        if chunks_file.exists():
            try:
                with open(chunks_file, "rb") as f:
                    chunks = pickle.load(f)
                log.info(f"Loaded {len(chunks)} chunk metadata")
                return chunks
            except Exception as e:
                log.warning(f"Failed to load chunks: {e}, starting fresh")

        return {}

    def _save_index(self):
        """Save FAISS index and metadata to disk."""
        try:
            faiss.write_index(self.index, str(self.index_path / "faiss.index"))

            with open(self.index_path / "chunks.pkl", "wb") as f:
                pickle.dump(self.chunks, f)

            log.info(f"Saved index: {self.index.ntotal} vectors, {len(self.chunks)} chunks")
        except Exception as e:
            log.error(f"Failed to save index: {e}")

    def index_filing(
        self,
        filing_section,
        summary: str = "",
        keywords: list[str] = None,
    ) -> int:
        """
        Index a SEC filing for vector search.

        Parameters
        ----------
        filing_section : FilingSection
            Parsed SEC filing from sec_parser.py
        summary : str
            Filing summary from llm_chain.py
        keywords : list[str]
            Keywords from llm_chain.py

        Returns
        -------
        int
            Number of chunks indexed

        Examples
        --------
        >>> from sec_parser import parse_8k_items
        >>> filings = parse_8k_items(filing_text, filing_url)
        >>> rag.index_filing(filings[0], summary="...", keywords=["earnings"])
        5  # 5 chunks indexed
        """
        # Chunk the filing text
        chunks_text = chunk_text(filing_section.text)

        if not chunks_text:
            log.warning(f"No chunks generated for {filing_section.ticker}")
            return 0

        log.info(
            f"Indexing {filing_section.ticker} {filing_section.filing_type}: "
            f"{len(chunks_text)} chunks"
        )

        # Create FilingChunk objects
        filing_chunks = []
        for i, chunk_text in enumerate(chunks_text):
            chunk_id = hashlib.md5(
                f"{filing_section.ticker}{filing_section.filing_url}{i}".encode()
            ).hexdigest()

            chunk = FilingChunk(
                chunk_id=chunk_id,
                ticker=filing_section.ticker,
                filing_type=filing_section.filing_type,
                filing_url=filing_section.filing_url,
                filed_at=datetime.utcnow(),  # Would use actual filing date if available
                chunk_index=i,
                text=chunk_text,
                metadata={
                    "summary": summary,
                    "keywords": keywords or [],
                    "catalyst_type": filing_section.catalyst_type,
                },
            )

            filing_chunks.append(chunk)

        # Generate embeddings
        chunk_texts = [c.text for c in filing_chunks]
        embeddings = self.encoder.encode(chunk_texts, normalize_embeddings=True)

        # Add to FAISS index
        self.index.add(embeddings.astype("float32"))

        # Store chunk metadata
        for chunk, embedding in zip(filing_chunks, embeddings):
            chunk.embedding = embedding
            self.chunks[chunk.chunk_id] = chunk

        # Save to disk
        self._save_index()

        return len(filing_chunks)

    def search(
        self,
        query: str,
        ticker: Optional[str] = None,
        top_k: int = None,
    ) -> list[SearchResult]:
        """
        Search indexed filings by natural language query.

        Parameters
        ----------
        query : str
            Natural language search query
        ticker : str, optional
            Filter results by ticker
        top_k : int, optional
            Number of results to return (default: RAG_MAX_CONTEXT_CHUNKS)

        Returns
        -------
        list[SearchResult]
            Search results ranked by similarity

        Examples
        --------
        >>> results = rag.search("What were the acquisition terms?", ticker="AAPL")
        >>> for result in results:
        ...     print(f"{result.rank}. {result.chunk.text[:100]}... (similarity: {result.similarity:.2f})")
        """
        if top_k is None:
            top_k = int(os.getenv("RAG_MAX_CONTEXT_CHUNKS", DEFAULT_MAX_CONTEXT_CHUNKS))

        # Generate query embedding
        query_embedding = self.encoder.encode([query], normalize_embeddings=True)

        # Search FAISS index
        similarities, indices = self.index.search(query_embedding.astype("float32"), top_k * 2)  # Get extra for filtering

        # Convert to SearchResults
        results = []
        for rank, (similarity, idx) in enumerate(zip(similarities[0], indices[0]), start=1):
            if idx == -1:  # FAISS returns -1 for empty slots
                continue

            # Get chunk by index
            chunk_id = list(self.chunks.keys())[idx]
            chunk = self.chunks[chunk_id]

            # Filter by ticker if specified
            if ticker and chunk.ticker != ticker:
                continue

            results.append(
                SearchResult(
                    chunk=chunk,
                    similarity=float(similarity),
                    rank=rank,
                )
            )

            if len(results) >= top_k:
                break

        log.info(f"Search query='{query[:50]}...' returned {len(results)} results")
        return results

    async def answer_question(
        self,
        query: str,
        ticker: str,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Answer user question about a filing using RAG.

        Flow:
        1. Search for relevant filing chunks
        2. Construct context from top results
        3. Send to LLM with prompt: "Based on this SEC filing, answer: {query}"
        4. Return concise answer

        Parameters
        ----------
        query : str
            User's question
        ticker : str
            Ticker symbol to query
        max_tokens : int, optional
            Max tokens for LLM answer (default: RAG_ANSWER_MAX_TOKENS)

        Returns
        -------
        str
            LLM-generated answer

        Examples
        --------
        >>> answer = await rag.answer_question("What were the revenue projections?", "AAPL")
        >>> print(answer)
        "The company projected Q2 2025 revenue of $150M-$175M..."
        """
        if max_tokens is None:
            max_tokens = int(os.getenv("RAG_ANSWER_MAX_TOKENS", DEFAULT_ANSWER_MAX_TOKENS))

        # Search for relevant chunks
        results = self.search(query, ticker=ticker)

        if not results:
            return f"No information found about {ticker} in indexed filings."

        # Construct context from top results
        context_parts = []
        for result in results:
            context_parts.append(
                f"[Chunk {result.rank}, similarity={result.similarity:.2f}]:\n{result.chunk.text}"
            )

        context = "\n\n".join(context_parts)

        # Construct LLM prompt
        prompt = f"""Based on the following SEC filing excerpt for {ticker}, answer this question concisely:

Question: {query}

Filing Context:
{context}

Provide a direct, factual answer in {max_tokens} tokens or less. Include specific numbers and dates when available."""

        # Call LLM (using hybrid router)
        try:
            from .llm_hybrid import query_hybrid_llm

            answer = await query_hybrid_llm(prompt, priority="high")

            if answer:
                log.info(f"RAG answered query for {ticker}: {query[:50]}...")
                return answer.strip()
            else:
                return "Unable to generate answer at this time. Please try again."

        except Exception as e:
            log.error(f"RAG answer generation failed: {e}")
            return f"Error generating answer: {str(e)[:100]}"

    def get_stats(self) -> dict:
        """Get RAG system statistics."""
        ticker_counts = {}
        for chunk in self.chunks.values():
            ticker_counts[chunk.ticker] = ticker_counts.get(chunk.ticker, 0) + 1

        return {
            "total_chunks": len(self.chunks),
            "total_vectors": self.index.ntotal,
            "unique_tickers": len(ticker_counts),
            "top_tickers": sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "embedding_dim": self.embedding_dim,
            "index_path": str(self.index_path),
        }


# ============================================================================
# Configuration Helpers
# ============================================================================


def is_rag_enabled() -> bool:
    """Check if RAG system is enabled in configuration."""
    return os.getenv("RAG_ENABLED", "true").lower() in ("true", "1", "yes")


def get_rag_vector_db() -> str:
    """Get configured vector database backend."""
    return os.getenv("RAG_VECTOR_DB", "faiss").lower()


# Global RAG instance (lazy initialization)
_rag_instance: Optional[SECFilingRAG] = None


def get_rag() -> Optional[SECFilingRAG]:
    """
    Get global RAG instance (singleton pattern).

    Returns
    -------
    SECFilingRAG or None
        RAG instance if enabled, else None

    Examples
    --------
    >>> rag = get_rag()
    >>> if rag:
    ...     results = rag.search("acquisition terms", ticker="AAPL")
    """
    global _rag_instance

    if not is_rag_enabled():
        log.debug("RAG system disabled via configuration")
        return None

    if not FAISS_AVAILABLE:
        log.warning("RAG system unavailable: FAISS not installed")
        return None

    if _rag_instance is None:
        try:
            _rag_instance = SECFilingRAG()
            log.info("RAG system initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize RAG system: {e}")
            return None

    return _rag_instance
