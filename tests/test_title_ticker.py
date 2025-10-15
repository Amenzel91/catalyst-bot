#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Comprehensive test suite for title_ticker.py ticker extraction patterns.

Tests the enhanced pattern matching for:
- Exchange-qualified tickers (Nasdaq: AAPL, NYSE: BA)
- Dollar tickers ($NVDA, $AAPL)
- Company + Ticker patterns (Apple (AAPL), Tesla Inc. (TSLA))
- Headline start patterns (TSLA: Deliveries Beat)
- Exclusion list validation (PRICE:, UPDATE:, ALERT:)
- Edge cases (multiple tickers, class shares, deduplication)
"""

import pytest

from catalyst_bot.title_ticker import extract_tickers_from_title, ticker_from_title


class TestExchangeQualifiedPatterns:
    """Test exchange-qualified ticker patterns."""

    def test_nasdaq_prefix(self):
        assert ticker_from_title("Alpha (Nasdaq: ABCD) announces") == "ABCD"
        assert ticker_from_title("Tesla Stock (Nasdaq: TSLA) Jumps") == "TSLA"

    def test_nyse_prefix(self):
        assert ticker_from_title("News (NYSE: XYZ) and more") == "XYZ"
        assert ticker_from_title("(NYSE: BA) stock rises") == "BA"

    def test_nyse_american(self):
        assert ticker_from_title("Breaking (NYSE American: ABC) news") == "ABC"

    def test_multiple_exchange_tickers(self):
        result = extract_tickers_from_title("NASDAQ: AAPL and NYSE: BA both up")
        assert result == ["AAPL", "BA"]


class TestDollarTickerPatterns:
    """Test dollar-prefixed ticker patterns ($TICKER)."""

    def test_simple_dollar_tickers(self):
        assert ticker_from_title("$NVDA shares surge 15%") == "NVDA"
        assert ticker_from_title("$AAPL hits new high") == "AAPL"
        assert ticker_from_title("$TSLA deliveries beat") == "TSLA"

    def test_dollar_with_price(self):
        assert ticker_from_title("Price: $GOOGL at $150") == "GOOGL"

    def test_multiple_dollar_tickers(self):
        result = extract_tickers_from_title("$TSLA and $NVDA lead tech rally")
        assert result == ["TSLA", "NVDA"]


class TestCompanyTickerPatterns:
    """Test Company (TICKER) patterns."""

    def test_simple_company_name(self):
        assert ticker_from_title("Apple (AAPL) Reports Strong Quarter") == "AAPL"
        assert ticker_from_title("Boeing (BA) announces layoffs") == "BA"

    def test_company_with_inc(self):
        assert ticker_from_title("Tesla Inc. (TSLA) reports Q3 earnings") == "TSLA"
        assert ticker_from_title("Meta Platforms Inc. (META) Q4 results") == "META"
        assert ticker_from_title("Alphabet Inc (GOOGL) search revenue") == "GOOGL"

    def test_company_with_corp(self):
        assert ticker_from_title("Nvidia Corp. (NVDA) Beats Estimates") == "NVDA"
        assert ticker_from_title("Microsoft Corp (MSFT) earnings") == "MSFT"

    def test_company_with_co(self):
        assert ticker_from_title("Boeing Co. (BA) announces layoffs") == "BA"

    def test_company_with_special_chars(self):
        assert (
            ticker_from_title("Amazon.com Inc. (AMZN) Announces New Services") == "AMZN"
        )
        assert ticker_from_title("Amazon.com Inc. (AMZN) earnings") == "AMZN"

    def test_multiple_company_tickers(self):
        result = extract_tickers_from_title(
            "Apple (AAPL) partners with Microsoft (MSFT)"
        )
        assert result == ["AAPL", "MSFT"]

    def test_class_shares(self):
        """Test class share tickers like BRK.A and BF.B"""
        assert ticker_from_title("Berkshire Hathaway (BRK.A) reports") == "BRK.A"
        assert ticker_from_title("Brown-Forman (BF.B) dividend") == "BF.B"


class TestHeadlineStartPatterns:
    """Test headline start patterns (TICKER: News)."""

    def test_simple_headline_start(self):
        assert ticker_from_title("TSLA: Deliveries Beat Estimates") == "TSLA"
        assert ticker_from_title("AAPL: Reports Strong Q3") == "AAPL"
        assert ticker_from_title("NVDA: AI Revenue Soars 200%") == "NVDA"
        assert ticker_from_title("BA: Manufacturing Issues Continue") == "BA"

    def test_multi_char_tickers(self):
        assert ticker_from_title("GOOGL: Search revenue up") == "GOOGL"
        assert ticker_from_title("MSFT: Cloud growth") == "MSFT"


class TestExclusionList:
    """Test exclusion list for false positive prevention."""

    def test_price_exclusion(self):
        """PRICE: should not be extracted as a ticker"""
        assert ticker_from_title("PRICE: Stock rises") is None
        assert extract_tickers_from_title("PRICE: Stock rises") == []

    def test_update_exclusion(self):
        """UPDATE: should not be extracted as a ticker"""
        assert ticker_from_title("UPDATE: Company announces") is None
        assert extract_tickers_from_title("UPDATE: Company announces") == []

    def test_alert_exclusion(self):
        """ALERT: should not be extracted as a ticker"""
        assert ticker_from_title("ALERT: Market moves") is None
        assert extract_tickers_from_title("ALERT: Market moves") == []

    def test_news_exclusion(self):
        """NEWS: should not be extracted as a ticker"""
        assert ticker_from_title("NEWS: Breaking story") is None

    def test_watch_exclusion(self):
        """WATCH: should not be extracted as a ticker"""
        assert ticker_from_title("WATCH: Live stream") is None

    def test_flash_exclusion(self):
        """FLASH: should not be extracted as a ticker"""
        assert ticker_from_title("FLASH: Breaking news") is None

    def test_brief_exclusion(self):
        """BRIEF: should not be extracted as a ticker"""
        assert ticker_from_title("BRIEF: Company update") is None

    def test_breaking_exclusion(self):
        """BREAKING: should not be extracted as a ticker"""
        assert ticker_from_title("BREAKING: News alert") is None

    def test_live_exclusion(self):
        """LIVE: should not be extracted as a ticker"""
        assert ticker_from_title("LIVE: Market coverage") is None


class TestNoTickerPresent:
    """Test that no tickers are extracted when none are present."""

    def test_company_name_only(self):
        assert ticker_from_title("Apple reports strong quarter") is None
        assert ticker_from_title("Tesla announces new model") is None

    def test_generic_news(self):
        assert ticker_from_title("Stock market rallies today") is None
        assert ticker_from_title("Breaking news from CEO") is None


class TestInvalidTickerFormats:
    """Test that invalid ticker formats are rejected."""

    def test_alphanumeric_mixed(self):
        """Tickers with numbers mixed in should not match"""
        assert ticker_from_title("Company (ABC123) announces") is None

    def test_lowercase_ticker(self):
        """Lowercase tickers should not match"""
        assert ticker_from_title("Firm (ab) reports") is None
        assert ticker_from_title("Company (abcd) news") is None

    def test_single_character(self):
        """Single character tickers should not match (except T via exchange)"""
        assert ticker_from_title("News (A) today") is None

    def test_too_long(self):
        """Tickers longer than 5 characters should not match"""
        assert ticker_from_title("Item (ABCDEFG) test") is None


class TestCommonAcronyms:
    """Test that common acronyms are not extracted as tickers."""

    def test_ceo(self):
        assert ticker_from_title("CEO announces new strategy") is None

    def test_usa(self):
        assert ticker_from_title("USA stocks rally today") is None

    def test_ai(self):
        assert ticker_from_title("AI technology advances") is None

    def test_fbi(self):
        assert ticker_from_title("FBI investigates company") is None

    def test_sec(self):
        assert ticker_from_title("SEC files charges") is None

    def test_fda(self):
        assert ticker_from_title("FDA approves drug") is None

    def test_ipo(self):
        assert ticker_from_title("IPO market heats up") is None

    def test_etf(self):
        assert ticker_from_title("ETF flows continue") is None


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_multiple_formats_same_ticker(self):
        """Test deduplication when same ticker appears in different formats"""
        result = extract_tickers_from_title("TSLA: Tesla Inc. (TSLA) stock jumps")
        assert result == ["TSLA"]

        result = extract_tickers_from_title("$AAPL (NASDAQ: AAPL) hits high")
        assert result == ["AAPL"]

    def test_mixed_patterns(self):
        """Test multiple tickers with different patterns"""
        result = extract_tickers_from_title(
            "Apple (AAPL) and $NVDA rise; NYSE: BA falls"
        )
        assert result == ["AAPL", "NVDA", "BA"]

    def test_empty_string(self):
        assert ticker_from_title("") is None
        assert extract_tickers_from_title("") == []

    def test_none_input(self):
        assert ticker_from_title(None) is None
        assert extract_tickers_from_title(None) == []


class TestOTCPatterns:
    """Test OTC ticker patterns when enabled."""

    def test_otc_disabled_by_default(self):
        """OTC tickers should not match by default"""
        result = extract_tickers_from_title("OTCMKTS: XYZ announces")
        assert result == []

    def test_otc_enabled(self):
        """OTC tickers should match when enabled"""
        result = extract_tickers_from_title("OTCMKTS: XYZ announces", allow_otc=True)
        assert result == ["XYZ"]

        result = extract_tickers_from_title("OTCQX: ABCD reports", allow_otc=True)
        assert result == ["ABCD"]


class TestDollarTickerRequireExchange:
    """Test DOLLAR_TICKERS_REQUIRE_EXCHANGE toggle."""

    def test_dollar_ticker_allowed_by_default(self):
        """Dollar tickers should work by default"""
        assert ticker_from_title("$AAPL rises") == "AAPL"

    def test_dollar_ticker_disabled(self):
        """Dollar tickers should not match when require_exch_for_dollar=True"""
        result = ticker_from_title("$AAPL rises", require_exch_for_dollar=True)
        assert result is None

    def test_exchange_qualified_still_works(self):
        """Exchange-qualified tickers should still work"""
        result = ticker_from_title("NYSE: AAPL rises", require_exch_for_dollar=True)
        assert result == "AAPL"

    def test_company_ticker_still_works(self):
        """Company (TICKER) patterns should still work"""
        result = ticker_from_title("Apple (AAPL) rises", require_exch_for_dollar=True)
        assert result == "AAPL"


class TestBackwardCompatibility:
    """Test that existing functionality is preserved."""

    def test_original_examples(self):
        """Test examples from original docstring"""
        # Default behavior
        result = extract_tickers_from_title(
            "Alpha (Nasdaq: ABCD) + $EFGH; OTCMKTS: XYZ should be ignored"
        )
        assert "ABCD" in result
        assert "EFGH" in result
        assert "XYZ" not in result  # OTC not enabled

        # With OTC enabled
        result = extract_tickers_from_title(
            "Up-listing news OTCMKTS: XYZ, plus (Nasdaq: ABCD)", allow_otc=True
        )
        assert "XYZ" in result
        assert "ABCD" in result

        # With require_exch_for_dollar
        result = extract_tickers_from_title(
            "Just $ABCD with no exchange should be dropped; but (NYSE: XYZ) should pass",
            require_exch_for_dollar=True,
        )
        assert "ABCD" not in result  # Dollar ticker dropped
        assert "XYZ" in result  # Exchange-qualified preserved


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
