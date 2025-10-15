"""
SEC EDGAR Document Fetcher
===========================

Fetches and parses actual SEC filing documents (8-K, etc.) from EDGAR
to extract text content for keyword matching.

Features:
- Fetches HTML documents from SEC EDGAR
- Extracts clean text from filing content
- Multi-level caching (memory + disk) with TTL
- Rate limiting for SEC compliance (10 req/sec max)

Author: Claude Code
Date: 2025-10-11
"""

from __future__ import annotations

import hashlib
import pickle
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from .logging_utils import get_logger

log = get_logger("sec_document_fetcher")

# Use same User-Agent as feeds module for consistency
USER_AGENT = "CatalystBot/1.0 (+https://example.local)"

# SEC rate limiting: 10 requests/second max
SEC_RATE_LIMIT = 0.1  # seconds between requests
_last_sec_request_time = 0.0

# Cache settings
CACHE_DIR = Path("data/cache/sec_documents")
CACHE_TTL_DAYS = 90  # SEC filings don't change, cache for 90 days
MEMORY_CACHE_SIZE = 100  # Keep 100 most recent in memory

# In-memory cache: {accession_number: (cached_at, text)}
_memory_cache: Dict[str, Tuple[datetime, str]] = {}


def _apply_rate_limit() -> None:
    """Apply SEC rate limiting (max 10 requests/second)."""
    global _last_sec_request_time

    now = time.time()
    elapsed = now - _last_sec_request_time

    if elapsed < SEC_RATE_LIMIT:
        time.sleep(SEC_RATE_LIMIT - elapsed)

    _last_sec_request_time = time.time()


def _get_cache_key(accession_number: str) -> str:
    """Generate cache key from accession number."""
    # Remove dashes from accession number for cleaner filenames
    return accession_number.replace("-", "")


def _get_disk_cache_path(accession_number: str) -> Path:
    """
    Get disk cache file path for an accession number.

    Args:
        accession_number: SEC accession number (e.g., 0001193125-24-249922)

    Returns:
        Path to cache file
    """
    cache_key = _get_cache_key(accession_number)
    key_hash = hashlib.md5(cache_key.encode()).hexdigest()

    # Create 2-level directory structure
    subdir = CACHE_DIR / key_hash[:2] / key_hash[2:4]
    subdir.mkdir(parents=True, exist_ok=True)

    return subdir / f"{cache_key}.pkl"


def _get_from_cache(accession_number: str) -> Optional[str]:
    """
    Get document text from cache.

    Args:
        accession_number: SEC accession number

    Returns:
        Cached text or None if not found/expired
    """
    # Check memory cache first
    if accession_number in _memory_cache:
        cached_at, text = _memory_cache[accession_number]
        cache_age_days = (datetime.now(timezone.utc) - cached_at).days

        if cache_age_days <= CACHE_TTL_DAYS:
            return text
        else:
            # Expired - remove from memory cache
            del _memory_cache[accession_number]

    # Check disk cache
    cache_path = _get_disk_cache_path(accession_number)

    if cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                cache_data = pickle.load(f)

            cached_at = cache_data.get("cached_at")
            text = cache_data.get("text")

            if cached_at and text:
                cache_age_days = (datetime.now(timezone.utc) - cached_at).days

                if cache_age_days <= CACHE_TTL_DAYS:
                    # Valid cache - load into memory
                    _memory_cache[accession_number] = (cached_at, text)

                    # Limit memory cache size
                    if len(_memory_cache) > MEMORY_CACHE_SIZE:
                        # Remove oldest entry
                        oldest_key = min(_memory_cache.keys(),
                                       key=lambda k: _memory_cache[k][0])
                        del _memory_cache[oldest_key]

                    return text

        except Exception as e:
            log.debug(f"disk_cache_load_failed accession={accession_number} err={e}")

    return None


def _put_in_cache(accession_number: str, text: str) -> None:
    """
    Put document text in cache.

    Args:
        accession_number: SEC accession number
        text: Document text
    """
    cached_at = datetime.now(timezone.utc)

    # Store in memory cache
    _memory_cache[accession_number] = (cached_at, text)

    # Limit memory cache size
    if len(_memory_cache) > MEMORY_CACHE_SIZE:
        oldest_key = min(_memory_cache.keys(),
                        key=lambda k: _memory_cache[k][0])
        del _memory_cache[oldest_key]

    # Store in disk cache
    try:
        cache_path = _get_disk_cache_path(accession_number)
        cache_data = {
            "accession_number": accession_number,
            "text": text,
            "cached_at": cached_at,
        }

        with open(cache_path, "wb") as f:
            pickle.dump(cache_data, f)

    except Exception as e:
        log.debug(f"disk_cache_write_failed accession={accession_number} err={e}")


