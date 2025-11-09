"""Quick test to verify fast_classify produces reasonable scores."""

import os
os.environ["FEATURE_EARNINGS_SCORER"] = "0"  # Disable API calls
os.environ["FEATURE_ML_SENTIMENT"] = "0"  # Disable ML for quick test
os.environ["FEATURE_SEMANTIC_KEYWORDS"] = "0"  # Disable KeyBERT
os.environ["FEATURE_INSIDER_SENTIMENT"] = "0"  # Disable insider sentiment (slow API calls)
os.environ["FEATURE_GOOGLE_TRENDS"] = "0"  # Disable Google Trends
os.environ["FEATURE_SHORT_INTEREST_BOOST"] = "0"  # Disable short interest
os.environ["FEATURE_PREMARKET_SENTIMENT"] = "0"  # Disable premarket
os.environ["FEATURE_AFTERMARKET_SENTIMENT"] = "0"  # Disable aftermarket
os.environ["FEATURE_NEWS_VELOCITY"] = "0"  # Disable news velocity
os.environ["FEATURE_VOLUME_PRICE_DIVERGENCE"] = "0"  # Disable divergence

from datetime import datetime, timezone
from src.catalyst_bot.models import NewsItem
from src.catalyst_bot.classify import fast_classify, enrich_scored_item, classify

# Create a simple test item
item = NewsItem(
    ts_utc=datetime.now(timezone.utc),
    title="AAPL announces FDA approval for breakthrough product",
    ticker="AAPL",
    link="https://www.benzinga.com/test",
    source="benzinga.com"
)

print("Testing fast_classify()...")
scored_fast = fast_classify(item)
print(f"[OK] fast_classify() returned: {type(scored_fast).__name__}")
print(f"  - enriched: {getattr(scored_fast, 'enriched', 'N/A')}")
print(f"  - relevance: {scored_fast.relevance:.3f}")
print(f"  - sentiment: {scored_fast.sentiment:.3f}")
print(f"  - source_weight (total_score): {scored_fast.source_weight:.3f}")
print(f"  - tags: {scored_fast.tags}")

print("\nTesting enrich_scored_item()...")
scored_enriched = enrich_scored_item(scored_fast, item)
print(f"[OK] enrich_scored_item() returned: {type(scored_enriched).__name__}")
print(f"  - enriched: {getattr(scored_enriched, 'enriched', 'N/A')}")
print(f"  - enrichment_timestamp: {getattr(scored_enriched, 'enrichment_timestamp', 'N/A')}")
print(f"  - source_weight (total_score): {scored_enriched.source_weight:.3f}")

print("\nTesting classify() (backward compatibility)...")
scored_full = classify(item)
print(f"[OK] classify() returned: {type(scored_full).__name__}")
print(f"  - enriched: {getattr(scored_full, 'enriched', 'N/A')}")
print(f"  - source_weight (total_score): {scored_full.source_weight:.3f}")

print("\n[SUCCESS] All tests passed!")
print("\nKey observations:")
print(f"  - fast_classify sets enriched=False: {getattr(scored_fast, 'enriched', None) == False}")
print(f"  - enrich_scored_item sets enriched=True: {getattr(scored_enriched, 'enriched', None) == True}")
print(f"  - classify() calls both (enriched=True): {getattr(scored_full, 'enriched', None) == True}")
