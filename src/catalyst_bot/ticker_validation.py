"""Ticker validation against official exchange lists."""

import logging
from typing import Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Fallback list of common valid tickers (updated periodically)
# This provides basic validation when get-all-tickers library fails
FALLBACK_VALID_TICKERS = {
    # Major tech stocks
    "AAPL",
    "MSFT",
    "GOOGL",
    "GOOG",
    "AMZN",
    "META",
    "TSLA",
    "NVDA",
    "AMD",
    "INTC",
    "ADBE",
    "CRM",
    "ORCL",
    "CSCO",
    "AVGO",
    "QCOM",
    "TXN",
    "NFLX",
    "DIS",
    "PYPL",
    "UBER",
    "LYFT",
    "SNAP",
    "PINS",
    "TWTR",
    "SQ",
    "SHOP",
    "SPOT",
    "ZM",
    "DOCU",
    # Financial stocks
    "JPM",
    "BAC",
    "WFC",
    "C",
    "GS",
    "MS",
    "BLK",
    "SCHW",
    "USB",
    "PNC",
    "V",
    "MA",
    "AXP",
    "COF",
    "DFS",
    # Healthcare & Pharma
    "JNJ",
    "UNH",
    "PFE",
    "ABBV",
    "TMO",
    "MRK",
    "ABT",
    "DHR",
    "BMY",
    "AMGN",
    "LLY",
    "GILD",
    "CVS",
    "CI",
    "HUM",
    "ANTM",
    "BIIB",
    "VRTX",
    "REGN",
    "ISRG",
    # Consumer & Retail
    "WMT",
    "HD",
    "MCD",
    "NKE",
    "SBUX",
    "TGT",
    "LOW",
    "TJX",
    "COST",
    "CMG",
    # Energy & Utilities
    "XOM",
    "CVX",
    "COP",
    "SLB",
    "EOG",
    "PXD",
    "OXY",
    "HAL",
    "MPC",
    "PSX",
    "NEE",
    "DUK",
    "SO",
    "D",
    "AEP",
    "EXC",
    "SRE",
    "PCG",
    "ED",
    # Industrial & Manufacturing
    "BA",
    "CAT",
    "GE",
    "MMM",
    "HON",
    "UPS",
    "LMT",
    "RTX",
    "DE",
    "UNP",
    # Popular small/mid caps
    "PLTR",
    "SOFI",
    "RIVN",
    "LCID",
    "NIO",
    "XPEV",
    "LI",
    "BABA",
    "JD",
    "PDD",
    "COIN",
    "HOOD",
    "AFRM",
    "UPST",
    "OPEN",
    "RBLX",
    "U",
    "PATH",
    "DKNG",
    "PENN",
    # ETFs and indices (sometimes extracted from news)
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "VOO",
    "VTI",
    "ARKK",
    "ARKG",
    "ARKF",
    "TLT",
}


