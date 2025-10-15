# Missed Opportunities Analyzer (MOA) - Design V2
## Enhanced with Institutional-Grade Backtesting Methodologies

**Version:** 2.0
**Date:** 2025-10-10
**Status:** Ready for Implementation

---

## Executive Summary

The Missed Opportunities Analyzer (MOA) V2 combines the original "learn from rejections" approach with institutional-grade backtesting methodologies used by quantitative hedge funds. This system doesn't just identify missed trades—it provides **statistically validated, walk-forward tested, bootstrap-confirmed insights** that accelerate your path to profitable trading.

### What's New in V2

**Institutional Methodologies Added:**
- ✅ **Walk-Forward Optimization** - Rolling 12-18 month training windows with 3-6 month out-of-sample validation
- ✅ **Combinatorial Purged Cross-Validation** - Superior to simple train/test splits, addresses information leakage
- ✅ **Bootstrap Validation** - 10,000 iteration confidence intervals without parametric assumptions
- ✅ **Multi-Metric Scoring** - F1 Score, Sortino, Calmar, Omega, Information Coefficient (not just Sharpe)
- ✅ **ROC-AUC Analysis** - Threshold-independent signal quality assessment
- ✅ **Parameter Sensitivity Testing** - Distinguish robust strategies from overfit noise
- ✅ **VectorBT Integration** - 1000x speedup for parameter optimization
- ✅ **Realistic Transaction Costs** - 6-8% round-trip modeling for stocks under $10

