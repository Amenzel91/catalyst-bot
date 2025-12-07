# Legacy System to TradingEngine Migration Plan

**Project:** Catalyst Bot - Trading System Consolidation
**Version:** 1.0
**Date:** 2025-11-26
**Status:** Ready for Review & Approval

---

## 📋 Executive Summary

### Current State
You have **TWO trading systems** running in parallel:
- **Legacy System**: `paper_trader.py` + `alpaca_wrapper.py` (synchronous, simple, CURRENTLY ACTIVE)
- **TradingEngine**: Modern async system (feature-rich, NOT connected to alerts)

### Migration Goal
Transition from legacy `execute_paper_trade()` to production-ready `TradingEngine` while:
- ✅ Maintaining 100% uptime (zero-downtime migration)
- ✅ Preserving existing positions and trade history
- ✅ Leveraging existing extended hours support (just implemented!)
- ✅ Adding advanced risk management and portfolio tracking
- ✅ Enabling future ML integration path

### Timeline
**Estimated Duration:** 2-3 weeks (with supervisor agent orchestration)

- **Week 1**: Research, architecture, adapter layer
- **Week 2**: Implementation, testing, parallel run
- **Week 3**: Validation, cutover, deprecation

### Success Criteria
- [ ] All alerts route through TradingEngine
- [ ] Legacy system deprecated and removed
- [ ] 100% backward compatibility with existing alerts
- [ ] Extended hours trading works correctly
- [ ] Zero data loss during migration
- [ ] All tests passing (95%+ coverage)

---

## 🏗️ Supervisor Agent Architecture

### Supervisor Agent Role
The **Supervisor Agent** orchestrates the entire migration by:
1. Creating and maintaining a **Migration Knowledge Base** (concise documentation)
2. Recruiting specialized agents for each phase
3. Ensuring consistency across all deliverables
4. Validating each milestone before proceeding
5. Maintaining a **single source of truth** for all agents

### Agent Team Structure

```
┌─────────────────────────────────────────────────────────┐
│                   SUPERVISOR AGENT                      │
│                                                         │
│  • Creates Migration Knowledge Base (MIGRATION_KB.md)  │
│  • Recruits & coordinates sub-agents                   │
│  • Validates all deliverables                          │
│  • Maintains implementation log                        │
└─────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┬────────────────┐
          │               │               │                │
┌─────────▼─────┐  ┌──────▼──────┐  ┌────▼─────┐  ┌──────▼──────┐
│   RESEARCH    │  │ ARCHITECTURE│  │  CODING  │  │   TESTING   │
│     AGENT     │  │    AGENT    │  │   AGENT  │  │    AGENT    │
└───────────────┘  └─────────────┘  └──────────┘  └─────────────┘
     │                   │                │              │
     ▼                   ▼                ▼              ▼
  Analyzes           Designs           Implements    Validates
  Current State      Migration         Code          Changes
  Documents          Architecture      Changes       & Tests
  Dependencies       Creates ADRs      Refactors     Coverage
```

### Migration Knowledge Base (MIGRATION_KB.md)

**Purpose**: Single source of truth for ALL agents
**Location**: `docs/migration/MIGRATION_KB.md`
**Length**: Maximum 500 lines (concise, actionable)

**Contents**:
1. **System Overview** (50 lines)
   - Legacy system architecture
   - TradingEngine architecture
   - Key differences

2. **Migration Strategy** (100 lines)
   - Phased approach
   - Risk mitigation
   - Rollback procedures

3. **Implementation Guidelines** (150 lines)
   - Code patterns
   - Testing requirements
   - Integration points

4. **Agent Instructions** (100 lines)
   - Research agent tasks
   - Architecture agent decisions
   - Coding agent standards
   - Testing agent criteria

5. **Progress Tracking** (100 lines)
   - Milestones
   - Blockers
   - Decisions log

---

## 📊 Migration Phases

### Phase 1: Discovery & Documentation (Week 1, Days 1-2)
**Supervisor recruits: RESEARCH AGENT**

**Objectives**:
- Analyze current alert → order flow in detail
- Document all integration points
- Identify migration risks and dependencies
- Create comprehensive mapping document

