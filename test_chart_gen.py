"""Test chart generation directly."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Import after loading env
from src.catalyst_bot.charts_advanced import generate_multi_panel_chart

print("Testing chart generation for AAPL...")
print(f"FEATURE_ADVANCED_CHARTS={os.getenv('FEATURE_ADVANCED_CHARTS')}")

try:
    chart_path = generate_multi_panel_chart("AAPL", timeframe="1D", style="dark")
    print(f"\nChart path: {chart_path}")
    print(f"Chart exists: {chart_path.exists() if chart_path else False}")

    if chart_path and chart_path.exists():
        print(f"Chart size: {chart_path.stat().st_size} bytes")
        print(f"Chart location: {chart_path.absolute()}")
    else:
        print("ERROR: Chart was not generated!")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
