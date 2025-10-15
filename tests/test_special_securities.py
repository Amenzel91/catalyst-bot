"""
Comprehensive tests for special security filtering in runner._is_instrument_like().

This test suite ensures that legitimate securities (preferred shares, ADRs,
international tickers) are NOT rejected, while synthetic instruments (warrants,
units, rights) ARE properly rejected.
"""

import pytest

# Import the function under test
from catalyst_bot.runner import _is_instrument_like


class TestPreferredShares:
    """Test that preferred shares in all formats are NOT rejected."""

    def test_lowercase_p_notation_4letter(self):
        """Preferred shares with lowercase 'p' notation (4-letter base)."""
        assert not _is_instrument_like("CDRpB")
        assert not _is_instrument_like("ABCpD")
        assert not _is_instrument_like("XYZpA")

    def test_lowercase_p_notation_3letter(self):
        """Preferred shares with lowercase 'p' notation (3-letter base)."""
        assert not _is_instrument_like("ABCpA")
        assert not _is_instrument_like("XYpB")

    def test_hyphen_notation_4letter(self):
        """Preferred shares with hyphen notation (4-letter base)."""
        assert not _is_instrument_like("ABCD-B")
        assert not _is_instrument_like("WXYZ-A")
        assert not _is_instrument_like("TEST-C")

    def test_hyphen_notation_3letter(self):
        """Preferred shares with hyphen notation (3-letter base)."""
        assert not _is_instrument_like("ABC-B")
        assert not _is_instrument_like("XYZ-A")
        assert not _is_instrument_like("FOO-D")

    def test_nasdaq_5letter_p_suffix(self):
        """NASDAQ 5-letter preferred ending in P."""
        assert not _is_instrument_like("ABCDP")
        assert not _is_instrument_like("XYZAP")
        assert not _is_instrument_like("TESTP")

    def test_nasdaq_5letter_q_suffix(self):
        """NASDAQ 5-letter preferred ending in Q."""
        assert not _is_instrument_like("ABCDQ")
        assert not _is_instrument_like("XYZQQ")
        assert not _is_instrument_like("TESTQ")

    def test_nasdaq_5letter_r_suffix(self):
        """NASDAQ 5-letter preferred ending in R."""
        assert not _is_instrument_like("ABCDR")
        assert not _is_instrument_like("XYZRR")
        assert not _is_instrument_like("TESTR")

    def test_case_insensitive(self):
        """Preferred shares are recognized regardless of input case."""
        assert not _is_instrument_like("cdrpb")  # lowercase
        assert not _is_instrument_like("CdRpB")  # mixed case
        assert not _is_instrument_like("abc-b")  # lowercase
        assert not _is_instrument_like("abcdp")  # lowercase


class TestADRs:
    """Test that ADRs (5-letter ending in Y/F) are NOT rejected."""

    def test_adrs_ending_in_y(self):
        """ADRs ending in Y should be allowed."""
        assert not _is_instrument_like("BYDDY")  # BYD Company
        assert not _is_instrument_like("NSRGY")  # Nestle
        assert not _is_instrument_like("TCEHY")  # Tencent
        assert not _is_instrument_like("FUJHY")  # Fujifilm

    def test_adrs_ending_in_f(self):
        """ADRs ending in F should be allowed."""
        assert not _is_instrument_like("TDOMF")  # TD Bank
        assert not _is_instrument_like("VODPF")  # Vodafone
        assert not _is_instrument_like("RHHBF")  # Roche
        assert not _is_instrument_like("DANOY")  # wait, this ends in Y

    def test_non_5letter_y_f_allowed(self):
        """Non-5-letter tickers ending in Y/F should also be allowed."""
        assert not _is_instrument_like("ABCF")  # 4-letter ending in F
        assert not _is_instrument_like("XY")  # 2-letter ending in Y
        assert not _is_instrument_like("TESTFY")  # 6-letter ending in Y


class TestInternationalTickers:
    """Test that international tickers with exchange codes are NOT rejected."""

    def test_london_stock_exchange(self):
        """London Stock Exchange tickers (.L suffix)."""
        assert not _is_instrument_like("BRK.L")  # Berkshire Hathaway London
        assert not _is_instrument_like("BP.L")  # BP London
        assert not _is_instrument_like("SHEL.L")  # Shell London

    def test_tokyo_stock_exchange(self):
        """Tokyo Stock Exchange tickers (.T suffix)."""
        assert not _is_instrument_like("SONY.T")  # Sony Tokyo
        assert not _is_instrument_like("TM.T")  # Toyota Tokyo

    def test_german_exchanges(self):
        """German exchange tickers (.DE, .F suffixes)."""
        assert not _is_instrument_like("SAP.DE")  # SAP Frankfurt
        assert not _is_instrument_like("BMW.DE")  # BMW Frankfurt
        assert not _is_instrument_like("BAYN.DE")  # Bayer Frankfurt

    def test_paris_exchange(self):
        """Paris exchange tickers (.PA suffix)."""
        assert not _is_instrument_like("MC.PA")  # LVMH Paris

    def test_hong_kong_exchange(self):
        """Hong Kong exchange tickers (.HK suffix)."""
        assert not _is_instrument_like("BABA.HK")  # Alibaba Hong Kong

    def test_2letter_exchange_codes(self):
        """International tickers with 2-letter exchange codes."""
        assert not _is_instrument_like("SAP.DE")  # Germany
        assert not _is_instrument_like("VOD.UK")  # UK
        assert not _is_instrument_like("AB.CD")  # Generic 2-letter exchange

    def test_1letter_exchange_codes(self):
        """International tickers with 1-letter exchange codes."""
        assert not _is_instrument_like("BRK.L")  # London
        assert not _is_instrument_like("TM.T")  # Tokyo
        assert not _is_instrument_like("AB.X")  # Generic 1-letter exchange


