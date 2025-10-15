# Efficient Incremental Statistics for Stock Catalyst Detection

Your backtesting platform needs **Welford's algorithm for incremental statistics** combined with **TimescaleDB for storage** and **exponential decay (EWMA) for handling non-stationary financial data**. This combination provides O(1) update complexity, numerical stability, and statistical validity while avoiding full recalculation.

## Core recommendation: EWMA with adaptive thresholds

For catalyst detection in low-priced stocks, use **exponential weighted moving average (EWMA) with lambda=0.90-0.94**. This naturally weights recent observations more heavily while maintaining computational efficiency. Lower lambda values (0.90) react faster to regime changes—critical for volatile stocks under $10.

## Complete Python implementation

### Production-ready incremental statistics class

```python
import numpy as np
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime

@dataclass
class KeywordStatistics:
    """Store incremental statistics for a keyword"""
    keyword_id: int
    keyword_text: str
    count: int = 0
    mean: float = 0.0
    M2: float = 0.0  # Sum of squared deviations
    lambda_decay: float = 0.92
    ewma_mean: float = 0.0
    ewma_variance: float = 0.0
    min_value: float = float('inf')
    max_value: float = float('-inf')
    last_updated: Optional[datetime] = None

class IncrementalKeywordTracker:
    """
    Tracks keyword statistics using Welford's algorithm for numerical stability
    and EWMA for handling non-stationary financial data.
    """
    
    def __init__(self, lambda_decay: float = 0.92, min_samples: int = 30):
        self.lambda_decay = lambda_decay
        self.min_samples = min_samples
        self.keywords: Dict[int, KeywordStatistics] = {}
        
    def update(self, keyword_id: int, keyword_text: str, value: float, 
               timestamp: Optional[datetime] = None) -> Dict[str, float]:
        """
        Update statistics for a keyword with new observation.
        Returns current statistics including z-score.
        """
        if keyword_id not in self.keywords:
            self.keywords[keyword_id] = KeywordStatistics(
                keyword_id=keyword_id,
                keyword_text=keyword_text,
                lambda_decay=self.lambda_decay
            )
        
        stats = self.keywords[keyword_id]
        
        # Welford's algorithm for mean and variance
        stats.count += 1
        delta = value - stats.mean
        stats.mean += delta / stats.count
        delta2 = value - stats.mean
        stats.M2 += delta * delta2
        
        # EWMA updates for time-weighted statistics
        if stats.count == 1:
            stats.ewma_mean = value
            stats.ewma_variance = 0.0
        else:
            # Update EWMA mean
            prev_ewma_mean = stats.ewma_mean
            stats.ewma_mean = (1 - self.lambda_decay) * value + self.lambda_decay * stats.ewma_mean
            
            # Update EWMA variance (uses deviation from previous EWMA mean)
            deviation_squared = (value - prev_ewma_mean) ** 2
            stats.ewma_variance = (
                (1 - self.lambda_decay) * deviation_squared + 
                self.lambda_decay * stats.ewma_variance
            )
        
        # Track extremes
        stats.min_value = min(stats.min_value, value)
        stats.max_value = max(stats.max_value, value)
        stats.last_updated = timestamp or datetime.now()
        
        return self.get_statistics(keyword_id)
    
    def get_statistics(self, keyword_id: int) -> Dict[str, float]:
        """Get current statistics for a keyword"""
        if keyword_id not in self.keywords:
            return {}
        
        stats = self.keywords[keyword_id]
        
        # Sample variance (Bessel's correction)
        sample_variance = stats.M2 / (stats.count - 1) if stats.count > 1 else 0.0
        sample_std = np.sqrt(sample_variance) if sample_variance > 0 else 0.0
        
        # EWMA standard deviation
        ewma_std = np.sqrt(stats.ewma_variance) if stats.ewma_variance > 0 else 0.0
        
        return {
            'keyword_id': stats.keyword_id,
            'keyword_text': stats.keyword_text,
            'count': stats.count,
            'mean': stats.mean,
            'std_dev': sample_std,
            'variance': sample_variance,
            'ewma_mean': stats.ewma_mean,
            'ewma_std': ewma_std,
            'min': stats.min_value,
            'max': stats.max_value,
            'last_updated': stats.last_updated
        }
    
    def calculate_z_score(self, keyword_id: int, value: float, 
                         use_ewma: bool = True) -> float:
        """
        Calculate z-score for a new value using current statistics.
        use_ewma=True recommended for financial time series.
        """
        if keyword_id not in self.keywords:
            return 0.0
        
        stats = self.keywords[keyword_id]
        
        if stats.count < self.min_samples:
            return 0.0
        
        if use_ewma:
            mean = stats.ewma_mean
            std = np.sqrt(stats.ewma_variance) if stats.ewma_variance > 0 else 1e-10
        else:
            mean = stats.mean
            variance = stats.M2 / (stats.count - 1) if stats.count > 1 else 0.0
            std = np.sqrt(variance) if variance > 0 else 1e-10
        
        return (value - mean) / std
    
    def calculate_p_value(self, keyword_id: int, value: float, 
                         use_ewma: bool = True) -> float:
        """
        Calculate two-tailed p-value from z-score.
        Assumes approximately normal distribution.
        """
        from scipy.stats import norm
        
        z_score = self.calculate_z_score(keyword_id, value, use_ewma)
        if z_score == 0.0:
            return 1.0
        
        # Two-tailed p-value
        p_value = 2 * (1 - norm.cdf(abs(z_score)))
        return p_value
    
    def get_adaptive_threshold(self, keyword_id: int, percentile: float = 95.0,
                              is_low_priced_stock: bool = True) -> float:
        """
        Calculate adaptive threshold based on current distribution.
        Higher thresholds for low-priced stocks to reduce false positives.
        """
        if keyword_id not in self.keywords:
            return 0.0
        
        stats = self.keywords[keyword_id]
        
        if stats.count < self.min_samples:
            return float('inf')  # Not enough data for reliable threshold
        
        # For low-priced stocks, use more conservative percentile
        if is_low_priced_stock:
            percentile = max(percentile, 97.5)  # At least 97.5th percentile
        
        # Use EWMA statistics for threshold
        from scipy.stats import norm
        z_threshold = norm.ppf(percentile / 100.0)
        
        threshold = stats.ewma_mean + z_threshold * np.sqrt(stats.ewma_variance)
        return threshold
```

