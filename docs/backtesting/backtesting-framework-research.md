# Backtesting Framework Research & Recommendations (2025)

## Executive Summary

This document provides comprehensive research on backtesting frameworks and best practices for trading algorithms, based on current 2025 information and industry standards. It covers framework comparisons, implementation strategies, and critical considerations to avoid common pitfalls.

---

## 1. Popular Backtesting Frameworks Comparison

### 1.1 VectorBT

**Status**: Actively developed (Pro version), free version maintained

**Key Features**:
- **Performance**: Fastest Python backtesting library available
- **Architecture**: Vectorized, array-based using NumPy, Pandas, and Numba
- **Speed**: Can process 1,000+ strategy combinations in the time other libraries process one
- **Visualization**: Integrated Plotly and Jupyter Widgets for interactive dashboards
- **Advanced Features**: Supports recursive features like trailing stop losses despite vectorized approach

**Best For**:
- Large-scale strategy testing
- Systematic trading and quantitative research
- Portfolio-level strategies
- Users comfortable with NumPy/Pandas

**Limitations**:
- Steeper learning curve
- Incomplete documentation
- Free version no longer actively developed (PRO version required for latest features)

**Performance Benchmark**: Optimized for testing thousands of strategies simultaneously using near C-level performance via Numba compilation

---

### 1.2 Backtrader

**Status**: Mature, feature-complete (last major release May 2019)

**Key Features**:
- **Architecture**: Event-driven, event-by-event loop
- **Community**: Large, active user base with extensive resources
- **Trading Support**: Live trading connections, complex order types, broker integration
- **Simulation**: Detailed commission, slippage, and order type modeling
- **Documentation**: Extensive, well-documented

**Best For**:
- Users migrating from proprietary platforms (TradeStation, ThinkorSwim)
- Swing traders and discretionary strategy developers
- Strategies requiring live trading integration
- Python learners (intuitive syntax)

**Limitations**:
- Significantly slower than VectorBT for large datasets
- Active development stopped in 2019
- Not suitable for minute-level data across thousands of assets

**Integration**: Supports Alpaca paper trading via `alpaca-backtrader-api` (PyPI)

---

### 1.3 backtesting.py

**Status**: Actively maintained

**Key Features**:
- **Design**: Intuitive, mature library
- **Ease of Use**: Very beginner-friendly
- **Performance**: Better than Backtrader, not as fast as VectorBT
- **Documentation**: Well-documented with clear examples

**Best For**:
- Users wanting balance between ease of use and performance
- Rapid prototyping
- Strategy validation

**Recommendation**: "Both VectorBT and Backtesting.Py are the best backtesting libraries in Python that are currently available. VectorBT is especially useful for performing thousands of iterations incredibly fast, whereas Backtesting.Py is a very intuitive and mature library."

---

### 1.4 Zipline

**Status**: Legacy, no longer actively maintained

**Key Features**:
- **Original Use**: Developed by Quantopian
- **Architecture**: Event-driven

**Current State (2025)**:
- Considered outdated by many traders
- Designed for Python 3.5-3.6
- Installation in 2025 requires workarounds or forks (Zipline-Live)
- Missing key features
- Very slow for large datasets (hours for thousands of assets at minute level)

**Recommendation**: **Not recommended for new projects in 2025**

---

### 1.5 QuantConnect LEAN Engine

**Status**: Actively developed

**Key Features**:
- **Platform**: Cloud-based with local development support
- **Data**: Institutional-grade historical data library
- **Asset Classes**: Multi-asset support (equities, crypto, forex, options, futures)
- **Languages**: Python 3.11 and C#
- **Integration**: Standard data providers and brokerages
- **Community**: 180+ contributors, powers 300+ hedge funds
- **Resources**: Hundreds of open-source examples

**Broker Support**:
- Paper Trading
- Interactive Brokers
- Alpaca (option 16)
- Multiple others

**Best For**:
- Large-scale backtesting and optimization
- Teams requiring professional infrastructure
- Multi-asset strategies
- Users wanting bundled historical data

**Getting Started**:
- Use LEAN CLI for local development
- Command: `lean init` downloads latest config and sample data
- PyPI package: `lean`
- GitHub: https://github.com/QuantConnect/Lean

---

### 1.6 QuantRocket

**Key Features**:
- Python-based platform
- Data collection tools
- Multiple data vendors
- Research environment
- Multiple backtesters
- Live and paper trading via Interactive Brokers