**Deliverables**:
- `docs/migration/CURRENT_STATE_ANALYSIS.md` (Research Agent)
- `docs/migration/INTEGRATION_POINTS.md` (Research Agent)
- `docs/migration/RISK_MATRIX.md` (Research Agent)
- Updated `MIGRATION_KB.md` with findings (Supervisor)

**Research Agent Tasks**:
```markdown
## Research Agent Instructions (from MIGRATION_KB.md)

### Task 1: Analyze Alert Flow
1. Trace code path from `runner.py` → `alerts.py` → `execute_paper_trade()`
2. Document all parameters passed
3. Identify any data transformations
4. Map to `ScoredItem` → `TradingSignal` conversion

### Task 2: Document Dependencies
1. List all modules importing `paper_trader`
2. Check for shared state or global variables
3. Document database interactions
4. Identify logging patterns

### Task 3: Risk Analysis
1. Identify potential breaking changes
2. Document rollback procedures
3. List critical path operations
4. Estimate downtime (goal: zero)

**Output**: CURRENT_STATE_ANALYSIS.md (max 200 lines)
```

---

### Phase 2: Architecture Design (Week 1, Days 3-4)
**Supervisor recruits: ARCHITECTURE AGENT**

**Objectives**:
- Design signal adapter layer (ScoredItem → TradingSignal)
- Create feature flag mechanism for gradual rollout
- Design backward compatibility layer
- Document migration architecture

**Deliverables**:
- `docs/migration/ARCHITECTURE_DESIGN.md` (Architecture Agent)
- `docs/migration/ADR-001-signal-adapter.md` (Architecture Decision Record)
- `docs/migration/ADR-002-feature-flags.md`
- Updated `MIGRATION_KB.md` with architecture (Supervisor)

**Architecture Agent Tasks**:
```markdown
## Architecture Agent Instructions (from MIGRATION_KB.md)

### Task 1: Design Signal Adapter
**Challenge**: Convert `ScoredItem` (from alerts.py) → `TradingSignal` (TradingEngine)

**Requirements**:
- Zero data loss
- Preserve all existing alert metadata
- Support extended hours parameter
- Async-compatible

**Design**:
```python
# src/catalyst_bot/adapters/signal_adapter.py
class SignalAdapter:
    """Converts ScoredItem to TradingSignal for TradingEngine."""

    @staticmethod
    def from_scored_item(
        item: ScoredItem,
        entry_price: Decimal,
        quantity: int
    ) -> TradingSignal:
        """
        Convert ScoredItem to TradingSignal.

        Mapping:
        - item.ticker → signal.ticker
        - item.score → signal.confidence
        - item.alert_id → signal.signal_id
        - item.metadata → signal.metadata
        """
        pass
```

### Task 2: Feature Flag System
**Challenge**: Enable gradual rollout (1% → 10% → 50% → 100%)

**Design**:
```python
# src/catalyst_bot/config.py
# Add new settings
use_trading_engine: bool = _b("USE_TRADING_ENGINE", False)
trading_engine_rollout_pct: int = _i("TRADING_ENGINE_ROLLOUT_PCT", 0)
```

### Task 3: Migration Architecture
**Flow Diagram**:
```
Current Flow:
  Alert → execute_paper_trade() → AlpacaBrokerWrapper → Order

New Flow:
  Alert → SignalAdapter → TradingEngine → OrderExecutor → Order

Transition Flow (Parallel Run):
  Alert → Router (feature flag) → [Legacy OR TradingEngine] → Order
```

**Output**: ARCHITECTURE_DESIGN.md (max 300 lines)
```

---

### Phase 3: Implementation (Week 1 Day 5 - Week 2 Day 3)
**Supervisor recruits: CODING AGENT**

**Objectives**:
- Implement SignalAdapter
- Create TradingEngineAdapter (wrapper for alerts.py)
- Add feature flags
- Migrate alerts.py to use adapter
- Preserve legacy path with flag

**Deliverables**:
- `src/catalyst_bot/adapters/signal_adapter.py` (Coding Agent)
- `src/catalyst_bot/adapters/trading_engine_adapter.py` (Coding Agent)
- Updated `src/catalyst_bot/alerts.py` (Coding Agent)
- Updated `src/catalyst_bot/config.py` (Coding Agent)
- Updated `.env` with new flags (Coding Agent)
- Updated `MIGRATION_KB.md` with implementation notes (Supervisor)