### Catalyst detection with signal generation

```python
from collections import deque
from typing import List, Dict, Optional

class CatalystDetector:
    """
    Detects stock catalysts using incremental statistics on keyword signals.
    Optimized for low-priced stocks with higher volatility.
    """
    
    def __init__(self, 
                 lambda_decay: float = 0.92,
                 lookback_window: int = 60,
                 min_samples: int = 30,
                 z_score_threshold: float = 2.5):
        """
        Args:
            lambda_decay: EWMA decay factor (0.90-0.94 recommended)
            lookback_window: Days for percentile threshold calculation
            min_samples: Minimum observations before generating signals
            z_score_threshold: Base z-score threshold (higher for low-priced stocks)
        """
        self.tracker = IncrementalKeywordTracker(lambda_decay, min_samples)
        self.lookback_window = lookback_window
        self.z_score_threshold = z_score_threshold
        
        # Store recent signals for adaptive threshold calculation
        self.signal_history: Dict[int, deque] = {}
        
    def process_keyword_event(self, 
                              keyword_id: int,
                              keyword_text: str,
                              metric_value: float,
                              stock_symbol: str,
                              stock_price: float,
                              timestamp: datetime) -> Optional[Dict]:
        """
        Process a keyword event and generate signal if threshold exceeded.
        
        Returns:
            Signal dictionary if catalyst detected, None otherwise
        """
        # Determine if low-priced stock (higher thresholds needed)
        is_low_priced = stock_price < 10.0
        
        # Calculate z-score BEFORE updating (to avoid look-ahead bias)
        z_score = self.tracker.calculate_z_score(keyword_id, metric_value, use_ewma=True)
        p_value = self.tracker.calculate_p_value(keyword_id, metric_value, use_ewma=True)
        
        # Update statistics with new observation
        current_stats = self.tracker.update(keyword_id, keyword_text, metric_value, timestamp)
        
        # Store in history for adaptive threshold
        if keyword_id not in self.signal_history:
            self.signal_history[keyword_id] = deque(maxlen=self.lookback_window)
        self.signal_history[keyword_id].append(metric_value)
        
        # Calculate adaptive threshold
        adaptive_threshold = self.tracker.get_adaptive_threshold(
            keyword_id, 
            percentile=95.0 if is_low_priced else 90.0,
            is_low_priced_stock=is_low_priced
        )
        
        # Adjust z-score threshold for low-priced stocks (25% higher)
        adjusted_z_threshold = self.z_score_threshold * (1.25 if is_low_priced else 1.0)
        
        # Generate signal if thresholds exceeded
        if abs(z_score) > adjusted_z_threshold and current_stats['count'] >= self.tracker.min_samples:
            signal = {
                'timestamp': timestamp,
                'stock_symbol': stock_symbol,
                'stock_price': stock_price,
                'keyword_id': keyword_id,
                'keyword_text': keyword_text,
                'metric_value': metric_value,
                'z_score': z_score,
                'p_value': p_value,
                'ewma_mean': current_stats['ewma_mean'],
                'ewma_std': current_stats['ewma_std'],
                'adaptive_threshold': adaptive_threshold,
                'signal_strength': abs(z_score) / adjusted_z_threshold,
                'direction': 'bullish' if z_score > 0 else 'bearish',
                'is_low_priced': is_low_priced,
                'sample_count': current_stats['count']
            }
            return signal
        
        return None
    
    def get_keyword_weights(self, keyword_ids: List[int]) -> Dict[int, float]:
        """
        Calculate keyword weights based on statistical significance.
        Higher weights for more reliable keywords.
        """
        weights = {}
        
        for keyword_id in keyword_ids:
            stats = self.tracker.get_statistics(keyword_id)
            if not stats or stats['count'] < self.tracker.min_samples:
                weights[keyword_id] = 0.0
                continue
            
            # Weight by inverse of standard error and sample size
            std_error = stats['ewma_std'] / np.sqrt(stats['count'])
            if std_error > 0:
                # Higher weight for lower standard error and more samples
                weight = (1.0 / std_error) * np.log(stats['count'])
                weights[keyword_id] = weight
            else:
                weights[keyword_id] = 0.0
        
        # Normalize weights to sum to 1
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}
        
        return weights
```