**Best For**: Professional traders requiring comprehensive infrastructure

---

## 2. Framework Selection Matrix

| Framework | Speed | Ease of Use | Live Trading | Active Dev | Best Use Case |
|-----------|-------|-------------|--------------|------------|---------------|
| **VectorBT** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ (Pro) | Large-scale quantitative research |
| **Backtrader** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | Live trading & swing strategies |
| **backtesting.py** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | Rapid prototyping |
| **Zipline** | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | Legacy systems only |
| **LEAN** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Professional multi-asset |

---

## 3. Critical Best Practices to Avoid Bias

### 3.1 Look-Ahead Bias Prevention

**Definition**: Using information that wasn't available at the time a trading decision should have been made.

**Severity**: "Look-ahead is the worst type of bias because the results are wrong."

**Prevention Strategies**:

1. **Point-in-Time Data**
   - Use bitemporal data systems
   - Ensure only data available at decision time is used
   - Never use the close of the same candle to decide a trade at that close

2. **Event-Driven Architecture**
   - Process data sequentially
   - Maintain temporal ordering
   - Respect causality

3. **Technical Indicators**
   - Apply indicators based only on past data
   - Account for realistic trade execution delays

4. **Execution Timing**
   - Use next bar's open instead of current bar's close
   - Model realistic order submission and fill times

**Paranoid Testing Approach**: Be extremely conservative about potential look-ahead bias in every aspect of strategy logic.

---

### 3.2 Overfitting Prevention

**Definition**: Strategy tuned so closely to historical data that it fails in live trading.

**Warning Signs**:
- Sharpe Ratio > 3.0
- Sortino Ratio > 3.0
- "Too perfect" results
- Excessive parameters

**Prevention Strategies**:

1. **Parameter Limitation**
   - Use 2-3 indicators maximum
   - Keep fittable parameters to minimum
   - Avoid indicator overload (max 3-4 per strategy)

2. **Data Segmentation**
   - In-Sample: 70-80% for development
   - Out-of-Sample: 20-30% for validation
   - Test Set: Additional holdout for final validation

3. **Walk-Forward Testing** (see Section 6)
   - Simulate real-time deployment
   - Progressive data incorporation
   - Multiple period validation

4. **Robustness Testing**
   - Test across multiple market regimes
   - Verify performance in different timeframes
   - Ensure strategy works across related instruments

5. **Simplicity Principle**
   - Simpler strategies often generalize better
   - Complex strategies are more prone to overfitting
   - Keep "what is robust across periods"

---

### 3.3 Additional Critical Biases

**Survivorship Bias**:
- Include delisted stocks in backtests
- Account for companies that went bankrupt
- Use complete historical datasets

**Selection Bias**:
- Don't cherry-pick instruments that worked
- Test on universe selection criteria
- Use systematic selection rules

**Data Snooping Bias**:
- Limit strategy iterations on same data
- Track number of tested variations
- Penalize for multiple testing

---

## 4. Transaction Costs and Slippage Modeling

### 4.1 Impact on Returns

**Key Finding**: "Including realistic slippage can trim simulated returns by 0.5-3 percent per year"

**Critical**: Small edges can vanish once costs are modeled, especially for high-frequency strategies.

---

### 4.2 Slippage Modeling Approaches

**1. Volume-Based Models**
- Guideline: "When a trade constitutes 1% of Average Daily Volume, the price tends to shift by about 10 basis points"
- Scale impact based on order size relative to liquidity

**2. Volatility-Adjusted Models**
- Increase slippage during high volatility periods
- Use regime-dependent slippage parameters
- Model spread widening in volatile markets

**3. Liquidity Analysis**
- Skip trades that exceed market capacity
- Model realistic volumes and spreads
- Account for market impact

**4. Order Book Simulation**
- Most realistic approach
- Simulate limit order fills
- Model partial fills and queue position

---

### 4.3 Transaction Cost Components

**Direct Costs**:
- Commission fees
- Exchange fees
- Regulatory fees
- Clearing fees

**Indirect Costs**:
- Bid-ask spread
- Market impact (temporary and permanent)
- Timing cost (delay between signal and execution)

**Cryptocurrency Specific**:
- Maker/taker fee structures
- Network fees (on-chain)
- Withdrawal fees
- Spread increases on smaller exchanges

---

### 4.4 Implementation Recommendations

