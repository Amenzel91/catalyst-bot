# Keywords to Add Immediately
## Based on MOA Sector Analysis + Industry Research

**Copy these into `src/catalyst_bot/config.py` to catch 15-25% more opportunities**

---

## How to Use This File

1. Open `src/catalyst_bot/config.py` (lines 371-520)
2. Find the relevant category (or create new one)
3. Copy keywords from sections below
4. Test with: `FEATURE_RECORD_ONLY=1 .venv/Scripts/python -m catalyst_bot.runner --once`
5. Monitor for increase in alerts

---

## ENERGY SECTOR (274.6% Avg Return - Highest Priority!)

**Create new category** `"energy_discovery"`:

```python
"energy_discovery": [
    "oil discovery",
    "gas discovery",
    "drilling results",
    "drilling program",
    "well completion",
    "well test",
    "well results",
    "proved reserves",
    "probable reserves",
    "reserves expansion",
    "reserves upgrade",
    "reserves increase",
    "production increase",
    "production milestone",
    "field development",
    "horizontal drilling",
    "unconventional resources",
    "enhanced oil recovery",
    "upstream operations",
    "midstream assets",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_ENERGY_DISCOVERY=0.75`

---

## HEALTHCARE/BIOTECH (Expand Existing Categories)

### Expand `"fda"` category:

**Current keywords in config.py:**
```python
"fda": [
    "fda approval",
    "fda clearance",
    "510(k)",
    "breakthrough therapy",
    # ...existing keywords
]
```

**ADD THESE** (proven high-value):
```python
"fda": [
    # Keep existing keywords, ADD these:
    "fast track designation",
    "fast track status",
    "orphan drug designation",
    "orphan drug status",
    "accelerated approval",
    "priority review",
    "biologics license application",
    "bla approval",
    "new drug application",
    "nda approval",
    "investigational new drug",
    "ind application",
    "expanded access",
    "compassionate use",
    "pma approval",
    "de novo clearance",
    "ce mark approval",
],
```

### Expand `"clinical"` category:

**ADD THESE:**
```python
"clinical": [
    # Keep existing, ADD:
    "primary endpoint met",
    "primary endpoint achieved",
    "statistically significant",
    "statistical significance",
    "pivotal trial",
    "pivotal study",
    "data readout",
    "topline data",
    "top-line results",
    "clinical hold lifted",
    "dosing completed",
    "last patient in",
    "last patient enrolled",
    "patient enrollment complete",
],
```

### Create NEW `"advanced_therapies"` category:

```python
"advanced_therapies": [
    "gene therapy",
    "cell therapy",
    "car-t",
    "car t",
    "crispr",
    "gene editing",
    "biomarker",
    "companion diagnostic",
    "monoclonal antibody",
    "small molecule",
    "biologic",
    "immunotherapy",
    "immuno-oncology",
    "checkpoint inhibitor",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_ADVANCED_THERAPIES=0.65`

---

## TECHNOLOGY SECTOR (54.9% Avg Return)

### Create NEW `"tech_contracts"` category:

```python
"tech_contracts": [
    "government contract",
    "federal contract",
    "defense contract",
    "enterprise agreement",
    "cloud contract",
    "cloud migration",
    "saas agreement",
    "platform agreement",
    "licensing agreement",
    "patent granted",
    "patent issued",
    "patent approval",
    "intellectual property",
    "exclusive license",
    "technology license",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_TECH_CONTRACTS=0.60`

### Create NEW `"ai_ml"` category:

```python
"ai_ml": [
    "artificial intelligence",
    "ai platform",
    "machine learning",
    "ml platform",
    "neural network",
    "deep learning",
    "ai breakthrough",
    "ai integration",
    "generative ai",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_AI_ML=0.55`

---

## FINANCIAL EVENTS (Expand Existing)

### Expand `"uplisting"` category:

**ADD THESE:**
```python
"uplisting": [
    # Keep existing, ADD:
    "nasdaq listing",
    "nyse listing",
    "exchange upgrade",
    "listing approval",
    "minimum bid price",
    "compliance notification",
    "listing standards",
],
```

### Create NEW `"institutional"` category:

```python
"institutional": [
    "institutional investment",
    "institutional investor",
    "strategic investment",
    "lead investor",
    "venture capital",
    "venture funding",
    "series a",
    "series b",
    "series c",
    "private placement",
    "pipe financing",
    "strategic financing",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_INSTITUTIONAL=0.55`

---

## PARTNERSHIPS (Enhance Existing)

### Expand `"partnership"` category:

