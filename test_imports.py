"""Test if advanced chart imports work."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("Testing imports...")

try:
    from src.catalyst_bot.chart_cache import get_cache
    print("✓ chart_cache.get_cache")
except Exception as e:
    print(f"✗ chart_cache.get_cache: {e}")

try:
    from src.catalyst_bot.charts_advanced import generate_multi_panel_chart
    print("✓ charts_advanced.generate_multi_panel_chart")
except Exception as e:
    print(f"✗ charts_advanced.generate_multi_panel_chart: {e}")

try:
    from src.catalyst_bot.discord_interactions import add_components_to_payload
    print("✓ discord_interactions.add_components_to_payload")
except Exception as e:
    print(f"✗ discord_interactions.add_components_to_payload: {e}")

try:
    from src.catalyst_bot.sentiment_gauge import generate_sentiment_gauge, log_sentiment_score
    print("✓ sentiment_gauge")
except Exception as e:
    print(f"✗ sentiment_gauge: {e}")

# Check HAS_ADVANCED_CHARTS in alerts.py
try:
    from src.catalyst_bot.alerts import HAS_ADVANCED_CHARTS
    print(f"\nHAS_ADVANCED_CHARTS = {HAS_ADVANCED_CHARTS}")
except Exception as e:
    print(f"\n✗ Cannot import HAS_ADVANCED_CHARTS: {e}")