**Expected Impact (Enhanced):**
- 30-40% reduction in false negatives (up from 30%)
- 20-25% Sharpe improvement (up from 15%)
- **Statistical confidence**: 95%+ probability of genuine edge
- **Deployment-ready**: Minimum 385 trades validation before live trading
- 20-30 new keywords discovered (validated with p<0.05)

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Phase 0: Historical Backtesting Infrastructure](#phase-0-historical-backtesting-infrastructure)
3. [Data Capture & Storage](#data-capture--storage)
4. [Analysis Engine](#analysis-engine)
5. [Statistical Validation Framework](#statistical-validation-framework)
6. [Recommendation Engine](#recommendation-engine)
7. [Learning Loop with Rollback](#learning-loop-with-rollback)
8. [Implementation Roadmap](#implementation-roadmap)
9. [Success Metrics & KPIs](#success-metrics--kpis)
10. [Code Examples](#code-examples)
11. [Risk Mitigation](#risk-mitigation)
12. [Appendices](#appendices)

---

## System Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Catalyst Bot Main Loop                       │
│              (Processes ~330 items/cycle)                        │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ├─────────────────┬─────────────────┐
                 ▼                 ▼                 ▼
          ┌──────────┐      ┌──────────┐    ┌─────────────┐
          │ Passed   │      │ Filtered │    │  Filtered   │
          │ (0-6)    │      │ (Low     │    │  (High      │
          │          │      │  Score)  │    │  Price)     │
          └────┬─────┘      └────┬─────┘    └──────┬──────┘
               │                 │                  │
               │                 └──────────────────┘
               │                          │
               ▼                          ▼
        ┌─────────────┐          ┌──────────────────────┐
        │ events.jsonl│          │  rejected_items.jsonl │
        │ (existing)  │          │  + SQLite Database    │
        └─────────────┘          └──────────┬────────────┘
                                            │
                                            ▼
                                 ┌──────────────────────┐
                                 │  MOA Nightly         │
                                 │  @ 2:00 AM UTC       │
                                 └──────────┬────────────┘
                                            │
                        ┌───────────────────┼───────────────────┐
                        │                   │                   │
                        ▼                   ▼                   ▼
                  ┌──────────┐       ┌──────────┐       ┌──────────┐
                  │Walk-Fwd  │       │ Keyword  │       │Parameter │
                  │Backtest  │       │Discovery │       │Optimizer │
                  └────┬─────┘       └────┬─────┘       └────┬─────┘
                       │                  │                   │
                       │    ┌─────────────┴─────────────┐     │
                       │    │                           │     │
                       ▼    ▼                           ▼     ▼
                  ┌──────────────────────────────────────────────┐
                  │         Statistical Validation Layer         │
                  │  • Bootstrap (10k iterations)                │
                  │  • Combinatorial Purged CV                   │
                  │  • ROC-AUC Analysis                          │
                  │  • Parameter Sensitivity                     │
                  │  • Information Coefficient                   │
                  └──────────────────┬───────────────────────────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │  Discord    │
                              │  Report +   │
                              │  Approval   │
                              └─────────────┘
```

### Technology Stack

**Core Components:**
- **Python 3.10+** - Primary language
- **PostgreSQL + TimescaleDB** - Time-series database for backtests
- **SQLite** - Lightweight storage for daily operations
- **VectorBT** - Vectorized backtesting (1000x speedup)
- **Backtrader** - Production deployment framework
- **scikit-learn** - TF-IDF, statistical tests
- **scipy** - Statistical validation (binomial tests, bootstrap)
- **yfinance** - Free price data (5-minute to daily bars)
- **spaCy** - Named Entity Recognition (future)

**Infrastructure:**
- **Disk Space:** ~1GB/month (logs + database)
- **Memory:** +200MB (VectorBT matrix operations)
- **API Calls:** yfinance free tier (no rate limits for historical)
- **Budget:** $0 additional cost

---

## Phase 0: Historical Backtesting Infrastructure

**⚠️ CRITICAL: Build this FIRST before implementing MOA**

### Why Phase 0 Matters

MOA learns from rejected trades, but without a robust backtesting foundation, you can't validate whether those learnings are genuine or noise. Phase 0 establishes the infrastructure to:

1. Store every backtest execution permanently
2. Validate strategies with walk-forward optimization
3. Calculate multi-metric performance scores
4. Generate confidence intervals via bootstrap
5. Test parameter robustness

### Database Schema

```sql
-- Backtest metadata
CREATE TABLE backtests (
    backtest_id BIGSERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(20),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    backtest_type VARCHAR(50), -- 'in_sample', 'out_of_sample', 'walk_forward'
    notes TEXT,
    CONSTRAINT chk_date_order CHECK (end_date >= start_date)
);

-- Strategy parameters
CREATE TABLE backtest_parameters (
    param_id BIGSERIAL PRIMARY KEY,
    backtest_id BIGINT REFERENCES backtests(backtest_id) ON DELETE CASCADE,
    param_name VARCHAR(100) NOT NULL,
    param_value TEXT NOT NULL,
    param_type VARCHAR(20) -- 'int', 'float', 'string', 'bool'
);

-- Performance metrics (institutional-grade)
CREATE TABLE backtest_results (
    result_id BIGSERIAL PRIMARY KEY,
    backtest_id BIGINT REFERENCES backtests(backtest_id) ON DELETE CASCADE,

    -- Returns
    total_return DECIMAL(10,4),
    annual_return DECIMAL(10,4),
    cumulative_return DECIMAL(10,4),

    -- Risk-adjusted metrics
    sharpe_ratio DECIMAL(10,4),
    sortino_ratio DECIMAL(10,4),
    calmar_ratio DECIMAL(10,4),
    omega_ratio DECIMAL(10,4),
    information_coefficient DECIMAL(10,4),

    -- Risk metrics
    max_drawdown DECIMAL(10,4),
    avg_drawdown DECIMAL(10,4),
    max_drawdown_duration_days INT,
    volatility DECIMAL(10,4),
    downside_deviation DECIMAL(10,4),

    -- Trade statistics
    num_trades INT,
    win_rate DECIMAL(10,4),
    loss_rate DECIMAL(10,4),
    avg_win DECIMAL(10,4),
    avg_loss DECIMAL(10,4),
    avg_win_loss_ratio DECIMAL(10,4),
    avg_hold_hours DECIMAL(10,2),

    -- Advanced metrics
    profit_factor DECIMAL(10,4),
    expectancy DECIMAL(10,4),
    f1_score DECIMAL(10,4),
    precision_score DECIMAL(10,4),
    recall_score DECIMAL(10,4),

    -- Validation metrics
    walk_forward_efficiency DECIMAL(10,4),
    parameter_robustness_score DECIMAL(10,4),
    bootstrap_prob_positive DECIMAL(10,4),
    bootstrap_ci_lower DECIMAL(10,4),
    bootstrap_ci_upper DECIMAL(10,4),

    -- Transaction costs
    total_commission DECIMAL(10,2),
    total_slippage DECIMAL(10,2),
    avg_cost_per_trade DECIMAL(10,4),

    CONSTRAINT chk_win_rate CHECK (win_rate >= 0 AND win_rate <= 1),
    CONSTRAINT chk_sharpe CHECK (sharpe_ratio >= -10 AND sharpe_ratio <= 10)
);

-- Individual trades
CREATE TABLE trades (
    trade_id BIGSERIAL PRIMARY KEY,
    backtest_id BIGINT REFERENCES backtests(backtest_id) ON DELETE CASCADE,

    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP NOT NULL,
    ticker VARCHAR(20) NOT NULL,

    entry_price DECIMAL(10,4) NOT NULL,
    exit_price DECIMAL(10,4) NOT NULL,
    shares INT NOT NULL,

    pnl DECIMAL(10,2),
    pnl_pct DECIMAL(10,4),

    exit_reason VARCHAR(50), -- 'TP', 'SL', 'TIME', 'SIGNAL', 'EOD'

    commission DECIMAL(10,2),
    slippage DECIMAL(10,2),
    bid_ask_spread DECIMAL(10,4),

    -- Contextual data
    entry_volume BIGINT,
    avg_daily_volume BIGINT,
    entry_sentiment DECIMAL(5,4),
    entry_score DECIMAL(5,4),

    CONSTRAINT chk_trade_duration CHECK (exit_time > entry_time),
    CONSTRAINT chk_shares CHECK (shares > 0)
);

-- Walk-forward windows
CREATE TABLE walk_forward_windows (
    window_id BIGSERIAL PRIMARY KEY,
    strategy_name VARCHAR(100),
    window_number INT,

    train_start DATE,
    train_end DATE,
    test_start DATE,
    test_end DATE,

    train_backtest_id BIGINT REFERENCES backtests(backtest_id),
    test_backtest_id BIGINT REFERENCES backtests(backtest_id),

    efficiency_ratio DECIMAL(10,4), -- OOS performance / IS performance

    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT chk_window_order CHECK (
        train_start < train_end AND
        test_start >= train_end AND
        test_start < test_end
    )
);

-- Bootstrap results
CREATE TABLE bootstrap_results (
    bootstrap_id BIGSERIAL PRIMARY KEY,
    backtest_id BIGINT REFERENCES backtests(backtest_id) ON DELETE CASCADE,

    n_iterations INT DEFAULT 10000,

    mean_return DECIMAL(10,4),
    median_return DECIMAL(10,4),
    std_return DECIMAL(10,4),

    ci_95_lower DECIMAL(10,4),
    ci_95_upper DECIMAL(10,4),

    prob_positive DECIMAL(10,4),
    prob_sharpe_gt_1 DECIMAL(10,4),

    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_backtests_strategy ON backtests(strategy_name, created_at DESC);
CREATE INDEX idx_backtests_symbol ON backtests(symbol, start_date);
CREATE INDEX idx_results_sharpe ON backtest_results(sharpe_ratio DESC);
CREATE INDEX idx_results_f1 ON backtest_results(f1_score DESC);
CREATE INDEX idx_results_efficiency ON backtest_results(walk_forward_efficiency DESC);
CREATE INDEX idx_trades_ticker ON trades(ticker, entry_time);
CREATE INDEX idx_trades_backtest ON trades(backtest_id, entry_time);
```

### VectorBT Integration

```python
import vectorbt as vbt
import numpy as np
import pandas as pd

class VectorizedBacktester:
    """
    1000x faster than iterative backtesting.
    Tests thousands of parameter combinations in seconds.
    """

    def __init__(self, symbols, start_date, end_date, interval='5m'):
        """
        Download price data once, reuse for all tests.

        Args:
            symbols: List of tickers
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Bar interval ('1m', '5m', '15m', '1h', '1d')
        """
        self.data = vbt.YFData.download(
            symbols,
            start=start_date,
            end=end_date,
            interval=interval
        )

        self.close = self.data.get('Close')
        self.high = self.data.get('High')
        self.low = self.data.get('Low')
        self.volume = self.data.get('Volume')

    def test_ma_crossover_grid(self, fast_range, slow_range):
        """
        Test all MA crossover combinations simultaneously.

        Example:
            fast_range = np.arange(5, 50, 1)  # 45 periods
            slow_range = np.arange(10, 100, 2)  # 45 periods
            → Tests 45 × 45 = 2,025 combinations in seconds

        Returns:
            pd.DataFrame with performance metrics for each combo
        """
        # Compute MAs for all periods at once (vectorized)
        fast_ma = vbt.MA.run(self.close, fast_range, short_name='fast')
        slow_ma = vbt.MA.run(self.close, slow_range, short_name='slow')

        # Generate signals (broadcast across all combinations)
        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)

        # Backtest all combinations
        pf = vbt.Portfolio.from_signals(
            self.close,
            entries,
            exits,
            init_cash=10000,
            fees=0.002,  # 0.2% commission
            slippage=0.01,  # 1% slippage for penny stocks
            freq='1h'  # For Sharpe calculation
        )

        # Extract results
        results = pd.DataFrame({
            'fast_period': pf.wrapper.columns.get_level_values('fast_period'),
            'slow_period': pf.wrapper.columns.get_level_values('slow_period'),
            'total_return': pf.total_return(),
            'sharpe_ratio': pf.sharpe_ratio(),
            'sortino_ratio': pf.sortino_ratio(),
            'max_drawdown': pf.max_drawdown(),
            'win_rate': pf.win_rate(),
            'num_trades': pf.trades.count(),
            'profit_factor': pf.trades.profit_factor()
        })

        return results.sort_values('sharpe_ratio', ascending=False)

    def test_sentiment_thresholds(self, sentiment_series, thresholds):
        """
        Test different sentiment score thresholds.

        Args:
            sentiment_series: pd.Series of sentiment scores (-1 to 1)
            thresholds: np.array of threshold values to test

        Returns:
            pd.DataFrame with F1 scores, precision, recall for each threshold
        """
        results = []

        for threshold in thresholds:
            # Entry when sentiment > threshold
            entries = sentiment_series > threshold

            # Exit after N bars (configurable)
            exits = vbt.signals.generate_exits(
                entries,
                wait=24  # Exit after 24 hours (bars)
            )

            pf = vbt.Portfolio.from_signals(
                self.close,
                entries,
                exits,
                init_cash=10000,
                fees=0.002,
                slippage=0.01
            )

            # Calculate precision, recall, F1
            trades = pf.trades
            wins = (trades.pnl > 0).sum()
            losses = (trades.pnl < 0).sum()
            total = len(trades)

            precision = wins / total if total > 0 else 0

            # Recall requires knowing all opportunities
            # For sentiment, assume all positive moves are opportunities
            total_opportunities = (self.close.pct_change(24) > 0.10).sum()
            recall = wins / total_opportunities if total_opportunities > 0 else 0

            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

            results.append({
                'threshold': threshold,
                'f1_score': f1,
                'precision': precision,
                'recall': recall,
                'sharpe': pf.sharpe_ratio(),
                'num_trades': total,
                'win_rate': wins / total if total > 0 else 0
            })

        return pd.DataFrame(results)
```

### Multi-Metric Scoring System

```python
from scipy.stats import skew, kurtosis
import numpy as np

class PerformanceMetrics:
    """
    Institutional-grade performance metrics.
    Goes beyond Sharpe ratio to capture non-normal distributions.
    """

    def __init__(self, returns, risk_free_rate=0.02):
        """
        Args:
            returns: pd.Series of period returns
            risk_free_rate: Annual risk-free rate (default 2%)
        """
        self.returns = returns
        self.rf = risk_free_rate / 252  # Daily risk-free rate
        self.excess_returns = returns - self.rf

    def sharpe_ratio(self):
        """Classic Sharpe ratio (penalizes both up and down volatility)."""
        return (self.returns.mean() - self.rf) / self.returns.std() * np.sqrt(252)

    def sortino_ratio(self, target_return=0):
        """
        Sortino ratio - only penalizes downside volatility.

        Better for asymmetric strategies (penny stocks with occasional big winners).
        Target for penny stocks: >1.5-2.0
        """
        downside_returns = self.returns[self.returns < target_return]
        downside_std = downside_returns.std()

        if downside_std == 0:
            return np.inf

        return (self.returns.mean() - target_return) / downside_std * np.sqrt(252)

    def calmar_ratio(self):
        """
        Calmar ratio = Annual Return / Max Drawdown

        Directly addresses tail risk and recovery capacity.
        Target for penny stocks: >2.0
        """
        annual_return = (1 + self.returns.mean()) ** 252 - 1
        max_dd = self.max_drawdown()

        if max_dd == 0:
            return np.inf

        return annual_return / abs(max_dd)

    def omega_ratio(self, threshold=0):
        """
        Omega ratio - gold standard for non-normal distributions.

        Ω(θ) = E[max(R-θ, 0)] / E[max(θ-R, 0)]

        Considers entire return distribution shape.
        Target: >2.0
        """
        gains = self.returns[self.returns > threshold] - threshold
        losses = threshold - self.returns[self.returns < threshold]

        if losses.sum() == 0:
            return np.inf

        return gains.sum() / losses.sum()

    def expectancy(self, avg_win, avg_loss, win_rate):
        """
        Expectancy = (Win% × Avg Win) - (Loss% × Avg Loss)

        The ONLY metric that matters for profitability.
        Target for penny stocks: >0.5 (50 cents profit per $1 risked)
        """
        loss_rate = 1 - win_rate
        return (win_rate * avg_win) - (loss_rate * avg_loss)

    def profit_factor(self, gross_profit, gross_loss):
        """
        Profit Factor = Gross Profit / Gross Loss

        Intuitive interpretation:
        - <1.0: Losing strategy
        - 1.75-2.5: Acceptable
        - >2.5: Strong edge
        - >4.0: Likely overfit

        Target for penny stocks: >2.0 (to overcome 6-8% transaction costs)
        """
        if gross_loss == 0:
            return np.inf

        return gross_profit / gross_loss

    def information_coefficient(self, predictions, actual_returns):
        """
        IC = Spearman correlation between predictions and outcomes

        Early warning of overfitting.
        - >0.10: Strong signal
        - 0.05-0.10: Decent signal
        - <0.03: Noise

        Should remain stable across time periods and stock subsets.
        """
        from scipy.stats import spearmanr

        ic, p_value = spearmanr(predictions, actual_returns)
        return ic, p_value

    def max_drawdown(self):
        """Maximum peak-to-trough decline."""
        cumulative = (1 + self.returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.min()

    def f1_score(self, precision, recall):
        """
        F1 = 2 × (Precision × Recall) / (Precision + Recall)

        Optimal metric for news alerts.
        Expect 0.4-0.6 for penny stocks (NOT 0.8+, that's overfit).
        """
        if precision + recall == 0:
            return 0

        return 2 * (precision * recall) / (precision + recall)

    def comprehensive_report(self):
        """Generate full metrics report."""
        return {
            'sharpe_ratio': self.sharpe_ratio(),
            'sortino_ratio': self.sortino_ratio(),
            'calmar_ratio': self.calmar_ratio(),
            'omega_ratio': self.omega_ratio(),
            'max_drawdown': self.max_drawdown(),
            'volatility': self.returns.std() * np.sqrt(252),
            'skewness': skew(self.returns),
            'kurtosis': kurtosis(self.returns),
            'var_95': np.percentile(self.returns, 5),
            'cvar_95': self.returns[self.returns <= np.percentile(self.returns, 5)].mean()
        }
```

### Phase 0 Deliverables Checklist

- [ ] PostgreSQL + TimescaleDB installed and configured
- [ ] Database schema created (all tables above)
- [ ] VectorBT installed (`pip install vectorbt`)
- [ ] PerformanceMetrics class implemented
- [ ] Transaction cost modeling (6-8% round-trip for stocks <$10)
- [ ] Basic backtest storage working (save/load from database)
- [ ] Multi-metric calculation tested
- [ ] Documentation written for future team members

**Estimated Time:** 1-2 weeks
**Critical Path:** Required before MOA Week 1

---

## Data Capture & Storage

### Rejected Items Logging

**Location:** `feeds.py` after classification, before filtering

```python
def log_rejected_item(item, rejection_reason, config):
    """
    Log rejected items for nightly MOA analysis.

    Only logs items within price range ($0.10-$10.00) to avoid massive files.
    """
    ticker = item.get('ticker', '').strip().upper()

    if not ticker:
        return  # Skip items without tickers

    # Get current price
    try:
        price, _ = get_last_price_change(ticker)
    except:
        price = None

    # Only log items within our price range
    if price is None or price < 0.10 or price > 10.00:
        return

    rejected_item = {
        'ts': item.get('ts', datetime.now(timezone.utc).isoformat()),
        'ticker': ticker,
        'title': item.get('title', ''),
        'source': item.get('source', ''),
        'price': price,

        # Classification data
        'cls': {
            'score': item.get('cls', {}).get('score', 0),
            'sentiment': item.get('cls', {}).get('sentiment', 0),
            'keywords': item.get('cls', {}).get('keywords', []),
            'confidence': item.get('cls', {}).get('confidence', 0)
        },

        # Rejection metadata
        'rejected': True,
        'rejection_reason': rejection_reason,
        'rejection_details': _get_rejection_details(item, config)
    }

    # Log to JSONL for daily processing
    with open('data/rejected_items.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(rejected_item) + '\n')

    # Also insert into SQLite for faster queries
    insert_into_sqlite(rejected_item)

def _get_rejection_details(item, config):
    """Capture why item was rejected."""
    score = item.get('cls', {}).get('score', 0)
    sentiment = item.get('cls', {}).get('sentiment', 0)
    price = item.get('price')

    details = {}

    if score < config.get('MIN_SCORE', 0):
        details['score_too_low'] = f"{score:.3f} < {config.get('MIN_SCORE')}"

    if price and price > config.get('PRICE_CEILING', 10):
        details['price_too_high'] = f"${price:.2f} > ${config.get('PRICE_CEILING')}"

    if abs(sentiment) < config.get('MIN_SENT_ABS', 0):
        details['sentiment_too_weak'] = f"{sentiment:.3f}"

    return details
```

### SQLite Schema (Daily Operations)

```python
import sqlite3

def init_moa_database():
    """Initialize SQLite database for fast daily queries."""
    conn = sqlite3.connect('data/moa.db')
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rejected_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TIMESTAMP NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            title TEXT,
            source VARCHAR(100),
            price DECIMAL(10,4),
            score DECIMAL(5,4),
            sentiment DECIMAL(5,4),
            keywords TEXT,  -- JSON array
            rejection_reason VARCHAR(100),
            rejection_details TEXT,  -- JSON object
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_cache (
            ticker VARCHAR(20),
            timestamp TIMESTAMP,
            timeframe VARCHAR(10),  -- '1h', '4h', '24h', '1w'
            price_change_pct DECIMAL(10,4),
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker, timestamp, timeframe)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_performance (
            keyword VARCHAR(100),
            occurrences INT DEFAULT 0,
            hits INT DEFAULT 0,
            misses INT DEFAULT 0,
            neutrals INT DEFAULT 0,
            avg_return DECIMAL(10,4),
            p_value DECIMAL(10,6),
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (keyword)
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejected_ts ON rejected_items(ts DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejected_ticker ON rejected_items(ticker)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejected_reason ON rejected_items(rejection_reason)")

    conn.commit()
    return conn
```

---

## Analysis Engine

### Walk-Forward Optimization

**The Gold Standard for Backtesting**

```python
from datetime import datetime, timedelta
import pandas as pd

class WalkForwardOptimizer:
    """
    Walk-forward optimization prevents overfitting by:
    1. Training on past data
    2. Testing on future data
    3. Rolling forward and repeating

    Expect 30-50% degradation from in-sample to out-of-sample.
    Efficiency >0.6 indicates genuine edge.
    """

    def __init__(self,
                 training_months=12,
                 testing_months=3,
                 step_months=1):
        """
        Args:
            training_months: In-sample training period (12-18 months)
            testing_months: Out-of-sample test period (3-6 months)
            step_months: How far to roll forward each iteration
        """
        self.training_months = training_months
        self.testing_months = testing_months
        self.step_months = step_months

    def run(self, data_start, data_end, optimization_func):
        """
        Execute walk-forward optimization.

        Args:
            data_start: datetime - Start of available data
            data_end: datetime - End of available data
            optimization_func: Function that takes (train_data) and returns optimal params

        Returns:
            List of walk-forward windows with results
        """
        windows = []
        current_date = data_start

        while current_date + timedelta(days=30 * (self.training_months + self.testing_months)) <= data_end:
            # Define training period
            train_start = current_date
            train_end = train_start + timedelta(days=30 * self.training_months)

            # Define testing period
            test_start = train_end
            test_end = test_start + timedelta(days=30 * self.testing_months)

            # Optimize on training data
            train_data = load_data(train_start, train_end)
            optimal_params = optimization_func(train_data)

            # Backtest on training data (in-sample)
            is_backtest = run_backtest(train_data, optimal_params)
            is_sharpe = is_backtest['sharpe_ratio']
            is_return = is_backtest['total_return']

            # Backtest on testing data (out-of-sample)
            test_data = load_data(test_start, test_end)
            oos_backtest = run_backtest(test_data, optimal_params)
            oos_sharpe = oos_backtest['sharpe_ratio']
            oos_return = oos_backtest['total_return']

            # Calculate efficiency
            efficiency = oos_return / is_return if is_return != 0 else 0

            window = {
                'train_start': train_start,
                'train_end': train_end,
                'test_start': test_start,
                'test_end': test_end,
                'optimal_params': optimal_params,
                'is_sharpe': is_sharpe,
                'is_return': is_return,
                'oos_sharpe': oos_sharpe,
                'oos_return': oos_return,
                'efficiency': efficiency
            }

            windows.append(window)

            # Roll forward
            current_date += timedelta(days=30 * self.step_months)

        return self.analyze_windows(windows)

    def analyze_windows(self, windows):
        """Analyze walk-forward results for robustness."""
        df = pd.DataFrame(windows)

        analysis = {
            'num_windows': len(windows),
            'avg_efficiency': df['efficiency'].mean(),
            'min_efficiency': df['efficiency'].min(),
            'max_efficiency': df['efficiency'].max(),
            'std_efficiency': df['efficiency'].std(),

            'avg_is_sharpe': df['is_sharpe'].mean(),
            'avg_oos_sharpe': df['oos_sharpe'].mean(),

            'consistent_windows': (df['efficiency'] > 0.6).sum(),
            'failed_windows': (df['efficiency'] < 0.4).sum(),

            'parameter_stability': self._check_parameter_stability(df),

            'verdict': self._verdict(df)
        }

        return analysis

    def _check_parameter_stability(self, df):
        """
        Check if optimal parameters vary wildly across windows.
        Wild variation = strategy breakdown, not adaptation.
        """
        # Example for MIN_SCORE parameter
        scores = [w['min_score'] for w in df['optimal_params']]
        cv = np.std(scores) / np.mean(scores) if np.mean(scores) > 0 else 999

        if cv < 0.3:
            return "STABLE - Parameters consistent across windows"
        elif cv < 0.6:
            return "MODERATE - Some parameter variation"
        else:
            return "UNSTABLE - Wild parameter swings indicate breakdown"

    def _verdict(self, df):
        """Final go/no-go decision."""
        avg_eff = df['efficiency'].mean()
        min_eff = df['efficiency'].min()
        consistent = (df['efficiency'] > 0.6).sum() / len(df)

        if avg_eff > 0.7 and min_eff > 0.5 and consistent > 0.7:
            return "DEPLOY - Strong walk-forward performance"
        elif avg_eff > 0.6 and consistent > 0.6:
            return "PAPER TRADE - Acceptable but monitor closely"
        else:
            return "REJECT - Failed walk-forward validation"
```

### Combinatorial Purged Cross-Validation

```python
from itertools import combinations

class CombinatorialPurgedCV:
    """
    Superior to simple train/test splits.

    Addresses information leakage where single news event
    influences prices for days/weeks.
    """

    def __init__(self, n_groups=10, n_test_groups=3, embargo_days=14):
        """
        Args:
            n_groups: Divide data into N chronological groups
            n_test_groups: Use K groups for testing each iteration
            embargo_days: Buffer period between train and test
        """
        self.n_groups = n_groups
        self.n_test_groups = n_test_groups
        self.embargo_days = embargo_days

    def split(self, data):
        """
        Generate all combinations of train/test splits with purging.

        For n_groups=10, n_test=3:
        C(10,3) = 120 different splits

        Yields:
            (train_data, test_data) tuples
        """
        # Divide data into chronological groups
        groups = self._divide_into_groups(data, self.n_groups)

        # Generate all test group combinations
        for test_group_indices in combinations(range(self.n_groups), self.n_test_groups):
            # Get test groups
            test_data = pd.concat([groups[i] for i in test_group_indices])

            # Get training groups (all others)
            train_group_indices = [i for i in range(self.n_groups) if i not in test_group_indices]
            train_data = pd.concat([groups[i] for i in train_group_indices])

            # PURGE: Remove training samples that overlap with test period
            train_data = self._purge_overlaps(train_data, test_data)

            # EMBARGO: Add buffer zone
            train_data = self._apply_embargo(train_data, test_data)

            yield train_data, test_data

    def _divide_into_groups(self, data, n):
        """Divide data into N chronological groups."""
        data = data.sort_values('timestamp')
        group_size = len(data) // n

        groups = []
        for i in range(n):
            start_idx = i * group_size
            end_idx = (i + 1) * group_size if i < n - 1 else len(data)
            groups.append(data.iloc[start_idx:end_idx])

        return groups

    def _purge_overlaps(self, train_data, test_data):
        """
        Remove training samples whose events overlap with test period.

        Critical for news-based strategies where one catalyst
        influences prices for weeks.
        """
        test_start = test_data['timestamp'].min()
        test_end = test_data['timestamp'].max()

        # Remove training samples that fall within test window
        train_data = train_data[
            (train_data['timestamp'] < test_start) |
            (train_data['timestamp'] > test_end)
        ]

        return train_data

    def _apply_embargo(self, train_data, test_data):
        """
        Add 2-4 week buffer between train and test.

        Prevents subtle look-ahead bias from delayed price reactions.
        """
        test_start = test_data['timestamp'].min()
        embargo_cutoff = test_start - timedelta(days=self.embargo_days)

        train_data = train_data[train_data['timestamp'] < embargo_cutoff]

        return train_data

    def evaluate(self, data, strategy_func):
        """
        Run CPCV and aggregate results.

        Args:
            data: Full dataset
            strategy_func: Function that takes (train, test) and returns performance

        Returns:
            dict with aggregated metrics
        """
        results = []

        for train, test in self.split(data):
            perf = strategy_func(train, test)
            results.append(perf)

        df = pd.DataFrame(results)

        return {
            'mean_sharpe': df['sharpe'].mean(),
            'std_sharpe': df['sharpe'].std(),
            'min_sharpe': df['sharpe'].min(),
            'max_sharpe': df['sharpe'].max(),
            'prob_positive_sharpe': (df['sharpe'] > 0).sum() / len(df),

            # Deflated Sharpe Ratio (accounting for multiple testing)
            'deflated_sharpe': self._calculate_deflated_sharpe(df['sharpe']),

            'prob_backtest_overfitting': self._calculate_pbo(df),

            'num_splits': len(results)
        }

    def _calculate_deflated_sharpe(self, sharpe_values):
        """
        Adjust for multiple hypothesis testing.

        Bailey & López de Prado (2014)
        """
        n = len(sharpe_values)
        sr_mean = sharpe_values.mean()
        sr_std = sharpe_values.std()

        # Deflation factor accounts for number of trials
        deflation = sr_std * np.sqrt(np.log(n) / n)

        return sr_mean - deflation

    def _calculate_pbo(self, df):
        """
        Probability of Backtest Overfitting.

        Lower is better. PBO > 0.5 = likely overfit.
        """
        # Count splits where in-sample > out-of-sample
        # (Simplified version - full PBO requires more complex logic)

        if 'is_sharpe' in df.columns and 'oos_sharpe' in df.columns:
            overfit_count = (df['is_sharpe'] > df['oos_sharpe']).sum()
            return overfit_count / len(df)

        return None
```

### Bootstrap Validation

```python
import numpy as np
from scipy import stats

class BootstrapValidator:
    """
    Generate confidence intervals without parametric assumptions.

    Resamples trade history 10,000 times to estimate probability
    of genuine edge.
    """

    def __init__(self, n_iterations=10000, confidence_level=0.95):
        """
        Args:
            n_iterations: Number of bootstrap samples (10,000 standard)
            confidence_level: Confidence interval (0.95 = 95%)
        """
        self.n_iterations = n_iterations
        self.confidence_level = confidence_level

    def validate_strategy(self, trades):
        """
        Bootstrap validation of trade sequence.

        Args:
            trades: List of trade P&Ls

        Returns:
            dict with confidence intervals and probability estimates
        """
        if len(trades) < 30:
            return {
                'error': 'Insufficient trades for bootstrap (need ≥30)',
                'num_trades': len(trades)
            }

        trades = np.array(trades)

        # Store results from each bootstrap iteration
        bootstrap_returns = []
        bootstrap_sharpes = []
        bootstrap_expectancies = []

        for _ in range(self.n_iterations):
            # Resample with replacement
            sample = np.random.choice(trades, size=len(trades), replace=True)

            # Randomly skip 5-10% to simulate execution failures
            skip_mask = np.random.random(len(sample)) > 0.075  # Skip 7.5%
            sample = sample[skip_mask]

            # Calculate metrics on this synthetic sequence
            total_return = sample.sum()
            sharpe = sample.mean() / sample.std() * np.sqrt(252) if sample.std() > 0 else 0
            expectancy = sample.mean()

            bootstrap_returns.append(total_return)
            bootstrap_sharpes.append(sharpe)
            bootstrap_expectancies.append(expectancy)

        # Calculate confidence intervals
        alpha = 1 - self.confidence_level
        ci_lower = alpha / 2
        ci_upper = 1 - ci_lower

        return_ci = np.percentile(bootstrap_returns, [ci_lower * 100, ci_upper * 100])
        sharpe_ci = np.percentile(bootstrap_sharpes, [ci_lower * 100, ci_upper * 100])
        expect_ci = np.percentile(bootstrap_expectancies, [ci_lower * 100, ci_upper * 100])

        # Calculate probabilities
        prob_positive_return = sum(r > 0 for r in bootstrap_returns) / self.n_iterations
        prob_positive_sharpe = sum(s > 0 for s in bootstrap_sharpes) / self.n_iterations
        prob_sharpe_gt_1 = sum(s > 1.0 for s in bootstrap_sharpes) / self.n_iterations

        # 95th percentile drawdown (stress test)
        # Simulate drawdown for each bootstrap sample
        bootstrap_drawdowns = []
        for sample in [np.random.choice(trades, size=len(trades), replace=True)
                      for _ in range(1000)]:
            cumulative = np.cumsum(sample)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max).min()
            bootstrap_drawdowns.append(drawdown)

        dd_95th = np.percentile(bootstrap_drawdowns, 95)

        return {
            'num_trades': len(trades),
            'n_iterations': self.n_iterations,

            # Confidence intervals
            'return_ci_lower': return_ci[0],
            'return_ci_upper': return_ci[1],
            'sharpe_ci_lower': sharpe_ci[0],
            'sharpe_ci_upper': sharpe_ci[1],
            'expectancy_ci_lower': expect_ci[0],
            'expectancy_ci_upper': expect_ci[1],

            # Probabilities
            'prob_positive_return': prob_positive_return,
            'prob_positive_sharpe': prob_positive_sharpe,
            'prob_sharpe_gt_1': prob_sharpe_gt_1,

            # Stress test
            'drawdown_95th_percentile': dd_95th,

            # Verdict
            'deploy_ready': self._verdict(prob_positive_return,
                                         sharpe_ci[0],
                                         len(trades))
        }

    def _verdict(self, prob_positive, sharpe_lower, num_trades):
        """
        Deployment decision based on bootstrap results.

        Criteria:
        - >70% probability of positive returns
        - Lower CI of Sharpe > 0
        - At least 385 trades (95% statistical confidence)
        """
        if num_trades < 107:
            return "INSUFFICIENT DATA - Need ≥107 trades (currently {})".format(num_trades)

        if num_trades < 385:
            verdict = "PAPER TRADE ONLY - Need 385 trades for 95% confidence"
        else:
            verdict = "SAMPLE SIZE OK"

        if prob_positive < 0.60:
            return f"REJECT - Only {prob_positive:.1%} bootstrap confidence"
        elif prob_positive < 0.70:
            return f"WEAK - {prob_positive:.1%} confidence (target >70%)"

        if sharpe_lower < 0:
            return "REJECT - Lower CI of Sharpe is negative"

        if prob_positive >= 0.70 and sharpe_lower > 0 and num_trades >= 385:
            return "DEPLOY - Passed bootstrap validation"

        return verdict
```

---

## Statistical Validation Framework

### ROC-AUC Analysis (Threshold-Independent)

```python
from sklearn.metrics import roc_curve, auc, roc_auc_score
import matplotlib.pyplot as plt

class ROCAUCAnalyzer:
    """
    Threshold-independent signal quality assessment.

    Use to compare different sentiment models or news sources
    without committing to specific threshold.
    """

    def analyze(self, scores, outcomes):
        """
        Args:
            scores: Array of signal scores (sentiment, relevance, etc.)
            outcomes: Binary array (1=winner, 0=loser/neutral)

        Returns:
            dict with ROC-AUC metrics and optimal threshold
        """
        # Calculate ROC curve
        fpr, tpr, thresholds = roc_curve(outcomes, scores)
        roc_auc = auc(fpr, tpr)

        # Find optimal threshold (maximizes TPR - FPR)
        optimal_idx = np.argmax(tpr - fpr)
        optimal_threshold = thresholds[optimal_idx]
        optimal_tpr = tpr[optimal_idx]
        optimal_fpr = fpr[optimal_idx]

        # Youden's J statistic
        j_statistic = tpr - fpr
        j_max = j_statistic[optimal_idx]

        return {
            'roc_auc': roc_auc,
            'optimal_threshold': optimal_threshold,
            'optimal_tpr': optimal_tpr,
            'optimal_fpr': optimal_fpr,
            'youden_j': j_max,

            'interpretation': self._interpret_auc(roc_auc),

            # Full curve for plotting
            'fpr': fpr,
            'tpr': tpr,
            'thresholds': thresholds
        }

    def _interpret_auc(self, auc_score):
        """
        Interpret AUC score.

        - 0.5: Random (no predictive power)
        - 0.6-0.7: Weak signal
        - 0.7-0.8: Acceptable signal
        - 0.8-0.9: Strong signal
        - >0.9: Excellent (or overfit - verify)
        """
        if auc_score < 0.55:
            return "NO SIGNAL - Worse than random"
        elif auc_score < 0.60:
            return "VERY WEAK - Barely better than coin flip"
        elif auc_score < 0.70:
            return "WEAK - Some predictive power"
        elif auc_score < 0.80:
            return "GOOD - Decent signal quality"
        elif auc_score < 0.90:
            return "STRONG - High signal quality"
        else:
            return "EXCELLENT - Verify not overfit"

    def plot_roc_curve(self, fpr, tpr, roc_auc, save_path=None):
        """Generate ROC curve visualization."""
        plt.figure(figsize=(8, 6))
        plt.plot(fpr, tpr, color='darkorange', lw=2,
                label=f'ROC curve (AUC = {roc_auc:.2f})')
        plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--',
                label='Random (AUC = 0.50)')
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.title('Receiver Operating Characteristic (ROC) Curve')
        plt.legend(loc="lower right")
        plt.grid(alpha=0.3)

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')

        plt.close()
```

### Parameter Sensitivity Analysis

```python
class ParameterSensitivityTester:
    """
    Distinguish robust strategies from overfit noise.

    Robust strategies maintain 70%+ performance when parameters
    shift ±20-50% from optimal.
    """

    def test_sensitivity(self, base_params, backtest_func, data):
        """
        Args:
            base_params: dict of optimal parameters
            backtest_func: Function that takes (params, data) and returns metrics
            data: Historical data for backtesting

        Returns:
            Sensitivity analysis results
        """
        base_performance = backtest_func(base_params, data)
        base_sharpe = base_performance['sharpe_ratio']

        # Test ±20%, ±30%, ±50% variations
        multipliers = [0.5, 0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.5, 2.0]

        results = []

        for param_name, base_value in base_params.items():
            if not isinstance(base_value, (int, float)):
                continue  # Skip non-numeric parameters

            param_results = {
                'parameter': param_name,
                'base_value': base_value,
                'variations': []
            }

            for mult in multipliers:
                varied_params = base_params.copy()
                varied_params[param_name] = base_value * mult

                perf = backtest_func(varied_params, data)
                sharpe = perf['sharpe_ratio']

                retention = sharpe / base_sharpe if base_sharpe != 0 else 0

                param_results['variations'].append({
                    'multiplier': mult,
                    'value': base_value * mult,
                    'sharpe': sharpe,
                    'retention': retention
                })

            results.append(param_results)

        # Aggregate analysis
        return self._analyze_sensitivity(results, base_sharpe)

    def _analyze_sensitivity(self, results, base_sharpe):
        """Analyze sensitivity test results."""
        all_retentions = []

        for param_result in results:
            retentions = [v['retention'] for v in param_result['variations']]
            all_retentions.extend(retentions)

            min_retention = min(retentions)
            max_retention = max(retentions)
            avg_retention = np.mean(retentions)

            param_result['min_retention'] = min_retention
            param_result['max_retention'] = max_retention
            param_result['avg_retention'] = avg_retention
            param_result['volatility'] = np.std(retentions)

        # Overall robustness score
        overall_min = min(all_retentions)
        overall_avg = np.mean(all_retentions)
        overall_std = np.std(all_retentions)

        # Monte Carlo random parameter sampling
        mc_score = self._monte_carlo_sensitivity(base_params, backtest_func, data)

        verdict = self._sensitivity_verdict(overall_min, overall_avg, mc_score)

        return {
            'base_sharpe': base_sharpe,
            'per_parameter_results': results,

            'overall_min_retention': overall_min,
            'overall_avg_retention': overall_avg,
            'overall_std': overall_std,

            'monte_carlo_robustness': mc_score,

            'verdict': verdict
        }

    def _monte_carlo_sensitivity(self, base_params, backtest_func, data, n=1000):
        """
        Test 1,000-10,000 random parameter combinations.

        Robustness Score = (95th percentile - 5th percentile) / Median
        - <0.5: High robustness
        - 0.5-1.0: Moderate robustness
        - >1.0: High fragility (likely overfit)
        """
        sharpes = []

        for _ in range(n):
            # Randomly perturb each parameter by ±50%
            varied_params = {}
            for name, value in base_params.items():
                if isinstance(value, (int, float)):
                    mult = np.random.uniform(0.5, 1.5)
                    varied_params[name] = value * mult
                else:
                    varied_params[name] = value

            try:
                perf = backtest_func(varied_params, data)
                sharpes.append(perf['sharpe_ratio'])
            except:
                continue

        if len(sharpes) < 100:
            return {'error': 'Monte Carlo failed - insufficient successful backtests'}

        p5 = np.percentile(sharpes, 5)
        p95 = np.percentile(sharpes, 95)
        median = np.median(sharpes)

        robustness_score = (p95 - p5) / median if median != 0 else 999

        return {
            'p5': p5,
            'p50': median,
            'p95': p95,
            'robustness_score': robustness_score,
            'n_successful': len(sharpes)
        }

    def _sensitivity_verdict(self, min_retention, avg_retention, mc_result):
        """Final robustness verdict."""
        mc_score = mc_result.get('robustness_score', 999)

        if min_retention < 0.50:
            return "REJECT - Strategy breaks with modest parameter changes"

        if min_retention < 0.70:
            return "FRAGILE - Poor retention at parameter boundaries"

        if mc_score > 1.0:
            return "FRAGILE - High Monte Carlo robustness score (>1.0)"

        if avg_retention > 0.80 and mc_score < 0.5:
            return "ROBUST - Strategy performs well across parameter space"

        return "MODERATE - Acceptable but monitor closely"
```

---

## Recommendation Engine

### Keyword Discovery with TF-IDF

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.stats import binom_test

class KeywordDiscoveryEngine:
    """
    Extract novel keywords from missed winners using TF-IDF.
    Validate with statistical significance tests.
    """

    def __init__(self, min_occurrences=10, significance_level=0.05):
        """
        Args:
            min_occurrences: Minimum times keyword must appear (default 10)
            significance_level: p-value threshold (default 0.05)
        """
        self.min_occurrences = min_occurrences
        self.alpha = significance_level

    def discover_keywords(self, missed_winners, current_weights):
        """
        Extract keywords from missed winners.

        Args:
            missed_winners: List of dicts with 'title', 'keywords', 'price_move'
            current_weights: Dict of existing keyword weights

        Returns:
            List of new keyword candidates with statistical validation
        """
        # Extract titles
        titles = [w['title'] for w in missed_winners]

        # TF-IDF extraction
        vectorizer = TfidfVectorizer(
            max_features=100,
            stop_words='english',
            ngram_range=(1, 2),  # Unigrams and bigrams
            min_df=self.min_occurrences  # Must appear at least N times
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(titles)
            keywords = vectorizer.get_feature_names_out()
        except:
            return []  # Insufficient data

        # For each keyword, calculate performance
        candidates = []

        for keyword in keywords:
            # Skip if already in weights
            if keyword in current_weights:
                continue

            # Find all missed winners containing this keyword
            containing_keyword = [
                w for w in missed_winners
                if keyword.lower() in w['title'].lower()
            ]

            if len(containing_keyword) < self.min_occurrences:
                continue

            # Calculate performance metrics
            returns = [w['price_move'] for w in containing_keyword]
            hits = sum(1 for r in returns if r >= 10.0)  # >10% = hit
            total = len(returns)
            avg_return = np.mean(returns)

            # Statistical significance test
            # Null hypothesis: 50% random win rate
            p_value = binom_test(hits, total, p=0.5, alternative='greater')

            if p_value < self.alpha:
                candidates.append({
                    'keyword': keyword,
                    'occurrences': total,
                    'hits': hits,
                    'hit_rate': hits / total,
                    'avg_return': avg_return,
                    'p_value': p_value,
                    'confidence': 'high' if p_value < 0.01 else 'medium',
                    'proposed_weight': self._calculate_initial_weight(hits, total, avg_return)
                })

        # Sort by statistical significance
        candidates.sort(key=lambda x: x['p_value'])

        return candidates

    def _calculate_initial_weight(self, hits, total, avg_return):
        """
        Propose initial weight based on performance.

        Conservative approach:
        - Start at 1.0 baseline
        - Adjust by performance vs expected
        - Cap between 0.5 and 2.0 for new keywords
        """
        hit_rate = hits / total
        expected_hit_rate = 0.5  # Null hypothesis

        # Performance ratio
        performance_ratio = hit_rate / expected_hit_rate

        # Weight adjustment
        weight = 1.0 * performance_ratio

        # Cap for safety
        weight = max(0.5, min(weight, 2.0))

        return round(weight, 2)

    def recommend_weight_adjustments(self, keyword_performance, current_weights):
        """
        Recommend adjustments to existing keyword weights.

        Args:
            keyword_performance: List of dicts with performance stats
            current_weights: Current weight values

        Returns:
            List of weight adjustment recommendations
        """
        recommendations = []

        for kp in keyword_performance:
            keyword = kp['category']  # Or kp['keyword']
            current = current_weights.get(keyword, 1.0)

            hits = kp['hits']
            misses = kp['misses']
            total = hits + misses

            if total < self.min_occurrences:
                continue  # Insufficient data

            # Statistical test
            p_value = binom_test(hits, total, p=0.5, alternative='greater')

            if p_value >= self.alpha:
                continue  # Not statistically significant

            # Calculate adjustment
            hit_rate = hits / total

            if hit_rate > 0.60:
                # Strong performer - increase weight
                proposed = current * 1.2
                reason = f"Strong hit rate ({hit_rate:.1%}) with p={p_value:.4f}"
                impact = 'high'
            elif hit_rate < 0.40:
                # Weak performer - decrease weight
                proposed = current * 0.8
                reason = f"Weak hit rate ({hit_rate:.1%}) with p={p_value:.4f}"
                impact = 'high'
            else:
                # Neutral - no change
                continue

            # Cap adjustments
            proposed = max(0.5, min(proposed, 3.0))

            recommendations.append({
                'keyword': keyword,
                'current_weight': current,
                'proposed_weight': round(proposed, 2),
                'reason': reason,
                'impact': impact,
                'p_value': p_value,
                'sample_size': total,
                'confidence': self._confidence_level(total, p_value)
            })

        return recommendations

    def _confidence_level(self, sample_size, p_value):
        """
        Assign confidence level based on sample size and p-value.

        High confidence = auto-approve
        Medium = manual review
        Low = A/B test required
        """
        if sample_size >= 385 and p_value < 0.01:
            return 'high'  # >90% confidence
        elif sample_size >= 107 and p_value < 0.05:
            return 'medium'  # 70-90% confidence
        else:
            return 'low'  # <70% confidence
```

---

## Learning Loop with Rollback

### Auto-Approval with Monitoring

```python
class LearningLoop:
    """
    Automated learning with safety checks and rollback.

    Confidence levels:
    - High (>90%): Auto-approve
    - Medium (70-90%): Manual review
    - Low (<70%): A/B test required

    Auto-rollback if Sharpe drops >10%.
    """

    def __init__(self, cooling_period_days=7):
        """
        Args:
            cooling_period_days: Minimum days between changes (default 7)
        """
        self.cooling_period = cooling_period_days
        self.change_history = self._load_change_history()

    def process_recommendations(self, recommendations):
        """
        Process weight recommendations based on confidence level.

        Args:
            recommendations: List from KeywordDiscoveryEngine

        Returns:
            dict with actions taken
        """
        # Check cooling period
        if not self._cooling_period_elapsed():
            return {
                'status': 'cooling',
                'message': f'Cooling period active (last change {self._days_since_last_change()} days ago)',
                'actions': []
            }

        actions = {
            'auto_approved': [],
            'manual_review': [],
            'ab_test': [],
            'rejected': []
        }

        for rec in recommendations:
            confidence = rec['confidence']

            if confidence == 'high':
                # Auto-approve
                self._apply_weight_change(rec)
                actions['auto_approved'].append(rec)

            elif confidence == 'medium':
                # Manual review required
                self._queue_for_review(rec)
                actions['manual_review'].append(rec)

            else:  # low confidence
                # A/B test required
                self._setup_ab_test(rec)
                actions['ab_test'].append(rec)

        # Record changes
        if actions['auto_approved']:
            self._record_change(actions['auto_approved'])

            # Start monitoring period
            self._start_monitoring()

        return actions

    def monitor_performance(self):
        """
        Monitor performance after weight changes.

        Auto-rollback if:
        - Sharpe drops >10%
        - Drawdown exceeds historical max by 2x
        - Win rate drops >15 percentage points
        """
        if not self._is_monitoring_active():
            return {'status': 'not_monitoring'}

        current_sharpe = self._calculate_current_sharpe()
        baseline_sharpe = self.change_history[-1]['baseline_sharpe']

        current_dd = self._calculate_current_drawdown()
        baseline_dd = self.change_history[-1]['baseline_max_dd']

        current_wr = self._calculate_current_win_rate()
        baseline_wr = self.change_history[-1]['baseline_win_rate']

        # Check rollback conditions
        sharpe_degradation = (baseline_sharpe - current_sharpe) / baseline_sharpe
        dd_increase = current_dd / baseline_dd
        wr_drop = baseline_wr - current_wr

        if sharpe_degradation > 0.10:
            # Sharpe dropped >10%
            self._rollback("Sharpe degradation: {:.1%}".format(sharpe_degradation))
            return {'status': 'rolled_back', 'reason': 'sharpe_degradation'}

        if dd_increase > 2.0:
            # Drawdown 2x worse
            self._rollback(f"Drawdown 2x worse: {current_dd:.1%} vs {baseline_dd:.1%}")
            return {'status': 'rolled_back', 'reason': 'excessive_drawdown'}

        if wr_drop > 0.15:
            # Win rate dropped >15%
            self._rollback(f"Win rate drop: {wr_drop:.1%}")
            return {'status': 'rolled_back', 'reason': 'win_rate_decline'}

        return {
            'status': 'monitoring',
            'sharpe_change': sharpe_degradation,
            'drawdown_ratio': dd_increase,
            'win_rate_change': wr_drop
        }

    def _rollback(self, reason):
        """
        Rollback to previous weights.

        Notify admin via Discord.
        """
        log.warning(f"AUTO-ROLLBACK triggered: {reason}")

        # Restore previous weights
        previous_weights = self.change_history[-1]['previous_weights']
        self._restore_weights(previous_weights)

        # Notify admin
        self._notify_admin_rollback(reason)

        # Record rollback
        self.change_history.append({
            'timestamp': datetime.now(timezone.utc),
            'action': 'rollback',
            'reason': reason,
            'restored_weights': previous_weights
        })

        self._save_change_history()

    def _cooling_period_elapsed(self):
        """Check if cooling period has passed."""
        if not self.change_history:
            return True

        days_since = self._days_since_last_change()
        return days_since >= self.cooling_period

    def _days_since_last_change(self):
        """Days since last weight change."""
        if not self.change_history:
            return 999

        last_change = self.change_history[-1]['timestamp']
        delta = datetime.now(timezone.utc) - last_change
        return delta.days
```

---

## Implementation Roadmap

### Phase 0: Historical Backtesting Infrastructure (Weeks 0-2)

**CRITICAL: Build this FIRST**

**Week 0:**
- [ ] Install PostgreSQL + TimescaleDB
- [ ] Create database schema (all tables from Phase 0 section)
- [ ] Install VectorBT (`pip install vectorbt`)
- [ ] Implement PerformanceMetrics class
- [ ] Write unit tests

**Week 1:**
- [ ] Implement VectorizedBacktester class
- [ ] Test with sample data (AAPL, TSLA, 2 years)
- [ ] Verify 1000x speedup vs iterative
- [ ] Store results in PostgreSQL

**Week 2:**
- [ ] Implement WalkForwardOptimizer
- [ ] Implement CombinatorialPurgedCV
- [ ] Implement BootstrapValidator
- [ ] Integration tests
- [ ] Documentation

**Deliverable:** Production-ready backtesting infrastructure

---

### Phase 1: MOA Data Capture (Weeks 3-4)

**Week 3:**
- [ ] Add rejected item logging to `feeds.py`
- [ ] Create SQLite schema for daily ops
- [ ] Implement price range filter ($0.10-$10)
- [ ] Test with dry-run mode (logging only)
- [ ] Verify <10ms overhead per item

**Week 4:**
- [ ] Multi-timeframe price fetcher (1h, 4h, 24h, 1w)
- [ ] Implement price caching
- [ ] Test with 100+ tickers
- [ ] Monitor for 7 days
- [ ] Verify data quality (>95% success rate)

**Deliverable:** 150+ rejected items logged per cycle with metadata

---

### Phase 2: Analysis Engine (Weeks 5-7)

**Week 5:**
- [ ] Identify missed winners (>10% gain)
- [ ] Calculate multi-timeframe returns
- [ ] Basic statistics (hit rate, avg return)
- [ ] Generate text report

**Week 6:**
- [ ] Implement TF-IDF keyword extraction
- [ ] Statistical validation (binomial tests)
- [ ] Minimum sample size enforcement (10+)
- [ ] ROC-AUC analysis

**Week 7:**
- [ ] Walk-forward validation on keywords
- [ ] Bootstrap confidence intervals
- [ ] Parameter sensitivity testing
- [ ] Integration with existing analyzer

**Deliverable:** Daily report showing missed opportunities with statistical validation

---

### Phase 3: Recommendation Engine (Weeks 8-10)

**Week 8:**
- [ ] Keyword discovery engine (TF-IDF)
- [ ] Weight adjustment recommendations
- [ ] Confidence scoring (high/med/low)
- [ ] Integration with Discord

**Week 9:**
- [ ] Discord embed design
- [ ] Interactive approval buttons
- [ ] Report formatting (tables, charts)
- [ ] Error handling

**Week 10:**
- [ ] Admin controls integration
- [ ] Approval workflow
- [ ] Manual review interface
- [ ] Testing with real data

**Deliverable:** Admin can review and approve changes in <5 minutes

---

### Phase 4: Learning Loop (Weeks 11-12)

**Week 11:**
- [ ] Auto-approval for high confidence (>90%)
- [ ] A/B testing framework
- [ ] Cooling period enforcement
- [ ] Change audit trail

**Week 12:**
- [ ] Performance monitoring
- [ ] Auto-rollback implementation
- [ ] Alerting system
- [ ] Full integration testing

**Deliverable:** Fully automated learning with safety checks

---

### Phase 5: Production Deployment (Weeks 13-14)

**Week 13:**
- [ ] Shadow mode (analysis only, no changes)
- [ ] Monitor for errors
- [ ] Performance optimization
- [ ] Load testing

**Week 14:**
- [ ] Enable auto-approval
- [ ] Monitor first week
- [ ] Adjust thresholds
- [ ] Documentation

**Deliverable:** MOA running in production with auto-approval

---

## Success Metrics & KPIs

### Weekly Tracking

**Week 1-2 (Phase 0):**
```
✓ Database created: Yes/No
✓ VectorBT speedup: ___x (target: >100x)
✓ Backtest storage: ___ runs stored
✓ Multi-metric calculation: All working
```

**Week 3-4 (Data Capture):**
```
✓ Rejected items logged: ___ (target: >150/cycle)
✓ File size: ___ MB (target: <50 MB/day)
✓ Logging overhead: ___ ms (target: <10ms)
✓ Price fetch success rate: ___% (target: >95%)
```

**Week 5-7 (Analysis):**
```
✓ Missed winners identified: ___ (target: 10-20/week)
✓ Keywords discovered: ___ (target: 2-5/week)
✓ Statistical significance: ___% (target: >60% have p<0.05)
✓ Walk-forward efficiency: ___ (target: >0.6)
```

**Week 8-10 (Recommendations):**
```
✓ Weight recommendations: ___ (target: 3-5/week)
✓ Auto-approved: ___ (confidence >90%)
✓ Manual review: ___ (confidence 70-90%)
✓ Admin review time: ___ min (target: <5min)
```

**Week 11-12 (Learning Loop):**
```
✓ Auto-approvals executed: ___
✓ Rollbacks triggered: ___ (target: 0-1)
✓ Sharpe improvement: ___% (target: >5%)
✓ False negative reduction: ___% (target: >10%)
```

### 6-Month Goals

| Metric | Baseline | 6-Month Target | Stretch Goal |
|--------|----------|----------------|--------------|
| **New Keywords Discovered** | 0 | 20-30 | 40+ |
| **False Negative Reduction** | 0% | 30-40% | 50%+ |
| **Sharpe Improvement** | Baseline | +20-25% | +30%+ |
| **F1 Score** | 0.3-0.4 | 0.5-0.6 | 0.65+ |
| **Walk-Forward Efficiency** | N/A | >0.6 | >0.7 |
| **Bootstrap Confidence** | N/A | >70% | >80% |
| **Minimum Trades Validated** | <100 | 385+ | 500+ |
| **Manual Tuning Time** | ~10 hrs/mo | ~5 hrs/mo | <2 hrs/mo |

### Critical Thresholds (Deploy/Reject)

**DO NOT DEPLOY if:**
- ❌ Walk-forward efficiency <0.4
- ❌ Bootstrap probability <60%
- ❌ F1 score <0.3 or >0.7 (overfit)
- ❌ Parameter robustness <60% retention
- ❌ ROC-AUC <0.6
- ❌ Information Coefficient <0.03
- ❌ Fewer than 107 trades (70% confidence minimum)

**PAPER TRADE if:**
- ⚠️ Walk-forward efficiency 0.4-0.6
- ⚠️ Bootstrap probability 60-70%
- ⚠️ Sample size 107-384 trades
- ⚠️ F1 score 0.3-0.4
- ⚠️ ROC-AUC 0.6-0.7

**DEPLOY if:**
- ✅ Walk-forward efficiency >0.6
- ✅ Bootstrap probability >70%
- ✅ F1 score 0.4-0.65
- ✅ Parameter robustness >70%
- ✅ ROC-AUC >0.7
- ✅ Information Coefficient >0.05
- ✅ At least 385 trades (95% confidence)
- ✅ Sortino ratio >1.5
- ✅ Profit factor >2.0

---

## Risk Mitigation

### Top 10 Pitfalls & Mitigations

| # | Pitfall | Risk Level | Mitigation |
|---|---------|------------|------------|
| 1 | **Overfitting** | HIGH | Walk-forward validation, min 385 trades, parameter sensitivity, bootstrap |
| 2 | **Data Snooping Bias** | MEDIUM | Bonferroni correction, holdout sets, CPCV |
| 3 | **Small Sample Issues** | HIGH | Confidence intervals, min sample sizes (10/107/385), Bayesian priors |
| 4 | **Survivorship Bias** | MEDIUM | Include delisted stocks in backtest data |
| 5 | **Look-Ahead Bias** | LOW | Point-in-time snapshots, timestamp validation, purging |
| 6 | **Transaction Costs Underestimation** | MEDIUM | Model 6-8% round-trip for stocks <$10, not 0.3% |
| 7 | **Data Quality Issues** | MEDIUM | Cross-reference sources, validate outliers, handle splits |
| 8 | **Performance Overhead** | LOW | Batch operations, caching, async processing, VectorBT |
| 9 | **Keyword Pollution** | MEDIUM | Strict validation (p<0.05), min 10 occurrences, periodic pruning |
| 10 | **Feedback Loop Instability** | LOW | 7-day cooling period, auto-rollback, exponential backoff |

### Specific Safeguards Implemented

**Against Overfitting:**
```python
# 1. Walk-Forward Validation
- Training: 12-18 months
- Testing: 3-6 months
- Require efficiency >0.6

# 2. Bootstrap Validation
- 10,000 iterations
- Require >70% prob of positive returns

# 3. Minimum Sample Sizes
- 10 for keyword discovery
- 107 for 70% confidence
- 385 for 95% confidence (deployment)

# 4. Parameter Sensitivity
- Test ±20%, ±50% variations
- Require >70% retention
- Monte Carlo robustness score <1.0

# 5. Multiple Validation Periods
- Train/Val/Test splits
- Combinatorial Purged CV
- No single point of failure
```

**Against Transaction Cost Errors:**
```python
# Realistic penny stock costs
TOTAL_COST_PER_TRADE = (
    0.002 * 2  # 0.4% commission round-trip
    + 0.02     # 2% bid-ask spread
    + 0.0075 * 2  # 1.5% slippage round-trip
) = 0.064  # 6.4% total

# Any strategy must overcome this friction
# Profit factor >2.0 required
```

**Against Look-Ahead Bias:**
```python
# Timestamp validation
def validate_no_lookahead(backtest_results, live_results):
    """
    Compare backtest on Jan 2025 data vs
    actual live trading during Jan 2025.

    Discrepancies indicate bias.
    """
    if abs(backtest_sharpe - live_sharpe) > 0.3:
        raise ValueError("Look-ahead bias detected")
```

---

## Appendices

### A. Research Sources

**Academic Papers:**
1. "Trade the Event: Corporate Events Detection for News-Based Event-Driven Trading" - ACL 2021
2. "Event-driven trading and the 'new news'" - Journal of Portfolio Management
3. "Sentiment Analysis in Algorithmic Trading" - ResearchGate 2024
4. "Backtesting Strategies Based on Multiple Signals" - NBER
5. Bailey & López de Prado (2014) - "The Deflated Sharpe Ratio"
6. Almgren (2005) - "Optimal execution of portfolio transactions"

**Industry Resources:**
- QuantStart backtesting guides
- VectorBT documentation
- Backtrader framework
- Trade the Event GitHub implementation

**Libraries:**
- `vectorbt` - Vectorized backtesting
- `backtrader` - Production deployment
- `scikit-learn` - TF-IDF, machine learning
- `scipy` - Statistical tests
- `yfinance` - Free price data
- `spaCy` - NER (future enhancement)

---

### B. Transaction Cost Modeling Details

**Realistic Penny Stock Costs ($5-$10 range):**

| Component | Large-Cap | Penny Stock | Multiplier |
|-----------|-----------|-------------|------------|
| Commission | 0.2% | 0.2% | 1x |
| Bid-Ask Spread | 0.01% | 2-4% | 200-400x |
| Slippage | 0.1% | 0.75-1.5% | 7.5-15x |
| **Round-Trip Total** | **0.3%** | **6-8%** | **20-26x** |

**Implementation:**

```python
def calculate_transaction_costs(entry_price, shares, avg_daily_volume):
    """
    Almgren (2005) market impact model adapted for penny stocks.
    """
    # Commission (fixed)
    commission = shares * entry_price * 0.002  # 0.2%

    # Bid-ask spread (2% for stocks $5-$10)
    spread_cost = shares * entry_price * 0.02  # 2%

    # Slippage (nonlinear with volume)
    order_value = shares * entry_price
    volume_ratio = order_value / avg_daily_volume

    if volume_ratio > 0.05:
        # Reject trades >5% of ADV
        return float('inf')

    slippage = 0.0075 * (volume_ratio ** 0.5)  # Exponential scaling
    slippage_cost = shares * entry_price * slippage

    # Total cost (one-way)
    total_cost = commission + spread_cost + slippage_cost

    # Round-trip
    return total_cost * 2
```

---

### C. Code Integration Points

**Minimal Changes Required:**

**1. feeds.py (Add logging):**
```python
# Line ~800, after classification, before filtering
if score < min_score:
    log_rejected_item(item, 'LOW_SCORE', config)
    continue

if price > price_ceiling:
    log_rejected_item(item, 'HIGH_PRICE', config)
    continue
```

**2. runner.py (Schedule MOA):**
```python
# Line ~150, in main loop
current_hour = datetime.now(timezone.utc).hour

if current_hour == 2:  # 2 AM UTC
    if not ran_moa_today:
        run_moa_analysis()
        ran_moa_today = True
else:
    ran_moa_today = False
```

**3. admin_controls.py (Add MOA section):**
```python
# Line ~400, in generate_admin_report()
if moa_results:
    embed_fields.append({
        'name': '🔍 Missed Opportunities',
        'value': format_moa_summary(moa_results)
    })
```

---

### D. Feature Flag Configuration

```env
# .env additions

# ===== MOA Configuration =====
FEATURE_MOA_ENABLED=1

# Phase 0: Historical Backtesting
FEATURE_WALK_FORWARD=1
FEATURE_BOOTSTRAP_VALIDATION=1
FEATURE_VECTORBT_OPTIMIZATION=1

# Data Capture
MOA_PRICE_MIN=0.10
MOA_PRICE_MAX=10.00
MOA_LOG_FILE=data/rejected_items.jsonl

# Analysis
MOA_MIN_OCCURRENCES=10
MOA_SIGNIFICANCE_LEVEL=0.05
MOA_TIMEFRAMES=1h,4h,24h,1w

# Recommendations
MOA_AUTO_APPROVE_CONFIDENCE=0.90
MOA_MANUAL_REVIEW_CONFIDENCE=0.70
MOA_COOLING_PERIOD_DAYS=7

# Walk-Forward
MOA_WF_TRAINING_MONTHS=12
MOA_WF_TESTING_MONTHS=3
MOA_WF_MIN_EFFICIENCY=0.60

# Bootstrap
MOA_BOOTSTRAP_ITERATIONS=10000
MOA_BOOTSTRAP_MIN_PROB=0.70

# Deployment Thresholds
MOA_MIN_TRADES_DEPLOY=385
MOA_MIN_SHARPE_DEPLOY=1.0
MOA_MIN_F1_DEPLOY=0.40
MOA_MAX_F1_DEPLOY=0.70  # Above = likely overfit

# Rollback
MOA_ROLLBACK_SHARPE_DROP=0.10  # 10%
MOA_ROLLBACK_DD_INCREASE=2.0   # 2x
MOA_ROLLBACK_WR_DROP=0.15      # 15%
```

---

### E. Database Maintenance

**Daily:**
```sql
-- Vacuum rejected_items table
VACUUM ANALYZE rejected_items;

-- Clear old price cache (>7 days)
DELETE FROM price_cache
WHERE fetched_at < NOW() - INTERVAL '7 days';
```

**Weekly:**
```sql
-- Archive old backtests to cold storage
INSERT INTO backtests_archive
SELECT * FROM backtests
WHERE created_at < NOW() - INTERVAL '90 days';

DELETE FROM backtests
WHERE created_at < NOW() - INTERVAL '90 days';
```

**Monthly:**
```sql
-- Aggregate keyword performance stats
INSERT INTO keyword_performance_monthly
SELECT
    DATE_TRUNC('month', last_updated) as month,
    keyword,
    SUM(occurrences) as total_occurrences,
    SUM(hits) as total_hits,
    AVG(avg_return) as avg_monthly_return
FROM keyword_performance
GROUP BY month, keyword;
```

---

## Conclusion

MOA V2 represents a **quantum leap** from the original design. By incorporating institutional-grade backtesting methodologies, you're not just identifying missed trades—you're building a **statistically validated, walk-forward tested, bootstrap-confirmed learning engine** that accelerates your path to profitability.

### Key Innovations

1. **Phase 0 Infrastructure** - Build backtesting foundation FIRST
2. **Walk-Forward Optimization** - 12-18 month training windows with 3-6 month OOS validation
3. **Combinatorial Purged CV** - Superior to simple train/test splits
4. **Bootstrap Validation** - 10,000 iterations for confidence intervals
5. **Multi-Metric Scoring** - F1, Sortino, Calmar, Omega, IC (not just Sharpe)
6. **VectorBT Integration** - 1000x speedup for parameter optimization
7. **Realistic Transaction Costs** - 6-8% modeling for penny stocks
8. **Statistical Rigor** - Min 385 trades, p<0.05, parameter sensitivity
9. **Auto-Rollback** - Safety net if performance degrades
10. **Production-Ready** - Full deployment roadmap with success criteria

### Timeline Summary

- **Weeks 0-2:** Phase 0 (backtesting infrastructure)
- **Weeks 3-4:** Data capture (rejected items logging)
- **Weeks 5-7:** Analysis engine (keyword discovery, validation)
- **Weeks 8-10:** Recommendation engine (Discord integration)
- **Weeks 11-12:** Learning loop (auto-approval, rollback)
- **Weeks 13-14:** Production deployment

**Total:** 14 weeks (3.5 months) from start to full production

### Expected ROI

**6 Months:**
- 20-30 new keywords discovered
- 30-40% reduction in false negatives
- 20-25% Sharpe improvement
- 50% reduction in manual tuning time
- Statistical confidence: 95%+

**1 Year:**
- Institutional-grade backtesting infrastructure
- Fully automated learning loop
- Competitive advantage through proprietary insights
- Foundation for advanced ML models (Phase 2)

---

**This is the blueprint. Now let's build it.**

Ready to start Phase 0?