**Coding Agent Tasks**:
```markdown
## Coding Agent Instructions (from MIGRATION_KB.md)

### Task 1: Implement SignalAdapter
**File**: `src/catalyst_bot/adapters/signal_adapter.py`
**Lines**: ~150

**Requirements from KB**:
- Use architecture design from ADR-001
- Follow existing type hints pattern
- Comprehensive docstrings
- Preserve extended hours support

**Key Method**:
```python
@staticmethod
def from_scored_item(
    item: ScoredItem,
    entry_price: Decimal,
    quantity: int,
    stop_loss_pct: Optional[float] = 0.05,  # 5% default
    take_profit_pct: Optional[float] = 0.15,  # 15% default
    extended_hours: bool = False
) -> TradingSignal:
    """Convert ScoredItem to TradingSignal."""
    return TradingSignal(
        signal_id=item.alert_id or f"signal_{uuid.uuid4().hex[:8]}",
        ticker=item.ticker,
        action="buy",  # Alerts are always buy signals
        confidence=min(item.score / 5.0, 1.0),  # Normalize score to [0,1]
        entry_price=entry_price,
        current_price=entry_price,
        stop_loss_price=entry_price * Decimal(1 - stop_loss_pct),
        take_profit_price=entry_price * Decimal(1 + take_profit_pct),
        quantity=quantity,
        metadata={
            "original_score": item.score,
            "keywords": item.keywords,
            "source": item.source,
            "extended_hours": extended_hours
        },
        timestamp=datetime.now(timezone.utc)
    )
```

### Task 2: Create TradingEngineAdapter
**File**: `src/catalyst_bot/adapters/trading_engine_adapter.py`
**Lines**: ~200

**Purpose**: Drop-in replacement for `execute_paper_trade()`

**Interface** (must match legacy):
```python
async def execute_paper_trade_async(
    ticker: str,
    price: Decimal,
    alert_id: str,
    quantity: int = 100,
    scored_item: Optional[ScoredItem] = None,
    extended_hours: bool = False
) -> Optional[str]:
    """
    Async version of execute_paper_trade() using TradingEngine.

    Args:
        ticker: Stock symbol
        price: Entry price
        alert_id: Alert identifier
        quantity: Number of shares
        scored_item: Original ScoredItem for metadata
        extended_hours: Whether to use extended hours trading

    Returns:
        Order ID if successful, None otherwise
    """
    # 1. Convert to TradingSignal using SignalAdapter
    # 2. Call TradingEngine.execute_signal()
    # 3. Return order ID or None
    # 4. Handle errors gracefully (log, don't crash)
    pass
```

### Task 3: Update alerts.py
**File**: `src/catalyst_bot/alerts.py`
**Lines Changed**: ~30

**Changes**:
```python
# Line ~27 (imports)
from .paper_trader import execute_paper_trade, is_enabled as paper_trading_enabled
from .adapters.trading_engine_adapter import execute_paper_trade_async
from .config import get_settings

# Line ~1337 (order execution)
# OLD:
order_id = execute_paper_trade(
    ticker=ticker,
    price=Decimal(str(price)),
    alert_id=alert_id,
    quantity=100
)

# NEW:
settings = get_settings()
use_new_engine = settings.use_trading_engine

if use_new_engine:
    # Use TradingEngine (async)
    import asyncio
    order_id = asyncio.run(execute_paper_trade_async(
        ticker=ticker,
        price=Decimal(str(price)),
        alert_id=alert_id,
        quantity=100,
        scored_item=item,  # Pass full ScoredItem for metadata
        extended_hours=is_extended_hours()  # Auto-detect extended hours
    ))
else:
    # Use legacy system (fallback)
    order_id = execute_paper_trade(
        ticker=ticker,
        price=Decimal(str(price)),
        alert_id=alert_id,
        quantity=100
    )