**Conservative Approach**:
- Use variable slippage models
- Include worst-case scenarios
- Model venue-specific liquidity
- Account for trade frequency impact

**Framework Support**:
- QuantConnect LEAN: Built-in slippage models with customization
- Backtrader: Detailed commission and slippage modeling
- VectorBT: Custom fee/slippage functions

---

## 5. Paper Trading Integration

### 5.1 Alpaca Paper Trading

**Features**:
- Free paper trading environment
- Full API access
- Web dashboard tracking
- Default: $100k starting balance (customizable)
- Easy reset functionality

**Integration Support**:
- **Backtrader**: `alpaca-backtrader-api` (PyPI)
- **LEAN**: Native support (option 16)
- **QuantRocket**: Via LEAN integration

**Advantages**:
- Python-first design
- Simple REST APIs
- Quick flip between paper and live
- U.S. equities focus

**Setup**: Straightforward, minimal configuration required

---

### 5.2 Interactive Brokers Paper Trading

**Features**:
- Professional-grade paper trading
- Full platform access
- Complex order types
- Multi-asset support

**Integration Support**:
- **LEAN**: Native support
- **QuantRocket**: Direct integration
- **Backtrader**: Community support

**Complexity**: More complex setup than Alpaca

---

### 5.3 Best Practices for Paper Trading

**1. Realistic Testing**
- Use similar position sizes to intended live trading
- Test during market hours with real market data
- Include all transaction costs

**2. Transition Strategy**
- Backtest → Paper Trade → Small Live → Full Live
- Verify all execution logic in paper trading
- Test error handling and edge cases

**3. Monitoring**
- Track fill quality vs. backtests
- Monitor slippage differences
- Validate order execution timing

**4. Common Pitfalls**
- Paper trading often has perfect fills (unrealistic)
- No real market impact
- May not account for liquidity constraints
- Position limits may differ from live

---

## 6. Trading Strategy Evaluation Metrics

### 6.1 Sharpe Ratio

**Formula**: (Return - Risk-Free Rate) / Standard Deviation

**Interpretation**:
- > 1.0: Good
- > 1.5: Very good (2025 target)
- > 2.0: Excellent
- > 3.0: Suspicious (potential overfitting)

**Advantages**:
- Most widely used metric
- Easy to understand
- Enables strategy comparison

**Limitations**:
- Treats all volatility as risk (upside and downside)
- Distorts evaluation for asymmetric strategies
- Assumes normal distribution of returns

**Best Practice**: "The Sharpe Ratio serves as an effective tool for strategy comparison yet its true value emerges when used alongside drawdowns and risk-adjusted returns"

---

### 6.2 Sortino Ratio

**Formula**: (Return - Risk-Free Rate) / Downside Deviation

**Key Difference**: Only penalizes downside volatility

**Interpretation**:
- Better for asymmetric strategies
- More appropriate for trend-following systems
- > 2.0: Good
- > 3.0: Excellent (but check for overfitting)

**Advantages**:
- Focuses on harmful volatility
- Better for strategies with significant upside
- More intuitive risk measurement

---

### 6.3 Calmar Ratio

**Formula**: Annual Return / Maximum Drawdown

**Interpretation**:
- > 1.0: Target minimum
- > 2.0: Elite systems
- Evaluates return vs. worst loss

**Advantages**:
- Direct measure of return per unit of worst-case loss
- Easy to understand
- Independent of volatility assumptions

---

### 6.4 Maximum Drawdown

**Definition**: Biggest drop from peak to trough

**Targets**:
- < 15-20%: Acceptable for most strategies
- < 10%: Conservative
- > 25%: High risk

**Importance**: Shows worst-case scenario traders may face

**Related Metrics**:
- Average Drawdown
- Drawdown Duration
- Recovery Time

---

### 6.5 Additional Important Metrics

**Profit Factor**:
- Gross Profits / Gross Losses
- Target: 1.5 - 2.0 (realistic and sustainable)
- > 2.0: Excellent
- < 1.5: Questionable

**Win Rate**:
- Percentage of winning trades
- Must be evaluated with avg win/loss ratio
- High win rate ≠ profitable strategy