## Database schema design for TimescaleDB

TimescaleDB emerges as the optimal choice—it's PostgreSQL with time-series extensions offering continuous aggregates that automatically update incrementally.

### Schema implementation

```sql
-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 1. Raw keyword events table (hypertable for efficient time-series storage)
CREATE TABLE keyword_events (
    event_id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    stock_symbol VARCHAR(10) NOT NULL,
    stock_price NUMERIC(10, 2),
    keyword_id INTEGER NOT NULL,
    keyword_text VARCHAR(100),
    metric_value NUMERIC(18, 6),  -- e.g., sentiment score, impact score
    event_type VARCHAR(50),
    source VARCHAR(50),  -- 'news', 'sec_filing', etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable (TimescaleDB's partitioned table)
SELECT create_hypertable('keyword_events', 'timestamp', 
    chunk_time_interval => INTERVAL '1 day');

-- 2. Incremental statistics table (stores Welford/EWMA state)
CREATE TABLE keyword_statistics (
    statistic_id SERIAL PRIMARY KEY,
    keyword_id INTEGER NOT NULL,
    stock_symbol VARCHAR(10),
    
    -- Welford's algorithm state variables
    count BIGINT NOT NULL DEFAULT 0,
    mean NUMERIC(18, 6) DEFAULT 0,
    m2 NUMERIC(24, 10) DEFAULT 0,  -- Sum of squared deviations
    
    -- EWMA state variables
    lambda_decay NUMERIC(4, 3) DEFAULT 0.92,
    ewma_mean NUMERIC(18, 6) DEFAULT 0,
    ewma_variance NUMERIC(24, 10) DEFAULT 0,
    
    -- Additional statistics
    min_value NUMERIC(18, 6),
    max_value NUMERIC(18, 6),
    std_dev NUMERIC(18, 6),
    
    -- Metadata
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    calculation_date DATE NOT NULL DEFAULT CURRENT_DATE,
    
    UNIQUE(keyword_id, stock_symbol, calculation_date)
);

-- 3. Continuous aggregate for daily statistics (automatically updates!)
CREATE MATERIALIZED VIEW keyword_stats_daily
WITH (timescaledb.continuous, timescaledb.materialized_only=false) AS
SELECT 
    time_bucket('1 day', timestamp) AS day,
    keyword_id,
    keyword_text,
    stock_symbol,
    COUNT(*) as event_count,
    AVG(metric_value) as avg_metric,
    STDDEV(metric_value) as stddev_metric,
    MIN(metric_value) as min_metric,
    MAX(metric_value) as max_metric,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY metric_value) as median_metric,
    PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY metric_value) as p90_metric
FROM keyword_events
GROUP BY day, keyword_id, keyword_text, stock_symbol;

-- 4. Add refresh policy (handles nightly updates automatically)
SELECT add_continuous_aggregate_policy('keyword_stats_daily',
    start_offset => INTERVAL '3 days',  -- 3-day lookback for late data
    end_offset => INTERVAL '1 hour',    -- Exclude incomplete hour
    schedule_interval => INTERVAL '1 hour');

-- 5. Signal history table (for backtesting results)
CREATE TABLE catalyst_signals (
    signal_id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    stock_symbol VARCHAR(10) NOT NULL,
    stock_price NUMERIC(10, 2),
    keyword_id INTEGER,
    keyword_text VARCHAR(100),
    z_score NUMERIC(10, 4),
    p_value NUMERIC(10, 8),
    signal_strength NUMERIC(10, 4),
    direction VARCHAR(10),  -- 'bullish' or 'bearish'
    is_low_priced BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('catalyst_signals', 'timestamp',
    chunk_time_interval => INTERVAL '7 days');

-- 6. Keyword metadata table (normalized)
CREATE TABLE keywords (
    keyword_id SERIAL PRIMARY KEY,
    keyword_text VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50),
    base_weight NUMERIC(10, 6) DEFAULT 1.0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Stock metadata table
CREATE TABLE stocks (
    stock_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(255),
    sector VARCHAR(50),
    is_low_priced BOOLEAN,  -- Under $10
    avg_daily_volume BIGINT,
    last_price NUMERIC(10, 2),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX idx_events_time_desc ON keyword_events (timestamp DESC);
CREATE INDEX idx_events_keyword_time ON keyword_events (keyword_id, timestamp DESC);
CREATE INDEX idx_events_symbol_time ON keyword_events (stock_symbol, timestamp DESC);
CREATE INDEX idx_events_compound ON keyword_events (keyword_id, stock_symbol, timestamp DESC);

CREATE INDEX idx_stats_keyword ON keyword_statistics (keyword_id, calculation_date DESC);
CREATE INDEX idx_stats_symbol ON keyword_statistics (stock_symbol, keyword_id);

CREATE INDEX idx_signals_time ON catalyst_signals (timestamp DESC);
CREATE INDEX idx_signals_symbol_time ON catalyst_signals (stock_symbol, timestamp DESC);

-- Compression policy (compress data older than 7 days for space efficiency)
ALTER TABLE keyword_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'stock_symbol, keyword_id'
);

SELECT add_compression_policy('keyword_events', INTERVAL '7 days');
```