```

### Task 4: Add Feature Flags
**File**: `src/catalyst_bot/config.py`
**File**: `.env`

**Config additions**:
```python
# Trading Engine Migration (config.py)
use_trading_engine: bool = _b("USE_TRADING_ENGINE", False)
trading_engine_rollout_pct: int = _i("TRADING_ENGINE_ROLLOUT_PCT", 0)
```

**Environment additions**:
```bash
# .env additions
# Trading Engine Migration
# Set to 1 to use new TradingEngine, 0 for legacy system
USE_TRADING_ENGINE=0

# Gradual rollout percentage (0-100)
# 0 = all legacy, 100 = all new engine
TRADING_ENGINE_ROLLOUT_PCT=0
```

**Output**: Functional code, ready for testing
```

---

### Phase 4: Testing & Validation (Week 2, Days 4-5)
**Supervisor recruits: TESTING AGENT**

**Objectives**:
- Create comprehensive test suite
- Test adapter layer
- Test feature flag switching
- Integration tests (end-to-end)
- Extended hours validation
- Parallel run testing

**Deliverables**:
- `tests/adapters/test_signal_adapter.py` (Testing Agent)
- `tests/adapters/test_trading_engine_adapter.py` (Testing Agent)
- `tests/integration/test_migration_parallel_run.py` (Testing Agent)
- `docs/migration/TEST_RESULTS.md` (Testing Agent)
- Updated `MIGRATION_KB.md` with test outcomes (Supervisor)

**Testing Agent Tasks**:
```markdown
## Testing Agent Instructions (from MIGRATION_KB.md)

### Task 1: Unit Tests - SignalAdapter
**File**: `tests/adapters/test_signal_adapter.py`
**Coverage Required**: 100%

**Test Cases**:
```python
def test_signal_adapter_basic_conversion():
    """Test ScoredItem → TradingSignal conversion."""
    pass

def test_signal_adapter_preserves_metadata():
    """Ensure all metadata is preserved."""
    pass

def test_signal_adapter_extended_hours_flag():
    """Test extended_hours parameter propagation."""
    pass

def test_signal_adapter_score_normalization():
    """Test score normalization to [0,1] range."""
    pass

def test_signal_adapter_stop_loss_calculation():
    """Validate stop loss price calculation."""
    pass
```

### Task 2: Integration Tests - Parallel Run
**File**: `tests/integration/test_migration_parallel_run.py`
**Coverage Required**: 95%

**Test Cases**:
```python
@pytest.mark.asyncio
async def test_parallel_run_both_systems():
    """
    Run same alert through both legacy and new system.
    Verify both produce valid orders.
    """
    pass

@pytest.mark.asyncio
async def test_extended_hours_both_systems():
    """
    Test extended hours order in both systems.
    Verify both use DAY limit orders.
    """
    pass

def test_feature_flag_routing():
    """
    Test USE_TRADING_ENGINE flag switches correctly.
    """
    pass
```

### Task 3: Validation Suite
**File**: `tests/migration/test_validation.py`

**Validation Tests**:
- ✅ No data loss in conversion
- ✅ Order IDs returned correctly
- ✅ Extended hours works in both systems
- ✅ Legacy fallback works
- ✅ Error handling preserved
- ✅ Logging maintains same format

**Output**: TEST_RESULTS.md with 95%+ pass rate
```

---

### Phase 5: Parallel Run & Monitoring (Week 3, Days 1-3)
**Supervisor coordinates: ALL AGENTS**

**Objectives**:
- Run both systems in parallel (shadow mode)
- Compare outputs
- Monitor for discrepancies
- Validate extended hours handling
- Gradual rollout (1% → 10% → 50%)

**Deliverables**:
- `docs/migration/PARALLEL_RUN_RESULTS.md` (Supervisor)
- `scripts/compare_trading_systems.py` (Coding Agent)
- Monitoring dashboard updates (Coding Agent)
- Updated `MIGRATION_KB.md` with findings (Supervisor)