**ADD THESE:**
```python
"partnership": [
    # Keep existing, ADD:
    "definitive agreement",
    "binding agreement",
    "letter of intent",
    "loi signed",
    "memorandum of understanding",
    "mou signed",
    "exclusive partnership",
    "exclusive collaboration",
    "joint development",
    "co-development",
    "revenue sharing",
    "profit sharing",
    "commercialization rights",
    "distribution rights",
    "marketing rights",
],
```

---

## M&A / BUYOUTS (Enhance Existing)

### Expand `"merger"` category:

**ADD THESE:**
```python
"merger": [
    # Keep existing, ADD:
    "tender offer",
    "takeover bid",
    "buyout offer",
    "go-private",
    "going private",
    "recapitalization",
    "strategic buyer",
    "financial buyer",
    "merger agreement",
    "merger complete",
    "acquisition complete",
    "earnout provision",
    "stock purchase agreement",
    "asset purchase agreement",
],
```

---

## NEGATIVE KEYWORDS (Exit Signals - Create NEW Categories)

### Create `"offering_negative"`:

```python
"offering_negative": [
    "offering priced",
    "offering closed",
    "public offering",
    "secondary offering",
    "follow-on offering",
    "registered direct",
    "direct offering",
    "shelf takedown",
    "underwritten offering",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_OFFERING_NEGATIVE=0.40`

### Create `"warrant_negative"`:

```python
"warrant_negative": [
    "warrant exercise",
    "warrant coverage",
    "warrant inducement",
    "cashless exercise",
    "warrant repricing",
    "warrant amendment",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_WARRANT_NEGATIVE=0.35`

### Create `"dilution_negative"`:

```python
"dilution_negative": [
    "shares outstanding",
    "dilutive effect",
    "anti-dilution",
    "share issuance",
    "authorized shares",
    "common stock issuance",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_DILUTION_NEGATIVE=0.30`

### Create `"distress_negative"`:

```python
"distress_negative": [
    "going concern",
    "substantial doubt",
    "delisting",
    "delisting notice",
    "nasdaq deficiency",
    "compliance deficiency",
    "bankruptcy",
    "chapter 11",
    "restructuring",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_DISTRESS_NEGATIVE=0.60`

---

## STOCK EVENTS (Create NEW Category)

### Create `"stock_events"`:

```python
"stock_events": [
    "stock split",
    "reverse split",
    "share consolidation",
    "dividend declared",
    "dividend increase",
    "special dividend",
    "share buyback",
    "share repurchase",
    "buyback program",
    "repurchase authorization",
    "insider buying",
    "insider purchase",
    "form 4",
    "beneficial ownership",
],
```

**Recommended weight**: `KEYWORD_WEIGHT_STOCK_EVENTS=0.50`

---

## QUICK IMPLEMENTATION CHECKLIST

### Step 1: Add Keywords to config.py

Open `src/catalyst_bot/config.py` around line 371 and add:

```python
keyword_categories = {
    # ... existing categories ...

    # NEW: Energy catalysts (274.6% avg return)
    "energy_discovery": [
        "oil discovery", "gas discovery", "drilling results",
        # ... rest from above
    ],

    # NEW: Advanced therapies (biotech high-value)
    "advanced_therapies": [
        "gene therapy", "cell therapy", "car-t",
        # ... rest from above
    ],

    # NEW: Tech contracts (54.9% avg return)
    "tech_contracts": [
        "government contract", "cloud contract", "patent granted",
        # ... rest from above
    ],

    # NEW: Institutional investment
    "institutional": [
        "institutional investment", "venture funding", "series b",
        # ... rest from above
    ],

    # NEW: Stock events
    "stock_events": [
        "stock split", "dividend increase", "share buyback",
        # ... rest from above
    ],

    # NEW: Negative keywords for exit signals
    "offering_negative": [
        "offering priced", "public offering", "direct offering",
        # ... rest from above
    ],
    "warrant_negative": [
        "warrant exercise", "warrant inducement",
        # ... rest from above
    ],
    "dilution_negative": [
        "dilutive effect", "share issuance",
        # ... rest from above
    ],
    "distress_negative": [
        "going concern", "delisting", "bankruptcy",
        # ... rest from above
    ],
}
```

### Step 2: Add Weights to .env

Open `.env` and add:

