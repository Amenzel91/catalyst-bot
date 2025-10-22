import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

print(f"FEATURE_ADVANCED_CHARTS={os.getenv('FEATURE_ADVANCED_CHARTS')}")
print(f"FEATURE_SENTIMENT_GAUGE={os.getenv('FEATURE_SENTIMENT_GAUGE')}")
print(f"FEATURE_RICH_ALERTS={os.getenv('FEATURE_RICH_ALERTS')}")