class TickerValidator:
    """Validate tickers against official NASDAQ/NYSE/AMEX lists."""

    def __init__(self):
        """Initialize validator and load ticker list."""
        self._valid_tickers: Optional[Set[str]] = None
        self._load_valid_tickers()

    def _load_valid_tickers(self):
        """Load valid ticker list from get-all-tickers library."""
        try:
            from get_all_tickers import Region
            from get_all_tickers.get_tickers import get_tickers as get_all_tickers_func

            # Try to load North American tickers (NASDAQ, NYSE, AMEX)
            ticker_list = get_all_tickers_func(Region.NORTH_AMERICA)
            self._valid_tickers = set(t.upper() for t in ticker_list if t)
            logger.info(
                f"Loaded {len(self._valid_tickers)} valid tickers from official exchanges"
            )
        except ImportError:
            logger.warning(
                "get-all-tickers not installed, using fallback list of %d common tickers",
                len(FALLBACK_VALID_TICKERS),
            )
            self._valid_tickers = FALLBACK_VALID_TICKERS.copy()
        except Exception as e:
            logger.warning(
                "Failed to load ticker list (%s), disabling ticker validation to avoid false rejections",
                str(e),
            )
            # Don't use restrictive fallback list for penny stock bot
            # Ticker extraction logic will handle false positives (ESMO, FDA, etc.)
            self._valid_tickers = None

    def is_valid(self, ticker: str) -> bool:
        """
        Check if ticker exists on major US exchanges.

        When get-all-tickers validation is unavailable, falls back to Yahoo Finance
        validation to catch completely invalid/delisted tickers.

        Args:
            ticker: Stock ticker symbol to validate

        Returns:
            True if ticker is valid, False otherwise
        """
        if not self._valid_tickers:
            # Fallback to Yahoo Finance validation when get-all-tickers unavailable
            # This catches completely invalid tickers like APXT (delisted/merged)
            return self.verify_with_yahoo_finance(ticker)
        return ticker.upper() in self._valid_tickers

    def validate_and_log(self, ticker: str, source: str = "unknown") -> bool:
        """
        Validate ticker and log rejections.

        Args:
            ticker: Stock ticker symbol to validate
            source: Source of the ticker for logging purposes

        Returns:
            True if ticker is valid, False otherwise
        """
        if not ticker or not ticker.strip():
            return False
        is_valid = self.is_valid(ticker)
        if not is_valid:
            logger.debug(f"Rejected invalid ticker '{ticker}' from {source}")
        return is_valid

    @property
    def ticker_count(self) -> int:
        """Return the number of valid tickers loaded."""
        return len(self._valid_tickers) if self._valid_tickers else 0

    @property
    def is_enabled(self) -> bool:
        """Return True if validation is enabled (tickers loaded successfully)."""
        return bool(self._valid_tickers)

    def is_otc(self, ticker: str) -> bool:
        """
        Check if ticker trades on OTC market (OTCQB, OTCQX, Pink Sheets).

        OTC stocks are typically illiquid and unsuitable for day trading alerts.

        Args:
            ticker: Stock ticker symbol to check

        Returns:
            True if ticker is OTC, False if on major exchange (NASDAQ/NYSE/AMEX)
        """
        if not ticker or not ticker.strip():
            return False

        ticker = ticker.upper().strip()

        # If validation is disabled, cannot determine OTC status
        if not self._valid_tickers:
            logger.debug(f"otc_check_skipped ticker={ticker} reason=validation_disabled")
            return False

        # If ticker is in our valid list (NASDAQ/NYSE/AMEX), it's NOT OTC
        if ticker in self._valid_tickers:
            return False

        # Ticker not in major exchanges = likely OTC
        # This is a conservative check: unknown tickers are treated as OTC
        logger.debug(f"otc_ticker_detected ticker={ticker}")
        return True

    def is_unit_or_warrant(self, ticker: str) -> bool:
        """
        Check if ticker is a unit, warrant, or rights security.

        These derivative securities typically have low liquidity and are
        unsuitable for day trading alerts.

        Common suffixes:
        - U: Units (stock + warrant bundle)
        - W, WS, WT: Warrants (right to purchase stock at set price)
        - R: Rights offerings

        Examples:
        - ATMVU: Unit security (detected by 'U' suffix)
        - TSLAW: Warrant for Tesla (hypothetical)
        - AAPLWS: Warrant for Apple (hypothetical)

        Args:
            ticker: Stock ticker symbol to check

        Returns:
            True if ticker is a unit/warrant/right, False otherwise
        """
        if not ticker or not ticker.strip():
            return False

        ticker = ticker.upper().strip()

        # Define unit/warrant/rights suffixes
        # Check longer suffixes first to avoid false positives (e.g., "WS" before "W")
        unit_warrant_suffixes = ["WS", "WT", "U", "W", "R"]

        for suffix in unit_warrant_suffixes:
            # Must end with suffix and have at least one character before it
            if len(ticker) > len(suffix) and ticker.endswith(suffix):
                # Additional check: ensure it's actually a suffix, not part of the ticker
                # For single-char suffixes, we're more strict
                if len(suffix) == 1:
                    # For single-char suffixes, ensure the char before is a letter
                    # This helps distinguish "ATMVU" (unit) from "W" (standalone ticker)
                    prefix = ticker[:-1]
                    if prefix and prefix[-1].isalpha():
                        logger.debug(f"unit_warrant_detected ticker={ticker} suffix={suffix}")
                        return True
                else:
                    # Multi-char suffixes are more reliable
                    logger.debug(f"unit_warrant_detected ticker={ticker} suffix={suffix}")
                    return True

        return False

    def verify_with_yahoo_finance(self, ticker: str, timeout: float = 2.0) -> bool:
        """
        Verify ticker exists and is tradeable using Yahoo Finance API.

        This is a stronger validation than get-all-tickers, useful for catching:
        - Delisted tickers (e.g., APXT which merged/changed ticker)
        - Completely invalid tickers that somehow passed initial validation
        - Tickers with no market data

        Args:
            ticker: Stock ticker symbol to verify
            timeout: Request timeout in seconds

        Returns:
            True if ticker is valid and tradeable, False otherwise
        """
        if not ticker or not ticker.strip():
            return False

        ticker = ticker.upper().strip()

        try:
            import yfinance as yf

            # Fetch ticker info with short timeout
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info

            if not info:
                logger.debug(f"yahoo_validation_failed ticker={ticker} reason=no_info")
                return False

            # Check for valid quote_type (should be 'EQUITY', 'ETF', etc.)
            quote_type = info.get("quoteType")
            if not quote_type:
                logger.debug(f"yahoo_validation_failed ticker={ticker} reason=no_quote_type")
                return False

            # Check for valid exchange (NASDAQ, NYSE, AMEX, etc.)
            exchange = info.get("exchange")
            if not exchange:
                logger.debug(f"yahoo_validation_failed ticker={ticker} reason=no_exchange")
                return False

            # Valid tickers should have a symbol field matching our input
            symbol = info.get("symbol")
            if not symbol or symbol.upper() != ticker:
                logger.debug(
                    f"yahoo_validation_failed ticker={ticker} reason=symbol_mismatch symbol={symbol}"
                )
                return False

            logger.debug(
                f"yahoo_validation_passed ticker={ticker} quote_type={quote_type} exchange={exchange}"
            )
            return True

        except ImportError:
            logger.warning("yfinance not installed, cannot perform deep validation")
            return True  # Fail-open: don't reject if yfinance unavailable
        except Exception as e:
            logger.debug(f"yahoo_validation_error ticker={ticker} err={str(e)}")
            return True  # Fail-open: don't reject on API errors to avoid false rejections

    def validate_and_check_otc(
        self, ticker: str, source: str = "unknown"
    ) -> Tuple[bool, bool]:
        """
        Validate ticker and check if it's OTC in one call.

        Args:
            ticker: Stock ticker symbol
            source: Source of ticker for logging

        Returns:
            Tuple of (is_valid, is_otc)
            - is_valid: True if ticker exists
            - is_otc: True if ticker is on OTC market
        """
        is_valid = self.is_valid(ticker)
        is_otc = self.is_otc(ticker)

        if is_otc:
            logger.info(f"otc_ticker_detected ticker={ticker} source={source}")

        return (is_valid, is_otc)
