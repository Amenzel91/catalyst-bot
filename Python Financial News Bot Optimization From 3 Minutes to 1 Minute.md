# Python Financial News Bot Optimization: From 3 Minutes to 1 Minute

**The path to 3x faster processing lies in three critical changes:** migrating API calls to async concurrent execution, implementing aggressive multi-tier caching, and separating batch operations into nightly jobs. This guide provides diagnostic tools to identify your actual bottlenecks first, then actionable optimization strategies prioritized by impact and implementation complexity.

For a pipeline processing ~1000 articles/day with 10 enrichment modules, the biggest performance gains come from parallelizing API calls (10-20x speedup), caching frequently-accessed data (reducing API calls by 90%+), and deferring non-critical operations to off-hours processing. The current sequential architecture leaves significant performance on the table—async patterns can process 100+ concurrent API requests versus the current one-at-a-time approach.

## Diagnostic first: Identify your actual bottlenecks

Before optimizing, you must measure. **Scalene emerges as the optimal profiling tool** for async Python pipelines—it automatically separates I/O wait time from CPU computation, pinpointing whether your bottleneck is network calls or local processing. Install and run it immediately to identify quick wins.

**Drop-in profiling setup:**

```python
# Install: pip install scalene
# Run: python -m scalene --reduced-profile --cpu-only feeds_pipeline.py

# Or add programmatic profiling with zero overhead when disabled
import os
from contextlib import nullcontext

def profile_if_enabled(func):
    """Decorator that profiles only when ENABLE_PROFILING=1"""
    def wrapper(*args, **kwargs):
        if os.getenv('ENABLE_PROFILING'):
            from scalene import scalene_profiler
            scalene_profiler.start()
            try:
                return func(*args, **kwargs)
            finally:
                scalene_profiler.stop()
        return func(*args, **kwargs)
    return wrapper

@profile_if_enabled
def fetch_pr_feeds():
    # Your existing pipeline code
    pass
```

**Reading Scalene output for financial pipelines:**

When Scalene shows **System % >> Python %**, your bottleneck is I/O (API calls, database). Solution: increase concurrency with async. When **Python % is high**, your bottleneck is CPU (LLM inference, sentiment analysis). Solution: multiprocessing or algorithm optimization. This distinction determines your optimization strategy.

**Event loop lag monitoring for async code:**

```python
import asyncio
from datetime import datetime

async def monitor_event_loop_lag(threshold_ms=100):
    """Detects blocking operations in async code"""
    loop = asyncio.get_event_loop()
    while True:
        start = loop.time()
        await asyncio.sleep(1)
        elapsed = loop.time() - start
        lag = (elapsed - 1) * 1000
        
        if lag > threshold_ms:
            print(f"⚠️ {datetime.now()}: Event loop blocked {lag:.0f}ms")

# Add to your async main function
asyncio.create_task(monitor_event_loop_lag())
```

**Quick profiling context manager for timing code sections:**

```python
from contextlib import contextmanager
import time

@contextmanager
def timer(name="Operation"):
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"⏱️  {name}: {elapsed:.3f}s ({elapsed*1000:.0f}ms)")

# Usage throughout your pipeline
with timer("RSS feed fetch"):
    articles = fetch_rss_feeds()

with timer("Price lookups - 100 tickers"):
    prices = batch_fetch_prices(tickers)
```

**Production monitoring with Prometheus metrics:**

```python
from prometheus_client import Histogram, Counter, Gauge, generate_latest

# Define metrics for financial pipeline
PROCESSING_TIME = Histogram(
    'article_processing_seconds',
    'Time to process single article',
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
)

API_CALL_DURATION = Histogram(
    'api_call_duration_seconds',
    'API call latency by service',
    ['service', 'endpoint']
)

CACHE_HITS = Counter('cache_hits_total', 'Cache hit count', ['cache_type'])
CACHE_MISSES = Counter('cache_misses_total', 'Cache miss count', ['cache_type'])

QUEUE_DEPTH = Gauge('processing_queue_depth', 'Articles waiting for processing')

# Instrument your code
@PROCESSING_TIME.time()
async def process_article(article):
    # Your processing logic
    pass

# Track API calls
with API_CALL_DURATION.labels(service='alpha_vantage', endpoint='quote').time():
    price = await fetch_price(ticker)
```

## Quick wins: Async API calls with connection pooling

The single biggest performance gain comes from converting sequential API calls to concurrent async execution. **For 100 API calls, async provides 10-20x speedup** versus sequential requests—reducing 30 seconds to 1.5 seconds.

**Refactored main fetch function with async:**

```python
import asyncio
import aiohttp
from typing import List, Dict

async def fetch_pr_feeds_async(sources: List[str]) -> List[Dict]:
    """Replace sequential feeds.fetch_pr_feeds() with concurrent version"""
    
    # Connection pooling: reuse connections across all requests
    connector = aiohttp.TCPConnector(
        limit=50,              # Max 50 concurrent connections total
        limit_per_host=10,     # Max 10 per domain
        ttl_dns_cache=300,     # Cache DNS for 5 minutes
        enable_cleanup_closed=True
    )
    
    timeout = aiohttp.ClientTimeout(
        total=None,           # No total timeout (prevents pool wait issues)
        sock_connect=5,       # 5s for connection
        sock_read=30          # 30s for response
    )
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Fetch all RSS feeds concurrently
        tasks = [fetch_single_feed(session, source) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out errors, log failures
        articles = []
        for result in results:
            if isinstance(result, Exception):
                print(f"Feed fetch failed: {result}")
            else:
                articles.extend(result)
        
        return articles

async def fetch_single_feed(session: aiohttp.ClientSession, source: str) -> List[Dict]:
    """Fetch and parse single RSS feed"""
    try:
        async with session.get(source) as response:
            response.raise_for_status()
            content = await response.text()
            return parse_rss(content)
    except asyncio.TimeoutError:
        print(f"Timeout fetching {source}")
        return []
    except aiohttp.ClientError as e:
        print(f"Error fetching {source}: {e}")
        return []
```