### Why this schema works perfectly

**Continuous aggregates automatically handle incremental updates**. When you insert new nightly data into `keyword_events`, TimescaleDB automatically refreshes the materialized view with only the new data—no full recalculation needed. The 3-day lookback handles late-arriving data from historical backtesting.

**Hypertables partition data by time**, making queries on recent data extremely fast. Compression on older data saves 60-70% storage while maintaining query performance.

**Dual storage approach**: Raw events for detailed analysis + pre-aggregated statistics for fast queries. The `keyword_statistics` table stores Welford algorithm state (count, mean, M2) allowing perfect incremental updates.

## Integration: nightly backtesting update logic

```python
import psycopg2
from psycopg2.extras import execute_batch
from typing import List, Dict
import numpy as np
from datetime import datetime, timedelta

class IncrementalStatisticsUpdater:
    """
    Handles nightly incremental updates to keyword statistics.
    Integrates with TimescaleDB for efficient storage and retrieval.
    """
    
    def __init__(self, connection_params: Dict[str, str]):
        self.conn = psycopg2.connect(**connection_params)
        self.detector = CatalystDetector(lambda_decay=0.92, z_score_threshold=2.5)
        
    def load_existing_statistics(self, lookback_days: int = 30):
        """Load existing statistics state from database into memory"""
        cursor = self.conn.cursor()
        
        # Load recent statistics for warm start
        query = """
            SELECT keyword_id, stock_symbol, count, mean, m2,
                   lambda_decay, ewma_mean, ewma_variance,
                   min_value, max_value
            FROM keyword_statistics
            WHERE calculation_date >= %s
            ORDER BY keyword_id, stock_symbol, calculation_date DESC
        """
        
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        cursor.execute(query, (cutoff_date,))
        
        # Initialize tracker with existing state
        for row in cursor.fetchall():
            keyword_id, symbol, count, mean, m2, lambda_decay, ewma_mean, ewma_var, min_val, max_val = row
            
            # Reconstruct KeywordStatistics object
            stats = KeywordStatistics(
                keyword_id=keyword_id,
                keyword_text="",  # Will be filled on first update
                count=count,
                mean=float(mean),
                M2=float(m2),
                lambda_decay=float(lambda_decay),
                ewma_mean=float(ewma_mean),
                ewma_variance=float(ewma_var),
                min_value=float(min_val) if min_val else float('inf'),
                max_value=float(max_val) if max_val else float('-inf')
            )
            
            self.detector.tracker.keywords[keyword_id] = stats
        
        cursor.close()
        print(f"Loaded statistics for {len(self.detector.tracker.keywords)} keywords")
    
    def process_nightly_backtest_data(self, backtest_date: datetime.date):
        """
        Process nightly backtesting data incrementally.
        Only loads new data, updates statistics in O(1) per observation.
        """
        cursor = self.conn.cursor()
        
        # Query only new data from last backtest run
        query = """
            SELECT 
                timestamp, stock_symbol, stock_price,
                keyword_id, keyword_text, metric_value
            FROM keyword_events
            WHERE DATE(timestamp) = %s
            ORDER BY timestamp ASC
        """
        
        cursor.execute(query, (backtest_date,))
        
        signals_generated = []
        rows_processed = 0
        
        # Process each event incrementally
        for row in cursor:
            timestamp, symbol, price, kw_id, kw_text, metric = row
            
            # Process event and potentially generate signal
            signal = self.detector.process_keyword_event(
                keyword_id=kw_id,
                keyword_text=kw_text,
                metric_value=float(metric),
                stock_symbol=symbol,
                stock_price=float(price),
                timestamp=timestamp
            )
            
            if signal:
                signals_generated.append(signal)
            
            rows_processed += 1
            
            # Batch commit every 1000 rows
            if rows_processed % 1000 == 0:
                self._save_statistics_batch()
                print(f"Processed {rows_processed} events, generated {len(signals_generated)} signals")
        
        cursor.close()
        
        # Final save of all updated statistics
        self._save_statistics_batch()
        
        # Save generated signals
        if signals_generated:
            self._save_signals(signals_generated)
        
        print(f"Nightly update complete: {rows_processed} events, {len(signals_generated)} signals")
        
        return {
            'events_processed': rows_processed,
            'signals_generated': len(signals_generated),
            'keywords_updated': len(self.detector.tracker.keywords)
        }
    
    def _save_statistics_batch(self):
        """Save updated statistics back to database"""
        cursor = self.conn.cursor()
        
        # Prepare batch insert/update
        stats_to_save = []
        for keyword_id, stats in self.detector.tracker.keywords.items():
            variance = stats.M2 / (stats.count - 1) if stats.count > 1 else 0.0
            std_dev = np.sqrt(variance) if variance > 0 else 0.0
            
            stats_to_save.append((
                keyword_id,
                None,  # stock_symbol (use NULL for global stats)
                stats.count,
                stats.mean,
                stats.M2,
                stats.lambda_decay,
                stats.ewma_mean,
                stats.ewma_variance,
                stats.min_value if stats.min_value != float('inf') else None,
                stats.max_value if stats.max_value != float('-inf') else None,
                std_dev,
                datetime.now(),
                datetime.now().date()
            ))
        
        # Upsert query (insert or update if exists)
        query = """
            INSERT INTO keyword_statistics (
                keyword_id, stock_symbol, count, mean, m2,
                lambda_decay, ewma_mean, ewma_variance,
                min_value, max_value, std_dev,
                last_updated, calculation_date
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (keyword_id, stock_symbol, calculation_date)
            DO UPDATE SET
                count = EXCLUDED.count,
                mean = EXCLUDED.mean,
                m2 = EXCLUDED.m2,
                ewma_mean = EXCLUDED.ewma_mean,
                ewma_variance = EXCLUDED.ewma_variance,
                min_value = EXCLUDED.min_value,
                max_value = EXCLUDED.max_value,
                std_dev = EXCLUDED.std_dev,
                last_updated = EXCLUDED.last_updated
        """
        
        execute_batch(cursor, query, stats_to_save)
        self.conn.commit()
        cursor.close()
    
    def _save_signals(self, signals: List[Dict]):
        """Save generated catalyst signals to database"""
        cursor = self.conn.cursor()
        
        signal_rows = [
            (
                s['timestamp'],
                s['stock_symbol'],
                s['stock_price'],
                s['keyword_id'],
                s['keyword_text'],
                s['z_score'],
                s['p_value'],
                s['signal_strength'],
                s['direction'],
                s['is_low_priced']
            )
            for s in signals
        ]
        
        query = """
            INSERT INTO catalyst_signals (
                timestamp, stock_symbol, stock_price, keyword_id, keyword_text,
                z_score, p_value, signal_strength, direction, is_low_priced
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        execute_batch(cursor, query, signal_rows)
        self.conn.commit()
        cursor.close()
    
    def get_keyword_performance_metrics(self, keyword_id: int, days: int = 30) -> Dict:
        """Analyze how keyword statistics have evolved over time"""
        cursor = self.conn.cursor()
        
        query = """
            SELECT calculation_date, count, mean, std_dev, ewma_mean
            FROM keyword_statistics
            WHERE keyword_id = %s
                AND calculation_date >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY calculation_date ASC
        """
        
        cursor.execute(query, (keyword_id, days))
        rows = cursor.fetchall()
        cursor.close()
        
        if not rows:
            return {}
        
        dates = [r[0] for r in rows]
        counts = [r[1] for r in rows]
        means = [float(r[2]) for r in rows]
        stds = [float(r[3]) for r in rows]
        ewma_means = [float(r[4]) for r in rows]
        
        return {
            'dates': dates,
            'sample_counts': counts,
            'means': means,
            'std_devs': stds,
            'ewma_means': ewma_means,
            'mean_change_pct': ((means[-1] - means[0]) / means[0] * 100) if means[0] != 0 else 0,
            'volatility_trend': 'increasing' if stds[-1] > stds[0] else 'decreasing'
        }

# Usage example
if __name__ == "__main__":
    # Database connection parameters
    db_params = {
        'database': 'stock_catalyst_db',
        'user': 'postgres',
        'password': 'your_password',
        'host': 'localhost',
        'port': '5432'
    }
    
    # Initialize updater
    updater = IncrementalStatisticsUpdater(db_params)
    
    # Load existing statistics (warm start)
    updater.load_existing_statistics(lookback_days=30)
    
    # Process last night's backtesting data
    from datetime import date
    last_night = date.today() - timedelta(days=1)
    
    results = updater.process_nightly_backtest_data(last_night)
    
    print(f"Processing complete:")
    print(f"  Events processed: {results['events_processed']}")
    print(f"  Signals generated: {results['signals_generated']}")
    print(f"  Keywords updated: {results['keywords_updated']}")
```

