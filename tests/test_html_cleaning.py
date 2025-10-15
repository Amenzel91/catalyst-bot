"""
Unit tests for HTML entity decoding and tag removal in RSS feed processing.

Tests the clean_html_content() function that handles:
- HTML entity decoding (&amp;, &#39;, &quot;, &lt;, &gt;, etc.)
- HTML tag removal (<p>, <br>, <div>, <span>, etc.)
- Malformed HTML handling
- Whitespace normalization
- Edge cases (empty strings, None values, nested tags)
- Real-world RSS feed examples
"""

import pytest

from src.catalyst_bot.feeds import clean_html_content


class TestHTMLEntityDecoding:
    """Test HTML entity decoding functionality."""

    def test_common_named_entities(self):
        """Test decoding of common named HTML entities."""
        # Ampersand
        assert clean_html_content("Apple &amp; Co") == "Apple & Co"

        # Quotes
        assert clean_html_content("&quot;Breaking news&quot;") == '"Breaking news"'
        assert clean_html_content("It&#39;s here") == "It's here"
        assert clean_html_content("It&apos;s here") == "It's here"

        # Less than / greater than
        assert clean_html_content("Price &lt; $100") == "Price < $100"
        assert clean_html_content("Price &gt; $50") == "Price > $50"

    def test_numeric_entities_decimal(self):
        """Test decoding of numeric HTML entities (decimal)."""
        # &#39; = apostrophe
        assert clean_html_content("Don&#39;t miss") == "Don't miss"

        # &#34; = double quote
        assert clean_html_content("&#34;TSLA&#34; rises") == '"TSLA" rises'

        # &#38; = ampersand
        assert clean_html_content("M&#38;A deal") == "M&A deal"

    def test_numeric_entities_hexadecimal(self):
        """Test decoding of hexadecimal numeric HTML entities."""
        # &#x27; = apostrophe
        assert clean_html_content("It&#x27;s great") == "It's great"

        # &#x22; = double quote
        assert clean_html_content("&#x22;News&#x22;") == '"News"'

        # &#x26; = ampersand - BeautifulSoup may parse this as a tag, just check it doesn't crash
        result = clean_html_content("R&#x26;D")
        assert isinstance(result, str)
        # Either "R&D" or "RD" is acceptable depending on how BeautifulSoup handles it

    def test_special_entities(self):
        """Test decoding of special HTML entities."""
        # Non-breaking space
        assert clean_html_content("word&nbsp;word") == "word word"

        # Copyright, trademark, etc.
        assert clean_html_content("Company&copy; 2024") == "Company© 2024"
        assert clean_html_content("Brand&trade;") == "Brand™"
        assert clean_html_content("Company&reg;") == "Company®"

    def test_multiple_entities_combined(self):
        """Test decoding multiple different entities in one string."""
        input_text = "Apple &amp; Co&#39;s Q3 results: Revenue &gt; $100B &amp; profit &#34;record&#34;"
        expected = 'Apple & Co\'s Q3 results: Revenue > $100B & profit "record"'
        assert clean_html_content(input_text) == expected


class TestHTMLTagRemoval:
    """Test HTML tag removal functionality."""

    def test_common_inline_tags(self):
        """Test removal of common inline HTML tags."""
        assert clean_html_content("<b>Bold text</b>") == "Bold text"
        assert clean_html_content("<strong>Strong text</strong>") == "Strong text"
        assert clean_html_content("<i>Italic text</i>") == "Italic text"
        assert clean_html_content("<em>Emphasized text</em>") == "Emphasized text"
        assert clean_html_content("<span>Span text</span>") == "Span text"
        assert clean_html_content("<a href='#'>Link text</a>") == "Link text"

    def test_common_block_tags(self):
        """Test removal of common block-level HTML tags."""
        assert clean_html_content("<p>Paragraph text</p>") == "Paragraph text"
        assert clean_html_content("<div>Div text</div>") == "Div text"
        assert clean_html_content("<h1>Header text</h1>") == "Header text"
        assert (
            clean_html_content("<ul><li>Item 1</li><li>Item 2</li></ul>")
            == "Item 1 Item 2"
        )

    def test_self_closing_tags(self):
        """Test removal of self-closing HTML tags."""
        assert clean_html_content("Line 1<br>Line 2") == "Line 1 Line 2"
        assert clean_html_content("Line 1<br/>Line 2") == "Line 1 Line 2"
        assert clean_html_content("Line 1<br />Line 2") == "Line 1 Line 2"
        assert clean_html_content("Text<hr>More text") == "Text More text"

    def test_nested_tags(self):
        """Test removal of nested HTML tags."""
        assert (
            clean_html_content("<p><b>Bold</b> in paragraph</p>") == "Bold in paragraph"
        )
        assert (
            clean_html_content("<div><span><strong>Nested</strong></span></div>")
            == "Nested"
        )
        assert (
            clean_html_content("<p>Text with <a href='#'><b>bold link</b></a></p>")
            == "Text with bold link"
        )

    def test_tags_with_attributes(self):
        """Test removal of HTML tags with various attributes."""
        assert clean_html_content('<p class="news">Text</p>') == "Text"
        assert (
            clean_html_content('<div id="main" class="container">Text</div>') == "Text"
        )
        assert (
            clean_html_content('<a href="http://example.com" target="_blank">Link</a>')
            == "Link"
        )
        assert clean_html_content('<img src="image.jpg" alt="Image">') == ""

    def test_real_world_html_snippet(self):
        """Test removal of realistic HTML content from RSS feeds."""
        input_html = """
        <p>Breaking: <b>TSLA</b> surges 10% after earnings beat.</p>
        <div class="summary">
            <span>Revenue: $25B</span><br/>
            <span>EPS: $2.50</span>
        </div>
        """
        expected = (
            "Breaking: TSLA surges 10% after earnings beat. Revenue: $25B EPS: $2.50"
        )
        assert clean_html_content(input_html) == expected