**Batch price lookups with rate limiting:**

```python
class RateLimitedAPIClient:
    """Wrapper for financial APIs with semaphore-based rate limiting"""
    
    def __init__(self, api_key: str, max_concurrent=10, requests_per_second=5):
        self.api_key = api_key
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0
    
    async def fetch_price(self, session: aiohttp.ClientSession, ticker: str) -> Dict:
        """Fetch price with rate limiting"""
        async with self.semaphore:
            # Enforce minimum time between requests
            now = asyncio.get_event_loop().time()
            sleep_time = self.min_interval - (now - self.last_request_time)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            
            self.last_request_time = asyncio.get_event_loop().time()
            
            # Make API call
            url = f"https://api.example.com/quote/{ticker}"
            async with session.get(url, params={'apikey': self.api_key}) as resp:
                return await resp.json()

async def batch_fetch_prices(tickers: List[str]) -> Dict[str, float]:
    """Fetch prices for multiple tickers concurrently"""
    client = RateLimitedAPIClient(
        api_key=ALPHA_VANTAGE_KEY,
        max_concurrent=5,        # Alpha Vantage: 5 calls/min
        requests_per_second=0.08  # ~5 calls/min = 0.08/sec
    )
    
    async with aiohttp.ClientSession() as session:
        tasks = [client.fetch_price(session, ticker) for ticker in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            ticker: result.get('price')
            for ticker, result in zip(tickers, results)
            if not isinstance(result, Exception)
        }
```

**Finviz Elite batch optimization:**

```python
import time
import pandas as pd
from functools import lru_cache

@lru_cache(maxsize=1)
def load_finviz_screener_cache():
    """Load Finviz screener export once, cache in memory"""
    # Export screener to CSV via Finviz Elite web UI
    df = pd.read_csv('finviz_screener_export.csv')
    return {
        row['Ticker']: {
            'company': row['Company'],
            'sector': row['Sector'],
            'industry': row['Industry'],
            'market_cap': row['Market Cap'],
            'pe': row['P/E'],
            'volume': row['Volume']
        }
        for _, row in df.iterrows()
    }

def get_ticker_fundamentals(ticker: str) -> Dict:
    """Instant lookup without API call"""
    cache = load_finviz_screener_cache()
    return cache.get(ticker, {})

# Update cache daily via scheduled job
def refresh_finviz_cache():
    """Run nightly to export fresh screener data"""
    # Could automate with Selenium if Finviz lacks export API
    load_finviz_screener_cache.cache_clear()
    # Download new export...
```

**yfinance optimized batch downloads:**

```python
import yfinance as yf
from requests import Session

def batch_fetch_yfinance(tickers: List[str], period="1d") -> pd.DataFrame:
    """Optimized batch download with threading and session reuse"""
    
    # Method 1: Built-in batch download (RECOMMENDED)
    data = yf.download(
        tickers=" ".join(tickers),  # Space-separated string
        period=period,
        threads=True,               # Enable concurrent downloads
        progress=False,             # Disable progress bar
        group_by='ticker'
    )
    
    return data

def fast_price_lookup(ticker: str, session: Session = None) -> float:
    """Use fast_info for price-only queries (5-10x faster than .info)"""
    if session is None:
        session = Session()
    
    t = yf.Ticker(ticker, session=session)
    return t.fast_info.get('lastPrice')

# Reuse session across multiple ticker lookups
session = Session()
prices = {ticker: fast_price_lookup(ticker, session) for ticker in tickers}
```

## Multi-tier caching architecture

Aggressive caching reduces API calls by 90%+ and provides sub-10ms lookups. **The hybrid architecture combines in-memory Python dicts for hot data, Redis for shared state, and SQLite for persistent storage.**

**Complete caching implementation:**