class TestClassShares:
    """Test that traditional class shares are NOT rejected."""

    def test_berkshire_hathaway(self):
        """Classic example: Berkshire Hathaway A/B shares."""
        assert not _is_instrument_like("BRK.A")
        assert not _is_instrument_like("BRK.B")

    def test_brown_forman(self):
        """Brown-Forman A/B shares."""
        assert not _is_instrument_like("BF.A")
        assert not _is_instrument_like("BF.B")

    def test_various_class_shares(self):
        """Various class share patterns."""
        assert not _is_instrument_like("GOOG.A")  # Google Class A (hypothetical)
        assert not _is_instrument_like("XYZ.C")  # Generic class C
        assert not _is_instrument_like("ABC.D")  # Generic class D

    def test_1to4letter_base(self):
        """Class shares with 1-4 letter base."""
        assert not _is_instrument_like("A.B")  # 1-letter base
        assert not _is_instrument_like("AB.C")  # 2-letter base
        assert not _is_instrument_like("ABC.D")  # 3-letter base
        assert not _is_instrument_like("ABCD.E")  # 4-letter base


class TestWarrantsRejected:
    """Test that warrants ARE properly rejected."""

    def test_warrant_wt_suffix(self):
        """Warrants with -WT suffix should be rejected."""
        assert _is_instrument_like("ABC-WT")
        assert _is_instrument_like("XYZW-WT")
        assert _is_instrument_like("TEST-WT")

    def test_warrant_w_suffix(self):
        """Warrants with -W suffix should be rejected."""
        assert _is_instrument_like("ABC-W")
        assert _is_instrument_like("XYZ-W")
        assert _is_instrument_like("TEST-W")

    def test_warrant_ws_suffix(self):
        """Warrants with .WS suffix should be rejected."""
        assert _is_instrument_like("ABC.WS")
        assert _is_instrument_like("XYZ.WS")
        assert _is_instrument_like("TEST.WS")

    def test_warrant_w_ending_5plus_letters(self):
        """5+ letter tickers ending in W should be rejected."""
        assert _is_instrument_like("ABCDW")  # 5-letter ending in W
        assert _is_instrument_like("XYZWW")  # 5-letter ending in WW
        assert _is_instrument_like("TESTAW")  # 6-letter ending in W

    def test_warrant_ww_suffix(self):
        """Warrants with WW suffix should be rejected."""
        assert _is_instrument_like("ABCDWW")
        assert _is_instrument_like("TESTWW")

    def test_short_tickers_ending_w_allowed(self):
        """Short tickers (< 5 letters) ending in W should be ALLOWED."""
        # These are too short to be warrants by our heuristic
        assert not _is_instrument_like("AAW")  # 3-letter
        assert not _is_instrument_like("ABCW")  # 4-letter


class TestUnitsRejected:
    """Test that units ARE properly rejected."""

    def test_unit_dash_u_suffix(self):
        """Units with -U suffix should be rejected."""
        assert _is_instrument_like("ABC-U")
        assert _is_instrument_like("XYZ-U")
        assert _is_instrument_like("TEST-U")

    def test_unit_dot_u_suffix(self):
        """Units with .U suffix should be rejected."""
        assert _is_instrument_like("ABC.U")
        assert _is_instrument_like("XYZ.U")
        assert _is_instrument_like("TEST.U")

    def test_unit_u_suffix_5plus_letters(self):
        """5+ letter tickers ending in U suffix should be rejected."""
        assert _is_instrument_like("ABCDPU")  # PU suffix (5 letters)
        assert _is_instrument_like("TESTPU")  # PU suffix (6 letters)