**Expectancy**:
- (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
- Positive expectancy required for profitability

**Alpha & Beta**:
- Alpha: Return beyond market
- Beta: Correlation with market
- Market-neutral strategies target beta ≈ 0

**R-Squared**:
- Measures strategy independence from benchmark
- Low R² = unique strategy

---

### 6.6 Comprehensive Evaluation Framework

**Minimum Metrics Set**:
1. Total Return
2. Sharpe Ratio (> 1.5)
3. Maximum Drawdown (< 15-20%)
4. Profit Factor (> 1.5)
5. Number of Trades (sufficient sample size)

**Advanced Analysis**:
6. Sortino Ratio
7. Calmar Ratio
8. Recovery Time
9. Rolling Sharpe
10. Monthly/Yearly consistency

**Risk Metrics**:
11. Value at Risk (VaR)
12. Conditional VaR (Expected Shortfall)
13. Tail Ratio
14. Worst Day/Week/Month

---

## 7. Walk-Forward Optimization & Cross-Validation

### 7.1 Why Walk-Forward Optimization is Critical

**Industry Consensus**: "Walk-forward analysis is now widely considered the 'gold standard' in trading strategy validation" (2025)

**Problem Solved**: Single out-of-sample validation can be "potentially lucky" - walk-forward reduces this risk

**Key Benefit**: Mimics real-world deployment where parameters are periodically re-optimized

---

### 7.2 Walk-Forward Optimization Process

**Basic Structure**:

1. **Divide Data into Periods**
   - Multiple sequential time windows
   - Each window has In-Sample (IS) and Out-of-Sample (OOS)
   - Typical split: 80% IS, 20% OOS

2. **Optimization Loop**:
   ```
   Period 1: Optimize on IS₁ → Test on OOS₁
   Period 2: Optimize on IS₂ → Test on OOS₂
   Period 3: Optimize on IS₃ → Test on OOS₃
   ...
   Combine all OOS results for final performance
   ```

3. **Rolling Windows**:
   - Fixed window: Use last N days for IS
   - Expanding window: Use all historical data for IS
   - Anchored: Fixed start date, expanding end

**Example Configuration**:
- Total data: 5 years
- Window size: 1 year IS + 3 months OOS
- Advance: 3 months
- Result: ~16 walk-forward periods

---

### 7.3 Cross-Validation vs Walk-Forward

**Traditional K-Fold Cross-Validation**:
- ❌ Breaks temporal ordering
- ❌ Violates causality
- ❌ Invites data leakage
- ❌ **Not suitable for time-series trading data**

**Walk-Forward Testing**:
- ✅ Respects temporal ordering
- ✅ Maintains causality
- ✅ Mimics production deployment
- ✅ **Recommended for all trading strategies**

**Exception**: Purged K-Fold cross-validation (advanced technique that respects time ordering)

---

### 7.4 Implementation Guidelines

**1. Period Selection**
- Longer IS periods: More stable parameters, less adaptive
- Shorter IS periods: More adaptive, risk of overfitting to noise
- Balance based on strategy frequency and market regime changes

**2. Reoptimization Frequency**
- Monthly: High-frequency strategies
- Quarterly: Medium-frequency strategies
- Annually: Low-frequency strategies

**3. Parameter Stability**
- Track how parameters change across windows
- Large changes indicate instability
- Prefer strategies with stable optimal parameters

**4. OOS Performance**
- OOS results should be ~70-90% of IS results
- Huge gap indicates overfitting
- Better OOS than IS indicates luck or selection bias

---

### 7.5 Machine Learning Specific Considerations

**2025 Best Practices**:
- Rolling train/validation/test sets
- Retrain periodically using rolling windows
- Mitigate overfitting through temporal validation

**Data Segmentation for ML**:
- Training Set: 60-70%
- Validation Set: 15-20%
- Test Set: 15-20%
- All sets must maintain temporal order

**Feature Engineering**:
- Features must only use past data
- No future information in feature calculation
- Respect look-ahead bias in feature construction

---

### 7.6 Framework Support

**QuantConnect LEAN**:
- Built-in walk-forward optimization
- Automated parameter sweeping
- Cloud-based parallel execution

**StrategyQuant**:
- Native walk-forward testing
- Visual performance analysis

**Custom Implementation**:
- Easy to implement with Python
- Control over all aspects
- Recommended for VectorBT, Backtrader, backtesting.py

---

## 8. Recommended Backtesting Setup

### 8.1 For Quantitative/Systematic Trading

**Framework**: VectorBT (Pro version recommended)

**Workflow**:
1. **Data Preparation**
   - Clean, point-in-time data
   - Multiple assets for robustness testing
   - Sufficient history (5+ years recommended)

2. **Strategy Development**
   - Rapid iteration using vectorized backtests
   - Test thousands of parameter combinations
   - Focus on simple, explainable strategies

3. **Validation**
   - Walk-forward optimization (5-10 periods)
   - Out-of-sample testing
   - Multiple market regimes

4. **Cost Modeling**
   - Conservative slippage (0.05-0.1% for liquid markets)
   - Realistic commissions
   - Market impact for larger positions

5. **Metric Evaluation**
   - Target Sharpe > 1.5
   - Max Drawdown < 15%
   - Profit Factor > 1.5
   - Consistent across OOS periods

6. **Paper Trading**
   - Alpaca integration for US equities
   - 1-3 months paper trading
   - Compare vs. backtest results

---

### 8.2 For Discretionary/Swing Trading

**Framework**: Backtrader

**Workflow**:
1. **Strategy Implementation**
   - Event-driven logic
   - Complex order types
   - Position sizing rules

2. **Backtesting**
   - Detailed commission/slippage modeling
   - Realistic order execution
   - Indicator calculation on past data only

3. **Validation**
   - Multiple time periods
   - Different market conditions
   - Walk-forward analysis

4. **Paper Trading**
   - Direct broker integration (Alpaca or IB)
   - Real-time strategy execution
   - Manual override capability

5. **Live Trading**
   - Seamless transition from paper
   - Same codebase
   - Minimal changes required

---

### 8.3 For Professional/Multi-Asset Trading

**Framework**: QuantConnect LEAN

**Workflow**:
1. **Cloud Development**
   - Access to institutional data
   - Multiple asset classes
   - Parallel backtesting

2. **Local Development**
   - LEAN CLI for strategy development
   - Version control integration
   - Custom data sources

3. **Optimization**
   - Built-in parameter optimization
   - Walk-forward analysis
   - Cloud-based parallel execution

4. **Broker Integration**
   - Multiple broker support
   - Paper trading
   - Live trading deployment

5. **Production**
   - Monitoring and alerting
   - Performance tracking
   - Risk management

---

### 8.4 For Rapid Prototyping

**Framework**: backtesting.py

**Workflow**:
1. **Quick Implementation**
   - Intuitive API
   - Fast iteration
   - Clear documentation

2. **Initial Testing**
   - Basic parameter sweep
   - Visual analysis
   - Quick validation

3. **Transition**
   - Move to VectorBT for scale
   - Or Backtrader for live trading
   - Or continue if sufficient

---

## 9. Critical Checklist Before Live Trading

### 9.1 Strategy Validation
- [ ] Walk-forward optimization completed
- [ ] Out-of-sample results acceptable (70-90% of in-sample)
- [ ] Tested across multiple market regimes
- [ ] Sharpe Ratio > 1.5 in OOS
- [ ] Maximum Drawdown < 15-20%
- [ ] Profit Factor > 1.5
- [ ] No look-ahead bias verified
- [ ] Overfitting checks passed (no Sharpe > 3.0)

### 9.2 Implementation Validation
- [ ] Transaction costs modeled realistically
- [ ] Slippage modeled conservatively
- [ ] Order execution logic tested
- [ ] Position sizing verified
- [ ] Risk management rules implemented
- [ ] All edge cases handled

### 9.3 Paper Trading
- [ ] Minimum 1-3 months paper trading
- [ ] Performance matches backtest expectations
- [ ] Slippage within expected range
- [ ] Order fills working correctly
- [ ] Error handling verified
- [ ] Monitoring and alerts functioning

### 9.4 Risk Management
- [ ] Maximum position size defined
- [ ] Maximum portfolio drawdown limit
- [ ] Daily loss limit set
- [ ] Correlation limits (if multiple strategies)
- [ ] Emergency stop procedures
- [ ] Manual override capability

### 9.5 Operational
- [ ] Monitoring dashboard setup
- [ ] Alert system configured
- [ ] Logging implemented
- [ ] Backup systems ready
- [ ] Kill switch available
- [ ] Contact list for issues

---

## 10. Common Pitfalls Summary

### High Priority Issues
1. **Look-ahead bias** - Most critical error
2. **Overfitting** - Use walk-forward optimization
3. **Ignoring transaction costs** - Can eliminate small edges
4. **Insufficient out-of-sample testing** - Single OOS period is risky
5. **Perfect fills in backtesting** - Model realistic slippage

### Medium Priority Issues
6. **Survivorship bias** - Include delisted stocks
7. **Data snooping** - Testing too many variations
8. **Parameter instability** - Parameters shouldn't change drastically
9. **Small sample size** - Need sufficient trades for statistical significance
10. **Ignoring market regimes** - Test in bull, bear, and sideways markets

### Monitoring Issues
11. **Paper trading != live trading** - Real fills differ from paper
12. **Market impact** - Larger orders have greater impact
13. **Changing market conditions** - Strategies can stop working
14. **Over-optimization** - Simpler is often better
15. **Ignoring correlations** - Multiple strategies may be redundant

---

## 11. Modern Developments (2025)

### Emerging Trends
- **VectorBT Pro**: Professional features for vectorized backtesting
- **Cloud-based backtesting**: LEAN continues to lead
- **ML integration**: Walk-forward validation critical for ML strategies
- **Order book simulation**: More realistic execution modeling
- **Regime detection**: Adaptive strategies based on market conditions

### Deprecated Tools
- **Zipline**: No longer maintained, not recommended
- **Quantopian**: Shut down, historical reference only

### Active Communities
- **QuantConnect**: Large community, regular updates
- **VectorBT**: Growing community, active development (Pro)
- **Backtrader**: Mature, stable community

---

## 12. Recommended Resources

### Documentation
- **VectorBT**: https://vectorbt.dev/
- **Backtrader**: https://www.backtrader.com/
- **backtesting.py**: https://kernc.github.io/backtesting.py/
- **LEAN**: https://www.quantconnect.com/docs/
- **Alpaca**: https://docs.alpaca.markets/

### GitHub Repositories
- **LEAN**: https://github.com/QuantConnect/Lean
- **VectorBT**: https://github.com/polakowo/vectorbt
- **Backtrader**: https://github.com/mementum/backtrader
- **backtesting.py**: https://github.com/kernc/backtesting.py

### PyPI Packages
- `vectorbt` / `vectorbt-pro`
- `backtrader`
- `backtesting`
- `lean`
- `alpaca-backtrader-api`

---

## 13. Final Recommendations

### For This Project (Catalyst Bot)

**Recommended Stack**:
1. **Primary Framework**: VectorBT or backtesting.py
   - VectorBT if you need to test many parameter combinations
   - backtesting.py if you prefer simplicity and intuitive API

2. **Paper Trading**: Alpaca
   - Easy integration
   - Free paper trading
   - Good for US equities

3. **Validation Methodology**:
   - Walk-forward optimization (mandatory)
   - Conservative cost modeling
   - Minimum 3 months paper trading
   - Track all metrics in Section 6

4. **Risk Management**:
   - Start with small position sizes
   - Strict drawdown limits (< 15%)
   - Daily loss limits
   - Regular performance reviews

### Development Workflow

```
1. Strategy Design (Simple, explainable)
   ↓
2. Backtest with VectorBT/backtesting.py
   ↓
3. Walk-Forward Optimization (5-10 periods)
   ↓
4. Verify metrics (Sharpe > 1.5, DD < 15%, PF > 1.5)
   ↓
5. Check for biases (Look-ahead, overfitting)
   ↓
6. Paper trading with Alpaca (1-3 months)
   ↓
7. Compare paper vs backtest performance
   ↓
8. Small live position (if paper successful)
   ↓
9. Scale gradually
   ↓
10. Continuous monitoring and validation
```

### Success Criteria

Before going live, ensure:
- Walk-forward OOS Sharpe > 1.5
- Maximum Drawdown < 15%
- Paper trading results within 20% of backtest
- No look-ahead bias
- Conservative cost assumptions
- All risk limits tested
- Kill switch functional

---

## Conclusion

Backtesting is both an art and a science. The frameworks available in 2025 are mature and capable, but success depends on:

1. **Choosing the right tool** for your use case
2. **Following best practices** to avoid bias
3. **Conservative assumptions** about costs and execution
4. **Rigorous validation** through walk-forward analysis
5. **Proper paper trading** before risking capital
6. **Continuous monitoring** and adaptation

The most sophisticated backtesting framework won't save a bad strategy, but a good framework with proper methodology can help validate potentially profitable strategies and avoid costly mistakes.

Remember: "If results look too perfect, check for overfitting, missing fees, or unrealistic fills."

---

*Document compiled: 2025-11-20*
*Based on current industry best practices and tool availability*