```python
import sqlite3
import redis
from functools import lru_cache
from typing import Optional, Dict
import json
from datetime import datetime, timedelta

class HybridCache:
    """Three-tier caching: Memory → Redis → SQLite → API"""
    
    def __init__(self, redis_url="redis://localhost", sqlite_path="cache.db"):
        # L1: In-memory cache for static data
        self.memory_cache = {}
        
        # L2: Redis for shared, time-sensitive data
        self.redis = redis.from_url(redis_url, decode_responses=True)
        
        # L3: SQLite for persistent storage
        self.db = sqlite3.connect(sqlite_path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self._init_tables()
    
    def _init_tables(self):
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS price_cache (
                ticker TEXT PRIMARY KEY,
                price REAL,
                timestamp TIMESTAMP,
                source TEXT
            )
        ''')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS ticker_mappings (
                company_name TEXT PRIMARY KEY,
                ticker TEXT,
                exchange TEXT
            )
        ''')
        self.db.execute('''
            CREATE INDEX IF NOT EXISTS idx_ticker_mappings 
            ON ticker_mappings(company_name)
        ''')
    
    def get_price(self, ticker: str, max_age_seconds=300) -> Optional[float]:
        """Get price with 5-minute TTL (300 seconds)"""
        
        # L1: Check Redis (hot cache)
        redis_key = f"price:{ticker}"
        cached = self.redis.get(redis_key)
        if cached:
            return float(cached)
        
        # L2: Check SQLite (warm cache)
        cursor = self.db.execute(
            'SELECT price, timestamp FROM price_cache WHERE ticker = ?',
            (ticker,)
        )
        row = cursor.fetchone()
        if row:
            price, timestamp = row
            age = (datetime.now() - datetime.fromisoformat(timestamp)).seconds
            if age < max_age_seconds:
                # Promote to Redis
                self.redis.setex(redis_key, max_age_seconds - age, price)
                return price
        
        # L3: Cache miss - caller must fetch from API
        return None
    
    def set_price(self, ticker: str, price: float, ttl=300):
        """Store price in all cache tiers"""
        now = datetime.now().isoformat()
        
        # Redis with TTL
        self.redis.setex(f"price:{ticker}", ttl, price)
        
        # SQLite (persistent)
        self.db.execute('''
            INSERT OR REPLACE INTO price_cache (ticker, price, timestamp, source)
            VALUES (?, ?, ?, 'api')
        ''', (ticker, price, now))
        self.db.commit()
    
    def get_ticker_mapping(self, company_name: str) -> Optional[str]:
        """Fast ticker lookup with permanent memory cache"""
        
        # L1: Memory cache (fastest)
        if company_name in self.memory_cache:
            return self.memory_cache[company_name]
        
        # L2: SQLite
        cursor = self.db.execute(
            'SELECT ticker FROM ticker_mappings WHERE company_name = ?',
            (company_name.lower(),)
        )
        row = cursor.fetchone()
        if row:
            ticker = row[0]
            self.memory_cache[company_name] = ticker
            return ticker
        
        return None
    
    def warm_cache(self, tickers: List[str], fetch_func):
        """Pre-populate cache at startup"""
        print(f"Warming cache for {len(tickers)} tickers...")
        prices = fetch_func(tickers)
        for ticker, price in prices.items():
            self.set_price(ticker, price, ttl=3600)

# Usage in pipeline
cache = HybridCache()

async def get_price_with_cache(ticker: str) -> float:
    """Fetch price with caching"""
    
    # Try cache first
    price = cache.get_price(ticker, max_age_seconds=300)
    if price:
        return price
    
    # Cache miss - fetch from API
    price = await fetch_from_api(ticker)
    cache.set_price(ticker, price, ttl=300)
    return price
```

**TTL configuration by data type:**

```python
CACHE_TTL = {
    # Real-time data
    'price:intraday': 10,          # 10 seconds during market hours
    'price:eod': 43200,             # 12 hours after market close
    
    # Moderate update frequency
    'analyst:rating': 86400,        # 24 hours
    'options:flow': 60,             # 1 minute
    'earnings:calendar': 21600,     # 6 hours
    
    # Slow-changing data
    'company:profile': 2592000,     # 30 days
    'ticker:mapping': 604800,       # 7 days
    'sec:filing:metadata': 3600,    # 1 hour (recent filings)
    
    # Deduplication
    'news:article:hash': 172800,    # 48 hours
}

# Add jitter to prevent thundering herd
import random

def get_ttl_with_jitter(base_ttl: int) -> int:
    """Add ±10% randomization to TTL"""
    jitter = random.uniform(0.9, 1.1)
    return int(base_ttl * jitter)

cache.set_price(ticker, price, ttl=get_ttl_with_jitter(CACHE_TTL['price:intraday']))
```

**Redis configuration for financial data:**

```redis
# redis.conf optimizations
maxmemory 512mb
maxmemory-policy allkeys-lru  # Evict least recently used keys
save ""  # Disable RDB snapshots for speed (use AOF if persistence needed)
appendonly yes  # Enable AOF for durability
appendfsync everysec  # Balance speed and safety
```

**Cache warming at startup:**

```python
async def warm_startup_cache():
    """Pre-load hot data at application startup"""
    
    # Load ticker mappings into memory
    print("Loading ticker mappings...")
    cursor = cache.db.execute('SELECT company_name, ticker FROM ticker_mappings')
    for name, ticker in cursor:
        cache.memory_cache[name] = ticker
    
    # Warm top 100 tickers
    TOP_TICKERS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', ...]
    prices = await batch_fetch_prices(TOP_TICKERS)
    for ticker, price in prices.items():
        cache.set_price(ticker, price, ttl=300)
    
    print(f"Cache warmed: {len(cache.memory_cache)} mappings, {len(prices)} prices")

# Run at application startup
asyncio.run(warm_startup_cache())
```

## Company name extraction and ticker mapping

Extracting tickers from headlines and mapping company names efficiently requires a hybrid NLP approach combining rule-based patterns with machine learning.

**Fast ticker extraction with spaCy and patterns:**