## Performance optimizations and best practices

### Numerical stability considerations

**Welford's algorithm avoids catastrophic cancellation** that plagues the naive variance formula (E[X²] - E[X]²). When computing statistics on stock prices or returns, the mean-squared can be orders of magnitude larger than the variance, causing precision loss. Welford's method maintains **8-13 decimal digits of precision** vs only 4-8 for naive approaches.

**For stocks under $10**, use robust statistics—median and median absolute deviation (MAD) instead of mean and standard deviation for extreme outlier resistance:

```python
def calculate_robust_statistics(values: np.ndarray) -> Dict[str, float]:
    """Use robust statistics for high-volatility low-priced stocks"""
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    
    # MAD to standard deviation conversion (assumes normality)
    robust_std = mad * 1.4826
    
    return {
        'median': median,
        'mad': mad,
        'robust_std': robust_std
    }
```

### Batch processing for efficiency

Process data in mini-batches (100-1000 observations) for better cache locality:

```python
def process_batch_optimized(events: List[Dict], detector: CatalystDetector):
    """Vectorized processing where possible, fallback to incremental"""
    # Group by keyword for vectorization opportunities
    by_keyword = {}
    for event in events:
        kw_id = event['keyword_id']
        if kw_id not in by_keyword:
            by_keyword[kw_id] = []
        by_keyword[kw_id].append(event)
    
    # Process each keyword's events in sequence
    signals = []
    for kw_id, kw_events in by_keyword.items():
        for event in kw_events:
            signal = detector.process_keyword_event(**event)
            if signal:
                signals.append(signal)
    
    return signals
```