**Supervisor Tasks**:
```markdown
## Supervisor Coordination: Parallel Run

### Configuration
1. Set USE_TRADING_ENGINE=1
2. Set TRADING_ENGINE_ROLLOUT_PCT=1 (1% traffic)
3. Keep legacy system active for comparison

### Monitoring
- Track success rate of both systems
- Compare order execution times
- Validate extended hours orders
- Check error rates

### Escalation Path
If any discrepancies:
1. Pause rollout (set ROLLOUT_PCT=0)
2. Recruit debugging agent
3. Analyze differences
4. Fix issues
5. Resume rollout

### Success Criteria for Rollout Increase
- 24 hours at current % with zero errors
- Success rate matches legacy system
- Extended hours orders working correctly
- No user-reported issues
```

---

### Phase 6: Cutover & Deprecation (Week 3, Days 4-5)
**Supervisor coordinates: CODING AGENT + TESTING AGENT**

**Objectives**:
- Set USE_TRADING_ENGINE=1 globally
- Remove legacy code path
- Update documentation
- Archive legacy system

**Deliverables**:
- Updated `alerts.py` (legacy code removed) (Coding Agent)
- `docs/migration/MIGRATION_COMPLETE.md` (Supervisor)
- `CHANGELOG.md` entry (Coding Agent)
- Archived `src/catalyst_bot/paper_trader.py` → `deprecated/` (Coding Agent)
- Final `MIGRATION_KB.md` update (Supervisor)

**Cutover Checklist**:
- [ ] 100% traffic on TradingEngine (ROLLOUT_PCT=100)
- [ ] 7 days zero errors
- [ ] All tests passing
- [ ] Extended hours validated in production
- [ ] Documentation updated
- [ ] Team sign-off

---

## 📝 Migration Knowledge Base Structure

**File**: `docs/migration/MIGRATION_KB.md`
**Max Length**: 500 lines

### Template:

```markdown
# Migration Knowledge Base (KB)

**Version**: 1.0
**Last Updated**: 2025-11-26
**Supervisor**: Claude Supervisor Agent

---

## 1. System Overview (50 lines)

### Legacy System Architecture
- Entry: `alerts.py:1337` → `execute_paper_trade()`
- Broker: `AlpacaBrokerWrapper` (synchronous)
- Position: `PositionManagerSync`
- Features: Basic order execution, 24h auto-close

### TradingEngine Architecture
- Entry: `TradingEngine.execute_signal()`
- Broker: `AlpacaBrokerClient` (async)
- Execution: `OrderExecutor` (bracket orders, risk management)
- Position: `PositionManager` (advanced tracking, P&L)
- Features: Risk limits, circuit breakers, ML-ready

### Key Differences
| Aspect | Legacy | TradingEngine |
|--------|--------|---------------|
| Async | No | Yes |
| Risk Mgmt | None | Comprehensive |
| Order Types | Market only | Market, Limit, Bracket |
| Position Mgmt | Basic | Advanced (P&L, metrics) |
| ML Ready | No | Yes |
| Extended Hours | Fixed (recent) | Built-in |

---

## 2. Migration Strategy (100 lines)

### Phased Approach
1. **Discovery**: Understand current system (2 days)
2. **Architecture**: Design adapter layer (2 days)
3. **Implementation**: Build adapters (4 days)
4. **Testing**: Validate changes (2 days)
5. **Parallel Run**: Shadow mode (3 days)
6. **Cutover**: Full migration (2 days)

### Risk Mitigation
- **Feature Flags**: Instant rollback capability
- **Parallel Run**: Validate before cutting over
- **Backward Compatibility**: Legacy path preserved during transition
- **Monitoring**: Real-time comparison of both systems

### Rollback Procedure
If issues detected:
1. Set `USE_TRADING_ENGINE=0` in .env
2. Restart bot (automatic fallback to legacy)
3. Investigate issue
4. Fix and re-test
5. Resume migration

---

## 3. Implementation Guidelines (150 lines)

### Code Patterns

#### SignalAdapter Pattern
```python
# All conversions go through adapter
from catalyst_bot.adapters import SignalAdapter

signal = SignalAdapter.from_scored_item(
    item=scored_item,
    entry_price=price,
    quantity=100,
    extended_hours=is_extended_hours()
)
```

#### Feature Flag Pattern
```python
# Always check feature flag before routing
settings = get_settings()
if settings.use_trading_engine:
    # New path
    await trading_engine.execute_signal(signal)
else:
    # Legacy path
    execute_paper_trade(ticker, price, alert_id)