class TestSyntheticInstrumentsRejected:
    """Test that synthetic instruments with special characters ARE rejected."""

    def test_caret_notation(self):
        """Tickers with caret (^) should be rejected."""
        assert _is_instrument_like("ABC^D")
        assert _is_instrument_like("XYZ^A")
        assert _is_instrument_like("TEST^B")

    def test_complex_dot_patterns(self):
        """Complex dot patterns (not class/international) should be rejected."""
        # 3+ letters after dot should be rejected (not a valid exchange code)
        assert _is_instrument_like("ABC.XYZ")  # 3+ letters after dot
        assert _is_instrument_like("ABCD.ABC")  # 3 letters after dot
        # 5+ letters before dot should be rejected (outside our pattern)
        assert _is_instrument_like("ABCDE.L")  # 5 letters before dot


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self):
        """Empty string should not be rejected (returns False)."""
        assert not _is_instrument_like("")

    def test_whitespace(self):
        """Whitespace should be stripped and handled correctly."""
        assert not _is_instrument_like("  ABC-B  ")  # preferred share
        assert _is_instrument_like("  ABC-WT  ")  # warrant

    def test_lowercase_input(self):
        """Lowercase input should be normalized to uppercase."""
        assert not _is_instrument_like("brk.a")  # class share
        assert not _is_instrument_like("byddy")  # ADR
        assert _is_instrument_like("abc-wt")  # warrant

    def test_mixed_case_input(self):
        """Mixed case input should be normalized."""
        assert not _is_instrument_like("BrK.A")  # class share
        assert not _is_instrument_like("ByDdY")  # ADR
        assert _is_instrument_like("AbC-Wt")  # warrant

    def test_none_input(self):
        """None input should not crash (returns False)."""
        assert not _is_instrument_like(None)

    def test_spaces_in_ticker(self):
        """Spaces should be stripped."""
        assert not _is_instrument_like("ABC -B")  # becomes ABC-B (preferred)
        assert _is_instrument_like("ABC -WT")  # becomes ABC-WT (warrant)


class TestRealWorldExamples:
    """Test real-world ticker examples to ensure correct classification."""

    # Legitimate securities that should NOT be rejected
    def test_real_preferred_shares(self):
        """Real preferred share tickers."""
        assert not _is_instrument_like("CDRpB")  # Cedar Realty Trust Preferred
        assert not _is_instrument_like("PSA-H")  # Public Storage Preferred H
        assert not _is_instrument_like("WFC-L")  # Wells Fargo Preferred L

    def test_real_adrs(self):
        """Real ADR tickers."""
        assert not _is_instrument_like("BYDDY")  # BYD Company ADR
        assert not _is_instrument_like("NSRGY")  # Nestle ADR
        assert not _is_instrument_like("TCEHY")  # Tencent ADR
        assert not _is_instrument_like("FUJHY")  # Fujifilm ADR

    def test_real_class_shares(self):
        """Real class share tickers."""
        assert not _is_instrument_like("BRK.A")  # Berkshire Hathaway Class A
        assert not _is_instrument_like("BRK.B")  # Berkshire Hathaway Class B
        assert not _is_instrument_like("BF.A")  # Brown-Forman Class A
        assert not _is_instrument_like("BF.B")  # Brown-Forman Class B

    def test_real_international_tickers(self):
        """Real international exchange tickers."""
        assert not _is_instrument_like("SHEL.L")  # Shell London
        assert not _is_instrument_like("SONY.T")  # Sony Tokyo
        assert not _is_instrument_like("SAP.DE")  # SAP Frankfurt

    # Synthetic instruments that SHOULD be rejected
    def test_real_warrants(self):
        """Real warrant tickers."""
        assert _is_instrument_like("DWACW")  # Digital World Acquisition warrant
        assert _is_instrument_like("CCIV-WT")  # Churchill Capital warrant
        assert _is_instrument_like("PSTH.WS")  # Pershing Square warrant

    def test_real_units(self):
        """Real unit tickers."""
        assert _is_instrument_like("PSTH-U")  # Pershing Square unit
        assert _is_instrument_like("CCIV.U")  # Churchill Capital unit


class TestRegressionPreventionDNOW:
    """Ensure we don't accidentally reject legitimate tickers like DNOW."""

    def test_dnow_allowed(self):
        """DNOW (NOW Inc.) should be allowed."""
        assert not _is_instrument_like("DNOW")

    def test_other_4letter_w_endings(self):
        """4-letter tickers ending in W should be allowed (not long enough for warrant rule)."""
        assert not _is_instrument_like("SNOW")  # Snowflake (hypothetical)
        assert not _is_instrument_like("KNOW")  # Generic 4-letter W ending


class TestCombinationsAndAmbiguity:
    """Test ambiguous cases and combinations."""

    def test_preferred_vs_warrant_precedence(self):
        """Preferred share patterns should take precedence over warrant patterns."""
        # ABC-B looks like it could be a warrant (-B), but it's a preferred share
        assert not _is_instrument_like("ABC-B")  # Preferred wins
        assert not _is_instrument_like("XYZ-A")  # Preferred wins

    def test_5letter_p_vs_5letter_f(self):
        """5-letter tickers ending in P (preferred) vs F (ADR)."""
        assert not _is_instrument_like("ABCDP")  # Preferred
        assert not _is_instrument_like("ABCDF")  # ADR

    def test_international_vs_class_shares(self):
        """Both international and class shares use dots but different patterns."""
        assert not _is_instrument_like("BRK.A")  # Class share (1 letter after dot)
        assert not _is_instrument_like("BRK.L")  # International (1 letter after dot)
        assert not _is_instrument_like("SAP.DE")  # International (2 letters after dot)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
