from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List

def classify_text(title: str) -> Dict[str, Any]:
    """
    Return {'tags': list[str], 'keyword_hits': dict[str,int]} using the primary
    classify() (with dynamic weights/AI) when available; fall back to legacy
    classifier.classify(). Never raises; returns empty result on failure.
    """
    # Prefer dynamic classifier: takes a NewsItem
    try:
        from .classify import classify as classify_item
        from .models import NewsItem
        item = NewsItem(ts_utc=datetime.now(timezone.utc), title=title or "")
        scored = classify_item(item)
        tags: List[str] = []
        hits: Dict[str, int] = {}
        if isinstance(scored, dict):
            tags = list(scored.get("keyword_hits") or scored.get("tags") or [])
            rh = scored.get("keyword_hits", {})
            hits = {str(k): int(v) for k, v in (rh.items() if isinstance(rh, dict) else [])}
            if not hits and tags:
                hits = {t: 1 for t in tags}
        else:
            # dataclass path
            try:
                rh = getattr(scored, "keyword_hits", None)
                if isinstance(rh, dict):
                    hits = {str(k): int(v) for k, v in rh.items()}
                elif isinstance(rh, list):
                    hits = {str(t): 1 for t in rh}
            except Exception:
                pass
            if not hits:
                tags = list(getattr(scored, "tags", []) or [])
                hits = {t: 1 for t in tags}
        return {"tags": tags, "keyword_hits": hits}
    except Exception:
        # Legacy fallback: title-only
        try:
            from .classifier import classify as legacy_classify, load_keyword_weights
            w = {}
            try:
                w = load_keyword_weights()
            except Exception:
                w = {}
            out = legacy_classify(title or "", w or {})
            tags = list(out.get("tags", [])) if isinstance(out, dict) else []
            return {"tags": tags, "keyword_hits": {t: 1 for t in tags}}
        except Exception:
            return {"tags": [], "keyword_hits": {}}