```

#### Error Handling Pattern
```python
# Preserve existing error handling behavior
try:
    order_id = await execute_async(...)
except Exception as e:
    log.error(f"order_failed: {e}")
    return None  # Same as legacy
```

### Testing Requirements
- Unit Tests: 100% coverage for adapters
- Integration Tests: 95% coverage
- End-to-End: All critical paths tested
- Extended Hours: Specific test cases
- Rollback: Test flag switching

### Integration Points
1. `alerts.py:1337` - Main integration point
2. `runner.py:3275` - TradingEngine initialization
3. `config.py` - Feature flag definitions
4. `.env` - Feature flag values

---

## 4. Agent Instructions (100 lines)

### Research Agent
**Goal**: Document current system thoroughly
**Deliverables**:
- CURRENT_STATE_ANALYSIS.md (200 lines)
- INTEGRATION_POINTS.md (100 lines)
- RISK_MATRIX.md (50 lines)

**Key Questions to Answer**:
- How does `ScoredItem` differ from `TradingSignal`?
- What metadata must be preserved?
- Are there any global state dependencies?
- What are critical failure modes?

### Architecture Agent
**Goal**: Design clean migration path
**Deliverables**:
- ARCHITECTURE_DESIGN.md (300 lines)
- ADR-001-signal-adapter.md (100 lines)
- ADR-002-feature-flags.md (100 lines)

**Design Principles**:
- Single Responsibility: Adapter only converts
- Open/Closed: Extend, don't modify TradingEngine
- Dependency Inversion: Depend on abstractions
- Zero Downtime: Always maintain working system

### Coding Agent
**Goal**: Implement migration code
**Deliverables**:
- SignalAdapter (150 lines)
- TradingEngineAdapter (200 lines)
- Updated alerts.py (30 lines changed)
- Feature flags (config + .env)

**Code Standards**:
- Type hints on all functions
- Docstrings (Google style)
- Error handling (try/except with logging)
- Async patterns (use `async def` for new code)

### Testing Agent
**Goal**: Validate migration thoroughly
**Deliverables**:
- test_signal_adapter.py (200 lines)
- test_trading_engine_adapter.py (300 lines)
- test_migration_parallel_run.py (200 lines)
- TEST_RESULTS.md (100 lines)

**Test Coverage Requirements**:
- SignalAdapter: 100%
- TradingEngineAdapter: 100%
- Integration: 95%
- Overall: 95%+

---

## 5. Progress Tracking (100 lines)

### Milestones
- [ ] M1: Research Complete (Day 2)
- [ ] M2: Architecture Approved (Day 4)
- [ ] M3: Code Implementation Done (Day 9)
- [ ] M4: Tests Passing 95%+ (Day 11)
- [ ] M5: Parallel Run Started (Day 12)
- [ ] M6: Rollout 1% (Day 13)
- [ ] M7: Rollout 50% (Day 14)
- [ ] M8: Rollout 100% (Day 15)
- [ ] M9: Legacy Deprecated (Day 17)

### Current Status
**Phase**: [To be updated by Supervisor]
**Blockers**: [To be updated by Supervisor]
**Risks**: [To be updated by Supervisor]

### Decisions Log
| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| 2025-11-26 | Use adapter pattern | Clean separation | Low risk |
| 2025-11-26 | Feature flag rollout | Gradual validation | Enables rollback |
| TBD | ... | ... | ... |

### Metrics
- Code Coverage: Target 95%+
- Migration Progress: [Supervisor tracks]
- Error Rate: Target 0%
- Rollback Events: Target 0

---

**END OF MIGRATION_KB.md**
```

---

## 🎯 Success Metrics

### Technical Metrics
- **Code Coverage**: 95%+ (adapters + integration)
- **Migration Time**: 2-3 weeks (target)
- **Downtime**: 0 minutes
- **Data Loss**: 0 records
- **Rollback Events**: 0 (successful migration)

### Business Metrics
- **Order Success Rate**: Maintain 100%
- **Order Latency**: < 200ms (same or better)
- **Extended Hours Orders**: 100% using DAY limit orders
- **Error Rate**: 0% (zero regressions)

