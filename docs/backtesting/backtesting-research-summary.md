# Backtesting Research Summary

## Overview

This research provides comprehensive guidance on backtesting frameworks and systems for trading algorithms, based on current 2025 best practices and tools.

## Documents Created

1. **backtesting-framework-research.md** - Comprehensive framework analysis, best practices, and recommendations
2. **backtesting-implementation-guide.md** - Practical code examples and implementation patterns

---

## Key Findings

### Top Framework Recommendations (2025)

| Use Case | Recommended Framework | Key Reason |
|----------|----------------------|------------|
| **Rapid Prototyping** | backtesting.py | Intuitive, easy to learn |
| **Large-Scale Testing** | VectorBT | Fastest, vectorized operations |
| **Live Trading Integration** | Backtrader | Seamless broker connections |
| **Professional/Multi-Asset** | QuantConnect LEAN | Institutional-grade infrastructure |
| **Legacy Systems** | ~~Zipline~~ | Not recommended (unmaintained) |

### Critical Best Practices

1. **Avoid Look-Ahead Bias**
   - Use only point-in-time data
   - Never use current bar close for decisions
   - Implement event-driven architecture

2. **Prevent Overfitting**
   - Limit parameters (2-3 indicators max)
   - Use walk-forward optimization (gold standard)
   - Reserve 20-30% for out-of-sample testing
   - Sharpe > 3.0 is suspicious

3. **Model Costs Realistically**
   - Slippage can reduce returns by 0.5-3% annually
   - Use volume-based slippage models
   - Include all commission structures

4. **Validate Thoroughly**
   - Walk-forward optimization is mandatory
   - OOS performance should be 70-90% of IS
   - Test across multiple market regimes

### Performance Metrics Targets

| Metric | Good | Excellent | Suspicious |
|--------|------|-----------|------------|
| **Sharpe Ratio** | > 1.5 | > 2.0 | > 3.0 |
| **Max Drawdown** | < 15-20% | < 10% | - |
| **Profit Factor** | > 1.5 | > 2.0 | - |
| **Sortino Ratio** | > 2.0 | > 3.0 | - |
| **Calmar Ratio** | > 1.0 | > 2.0 | - |

---

## Recommended Setup for Catalyst Bot

### Phase 1: Development & Backtesting

**Framework**: VectorBT or backtesting.py
- VectorBT for testing multiple parameter combinations
- backtesting.py for simpler, more intuitive development

**Data Source**:
- Yahoo Finance (yfinance) for historical data
- Minimum 5 years of data recommended

**Validation**:
- Walk-forward optimization with 5-10 periods
- In-sample: 80%, Out-of-sample: 20%
- Rebalance every 3 months

### Phase 2: Paper Trading

**Broker**: Alpaca Paper Trading
- Free, unlimited paper trading
- Easy Python integration
- Quick switch to live trading

**Integration**:
- Backtrader + alpaca-backtrader-api (PyPI)
- Or QuantConnect LEAN with Alpaca support

**Duration**: 1-3 months minimum
- Verify execution logic
- Compare vs backtest performance
- Test error handling

### Phase 3: Live Trading (Small Scale)

**Initial Capital**: Start with small position sizes
- Test with minimal capital first
- Gradually scale as performance validates

**Risk Management**:
- Maximum 2% risk per trade
- Daily loss limit: 5%
- Maximum drawdown: 15%
- Position size limits

### Phase 4: Monitoring & Adaptation

**Metrics to Track**:
- Daily/weekly Sharpe ratio
- Rolling drawdown
- Slippage vs expectations
- Fill quality
- Strategy correlation

**Reoptimization**:
- Monthly for high-frequency strategies
- Quarterly for medium-frequency
- Track parameter stability

---

## Walk-Forward Optimization (Mandatory)

### Why It's Critical

Industry consensus (2025): "Walk-forward analysis is the gold standard in trading strategy validation"

### Implementation

```
Period 1: Train on Year 1-2 → Test on Quarter 1 of Year 3
Period 2: Train on Year 1-3 → Test on Quarter 2 of Year 3
Period 3: Train on Year 2-3 → Test on Quarter 3 of Year 3
...
Combine all test results for final performance
```

### Key Benefits
- Mimics real-world deployment
- Reduces overfitting risk
- Tests adaptability across regimes
- More reliable than single OOS test

---

## Transaction Cost Modeling

### Conservative Assumptions

**For US Equities**:
- Commission: 0.1% (0.001)
- Slippage: 0.1% (0.001)
- Total round-trip cost: ~0.4%

**For Cryptocurrency**:
- Maker fees: 0.1-0.2%
- Taker fees: 0.2-0.4%
- Slippage: 0.1-0.5% (depending on liquidity)
- Total round-trip cost: 0.5-1.5%

### Volume-Based Slippage Rule

"When a trade constitutes 1% of Average Daily Volume, price tends to shift by about 10 basis points"

---

## Implementation Checklist

### Before Development
- [ ] Choose appropriate framework for use case
- [ ] Set up data pipeline (yfinance, Alpha Vantage, etc.)
- [ ] Define strategy logic clearly
- [ ] Limit indicators to 2-3 maximum

### During Development
- [ ] Implement strict no-look-ahead rules
- [ ] Use only past data in all calculations
- [ ] Model realistic transaction costs
- [ ] Calculate comprehensive metrics

### Validation Phase
- [ ] Implement walk-forward optimization
- [ ] Verify OOS Sharpe > 1.5
- [ ] Check Max Drawdown < 15%
- [ ] Ensure Profit Factor > 1.5
- [ ] Validate sufficient sample size (30+ trades)
- [ ] Test across different market conditions