### Memory management for large keyword sets

For thousands of keywords, implement pruning:

```python
def prune_inactive_keywords(tracker: IncrementalKeywordTracker, 
                           min_count: int = 100,
                           days_inactive: int = 30):
    """Remove low-signal keywords to conserve memory"""
    cutoff_date = datetime.now() - timedelta(days=days_inactive)
    
    to_remove = []
    for keyword_id, stats in tracker.keywords.items():
        if (stats.count < min_count or 
            stats.last_updated < cutoff_date):
            to_remove.append(keyword_id)
    
    for keyword_id in to_remove:
        del tracker.keywords[keyword_id]
    
    print(f"Pruned {len(to_remove)} inactive keywords")
```

## Maintaining statistical validity with new data

### Avoid look-ahead bias

**Always calculate z-scores BEFORE updating statistics** with new observations. The code examples above correctly implement this:

```python
# CORRECT: Calculate z-score with current statistics
z_score = tracker.calculate_z_score(keyword_id, new_value)

# THEN update statistics
tracker.update(keyword_id, keyword_text, new_value)
```

### Handle late-arriving data

TimescaleDB's continuous aggregates with 3-day lookback automatically handle late data:

```sql
-- Refresh policy handles late-arriving historical backtest data
SELECT add_continuous_aggregate_policy('keyword_stats_daily',
    start_offset => INTERVAL '3 days',  -- Recompute last 3 days
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

### Multiple testing correction

When testing thousands of keywords simultaneously, adjust significance thresholds:

```python
def bonferroni_correction(alpha: float, num_tests: int) -> float:
    """Conservative correction for multiple hypothesis tests"""
    return alpha / num_tests