### Quality Metrics
- **Documentation**: 100% coverage of changes
- **Code Review**: 100% of code reviewed
- **Test Pass Rate**: 100% before cutover
- **Knowledge Transfer**: Full KB documentation

---

## 🚨 Risk Management

### High Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Data loss in conversion | Low | High | Comprehensive tests, parallel run |
| Extended hours regression | Low | High | Specific test cases, validation |
| Async/sync conflicts | Medium | Medium | Careful async wrapper design |
| Performance degradation | Low | Medium | Benchmarking, monitoring |

### Rollback Triggers
**Automatic Rollback** if:
- Error rate > 1%
- Order success rate < 99%
- Extended hours orders fail
- Data corruption detected

**Manual Rollback** if:
- Team decision
- Unexpected behavior
- User complaints

---

## 📦 Deliverables Checklist

### Documentation
- [ ] MIGRATION_KB.md (Supervisor)
- [ ] CURRENT_STATE_ANALYSIS.md (Research Agent)
- [ ] ARCHITECTURE_DESIGN.md (Architecture Agent)
- [ ] ADR-001-signal-adapter.md (Architecture Agent)
- [ ] ADR-002-feature-flags.md (Architecture Agent)
- [ ] TEST_RESULTS.md (Testing Agent)
- [ ] PARALLEL_RUN_RESULTS.md (Supervisor)
- [ ] MIGRATION_COMPLETE.md (Supervisor)

### Code
- [ ] src/catalyst_bot/adapters/signal_adapter.py (Coding Agent)
- [ ] src/catalyst_bot/adapters/trading_engine_adapter.py (Coding Agent)
- [ ] src/catalyst_bot/alerts.py (updated) (Coding Agent)
- [ ] src/catalyst_bot/config.py (updated) (Coding Agent)
- [ ] .env (updated) (Coding Agent)

### Tests
- [ ] tests/adapters/test_signal_adapter.py (Testing Agent)
- [ ] tests/adapters/test_trading_engine_adapter.py (Testing Agent)
- [ ] tests/integration/test_migration_parallel_run.py (Testing Agent)

### Scripts
- [ ] scripts/compare_trading_systems.py (Coding Agent)
- [ ] scripts/validate_migration.py (Testing Agent)

---

## 🤔 Open Questions for Review

Before proceeding, please review and approve:

1. **Phased Approach**: Is 2-3 weeks acceptable, or do you want faster/slower?

2. **Parallel Run**: Should we run both systems simultaneously for data collection?

3. **Feature Flag Granularity**:
   - Global on/off switch?
   - Percentage-based rollout (1% → 10% → 50% → 100%)?
   - Both?

4. **Legacy Code**: After migration, should we:
   - Delete `paper_trader.py` entirely?
   - Move to `deprecated/` directory?
   - Keep as fallback for 1 month?

5. **Extended Hours**: Current fix in `alpaca_wrapper.py` - deprecate immediately or keep during transition?

6. **Testing Environment**:
   - Test with real Alpaca paper account?
   - Mock Alpaca API?
   - Both?

7. **Rollback Strategy**: What triggers an automatic rollback vs. manual decision?

8. **Documentation**: Should we create video walkthrough or written docs sufficient?

---

## 📞 Next Steps

### For User Review
1. Read this plan thoroughly
2. Answer open questions above
3. Approve or request changes
4. Give go-ahead to start

### For Supervisor Agent (After Approval)
1. Create `docs/migration/` directory
2. Initialize `MIGRATION_KB.md`
3. Recruit Research Agent
4. Begin Phase 1: Discovery

### Timeline After Approval
- **Day 1**: Supervisor creates KB, recruits Research Agent
- **Day 2**: Research complete, Architecture Agent recruited
- **Day 4**: Architecture approved, Coding Agent recruited
- **Day 9**: Implementation complete, Testing Agent recruited
- **Day 12**: Parallel run begins
- **Day 17**: Migration complete

---

**Status**: ⏸️ **AWAITING USER APPROVAL**
**Ready to Start**: YES
**Questions to Answer**: 8 (see above)

---

**Document Created By**: Claude Code (Planning Agent)
**Version**: 1.0
**Date**: 2025-11-26
**Estimated Reading Time**: 30 minutes