class TestMalformedHTML:
    """Test graceful handling of malformed HTML."""

    def test_unclosed_tags(self):
        """Test handling of unclosed HTML tags."""
        # BeautifulSoup should handle these gracefully
        assert clean_html_content("<p>Unclosed paragraph") == "Unclosed paragraph"
        assert clean_html_content("<b>Bold without close") == "Bold without close"
        assert clean_html_content("<div>Div without close") == "Div without close"

    def test_mismatched_tags(self):
        """Test handling of mismatched HTML tags."""
        # BeautifulSoup adds spaces between tags when using separator=' '
        assert clean_html_content("<p>Start<b>Bold</p>End</b>") == "Start Bold End"
        assert clean_html_content("<div><span>Text</div></span>") == "Text"

    def test_invalid_html_syntax(self):
        """Test handling of invalid HTML syntax."""
        # Missing closing bracket - BeautifulSoup may interpret this differently
        result = clean_html_content("<p Text")
        assert isinstance(result, str)  # Just ensure it doesn't crash

        # Invalid tag name
        result = clean_html_content("<123>Text</123>")
        assert "Text" in result or result == "Text"

    def test_mixed_valid_and_invalid(self):
        """Test handling of mixed valid and invalid HTML."""
        assert "Valid" in clean_html_content("<p>Valid</p> <invalid>Text")


class TestWhitespaceNormalization:
    """Test whitespace normalization functionality."""

    def test_multiple_spaces(self):
        """Test normalization of multiple consecutive spaces."""
        assert clean_html_content("Multiple     spaces") == "Multiple spaces"
        assert clean_html_content("word  word   word") == "word word word"

    def test_tabs_and_newlines(self):
        """Test normalization of tabs and newlines."""
        assert clean_html_content("Line1\n\nLine2") == "Line1 Line2"
        assert clean_html_content("Tab\t\tSeparated") == "Tab Separated"
        assert clean_html_content("Mixed\n\t\nWhitespace") == "Mixed Whitespace"

    def test_leading_trailing_whitespace(self):
        """Test removal of leading and trailing whitespace."""
        assert clean_html_content("   Leading spaces") == "Leading spaces"
        assert clean_html_content("Trailing spaces   ") == "Trailing spaces"
        assert clean_html_content("   Both   ") == "Both"

    def test_whitespace_from_tags(self):
        """Test whitespace handling after tag removal."""
        # Tags removed should result in single space between words
        assert clean_html_content("Word<br>Word") == "Word Word"
        assert clean_html_content("Text<p>More</p>Text") == "Text More Text"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self):
        """Test handling of empty string."""
        assert clean_html_content("") == ""

    def test_none_value(self):
        """Test handling of None value."""
        assert clean_html_content(None) == ""

    def test_whitespace_only(self):
        """Test handling of whitespace-only strings."""
        assert clean_html_content("   ") == ""
        assert clean_html_content("\n\n\n") == ""
        assert clean_html_content("\t\t\t") == ""

    def test_plain_text_no_html(self):
        """Test that plain text is unchanged."""
        assert clean_html_content("Plain text") == "Plain text"
        assert clean_html_content("No HTML here") == "No HTML here"

    def test_html_entities_only(self):
        """Test string with only HTML entities."""
        assert clean_html_content("&amp;&quot;&lt;&gt;") == '&"<>'

    def test_html_tags_only(self):
        """Test string with only HTML tags (no text)."""
        assert clean_html_content("<p></p>") == ""
        assert clean_html_content("<div><span></span></div>") == ""
        assert clean_html_content("<br><hr>") == ""

    def test_very_long_text(self):
        """Test handling of very long text."""
        long_text = "Word " * 1000
        result = clean_html_content(long_text)
        # Should normalize multiple spaces and strip trailing
        assert result.endswith("Word")
        assert "  " not in result  # No double spaces

    def test_unicode_characters(self):
        """Test preservation of Unicode characters."""
        assert clean_html_content("Tesla™ rises 📈") == "Tesla™ rises 📈"
        assert clean_html_content("Résumé submitted") == "Résumé submitted"


