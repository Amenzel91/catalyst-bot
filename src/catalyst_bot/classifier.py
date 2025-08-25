from __future__ import annotations
from typing import Dict, List, Tuple
import json, os
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_DEFAULT_WEIGHTS: Dict[str, float] = {
    "fda clearance": 3.0,
    "fda approval": 3.2,
    "phase 3": 2.5,
    "breakthrough": 2.0,
    "contract award": 2.2,
    "strategic partnership": 1.8,
    "uplisting": 1.5,
    "offering": -3.0,
    "dilution": -3.2,
    "going concern": -3.0,
}

def load_keyword_weights(path: str = "data/keyword_weights.json") -> Dict[str, float]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return _DEFAULT_WEIGHTS.copy()

def save_keyword_weights(weights: Dict[str, float], path: str = "data/keyword_weights.json") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2, sort_keys=True)

_ANALYZER = SentimentIntensityAnalyzer()

def classify(title: str, weights: Dict[str, float]) -> Dict:
    t = title.lower()
    wscore = 0.0
    tags: List[str] = []
    for k, w in weights.items():
        if k in t:
            wscore += w
            tags.append(k)
    s = _ANALYZER.polarity_scores(title)["compound"]
    return {"relevance_score": wscore, "sentiment_score": s, "tags": tags}

def sort_key(item: Dict) -> Tuple:
    # recency desc, sentiment desc, simple source rank, ticker alpha
    src_rank = {"businesswire": 3, "globenewswire": 2, "accesswire": 1, "prnewswire": 2}.get(item["source"], 0)
    return (-int(item["ts"].replace("-", "").replace(":", "")[:14]), -item["cls"]["sentiment_score"], -src_rank, (item.get("ticker") or "ZZZZZ"))