def _extract_accession_from_link(link: str) -> Optional[str]:
    """
    Extract accession number from SEC EDGAR link.

    Args:
        link: EDGAR link (e.g., https://www.sec.gov/cgi-bin/viewer?action=view&cik=6201&accession_number=0001193125-24-249922)

    Returns:
        Accession number or None if not found
    """
    # Pattern: accession_number=NNNNNNNNNN-NN-NNNNNN
    match = re.search(r"accession_number=(\d{10}-\d{2}-\d{6})", link)
    if match:
        return match.group(1)

    # Alternative pattern: /Archives/edgar/data/CIK/ACCESSION/filename.htm
    match = re.search(r"/(\d{10}-\d{2}-\d{6})/", link)
    if match:
        return match.group(1)

    # Pattern for links with dashes removed: /NNNNNNNNNNNNNNNNNN/
    match = re.search(r"/(\d{18})/", link)
    if match:
        # Re-add dashes: NNNNNNNNNN-NN-NNNNNN
        raw = match.group(1)
        return f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"

    return None


def _extract_cik_from_link(link: str) -> Optional[str]:
    """
    Extract CIK from SEC EDGAR link.

    Args:
        link: EDGAR link containing CIK

    Returns:
        CIK as string or None if not found
    """
    # Pattern: cik=NNNNNN
    match = re.search(r"cik=(\d+)", link, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern: /data/CIK/
    match = re.search(r"/data/(\d+)/", link)
    if match:
        return match.group(1)

    return None


def _build_document_url(accession_number: str, cik: Optional[str] = None) -> str:
    """
    Build URL to SEC EDGAR document.

    Args:
        accession_number: SEC accession number (e.g., 0001193125-24-249922)
        cik: Central Index Key (optional, can be extracted from accession)

    Returns:
        URL to document
    """
    # Remove dashes from accession number for URL
    accession_clean = accession_number.replace("-", "")

    # Extract CIK from accession number if not provided
    # First 10 digits of accession number are often the filer CIK
    if not cik:
        # Try to extract CIK from the accession number structure
        # Format: NNNNNNNNNN-YY-NNNNNN where first part is often CIK
        cik = accession_number.split("-")[0].lstrip("0") or "0"

    # Build URL to filing index page
    # Format: https://www.sec.gov/cgi-bin/viewer?action=view&cik=CIK&accession_number=ACCESSION
    url = f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={cik}&accession_number={accession_number}&xbrl_type=v"

    return url


def _parse_sec_html(html: str) -> str:
    """
    Parse SEC HTML document and extract clean text.

    Args:
        html: Raw HTML content

    Returns:
        Extracted text content
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return text

    except Exception as e:
        log.warning(f"sec_html_parse_failed err={e}")
        return ""


def _get_primary_document_via_api(cik: str, accession: str) -> Optional[str]:
    """
    Use SEC Submissions API to get primary document filename.

    This is the recommended approach per SEC EDGAR API documentation.

    Args:
        cik: Central Index Key (e.g., "6201")
        accession: Accession number with dashes (e.g., "0001193125-24-249922")

    Returns:
        Full URL to primary document or None if not found
    """
    try:
        # Pad CIK to 10 digits
        cik_padded = f"{int(cik):010d}"

        # Build Submissions API URL
        api_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }

        # Apply rate limiting
        _apply_rate_limit()

        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Search for accession number in recent filings
        recent = data.get("filings", {}).get("recent", {})
        accessions = recent.get("accessionNumber", [])

        if accession not in accessions:
            log.debug(f"accession_not_in_recent cik={cik} accession={accession}")
            return None

        # Get index of our filing
        idx = accessions.index(accession)

        # Get primary document filename
        primary_docs = recent.get("primaryDocument", [])
        if idx >= len(primary_docs):
            log.debug(f"primary_doc_not_found idx={idx} len={len(primary_docs)}")
            return None

        primary_doc_filename = primary_docs[idx]

        # Construct full URL
        accession_clean = accession.replace("-", "")
        primary_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{primary_doc_filename}"

        log.debug(f"primary_doc_found via_api cik={cik} accession={accession} doc={primary_doc_filename}")
        return primary_url

    except requests.RequestException as e:
        log.debug(f"submissions_api_failed cik={cik} err={e}")
        return None
    except (KeyError, ValueError, IndexError) as e:
        log.debug(f"submissions_api_parse_failed cik={cik} err={e}")
        return None
    except Exception as e:
        log.warning(f"submissions_api_error cik={cik} err={e}")
        return None


def _extract_primary_doc_from_index(index_url: str) -> Optional[str]:
    """
    Parse index page HTML to extract primary document link.

    This is a fallback when Submissions API fails.

    Args:
        index_url: URL to -index.htm page

    Returns:
        Full URL to primary document or None if not found
    """
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Accept-Encoding": "gzip, deflate",
        }

        # Apply rate limiting
        _apply_rate_limit()

        response = requests.get(index_url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Find table with document list
        # Look for first .htm/.html link that's not the -index.htm itself
        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Skip index pages and XML files
            if "index.htm" in href or href.endswith(".xml"):
                continue

            # Look for primary document (usually .htm or .html)
            if href.endswith(".htm") or href.endswith(".html"):
                # Construct full URL
                if href.startswith("http"):
                    doc_url = href
                else:
                    # Relative URL - construct from index URL
                    base_url = index_url.rsplit("/", 1)[0]
                    doc_url = f"{base_url}/{href}"

                log.debug(f"primary_doc_found via_index doc={href}")
                return doc_url

        log.debug(f"primary_doc_not_found_in_index url={index_url}")
        return None

    except requests.RequestException as e:
        log.debug(f"index_parse_failed url={index_url} err={e}")
        return None
    except Exception as e:
        log.warning(f"index_parse_error url={index_url} err={e}")
        return None


def fetch_sec_document_text(link: str, accession_number: Optional[str] = None) -> str:
    """
    Fetch and extract text from SEC EDGAR document.

    Enhanced to extract primary documents using:
    1. SEC Submissions API (recommended)
    2. Index page parsing (fallback)

    This ensures we get actual filing content, not just index pages.

    Args:
        link: SEC EDGAR link (may be RSS link, index page, or primary document)
        accession_number: Optional accession number (will extract from link if not provided)

    Returns:
        Extracted text content (empty string if fetch fails)
    """
    # Extract accession number from link if not provided
    if not accession_number:
        accession_number = _extract_accession_from_link(link)
        if not accession_number:
            log.debug(f"sec_accession_not_found link={link}")
            return ""

    # Check cache first
    cached_text = _get_from_cache(accession_number)
    if cached_text is not None:
        log.debug(f"sec_cache_hit accession={accession_number}")
        return cached_text

    # Extract CIK from link (needed for API and URL construction)
    cik = _extract_cik_from_link(link)
    if not cik:
        log.debug(f"sec_cik_not_found link={link}")
        # Try fallback: use first 10 digits of accession as CIK
        cik = accession_number.split("-")[0]

    log.debug(f"sec_extracted cik={cik} accession={accession_number}")

    # Strategy 1: Use Submissions API to get primary document (RECOMMENDED)
    log.debug(f"trying_submissions_api cik={cik} accession={accession_number}")
    primary_doc_url = _get_primary_document_via_api(cik, accession_number)

    # Strategy 2: Fallback to index page parsing
    if not primary_doc_url:
        # Construct index URL from accession and CIK
        accession_clean = accession_number.replace("-", "")
        index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{accession_number}-index.htm"

        log.debug(f"trying_index_parse cik={cik} accession={accession_number} url={index_url}")
        primary_doc_url = _extract_primary_doc_from_index(index_url)

    # If we still don't have a primary document URL, try the original link as last resort
    if not primary_doc_url:
        log.warning(f"all_strategies_failed falling_back_to_original accession={accession_number} original_link={link}")
        primary_doc_url = link
    else:
        log.info(f"primary_doc_discovered accession={accession_number} url={primary_doc_url}")

    # Now fetch and parse the primary document
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "gzip, deflate",
        }

        # Apply rate limiting
        _apply_rate_limit()

        response = requests.get(primary_doc_url, headers=headers, timeout=30)
        response.raise_for_status()

        # Parse HTML and extract text
        text = _parse_sec_html(response.text)

        # Limit text length (for memory efficiency, but keep enough for LLM)
        max_length = 100000  # 100KB text limit (increased for full document analysis)
        if len(text) > max_length:
            text = text[:max_length]

        # Cache the result
        _put_in_cache(accession_number, text)

        log.info(f"sec_fetch_success accession={accession_number} length={len(text)} url={primary_doc_url}")
        return text

    except requests.RequestException as e:
        log.warning(f"sec_fetch_failed accession={accession_number} url={primary_doc_url} err={e}")
        return ""
    except Exception as e:
        log.error(f"sec_fetch_error accession={accession_number} url={primary_doc_url} err={e}")
        return ""


def enrich_sec_summary(link: str, original_summary: str) -> str:
    """
    Enrich SEC feed summary with actual document content.

    Args:
        link: SEC EDGAR link
        original_summary: Original RSS feed summary (filing metadata)

    Returns:
        Enhanced summary (original + document excerpt)
    """
    # Fetch document text
    doc_text = fetch_sec_document_text(link)

    if not doc_text:
        return original_summary

    # Extract a relevant excerpt (first 2000 chars after header)
    # Skip the first 500 chars which are usually boilerplate
    excerpt = doc_text[500:2500] if len(doc_text) > 500 else doc_text

    # Combine original metadata with document excerpt
    enhanced = f"{original_summary}\n\nDocument Content: {excerpt}"

    return enhanced


# Initialize cache directory
CACHE_DIR.mkdir(parents=True, exist_ok=True)
