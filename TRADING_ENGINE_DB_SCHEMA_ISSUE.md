# Trading Engine Database Schema Issue

## Issue Summary
Paper trading engine is non-functional due to database schema mismatch. Position saves are failing, preventing trade execution.

## Error Details

**Error Message:**
```
ERROR: table positions has no column named side
Failed to save position to database: table positions has no column named side
```

**Occurrence Context:**
- Triggered during trade execution when attempting to save position
- Occurs in: `catalyst_bot.portfolio.position_manager`
- Frequency: 2 errors logged in 9-hour period (attempted trades)

**Example Failed Trade:**
```
[14:05:24] Error executing trade for NOTV via TradingEngine
[14:02:04] gemini_query_timeout during trade analysis
```

## Technical Context

### Database Location
- **Path**: `data/market.db` (SQLite with WAL mode)
- **Schema**: Defined in `src/catalyst_bot/portfolio/position_manager.py`

### Current Schema vs Required Schema

**Current `positions` table** (presumed):
- Missing: `side` column

**Required Fields** (from position_manager code):
- `ticker` - Stock symbol
- `entry_price` - Price at entry
- `shares` - Position size
- `entry_time` - Timestamp
- **`side`** - Direction (LONG/SHORT) ⚠️ **MISSING**
- `exit_price` - Price at exit (nullable)
- `exit_time` - Exit timestamp (nullable)
- `pnl` - Profit/loss (nullable)

## Impact Assessment

**Severity**: 🔴 **CRITICAL** - Blocks core functionality

**Affected Components:**
1. ❌ **Paper Trading** - Cannot execute or track trades
2. ❌ **Position Management** - Cannot save position state
3. ❌ **Portfolio Tracking** - No position history
4. ❌ **P&L Calculation** - Cannot calculate returns
5. ⚠️ **Trading Signals** - Generated but not executed

**Business Impact:**
- Bot generates valid trading signals (score >2.0 seen recently)
- Signals cannot be executed or tracked
- No performance metrics available
- Paper trading feature completely non-functional

## Root Cause Analysis

**Likely Scenario 1: Schema Evolution**
- Code was updated to include `side` field for long/short support
- Database schema not migrated
- No automatic migration system in place

**Likely Scenario 2: Fresh Database**
- Database recreated without full schema
- Initialization script missing `side` column definition

**Likely Scenario 3: Manual Intervention**
- Table created manually without all columns
- Schema definition incomplete

## Proposed Solutions

### Option A: Add Missing Column (Quick Fix)
```sql
ALTER TABLE positions ADD COLUMN side TEXT NOT NULL DEFAULT 'LONG';
```
- **Pros**: Fast, preserves existing data
- **Cons**: May miss other schema issues, defaults all to LONG

### Option B: Recreate Table (Clean Slate)
```sql
DROP TABLE IF EXISTS positions;
-- Then recreate with full schema from position_manager.py
```
- **Pros**: Ensures complete schema, clean start
- **Cons**: Loses historical data (acceptable for paper trading)

### Option C: Database Migration System
- Implement proper versioned migrations (e.g., Alembic)
- **Pros**: Professional approach, prevents future issues
- **Cons**: Requires setup time, may be overkill

## Recommended Resolution Path

**Immediate (Today):**
1. **Option B** - Drop and recreate `positions` table with complete schema
2. Verify schema matches `position_manager.py` requirements
3. Test with small trade to confirm fix

**Short-term (This Week):**
1. Add schema validation on startup
2. Create initialization script with full schema
3. Add logging for schema mismatches

**Long-term (Optional):**
1. Consider migration system if schema changes frequently
2. Add database backup before schema changes
3. Document schema in separate file

## Files to Review

**Primary:**
- `src/catalyst_bot/portfolio/position_manager.py` - Schema definition
- `src/catalyst_bot/trading/trading_engine.py` - Trade execution
- `data/market.db` - Database file

**Secondary:**
- `src/catalyst_bot/config.py` - Database configuration
- Database initialization code (if exists)

## Verification Steps

After fix, verify:
1. ✅ `positions` table exists with all required columns
2. ✅ Test trade executes without error
3. ✅ Position saves to database successfully
4. ✅ Position can be retrieved and displayed
5. ✅ P&L calculation works correctly

## Additional Context

**Database Type**: SQLite (single file, no server)
**ORM/Library**: Likely direct SQL or lightweight wrapper
**Current State**: WAL mode enabled (good for concurrency)

---

**Created**: 2025-12-11
**Reported By**: Claude Code Analysis
**Priority**: P0 - Critical (blocks core functionality)