### Paper Trading
- [ ] Set up Alpaca paper account
- [ ] Integrate strategy with paper trading
- [ ] Run for 1-3 months minimum
- [ ] Compare performance vs backtest
- [ ] Verify slippage within expectations
- [ ] Test all error handling

### Pre-Live Deployment
- [ ] All validation metrics met
- [ ] Paper trading successful
- [ ] Risk management rules implemented
- [ ] Stop-loss mechanisms tested
- [ ] Emergency kill switch ready
- [ ] Monitoring dashboard configured

---

## Common Pitfalls to Avoid

### Critical Errors
1. Look-ahead bias (most severe)
2. Ignoring transaction costs
3. Single out-of-sample test
4. Overfitting (too many parameters)
5. Perfect fills assumption

### Medium Priority
6. Survivorship bias
7. Data snooping
8. Small sample size
9. Parameter instability
10. Ignoring market regimes

### Operational Issues
11. No paper trading
12. Insufficient monitoring
13. No kill switch
14. Ignoring correlations
15. Over-optimization

---

## Code Examples Location

All practical code examples are in `backtesting-implementation-guide.md`:

- VectorBT: Basic strategies, walk-forward, multi-asset
- backtesting.py: Strategy templates, risk management
- Backtrader: Basic strategies, Alpaca integration
- QuantConnect LEAN: Algorithm templates, momentum rotation
- Common patterns: Data loading, metrics, position sizing

---

## Framework Comparison Quick Reference

### VectorBT
- **Speed**: ⭐⭐⭐⭐⭐ (Fastest)
- **Ease**: ⭐⭐⭐ (Moderate learning curve)
- **Live Trading**: ⭐⭐ (Limited, requires StrateQueue)
- **Best For**: Large-scale parameter optimization

### backtesting.py
- **Speed**: ⭐⭐⭐ (Good)
- **Ease**: ⭐⭐⭐⭐⭐ (Very intuitive)
- **Live Trading**: ⭐⭐ (Limited)
- **Best For**: Rapid prototyping, learning

### Backtrader
- **Speed**: ⭐⭐ (Slower)
- **Ease**: ⭐⭐⭐⭐ (User-friendly)
- **Live Trading**: ⭐⭐⭐⭐⭐ (Excellent broker support)
- **Best For**: Transitioning to live trading

### QuantConnect LEAN
- **Speed**: ⭐⭐⭐⭐ (Fast, cloud-based)
- **Ease**: ⭐⭐⭐ (Professional complexity)
- **Live Trading**: ⭐⭐⭐⭐⭐ (Institutional-grade)
- **Best For**: Professional multi-asset strategies

---

## Resources

### Documentation
- VectorBT: https://vectorbt.dev/
- backtesting.py: https://kernc.github.io/backtesting.py/
- Backtrader: https://www.backtrader.com/
- LEAN: https://www.quantconnect.com/docs/
- Alpaca: https://docs.alpaca.markets/

### GitHub Repositories
- VectorBT: https://github.com/polakowo/vectorbt
- backtesting.py: https://github.com/kernc/backtesting.py
- Backtrader: https://github.com/mementum/backtrader
- LEAN: https://github.com/QuantConnect/Lean

### Key PyPI Packages
```bash
pip install vectorbt
pip install backtesting
pip install backtrader
pip install lean
pip install alpaca-backtrader-api
pip install yfinance
pip install ta-lib
```

---

## Next Steps for Implementation

### Immediate (Week 1)
1. Choose framework (recommend: backtesting.py or VectorBT)
2. Set up development environment
3. Implement simple strategy (MA crossover)
4. Calculate basic metrics

### Short Term (Weeks 2-4)
1. Implement walk-forward optimization
2. Test multiple strategies
3. Refine transaction cost modeling
4. Set up Alpaca paper account

### Medium Term (Months 2-3)
1. Paper trade top strategies
2. Monitor performance daily
3. Compare vs backtest expectations
4. Refine risk management

### Long Term (Month 4+)
1. Small live deployment (if paper successful)
2. Continuous monitoring
3. Quarterly reoptimization
4. Scale gradually

---

## Risk Warnings

1. **Past performance does not guarantee future results**
2. **All backtests are approximations** - real trading differs
3. **Market conditions change** - strategies can stop working
4. **Start small** - test with capital you can afford to lose
5. **Never skip paper trading** - it catches many issues
6. **Monitor continuously** - automated ≠ unattended

---

## Final Recommendation

**For Catalyst Bot Project**:

1. **Development**: Use **VectorBT** or **backtesting.py**
   - VectorBT if you need to test many strategies quickly
   - backtesting.py if you prefer simplicity

2. **Validation**: Mandatory walk-forward optimization
   - 5-10 periods
   - 80/20 in-sample/out-of-sample split

3. **Paper Trading**: Use **Alpaca**
   - 1-3 months minimum
   - Verify performance matches backtest

4. **Live Trading**: Start extremely small
   - Gradual scaling only after proven success
   - Strict risk limits

5. **Monitoring**: Track all metrics
   - Daily performance review
   - Quarterly strategy reoptimization
   - Immediate kill switch if issues arise

---

**Remember**: The goal of backtesting is not to find the perfect strategy, but to avoid the catastrophically bad ones and validate that your edge is real and sustainable.

Good luck with your implementation!

---

*Research compiled: 2025-11-20*
*All information based on current 2025 best practices*