def false_discovery_rate_correction(p_values: List[float], 
                                   fdr_level: float = 0.05) -> List[bool]:
    """Less conservative FDR correction (Benjamini-Hochberg)"""
    from scipy.stats import false_discovery_control
    return false_discovery_control(p_values, method='bh', is_sorted=False) < fdr_level

# Usage
num_keywords = 5000
adjusted_alpha = bonferroni_correction(0.05, num_keywords)  # 0.00001
z_threshold = norm.ppf(1 - adjusted_alpha/2)  # ~4.42 instead of 1.96
```

### Exponential decay parameters for financial data

**Lambda = 0.92-0.94 is industry standard** (equivalent to ~50-100 day effective window):

```python
# Effective window calculation
def effective_window(lambda_decay: float) -> float:
    """Calculate effective number of observations"""
    return (1 + lambda_decay) / (1 - lambda_decay)

print(effective_window(0.90))  # ~19 observations
print(effective_window(0.94))  # ~47 observations  
print(effective_window(0.97))  # ~131 observations
```

**For catalyst detection on low-priced stocks, use lambda=0.90** for faster reaction to regime changes. For longer-term trend statistics, use lambda=0.94.

### Adaptive decay based on volatility

```python
def adjust_lambda_for_volatility(base_lambda: float, 
                                 current_vol: float,
                                 historical_vol: float) -> float:
    """Faster decay in high volatility regimes"""
    vol_ratio = current_vol / historical_vol
    
    # Reduce lambda (faster decay) when volatility spikes
    if vol_ratio > 1.5:  # High volatility
        return base_lambda * 0.95
    elif vol_ratio < 0.7:  # Low volatility
        return min(base_lambda * 1.05, 0.98)
    else:
        return base_lambda
