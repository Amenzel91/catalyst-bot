import re

# (NASDAQ: ABCD), (NYSE American: XYZ), Nasdaq: ABCD, $ABCD, etc.
_TICKER_RE = re.compile(
    r"\b(?:NASDAQ|Nasdaq|NYSE(?:\s+American)?|AMEX|CBOE|TSX|LSE|ASX|Euronext)\s*[:\-]\s*\$?([A-Z][A-Z0-9.\-]{0,5})\b"
    r"|(?:^|\s)\$([A-Z][A-Z0-9.\-]{0,5})\b"
)

def ticker_from_title(title: str | None):
    if not title:
        return None
    m = _TICKER_RE.search(title)
    if not m:
        return None
    return (m.group(1) or m.group(2)).upper()
