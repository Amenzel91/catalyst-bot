import os
import types


def _make_sample_entries():
    """Return a simple RSS sample as a string and expected mapping.

    The returned XML contains two items with sentiment values embedded in
    dedicated ``<sentiment>`` elements.  The expectation mapping uses
    canonicalised links (lowercased host, https scheme, no trailing slash).
    """
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample FMP Sentiment Feed</title>
    <item>
      <title>Company A beats earnings</title>
      <link>http://example.com/news/a</link>
      <description>Sentiment score: 0.67. Positive outlook.</description>
      <sentiment>0.67</sentiment>
    </item>
    <item>
      <title>Company B misses earnings</title>
      <link>http://example.com/news/b</link>
      <description>Sentiment score: -0.12. Negative outlook.</description>
      <sentiment>-0.12</sentiment>
    </item>
  </channel>
</rss>"""
    expected = {
        "https://example.com/news/a": 0.67,
        "https://example.com/news/b": -0.12,
    }
    return xml, expected


def test_attach_fmp_sentiment_simple():
    """attach_fmp_sentiment assigns values to matching events."""
    from catalyst_bot.fmp_sentiment import attach_fmp_sentiment

    # Prepare events with links that should match and one unmatched
    events = [
        {"link": "https://example.com/news/a", "title": "A"},
        {"link": "https://example.com/news/c", "title": "C"},
    ]
    sentiments = {"https://example.com/news/a": 0.5, "https://example.com/news/b": -0.2}
    attach_fmp_sentiment(events, sentiments)
    assert events[0].get("sentiment_fmp") == 0.5
    assert "sentiment_fmp" not in events[1]


def test_fetch_fmp_sentiment_parses_sample(monkeypatch):
    """fetch_fmp_sentiment parses a sample feed via mocked requests and feedparser."""
    from catalyst_bot import fmp_sentiment

    # Produce sample XML and expected mapping
    xml, expected = _make_sample_entries()

    # Mock requests.get to return our sample XML
    class _MockResp:
        status_code = 200

        def __init__(self, text):
            self.text = text

    def mock_get(url, params=None, timeout=12):
        return _MockResp(xml)

    monkeypatch.setattr(fmp_sentiment.requests, "get", mock_get)

    # Mock feedparser.parse to build entries from the provided text
    def mock_parse(text):
        # Build a minimal parsed object with entries attribute
        class _R:
            pass

        # Parse the XML manually to avoid dependencies
        import xml.etree.ElementTree as ET

        root = ET.fromstring(text)
        entries = []
        for item in root.findall(".//item"):
            o = types.SimpleNamespace()
            link_el = item.find("link")
            o.link = link_el.text.strip() if link_el is not None else None
            sent_el = item.find("sentiment")
            # Some feeds may embed sentiment in various fields; here we attach it
            if sent_el is not None:
                setattr(o, "sentiment", sent_el.text.strip())
            desc_el = item.find("description")
            if desc_el is not None:
                o.summary = desc_el.text.strip()
            entries.append(o)
        res = types.SimpleNamespace(entries=entries)
        return res

    # Override the feedparser used inside fmp_sentiment
    monkeypatch.setattr(
        fmp_sentiment, "feedparser", types.SimpleNamespace(parse=mock_parse)
    )

    # Ensure the feature flag is enabled via settings fallback.  We bypass
    # get_settings by clearing FEATURE_FMP_SENTIMENT in settings and using env.
    # Save old environment
    orig_val = os.getenv("FEATURE_FMP_SENTIMENT")
    monkeypatch.setenv("FEATURE_FMP_SENTIMENT", "1")
    # Make sure no API key is required
    monkeypatch.setenv("FMP_API_KEY", "")

    try:
        mapping = fmp_sentiment.fetch_fmp_sentiment()
    finally:
        # Restore original environment value if present
        if orig_val is not None:
            monkeypatch.setenv("FEATURE_FMP_SENTIMENT", orig_val)
        else:
            monkeypatch.delenv("FEATURE_FMP_SENTIMENT", raising=False)

    # Convert keys to canonical form for comparison
    assert mapping == expected