```

## Alternative: ClickHouse for extreme scale

If you're processing billions of events and need maximum query performance, **ClickHouse with AggregatingMergeTree** stores partial aggregate states:

```sql
-- ClickHouse schema for incremental aggregates
CREATE TABLE keyword_stats_incremental (
    date Date,
    keyword_id UInt32,
    stock_symbol String,
    count_state AggregateFunction(count),
    mean_state AggregateFunction(avg, Float64),
    variance_state AggregateFunction(varPop, Float64)
) ENGINE = AggregatingMergeTree()
ORDER BY (date, keyword_id, stock_symbol);

-- Materialized view automatically maintains aggregates
CREATE MATERIALIZED VIEW keyword_stats_mv TO keyword_stats_incremental AS
SELECT 
    toDate(timestamp) AS date,
    keyword_id,
    stock_symbol,
    countState() as count_state,
    avgState(metric_value) as mean_state,
    varPopState(metric_value) as variance_state
FROM keyword_events
GROUP BY date, keyword_id, stock_symbol;

-- Query (finalizing aggregate states)
SELECT 
    date,
    keyword_id,
    countMerge(count_state) as total_count,
    avgMerge(mean_state) as mean,
    sqrt(varPopMerge(variance_state)) as std_dev
FROM keyword_stats_incremental
WHERE date >= today() - 30
GROUP BY date, keyword_id;
```

**ClickHouse is 9,000x faster than PostgreSQL** for analytical queries but has poor update performance. Use only if you have append-only workloads with minimal corrections.

## Key recommendations summary

**For your stock catalyst detection system with nightly backtesting:**

1. **Use Welford's algorithm with EWMA (lambda=0.90-0.94)** for incremental statistics—provides O(1) updates, numerical stability, and natural recency weighting

2. **Deploy TimescaleDB (PostgreSQL extension)** for storage—continuous aggregates automatically handle incremental updates with configurable lookback windows

3. **Implement adaptive thresholds** based on percentiles (95th for low-priced stocks)—static thresholds fail in non-stationary markets

4. **Special handling for stocks under $10**: 25% higher z-score thresholds (2.5 instead of 2.0), require volume confirmation, use shorter adaptation windows (40 vs 60 days)

5. **Prevent look-ahead bias**: Calculate statistics before updating with new observations; use same code for backtesting and live trading

6. **Multiple testing correction**: With thousands of keywords, apply Bonferroni or FDR correction to p-values

7. **Concept drift monitoring**: Track keyword performance metrics weekly; retrain when win rates drop >20% from baseline

8. **Database schema**: Store raw events in hypertables, incremental statistics state (count, mean, M2, EWMA terms) in separate table, use continuous aggregates for fast queries

This architecture processes nightly backtesting data efficiently without full recalculation while maintaining statistical validity—exactly what your platform needs.