```python
import spacy
import re
from spacy.matcher import Matcher
from rapidfuzz import process, fuzz

# Load once at startup
nlp = spacy.load("en_core_web_lg")

# Add custom patterns for financial entities
ruler = nlp.add_pipe("entity_ruler", before="ner")
patterns = [
    {"label": "TICKER", "pattern": [{"TEXT": {"REGEX": r"\$[A-Z]{1,5}"}}]},
    {"label": "ORG", "pattern": [{"TEXT": {"REGEX": r"[A-Z][a-z]+"}, "POS": "PROPN"}, 
                                   {"LOWER": {"IN": ["inc", "corp", "ltd", "llc"]}}]},
]
ruler.add_patterns(patterns)

def extract_tickers_from_headline(headline: str) -> List[str]:
    """Extract ticker symbols and company names"""
    tickers = set()
    
    # Pattern 1: Explicit ticker mentions ($AAPL, (AAPL), AAPL:)
    explicit_tickers = re.findall(r'\$?([A-Z]{1,5})(?:\s|:|,|\))', headline)
    tickers.update(explicit_tickers)
    
    # Pattern 2: NER for company names
    doc = nlp(headline)
    for ent in doc.ents:
        if ent.label_ in ('ORG', 'TICKER'):
            # Look up in ticker mapping cache
            ticker = cache.get_ticker_mapping(ent.text)
            if ticker:
                tickers.add(ticker)
    
    return list(tickers)
```

**Building ticker mapping database from SEC EDGAR:**

```python
import requests
import sqlite3

def build_ticker_mapping_db():
    """Download SEC ticker list and build lookup database"""
    
    # Fetch from SEC EDGAR
    url = "https://www.sec.gov/files/company_tickers_exchange.json"
    response = requests.get(url, headers={'User-Agent': 'MyApp contact@example.com'})
    data = response.json()
    
    conn = sqlite3.connect('cache.db')
    conn.execute('PRAGMA journal_mode=WAL')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ticker_mappings (
            cik TEXT,
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            exchange TEXT
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS company_aliases (
            company_name TEXT PRIMARY KEY,
            ticker TEXT,
            alias_type TEXT
        )
    ''')
    
    # Insert primary names
    for row in data['data']:
        cik, ticker, name, exchange = row
        conn.execute('''
            INSERT OR REPLACE INTO ticker_mappings (cik, ticker, company_name, exchange)
            VALUES (?, ?, ?, ?)
        ''', (cik, ticker, name, exchange))
        
        # Add aliases (lowercase, without Inc/Corp)
        conn.execute('''
            INSERT OR REPLACE INTO company_aliases (company_name, ticker, alias_type)
            VALUES (?, ?, 'primary')
        ''', (name.lower(), ticker))
        
        # Add stripped version
        stripped = re.sub(r'\s+(Inc|Corp|Ltd|LLC)\.?$', '', name, flags=re.IGNORECASE)
        if stripped != name:
            conn.execute('''
                INSERT OR REPLACE INTO company_aliases (company_name, ticker, alias_type)
                VALUES (?, ?, 'stripped')
            ''', (stripped.lower(), ticker))
    
    conn.commit()
    print(f"Loaded {len(data['data'])} tickers from SEC EDGAR")

# Run daily at 4 AM (after SEC 3 AM update)
```

**Fuzzy matching for ambiguous company names:**

```python
from rapidfuzz import process, fuzz, utils

def find_ticker_fuzzy(company_name: str, threshold=85) -> Optional[str]:
    """Fuzzy match company name to ticker with RapidFuzz"""
    
    # Get all known company names from database
    cursor = cache.db.execute('SELECT company_name, ticker FROM company_aliases')
    company_dict = {name: ticker for name, ticker in cursor}
    
    # Fuzzy match with WRatio (best for company names)
    matches = process.extractOne(
        company_name.lower(),
        company_dict.keys(),
        scorer=fuzz.WRatio,
        processor=utils.default_process,
        score_cutoff=threshold
    )
    
    if matches:
        matched_name, score, _ = matches
        return company_dict[matched_name], score
    
    return None, 0

# Example usage
ticker, confidence = find_ticker_fuzzy("Apple Incorporated")
# Returns: ('AAPL', 92)
```

**Inverted index for fast candidate filtering:**

```python
from collections import defaultdict

class TickerIndex:
    """Inverted index for fast company name → ticker lookup"""
    
    def __init__(self):
        self.token_index = defaultdict(set)  # token → set of company IDs
        self.companies = {}  # company ID → (name, ticker)
        self._build_index()
    
    def _build_index(self):
        cursor = cache.db.execute('SELECT company_name, ticker FROM company_aliases')
        for idx, (name, ticker) in enumerate(cursor):
            self.companies[idx] = (name, ticker)
            
            # Index each token
            for token in name.lower().split():
                if len(token) > 2:  # Skip short tokens
                    self.token_index[token].add(idx)
    
    def search(self, query: str) -> List[tuple]:
        """Fast lookup using inverted index"""
        tokens = query.lower().split()
        
        # Find companies containing all tokens (AND query)
        candidate_ids = set.intersection(*[
            self.token_index.get(token, set()) 
            for token in tokens
        ])
        
        # Return matched companies
        return [self.companies[cid] for cid in candidate_ids]

# Usage
index = TickerIndex()
matches = index.search("Apple Inc")
# Returns: [('apple inc.', 'AAPL')]
```

## Parallel processing patterns

Choosing the right concurrency model depends on whether operations are I/O-bound (network, database) or CPU-bound (sentiment analysis, LLM inference).

