"""Ticker validation against official exchange lists."""

import logging
from typing import Optional, Set

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

        Args:
            ticker: Stock ticker symbol to validate

        Returns:
            True if ticker is valid or validation is disabled, False otherwise
        """
        if not self._valid_tickers:
            return True  # Validation disabled
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