```bash
# MOA-Enhanced Keyword Weights
KEYWORD_WEIGHT_ENERGY_DISCOVERY=0.75        # Highest returns
KEYWORD_WEIGHT_ADVANCED_THERAPIES=0.65
KEYWORD_WEIGHT_TECH_CONTRACTS=0.60
KEYWORD_WEIGHT_INSTITUTIONAL=0.55
KEYWORD_WEIGHT_AI_ML=0.55
KEYWORD_WEIGHT_STOCK_EVENTS=0.50
KEYWORD_WEIGHT_OFFERING_NEGATIVE=0.40       # Lower = less aggressive
KEYWORD_WEIGHT_WARRANT_NEGATIVE=0.35
KEYWORD_WEIGHT_DILUTION_NEGATIVE=0.30
KEYWORD_WEIGHT_DISTRESS_NEGATIVE=0.60       # Higher = critical exit signals
```

### Step 3: Test

```bash
# Dry run (no Discord posting)
FEATURE_RECORD_ONLY=1 .venv/Scripts/python -m catalyst_bot.runner --once
```

**Check logs for new keyword hits:**
```bash
grep "keyword_hit" data/logs/bot.jsonl | grep "energy_discovery"
grep "keyword_hit" data/logs/bot.jsonl | grep "advanced_therapies"
```

### Step 4: Compare Before/After

**Baseline** (run first):
```bash
.venv/Scripts/python -m catalyst_bot.backtesting.engine \
    --start 2024-09-01 --end 2025-10-01 \
    --output backtest_baseline.json
```

**After adding keywords**:
```bash
.venv/Scripts/python -m catalyst_bot.backtesting.engine \
    --start 2024-09-01 --end 2025-10-01 \
    --output backtest_enhanced.json
```

**Expected improvement**:
- +15-25% more alerts
- +10-15% coverage (catching profitable catalysts)
- <10% decrease in hit rate (acceptable tradeoff)

---

## Priority Order (If Adding Incrementally)

**Week 1** (Highest Impact):
1. `energy_discovery` - 274.6% avg return
2. Expand `fda` category - proven high-value
3. `advanced_therapies` - biotech gold mine

**Week 2** (High Value):
4. `tech_contracts` - 54.9% avg return
5. Expand `clinical` category
6. `institutional` - momentum triggers

**Week 3** (Medium Value):
7. `stock_events` - volatility catalysts
8. Expand `partnership` category
9. Expand `merger` category

**Week 4** (Defensive):
10. Negative keyword categories (exit signals)

---

## Expected Outcomes

Based on MOA analysis of 468 missed opportunities:

**Before** (current keywords):
- Coverage: 85.2% of profitable catalysts caught
- 14.8% miss rate (468 missed opportunities)
- Average alert score threshold: 0.20

**After** (enhanced keywords):
- **Coverage: 92-95%** (+7-10% improvement)
- **Miss rate: 5-8%** (down from 14.8%)
- **Additional 100-140 alerts/year** caught
- **Estimated profit increase**: $20-35k/year (conservative $1k sizing)

---

## Long-Term: Enable Full Keyword Discovery

For ongoing keyword optimization, enable rejected_items logging:

**File**: `src/catalyst_bot/rejected_items_logger.py` (create new file)

```python
"""Log rejected items for keyword extraction."""
import json
from pathlib import Path
from typing import Optional


def log_rejected_item(
    ticker: str,
    title: str,
    summary: str,
    source: str,
    rejection_reason: str,
    rejection_ts: str,
    price: float,
):
    """Log rejected item to JSONL for keyword analysis."""
    log_path = Path("data/rejected_items.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "ticker": ticker,
        "title": title,
        "summary": summary,
        "source": source,
        "rejection_reason": rejection_reason,
        "rejection_ts": str(rejection_ts),
        "price": price,
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")
```

**Then in `src/catalyst_bot/feeds.py`**, add after each rejection:

```python
from .rejected_items_logger import log_rejected_item

# After price ceiling rejection:
log_rejected_item(
    ticker=item.ticker,
    title=item.title,
    summary=getattr(item, "summary", ""),
    source=getattr(item, "source", ""),
    rejection_reason="HIGH_PRICE",
    rejection_ts=item.published_time,
    price=price,
)
```

After 1 month, run:
```bash
python extract_moa_keywords.py
```

This will extract actual keywords from YOUR rejected items.

---

## Support

- **Full guide**: `KEYWORD_DISCOVERY_GUIDE.md`
- **Config file**: `src/catalyst_bot/config.py:371-520`
- **Classifier**: `src/catalyst_bot/classify.py:610-630`

---

**Last Updated**: October 16, 2025
**Estimated Impact**: +15-25% coverage, +100-140 alerts/year
**Time to Implement**: 15-30 minutes