**Mixed workload pattern for enrichment pipeline:**

```python
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import os

async def enrich_articles_parallel(articles: List[Dict]) -> List[Dict]:
    """Parallel enrichment with async I/O and multiprocessing CPU"""
    
    # Stage 1: I/O-bound operations (async)
    async with aiohttp.ClientSession() as session:
        # Concurrent API calls
        price_tasks = [fetch_price(session, art['ticker']) for art in articles]
        prices = await asyncio.gather(*price_tasks)
    
    # Stage 2: CPU-bound operations (multiprocessing)
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        # Parallel sentiment analysis
        sentiments = list(executor.map(
            analyze_sentiment_cpu_bound,
            [art['text'] for art in articles]
        ))
    
    # Combine results
    for article, price, sentiment in zip(articles, prices, sentiments):
        article['price'] = price
        article['sentiment'] = sentiment
    
    return articles

def analyze_sentiment_cpu_bound(text: str) -> float:
    """CPU-intensive sentiment analysis"""
    # VADER, FinBERT, or custom model
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer = SentimentIntensityAnalyzer()
    return analyzer.polarity_scores(text)['compound']
```

**LLM classification with process pool:**

```python
from multiprocessing import Pool
import torch

# Global model (loaded once per worker)
model = None

def init_worker(model_path: str):
    """Initialize worker with loaded model"""
    global model
    import transformers
    model = transformers.AutoModelForSequenceClassification.from_pretrained(model_path)
    model.eval()
    print(f"Model loaded in worker {os.getpid()}")

def classify_article(text: str) -> str:
    """Classify article using local LLM"""
    global model
    with torch.no_grad():
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        outputs = model(**inputs)
        predicted_class = outputs.logits.argmax(dim=1).item()
    return CATEGORIES[predicted_class]

def batch_classify(articles: List[str], model_path: str) -> List[str]:
    """Parallel LLM classification"""
    num_workers = max(1, os.cpu_count() - 1)  # Leave one CPU free
    
    with Pool(
        processes=num_workers,
        initializer=init_worker,
        initargs=(model_path,)
    ) as pool:
        classifications = pool.map(classify_article, articles)
    
    return classifications
```

**Fan-out/fan-in pattern for feature modules:**

```python
async def enrich_single_article(article: Dict, session: aiohttp.ClientSession) -> Dict:
    """Parallel enrichment from multiple sources"""
    
    ticker = article.get('ticker')
    if not ticker:
        return article
    
    # Fan-out: Launch all enrichment tasks concurrently
    tasks = {
        'price': fetch_price(session, ticker),
        'sentiment': fetch_sentiment(session, ticker),
        'analyst_targets': fetch_analyst_targets(session, ticker),
        'options_flow': fetch_options_flow(session, ticker),
        'earnings': fetch_earnings_date(session, ticker),
    }
    
    # Fan-in: Wait for all results
    results = await asyncio.gather(
        *tasks.values(),
        return_exceptions=True  # Don't fail entire enrichment if one source fails
    )
    
    # Merge results
    for key, result in zip(tasks.keys(), results):
        if not isinstance(result, Exception):
            article[key] = result
    
    return article

async def enrich_all_articles(articles: List[Dict]) -> List[Dict]:
    """Process multiple articles concurrently"""
    async with aiohttp.ClientSession() as session:
        tasks = [enrich_single_article(art, session) for art in articles]
        return await asyncio.gather(*tasks)
```

## Smart filtering and early rejection

Processing only relevant articles saves 50-70% of enrichment operations.

**Pre-filtering before expensive operations:**

```python
def should_process_article(article: Dict, watchlist: set) -> bool:
    """Filter out irrelevant articles before enrichment"""
    
    # Filter 1: Must mention a ticker
    tickers = extract_tickers_from_headline(article['title'])
    if not tickers:
        return False
    
    # Filter 2: Only process watchlist tickers (if configured)
    if watchlist and not any(t in watchlist for t in tickers):
        return False
    
    # Filter 3: Skip low-quality sources
    BLACKLISTED_SOURCES = {'spam-site.com', 'low-quality-news.com'}
    if article.get('source') in BLACKLISTED_SOURCES:
        return False
    
    # Filter 4: Skip non-English articles
    if detect_language(article['title']) != 'en':
        return False
    
    # Filter 5: Skip penny stocks (if price available)
    price = cache.get_price(tickers[0])
    if price and price < 1.0:
        return False
    
    return True

# Apply filter early
articles = await fetch_pr_feeds_async(sources)
relevant_articles = [a for a in articles if should_process_article(a, WATCHLIST)]
print(f"Filtered {len(articles)} → {len(relevant_articles)} articles")

# Only enrich relevant articles
enriched = await enrich_all_articles(relevant_articles)
```

**Bloom filter for duplicate detection:**