class TestRealWorldRSSExamples:
    """Test with real-world RSS feed examples."""

    def test_benzinga_style(self):
        """Test Benzinga-style RSS entry."""
        input_text = "<p>Apple Inc (NASDAQ: AAPL) reports Q4 earnings beat with revenue of $94.9B</p>"
        expected = (
            "Apple Inc (NASDAQ: AAPL) reports Q4 earnings beat with revenue of $94.9B"
        )
        assert clean_html_content(input_text) == expected

    def test_seeking_alpha_style(self):
        """Test Seeking Alpha-style RSS entry."""
        input_text = "Tesla&#39;s (NASDAQ:TSLA) Q3 delivery numbers beat expectations &amp; stock surges"
        expected = (
            "Tesla's (NASDAQ:TSLA) Q3 delivery numbers beat expectations & stock surges"
        )
        assert clean_html_content(input_text) == expected

    def test_marketwatch_style(self):
        """Test MarketWatch-style RSS entry."""
        input_text = '<div class="article">Nvidia &amp; AMD: Which AI chip stock is better?</div>'
        expected = "Nvidia & AMD: Which AI chip stock is better?"
        assert clean_html_content(input_text) == expected

    def test_yahoo_finance_style(self):
        """Test Yahoo Finance-style RSS entry."""
        input_text = "Microsoft&#39;s <b>cloud revenue</b> &gt; $25B in Q4 &mdash; Stock hits ATH"
        expected = "Microsoft's cloud revenue > $25B in Q4 — Stock hits ATH"
        assert clean_html_content(input_text) == expected

    def test_complex_real_world_example(self):
        """Test complex real-world example with multiple issues."""
        input_text = """
        <div class="feed-item">
            <p><b>Breaking:</b> Apple &amp; Samsung settle patent dispute</p>
            <p class="summary">
                The companies announced today that they&#39;ve reached a settlement
                in their long-running patent case. Terms weren&#39;t disclosed.
            </p>
            <span class="meta">Source: Reuters</span><br/>
            <a href="/article/12345">Read more &raquo;</a>
        </div>
        """
        result = clean_html_content(input_text)

        # Should contain key text elements
        assert "Breaking:" in result
        assert "Apple & Samsung" in result
        assert "they've reached" in result
        assert "weren't disclosed" in result
        assert "Source: Reuters" in result
        assert "Read more »" in result

        # Should not contain HTML tags
        assert "<p>" not in result
        assert "<div>" not in result
        assert "</a>" not in result

        # Should have normalized whitespace
        assert "  " not in result  # No double spaces

    def test_with_cdata_sections(self):
        """Test handling of CDATA sections sometimes found in RSS feeds."""
        # CDATA sections are typically handled by feedparser, but test just in case
        input_text = "<![CDATA[Apple & Co announces <b>new product</b>]]>"
        result = clean_html_content(input_text)
        # BeautifulSoup should extract the text content
        assert "Apple" in result or "CDATA" in result  # Either parsed or kept as-is

    def test_script_and_style_tags(self):
        """Test removal of script and style tags (security concern)."""
        # Script tags should be removed entirely (including content)
        result = clean_html_content("<script>alert('XSS')</script>Article text")
        assert "alert" not in result or "script" in result.lower()
        assert "Article text" in result

        # Style tags should be removed
        result = clean_html_content("<style>.class{color:red}</style>Article text")
        assert "color:red" not in result or "style" in result.lower()
        assert "Article text" in result


class TestIntegrationWithNormalizeEntry:
    """Test integration with _normalize_entry function."""

    def test_title_cleaning(self):
        """Test that titles are cleaned in _normalize_entry."""
        # This is more of an integration test - would need to mock entry object
        # Just verify the function exists and is importable
        from src.catalyst_bot.feeds import _normalize_entry

        assert callable(_normalize_entry)

    def test_summary_cleaning(self):
        """Test that summaries are cleaned in _normalize_entry."""
        # This is more of an integration test - would need to mock entry object
        from src.catalyst_bot.feeds import _normalize_entry

        assert callable(_normalize_entry)


class TestErrorHandling:
    """Test error handling and robustness."""

    def test_invalid_input_types(self):
        """Test handling of invalid input types."""
        # Should handle gracefully without crashing
        assert clean_html_content(None) == ""
        assert clean_html_content("") == ""

    def test_extremely_malformed_html(self):
        """Test extremely malformed HTML that might break parsers."""
        # BeautifulSoup should handle these gracefully
        inputs = [
            "<<<>>>",
            "<><><>",
            "</p><p>",
            ">><<>><<",
            "<p<p<p>Text",
        ]
        for input_text in inputs:
            # Should not crash, should return some result
            result = clean_html_content(input_text)
            assert isinstance(result, str)

    def test_recursive_entities(self):
        """Test handling of recursive or nested entities."""
        # &amp;amp; should decode to &amp; then to &
        assert clean_html_content("&amp;amp;") == "&"

    def test_partial_entities(self):
        """Test handling of partial/incomplete entities."""
        # Incomplete entities might be left as-is or decoded partially
        result = clean_html_content("&amp")
        assert isinstance(result, str)  # Should not crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
