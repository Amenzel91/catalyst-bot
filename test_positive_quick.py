#!/usr/bin/env python3
"""Quick test to verify positive alerts still work after negative alert fix."""

from dotenv import load_dotenv
load_dotenv()

from src.catalyst_bot.models import NewsItem
from src.catalyst_bot.classify import classify
from datetime import datetime, timezone

# Create a positive news item
item = NewsItem(
    title='Company Announces FDA Approval for New Drug',
    link='https://example.com',
    published='2025-01-01T00:00:00Z',
    ticker='TEST',
    source='test',
    summary='Major breakthrough in treatment',
    ts_utc=datetime.now(timezone.utc)
)

result = classify(item)
score = result.source_weight
alert_type = getattr(result, 'alert_type', 'N/A')
neg_kws = getattr(result, 'negative_keywords', [])

print("Positive Alert Regression Test:")
print(f"  Score: {score:.3f}")
print(f"  Alert Type: {alert_type}")
print(f"  Negative Keywords: {neg_kws}")

# Check that positive alerts work
is_positive = score > 0 and alert_type != 'NEGATIVE' and len(neg_kws) == 0
print(f"\nStatus: {'PASS - Positive alerts still work!' if is_positive else 'FAIL - Positive alerts broken!'}")