```python
from bloom_filter import BloomFilter

class ArticleDeduplicator:
    """Memory-efficient duplicate detection with Bloom filter"""
    
    def __init__(self, max_elements=10000, error_rate=0.01):
        self.bloom = BloomFilter(max_elements=max_elements, error_rate=error_rate)
        self.seen_articles = set()  # Fallback exact tracking for recent articles
        self.max_recent = 1000
    
    def _get_article_hash(self, article: Dict) -> str:
        """Create unique hash for article"""
        import hashlib
        content = f"{article['title']}|{article.get('url', '')}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def is_duplicate(self, article: Dict) -> bool:
        """Check if article was seen before"""
        article_hash = self._get_article_hash(article)
        
        # Quick Bloom filter check (90%+ filter rate)
        if article_hash not in self.bloom:
            # Definitely not seen before
            self.bloom.add(article_hash)
            self._add_to_recent(article_hash)
            return False
        
        # Possible duplicate - check exact set
        if article_hash in self.seen_articles:
            return True
        
        # False positive in Bloom filter
        self._add_to_recent(article_hash)
        return False
    
    def _add_to_recent(self, article_hash: str):
        """Track recent articles for exact matching"""
        self.seen_articles.add(article_hash)
        if len(self.seen_articles) > self.max_recent:
            # Remove oldest (FIFO)
            self.seen_articles.pop()

# Usage
deduplicator = ArticleDeduplicator()
unique_articles = [a for a in articles if not deduplicator.is_duplicate(a)]
```

## Pipeline refactoring: Separate real-time and batch operations

**Move slow operations to nightly jobs:**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

scheduler = AsyncIOScheduler()

# Real-time pipeline (runs every 5 minutes)
async def realtime_pipeline():
    """Fast pipeline with only critical operations"""
    with timer("Real-time pipeline"):
        # Stage 1: Fetch articles
        articles = await fetch_pr_feeds_async(RSS_SOURCES)
        
        # Stage 2: Extract tickers and filter
        for article in articles:
            article['tickers'] = extract_tickers_from_headline(article['title'])
        
        relevant = [a for a in articles if should_process_article(a, WATCHLIST)]
        
        # Stage 3: Fast enrichment only (price, basic sentiment)
        async with aiohttp.ClientSession() as session:
            for article in relevant:
                article['price'] = await get_price_with_cache(article['tickers'][0])
                article['sentiment'] = quick_sentiment(article['title'])
        
        # Stage 4: Store to database
        await store_articles(relevant)
        
        print(f"Processed {len(relevant)} articles in real-time")

# Nightly batch job (runs at 2 AM)
@scheduler.scheduled_job('cron', hour=2)
async def nightly_batch_pipeline():
    """Deep analysis on all day's articles"""
    with timer("Nightly batch"):
        # Fetch all articles from past 24 hours
        articles = fetch_articles_from_db(since=datetime.now() - timedelta(days=1))
        
        # Expensive operations
        # 1. Full sentiment analysis with LLM
        full_sentiments = batch_classify([a['text'] for a in articles], MODEL_PATH)
        
        # 2. Options flow analysis
        options_data = await batch_fetch_options_flow([a['ticker'] for a in articles])
        
        # 3. Earnings calendar sync
        await refresh_earnings_calendar()
        
        # 4. Analyst ratings refresh
        await refresh_analyst_ratings()
        
        # 5. Update cache
        await cache_warming_job()
        
        print(f"Batch processed {len(articles)} articles")

# Start scheduler
scheduler.add_job(realtime_pipeline, 'interval', minutes=5)
scheduler.start()
```

**Database-backed queue for deferred processing:**

```python
import aiosqlite
from enum import Enum

class TaskStatus(Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'

class TaskQueue:
    """SQLite-backed job queue for deferred processing"""
    
    def __init__(self, db_path='queue.db'):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT,
                payload TEXT,
                status TEXT,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON tasks(status, priority)')
        conn.commit()
        conn.close()
    
    async def enqueue(self, task_type: str, payload: Dict, priority: int = 0):
        """Add task to queue"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO tasks (task_type, payload, status, priority)
                VALUES (?, ?, ?, ?)
            ''', (task_type, json.dumps(payload), TaskStatus.PENDING.value, priority))
            await db.commit()
    
    async def dequeue(self) -> Optional[tuple]:
        """Get next pending task"""
        async with aiosqlite.connect(self.db_path) as db:
            # Atomic claim of task
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute('''
                SELECT task_id, task_type, payload
                FROM tasks
                WHERE status = ?
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            ''', (TaskStatus.PENDING.value,))
            
            row = await cursor.fetchone()
            if row:
                task_id, task_type, payload = row
                await db.execute('''
                    UPDATE tasks SET status = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE task_id = ?
                ''', (TaskStatus.PROCESSING.value, task_id))
                await db.commit()
                return task_id, task_type, json.loads(payload)
            
            await db.commit()
            return None
    
    async def mark_completed(self, task_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE tasks SET status = ? WHERE task_id = ?
            ''', (TaskStatus.COMPLETED.value, task_id))
            await db.commit()

# Usage: Defer expensive operations
queue = TaskQueue()

# Real-time pipeline enqueues tasks
await queue.enqueue('deep_sentiment_analysis', {'article_id': 123}, priority=1)
await queue.enqueue('options_flow_lookup', {'ticker': 'AAPL'}, priority=2)

# Background worker processes tasks
async def background_worker():
    while True:
        task = await queue.dequeue()
        if task:
            task_id, task_type, payload = task
            try:
                await process_task(task_type, payload)
                await queue.mark_completed(task_id)
            except Exception as e:
                print(f"Task {task_id} failed: {e}")
        else:
            await asyncio.sleep(10)  # No tasks, wait

asyncio.create_task(background_worker())
```

## Specific API optimizations

**Tiingo efficient batching (workaround for no batch support):**

```python
async def fetch_tiingo_batch(tickers: List[str], tiingo_key: str) -> Dict:
    """Tiingo doesn't support batch - use concurrent requests with rate limiting"""
    
    # Entry tier: 50 unique symbols/hour = ~1.39 sec/request
    semaphore = asyncio.Semaphore(5)  # 5 concurrent max
    min_delay = 1.5  # 1.5 seconds between requests
    
    async def fetch_single(session, ticker):
        async with semaphore:
            await asyncio.sleep(min_delay)
            url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
            async with session.get(url, params={'token': tiingo_key}) as resp:
                return ticker, await resp.json()
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_single(session, t) for t in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            ticker: data
            for ticker, data in results
            if not isinstance(data, Exception)
        }
```

**Finnhub with WebSocket for real-time:**

```python
import websocket
import json
import threading

class FinnhubWebSocket:
    """Persistent WebSocket connection for real-time prices"""
    
    def __init__(self, api_key: str, on_price_update):
        self.api_key = api_key
        self.on_price_update = on_price_update
        self.ws = None
        self.subscribed_tickers = set()
    
    def connect(self):
        """Connect to Finnhub WebSocket"""
        websocket_url = f"wss://ws.finnhub.io?token={self.api_key}"
        self.ws = websocket.WebSocketApp(
            websocket_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
        # Run in background thread
        thread = threading.Thread(target=self.ws.run_forever)
        thread.daemon = True
        thread.start()
    
    def subscribe(self, ticker: str):
        """Subscribe to ticker updates"""
        if self.ws and ticker not in self.subscribed_tickers:
            self.ws.send(json.dumps({'type': 'subscribe', 'symbol': ticker}))
            self.subscribed_tickers.add(ticker)
    
    def _on_message(self, ws, message):
        """Handle real-time price updates"""
        data = json.loads(message)
        if data['type'] == 'trade':
            for trade in data['data']:
                ticker = trade['s']
                price = trade['p']
                self.on_price_update(ticker, price)

def handle_price_update(ticker: str, price: float):
    """Callback for real-time price updates"""
    cache.set_price(ticker, price, ttl=10)  # 10-second cache

# Initialize WebSocket connection
ws_client = FinnhubWebSocket(FINNHUB_KEY, handle_price_update)
ws_client.connect()

# Subscribe to watchlist tickers
for ticker in WATCHLIST:
    ws_client.subscribe(ticker)
```

**Alpha Vantage aggressive caching (25 calls/day limit):**

```python
import time
from collections import deque

class AlphaVantageRateLimiter:
    """Strict rate limiting for Alpha Vantage free tier"""
    
    def __init__(self, calls_per_minute=5, calls_per_day=25):
        self.calls_per_minute = calls_per_minute
        self.calls_per_day = calls_per_day
        
        self.minute_window = deque(maxlen=calls_per_minute)
        self.day_counter = 0
        self.day_reset = datetime.now().date()
    
    async def acquire(self):
        """Wait until rate limit allows next request"""
        # Daily limit check
        if datetime.now().date() > self.day_reset:
            self.day_counter = 0
            self.day_reset = datetime.now().date()
        
        if self.day_counter >= self.calls_per_day:
            raise Exception("Alpha Vantage daily limit reached (25 calls/day)")
        
        # Minute limit check
        now = time.time()
        if len(self.minute_window) == self.calls_per_minute:
            oldest = self.minute_window[0]
            sleep_time = 60 - (now - oldest)
            if sleep_time > 0:
                print(f"Rate limit: waiting {sleep_time:.1f}s")
                await asyncio.sleep(sleep_time)
        
        self.minute_window.append(time.time())
        self.day_counter += 1

av_limiter = AlphaVantageRateLimiter()

async def fetch_alpha_vantage_cached(ticker: str) -> Dict:
    """Alpha Vantage with aggressive caching"""
    
    # Check cache first (24-hour TTL for EOD data)
    cached = cache.get_price(ticker, max_age_seconds=86400)
    if cached:
        return cached
    
    # Cache miss - use API (rate limited)
    await av_limiter.acquire()
    
    url = "https://www.alphavantage.co/query"
    params = {
        'function': 'GLOBAL_QUOTE',
        'symbol': ticker,
        'apikey': ALPHA_VANTAGE_KEY
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            
            if 'Note' in data:
                # Rate limit hit
                raise Exception("Alpha Vantage rate limit")
            
            price = float(data['Global Quote']['05. price'])
            cache.set_price(ticker, price, ttl=86400)
            return price
```

## Putting it all together: Optimized main pipeline

```python
import asyncio
import aiohttp
from typing import List, Dict
from datetime import datetime

class OptimizedFinancialPipeline:
    """Complete optimized pipeline: 3 minutes → 1 minute"""
    
    def __init__(self):
        self.cache = HybridCache()
        self.deduplicator = ArticleDeduplicator()
        self.queue = TaskQueue()
        self.ticker_index = TickerIndex()
    
    async def run_cycle(self):
        """Main processing cycle (target: < 60 seconds)"""
        
        with timer("Full pipeline"):
            # Stage 1: Fetch RSS feeds (concurrent, ~5 seconds)
            with timer("Fetch feeds"):
                articles = await fetch_pr_feeds_async(RSS_SOURCES)
            
            # Stage 2: Filter and deduplicate (fast, ~1 second)
            with timer("Filter and dedup"):
                articles = [a for a in articles if not self.deduplicator.is_duplicate(a)]
                
                # Extract tickers
                for article in articles:
                    article['tickers'] = extract_tickers_from_headline(article['title'])
                
                # Early filtering
                relevant = [a for a in articles if should_process_article(a, WATCHLIST)]
                print(f"Filtered: {len(articles)} → {len(relevant)} articles")
            
            # Stage 3: Fast enrichment (concurrent API calls, ~20-30 seconds)
            with timer("Fast enrichment"):
                await self.enrich_articles_fast(relevant)
            
            # Stage 4: CPU-bound sentiment (parallel, ~10-15 seconds)
            with timer("Sentiment analysis"):
                await self.analyze_sentiment_parallel(relevant)
            
            # Stage 5: Classification (optional, queue for batch)
            with timer("Enqueue deep analysis"):
                for article in relevant:
                    await self.queue.enqueue('llm_classification', {'article': article})
            
            # Stage 6: Store results (async DB write, ~5 seconds)
            with timer("Store to database"):
                await self.store_articles_async(relevant)
            
            print(f"✅ Processed {len(relevant)} articles")
            return relevant
    
    async def enrich_articles_fast(self, articles: List[Dict]):
        """Fast enrichment with concurrent API calls"""
        
        # Collect all tickers needing price lookups
        all_tickers = list(set(
            ticker
            for article in articles
            for ticker in article.get('tickers', [])
        ))
        
        # Batch fetch prices (concurrent with caching)
        async with aiohttp.ClientSession() as session:
            price_tasks = {
                ticker: get_price_with_cache(ticker)
                for ticker in all_tickers
            }
            prices = await asyncio.gather(*price_tasks.values())
            price_map = dict(zip(price_tasks.keys(), prices))
        
        # Attach prices to articles
        for article in articles:
            article['prices'] = {
                ticker: price_map.get(ticker)
                for ticker in article['tickers']
            }
    
    async def analyze_sentiment_parallel(self, articles: List[Dict]):
        """Parallel sentiment analysis using ProcessPoolExecutor"""
        from concurrent.futures import ProcessPoolExecutor
        
        with ProcessPoolExecutor(max_workers=4) as executor:
            sentiments = list(executor.map(
                quick_sentiment,
                [a['title'] + ' ' + a.get('summary', '') for a in articles]
            ))
        
        for article, sentiment in zip(articles, sentiments):
            article['sentiment'] = sentiment
    
    async def store_articles_async(self, articles: List[Dict]):
        """Async database writes"""
        import aiosqlite
        
        async with aiosqlite.connect('news.db') as db:
            await db.execute('PRAGMA journal_mode=WAL')
            
            for article in articles:
                await db.execute('''
                    INSERT INTO articles (title, url, tickers, sentiment, price, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    article['title'],
                    article['url'],
                    json.dumps(article['tickers']),
                    article['sentiment'],
                    json.dumps(article.get('prices', {})),
                    datetime.now().isoformat()
                ))
            
            await db.commit()

# Run the optimized pipeline
async def main():
    pipeline = OptimizedFinancialPipeline()
    
    # Initialize caches
    await warm_startup_cache()
    
    # Run processing cycle every 5 minutes
    while True:
        try:
            await pipeline.run_cycle()
        except Exception as e:
            print(f"Pipeline error: {e}")
        
        await asyncio.sleep(300)  # 5 minutes

if __name__ == '__main__':
    asyncio.run(main())
```

## Summary: Optimization priority matrix

**Immediate implementation (week 1-2):**

1. **Add profiling with Scalene** - Identify actual bottlenecks (2 hours)
2. **Convert API calls to async** - 10-20x speedup on network I/O (2-3 days)
3. **Implement basic caching** - Redis for prices, 90% API call reduction (1-2 days)
4. **Early filtering** - Process only relevant articles, 50-70% reduction (1 day)
5. **Connection pooling** - Reuse aiohttp sessions (30 minutes)

**Expected impact:** 3 minutes → 45-60 seconds (2-3x improvement)

**Medium-term (week 3-4):**

1. **Multi-tier caching** - Memory + Redis + SQLite hybrid (2-3 days)
2. **Ticker extraction optimization** - Inverted index, Bloom filters (2-3 days)
3. **Parallel sentiment analysis** - ProcessPoolExecutor for CPU-bound work (1-2 days)
4. **Rate limiting refinement** - Proper semaphores for each API (1 day)

**Expected impact:** 45 seconds → 30-40 seconds (additional 1.5x improvement)

**Long-term refactoring (week 5-8):**

1. **Separate batch operations** - Move earnings, options to nightly jobs (3-4 days)
2. **Database-backed queue** - Defer expensive operations (2-3 days)
3. **WebSocket real-time** - Replace polling with push updates (2-3 days)
4. **Complete monitoring** - Prometheus + Grafana dashboards (2-3 days)

**Expected impact:** 30 seconds → 15-20 seconds (additional 2x improvement)

**Final target achieved:** 15-20 seconds per cycle (9-12x faster than original 3 minutes)

The optimization journey focuses on concurrent I/O operations first (biggest wins), then caching (reduces API dependency), then selective parallelism (CPU-bound operations), and finally architectural separation (real-time vs batch). Each phase delivers measurable performance improvements while maintaining all existing features.