# MOA Keyword Review System - Complete Implementation Plan

**Project:** Catalyst Bot - MOA Keyword Review Workflow
**Purpose:** Replace auto-apply keyword weights with interactive Discord review system
**Date:** 2025-11-11
**Status:** Ready for Implementation

---

## Executive Summary

The MOA (Missed Opportunities Analyzer) currently **auto-applies** keyword weight changes with confidence ≥ 0.6. This implementation plan adds a **manual review workflow** with Discord-based approval, comprehensive audit trails, and rollback capabilities.

### Current State
```python
# moa_historical_analyzer.py:1053-1132
def update_keyword_stats_file(recommendations, min_confidence=0.6):
    # PROBLEM: Automatically updates keyword_stats.json
    # No human review, no visibility into changes
    existing_weights[keyword] = weight  # ← Direct apply
```

### Target State
```python
# New workflow with review
def update_keyword_stats_file(recommendations):
    # 1. Create pending review
    review = create_pending_review(recommendations)

    # 2. Post to Discord for approval
    post_review_request(review.review_id)

    # 3. Admin clicks "Approve" button in Discord
    # 4. Changes applied with audit trail
    # 5. Rollback available if needed
```

### Key Features
- ✅ **Discord Review Interface** - Interactive buttons for approve/reject
- ✅ **Audit Trail** - Complete history in JSONL + SQLite
- ✅ **Auto-Approve Option** - High-confidence changes (≥0.9) can auto-apply
- ✅ **Rollback Support** - Snapshot-based rollback mechanism
- ✅ **Conflict Detection** - Prevents concurrent modifications
- ✅ **Backward Compatible** - Feature flag controlled

---

## Claude Code CLI Delegation Structure

### Phase Overview

```
SUPERVISOR AGENT (Orchestrator)
    │
    ├── PHASE 1: Discovery & Design Team
    │   ├── Architectural Agent (analyze integration points)
    │   ├── Design Agent (design data structures & state machine)
    │   ├── Research Agent (examine existing patterns)
    │   └── Documentation Agent (create schemas & examples)
    │
    ├── PHASE 2: Implementation Team
    │   ├── Core Workflow Agent (keyword_review.py)
    │   ├── Discord Integration Agent (moa_discord_reviewer.py)
    │   ├── Interaction Handler Agent (moa_interaction_handler.py)
    │   └── Database Agent (schema setup & migrations)
    │
    ├── PHASE 3: Integration Team
    │   ├── MOA Integration Agent (modify moa_historical_analyzer.py)
    │   ├── Runner Integration Agent (modify runner.py)
    │   └── Admin Controls Agent (modify admin_interactions.py)
    │
    └── PHASE 4: Review & Testing Team
        ├── Unit Test Agent (create test files)
        ├── Integration Test Agent (end-to-end tests)
        ├── Validation Agent (validation scripts)
        └── Alpha Testing Agent (manual test guide)
```

---

## Implementation Phases

### PHASE 1: Discovery & Design (Week 1)

#### Objective
Analyze existing codebase, design integration points, and create detailed specifications.

#### Agents Required
1. **Architectural Agent** - Map integration points
2. **Design Agent** - Design state machine & workflows
3. **Research Agent** - Study existing patterns
4. **Documentation Agent** - Create schemas

#### Claude Code CLI Commands

```bash
# Launch Supervisor Agent
claude-code agent create supervisor \
  --task "Oversee MOA Keyword Review implementation" \
  --plan-file docs/MOA_KEYWORD_REVIEW_IMPLEMENTATION_PLAN.md

# Supervisor launches Discovery Team
claude-code agent create architectural-analyst \
  --parent supervisor \
  --task "Map all integration points for MOA review workflow. Identify:
    1. Files to modify with exact line numbers
    2. Functions to integrate with
    3. Data flow paths
    4. Dependencies (internal & external)
    Output: integration_points.md with file paths and line numbers"

claude-code agent create design-architect \
  --parent supervisor \
  --task "Design complete state machine and workflows. Create:
    1. State diagram with transitions
    2. Database schema (SQLite)
    3. Data structures (Review, KeywordChange, etc.)
    4. Function signatures for all new modules
    Output: workflow_design.md with state machine & schemas"

claude-code agent create research-analyst \
  --parent supervisor \
  --task "Analyze existing patterns in codebase:
    1. Study accepted_items_logger.py logging patterns
    2. Study admin_interactions.py Discord patterns
    3. Study breakout_feedback.py database patterns
    4. Study moa_analyzer.py integration patterns
    Output: existing_patterns.md with code examples"

claude-code agent create documentation-writer \
  --parent supervisor \
  --task "Create comprehensive documentation:
    1. Complete file inventory
    2. API documentation for new functions
    3. Configuration guide (env vars)
    4. Example payloads (Discord embeds, etc.)
    Output: api_documentation.md"
```

#### Deliverables
- ✅ `docs/integration_points.md` - Complete integration map
- ✅ `docs/workflow_design.md` - State machine & schemas
- ✅ `docs/existing_patterns.md` - Pattern analysis
- ✅ `docs/api_documentation.md` - API docs

---

### PHASE 2: Core Implementation (Week 2-3)

#### Objective
Implement core modules: workflow engine, Discord interface, interaction handlers.

#### Files to Create

| File Path | Purpose | Lines | Agent |
|-----------|---------|-------|-------|
| `src/catalyst_bot/keyword_review.py` | Core workflow engine | ~800 | Core Workflow Agent |
| `src/catalyst_bot/moa_discord_reviewer.py` | Discord embed builders | ~400 | Discord Integration Agent |
| `src/catalyst_bot/moa_interaction_handler.py` | Button interaction handlers | ~600 | Interaction Handler Agent |
| `src/catalyst_bot/keyword_review_rules.py` | Business logic rules | ~200 | Core Workflow Agent |
| `data/keyword_review.db` | SQLite database | N/A | Database Agent |

#### Claude Code CLI Commands

```bash
# Core Workflow Agent
claude-code agent create core-workflow-impl \
  --parent supervisor \
  --task "Implement src/catalyst_bot/keyword_review.py with:

  FUNCTIONS TO IMPLEMENT:
  1. create_pending_review(recommendations, auto_approve=False)
  2. approve_changes(review_id, reviewer_id, notes)
  3. reject_changes(review_id, reviewer_id, notes)
  4. approve_individual(review_id, keywords, reviewer_id)
  5. expire_review(review_id)
  6. apply_approved_changes(review_id, applied_by, dry_run=False)
  7. rollback_changes(review_id, reason)

  CLASSES TO IMPLEMENT:
  - ReviewState (Enum): PENDING, APPROVED, REJECTED, EXPIRED, APPLIED, FAILED, ROLLED_BACK
  - ChangeStatus (Enum): PENDING, APPROVED, REJECTED, SKIPPED
  - KeywordChange (dataclass): keyword, old_weight, new_weight, confidence, evidence
  - Review (dataclass): review_id, state, changes, timestamps

  DATABASE SCHEMA:
  - keyword_reviews table (id, review_id, state, created_at, expires_at, ...)
  - keyword_changes table (id, review_id, keyword, old_weight, new_weight, ...)
  - keyword_stats_snapshots table (id, review_id, snapshot_data, snapshot_at)

  INTEGRATION POINTS:
  - Load existing weights from data/analyzer/keyword_stats.json
  - Save updated weights to data/analyzer/keyword_stats.json
  - Use init_optimized_connection() from storage.py
  - Use get_logger() from logging_utils.py

  REFERENCE: See docs/workflow_design.md for complete specifications
  OUTPUT: Fully tested keyword_review.py with all functions"

# Discord Integration Agent
claude-code agent create discord-integration-impl \
  --parent supervisor \
  --task "Implement src/catalyst_bot/moa_discord_reviewer.py with:

  FUNCTIONS TO IMPLEMENT:
  1. build_review_embed(change_id, recommendations, summary) -> Dict
     Returns Discord embed JSON with:
     - Title: '📊 MOA Keyword Review Required'
     - Fields: Analysis summary, top recommendations
     - Color: 0x3498DB (blue)
     - Footer: Review instructions

  2. build_review_components(change_id) -> List[Dict]
     Returns Discord button components:
     - 'Approve All' button (style=3, green)
     - 'Reject All' button (style=4, red)
     - 'Review Individual' button (style=1, primary)
     - 'View Details' button (style=2, secondary)

  3. post_review_request(change_id, recommendations, summary) -> bool
     Posts review embed to Discord using:
     - DISCORD_ADMIN_WEBHOOK or DISCORD_BOT_TOKEN
     - discord_transport.post_discord_with_backoff()

  INTEGRATION:
  - Use existing discord_transport.py patterns
  - Follow admin_reporter.py embed structure
  - Custom IDs format: 'moa_review_{action}_{change_id}'

  REFERENCE: See docs/discord_integration.md for embed examples
  OUTPUT: Fully functional moa_discord_reviewer.py"

# Interaction Handler Agent
claude-code agent create interaction-handler-impl \
  --parent supervisor \
  --task "Implement src/catalyst_bot/moa_interaction_handler.py with:

  MAIN ROUTER:
  handle_moa_review_interaction(interaction_data) -> Dict
    Routes based on custom_id:
    - 'moa_review_approve_all_{id}' → handle_approve_all()
    - 'moa_review_reject_all_{id}' → handle_reject_all()
    - 'moa_review_individual_{id}' → handle_review_individual()
    - 'moa_review_details_{id}' → handle_view_details()

  HANDLER FUNCTIONS:
  1. handle_approve_all(review_id, interaction_data)
     - Load review from database
     - Call keyword_review.approve_changes()
     - Call keyword_review.apply_approved_changes()
     - Return success embed

  2. handle_reject_all(review_id, interaction_data)
     - Load review
     - Call keyword_review.reject_changes()
     - Return rejection confirmation

  3. handle_review_individual(review_id, interaction_data)
     - Load review
     - Build paginated keyword review embed
     - Show first keyword with approve/reject buttons

  INTEGRATION:
  - Use INTERACTION_TYPE constants from admin_interactions.py
  - Use RESPONSE_TYPE constants for Discord responses
  - Extract user_id from interaction_data['member']['user']['id']

  REFERENCE: See docs/interaction_handlers.md
  OUTPUT: Complete moa_interaction_handler.py with error handling"

# Database Agent
claude-code agent create database-impl \
  --parent supervisor \
  --task "Create database schema and migration utilities:

  FILE: src/catalyst_bot/keyword_review_db.py

  FUNCTIONS:
  1. init_review_database(conn: sqlite3.Connection)
     Creates tables:
     - keyword_reviews (see schema below)
     - keyword_changes (see schema below)
     - keyword_stats_snapshots (see schema below)
     - review_conflicts (for conflict detection)

  2. migrate_database(conn, target_version)
     Version control for schema changes

  SCHEMA:
  keyword_reviews:
    - id INTEGER PRIMARY KEY AUTOINCREMENT
    - review_id TEXT UNIQUE NOT NULL
    - state TEXT NOT NULL
    - moa_run_timestamp INTEGER
    - created_at INTEGER NOT NULL
    - updated_at INTEGER NOT NULL
    - expires_at INTEGER
    - total_keywords INTEGER
    - approved_count INTEGER DEFAULT 0
    - rejected_count INTEGER DEFAULT 0
    - applied_at INTEGER
    - applied_by TEXT
    - reviewer_id TEXT

  keyword_changes:
    - id INTEGER PRIMARY KEY AUTOINCREMENT
    - review_id TEXT NOT NULL
    - keyword TEXT NOT NULL
    - old_weight REAL
    - new_weight REAL
    - weight_delta REAL
    - confidence REAL
    - occurrences INTEGER
    - success_rate REAL
    - avg_return_pct REAL
    - evidence_json TEXT
    - status TEXT DEFAULT 'PENDING'
    - FOREIGN KEY (review_id) REFERENCES keyword_reviews(review_id)
    - UNIQUE(review_id, keyword)

  INDEXES:
    - idx_review_state ON keyword_reviews(state)
    - idx_review_created_at ON keyword_reviews(created_at)
    - idx_changes_review ON keyword_changes(review_id)
    - idx_changes_keyword ON keyword_changes(keyword)

  REFERENCE: Use storage.py patterns (init_optimized_connection, WAL mode)
  OUTPUT: keyword_review_db.py with schema and migrations"
```

#### Implementation Order

1. **Database First** (Database Agent)
   ```bash
   # Create schema
   python -c "from catalyst_bot.keyword_review_db import init_review_database; \
              from catalyst_bot.storage import init_optimized_connection; \
              conn = init_optimized_connection('data/keyword_review.db'); \
              init_review_database(conn)"
   ```

2. **Core Workflow** (Core Workflow Agent)
   ```bash
   # Test basic workflow functions
   pytest tests/test_keyword_review.py::test_create_pending_review -v
   pytest tests/test_keyword_review.py::test_approve_changes -v
   ```

3. **Discord Integration** (Discord Integration Agent)
   ```bash
   # Test embed generation
   pytest tests/test_moa_discord_reviewer.py::test_build_review_embed -v
   ```

4. **Interaction Handlers** (Interaction Handler Agent)
   ```bash
   # Test interaction routing
   pytest tests/test_moa_interaction_handler.py::test_handle_approve_all -v
   ```

---

### PHASE 3: Integration (Week 3-4)

#### Objective
Integrate new modules with existing MOA system, runner, and admin controls.

#### Files to Modify

| File Path | Lines to Modify | Changes | Agent |
|-----------|-----------------|---------|-------|
| `src/catalyst_bot/moa_historical_analyzer.py` | 1053-1132 | Replace direct apply with review workflow | MOA Integration Agent |
| `src/catalyst_bot/moa_reporter.py` | 275-323 | Add review workflow call | MOA Integration Agent |
| `src/catalyst_bot/admin_interactions.py` | 216-287 | Add MOA review routing | Admin Controls Agent |
| `src/catalyst_bot/runner.py` | 84-86, ~3450 | Add imports, pending review check | Runner Integration Agent |
| `src/catalyst_bot/config.py` | End of file | Add MOA review settings | Config Agent |
| `.env.example` | End of file | Add MOA review env vars | Config Agent |

#### Claude Code CLI Commands

```bash
# MOA Integration Agent
claude-code agent create moa-integration \
  --parent supervisor \
  --task "Integrate review workflow into MOA analyzer:

  FILE 1: src/catalyst_bot/moa_historical_analyzer.py

  LOCATION: Function update_keyword_stats_file() at lines 1053-1132

  CHANGES:
  1. ADD imports at top of file:
     from .keyword_review import create_pending_review, apply_approved_changes, ReviewState
     from .moa_discord_reviewer import post_review_request

  2. MODIFY update_keyword_stats_file() function:

     BEFORE (line 1053):
     def update_keyword_stats_file(recommendations, min_confidence=0.6):
         # Load existing weights
         existing_weights = {}
         # ... existing code ...

         # Apply recommendations
         for rec in recommendations:
             if confidence >= min_confidence:
                 existing_weights[keyword] = weight  # ← REMOVE THIS

         # Save to file
         _save_keyword_stats(existing_weights)

     AFTER:
     def update_keyword_stats_file(recommendations, min_confidence=0.6):
         from .config import get_settings
         settings = get_settings()

         # Check if review system is enabled
         if settings.moa_review_enabled:
             log.info('using_review_workflow')

             # Create pending review
             review = create_pending_review(
                 recommendations=recommendations,
                 auto_approve=settings.moa_auto_apply,
                 auto_approve_confidence=settings.moa_min_confidence_auto,
                 timeout_hours=settings.moa_review_timeout_hours
             )

             log.info(f'created_review review_id={review.review_id} state={review.state}')

             # Post to Discord for review
             post_review_request(
                 review_id=review.review_id,
                 recommendations=recommendations,
                 summary={}  # Will be filled by function
             )

             # If fully auto-approved, apply immediately
             if review.state == ReviewState.APPROVED and settings.moa_auto_apply:
                 success, error = apply_approved_changes(
                     review.review_id,
                     applied_by='moa_nightly_auto',
                     min_confidence=min_confidence
                 )
                 if success:
                     log.info(f'auto_applied review_id={review.review_id}')
                     return Path('data/analyzer/keyword_stats.json')
                 else:
                     log.error(f'auto_apply_failed error={error}')

             # Return path to pending review (not applied yet)
             return Path(f'pending_review:{review.review_id}')

         else:
             # Legacy direct apply (backward compatibility)
             log.info('using_legacy_direct_apply')
             # ... keep existing implementation ...

  FILE 2: src/catalyst_bot/moa_reporter.py

  LOCATION: After line 323 in post_moa_completion_report()

  ADD NEW FUNCTION:
  def initiate_review_workflow(
      moa_result: Optional[Dict[str, Any]] = None,
      fp_result: Optional[Dict[str, Any]] = None,
      top_n: int = 10
  ) -> Optional[str]:
      '''Initiate review workflow after MOA completion.'''
      if not moa_result and not fp_result:
          return None

      try:
          from .keyword_review import create_pending_review
          from .moa_discord_reviewer import post_review_request

          # Merge recommendations
          merged_recs = merge_recommendations(
              moa_result.get('recommendations', []) if moa_result else [],
              fp_result.get('recommendations', []) if fp_result else [],
              min_confidence=0.6,
              top_n=top_n
          )

          # Create pending review
          review = create_pending_review(
              recommendations=merged_recs,
              auto_approve=False  # Always require manual review from reporter
          )

          # Post to Discord
          success = post_review_request(
              review_id=review.review_id,
              recommendations=merged_recs,
              summary={
                  'moa': moa_result.get('summary') if moa_result else {},
                  'fp': fp_result.get('summary') if fp_result else {}
              }
          )

          log.info(f'review_workflow_initiated review_id={review.review_id} posted={success}')
          return review.review_id

      except Exception as e:
          log.error(f'review_workflow_failed err={e}', exc_info=True)
          return None

  MODIFY post_moa_completion_report() at line 323:
  ADD after existing return statement:
      # Initiate review workflow if enabled
      if success and os.getenv('FEATURE_MOA_REVIEW_WORKFLOW', '1') == '1':
          initiate_review_workflow(moa_result, fp_result, top_n)

  TEST:
  - Run MOA analysis manually
  - Verify review created in database
  - Verify Discord message posted

  OUTPUT: Modified files with review workflow integrated"

# Admin Controls Integration Agent
claude-code agent create admin-controls-integration \
  --parent supervisor \
  --task "Add MOA review routing to admin interactions:

  FILE: src/catalyst_bot/admin_interactions.py

  LOCATION: Function handle_admin_interaction() at line 216

  CHANGES:
  1. ADD import at top:
     from .moa_interaction_handler import handle_moa_review_interaction

  2. ADD routing in handle_admin_interaction():

     FIND this section (around line 245-278):
     if interaction_type == INTERACTION_TYPE_COMPONENT:
         data = interaction_data.get('data', {})
         custom_id = data.get('custom_id', '')

         if not custom_id.startswith('admin_'):
             return error_response()

     INSERT BEFORE the 'if not custom_id.startswith' check:
         # Route MOA review interactions
         if custom_id.startswith('moa_review_'):
             return handle_moa_review_interaction(interaction_data)

     RESULT:
     if interaction_type == INTERACTION_TYPE_COMPONENT:
         data = interaction_data.get('data', {})
         custom_id = data.get('custom_id', '')

         # NEW: Route MOA review interactions
         if custom_id.startswith('moa_review_'):
             return handle_moa_review_interaction(interaction_data)

         if not custom_id.startswith('admin_'):
             return error_response()

         # ... rest of existing code ...

  TEST:
  - Send mock Discord interaction with custom_id='moa_review_approve_all_test123'
  - Verify it routes to moa_interaction_handler

  OUTPUT: Modified admin_interactions.py with routing"

# Runner Integration Agent
claude-code agent create runner-integration \
  --parent supervisor \
  --task "Integrate pending review monitoring into main loop:

  FILE: src/catalyst_bot/runner.py

  CHANGES:
  1. ADD import at line 87 (after existing MOA imports):
     from .keyword_review import get_pending_reviews, expire_old_reviews

  2. ADD pending review check in main loop (around line 3450):

     FIND this section:
         # MOA price tracking
         if settings.feature_moa_price_tracker:
             try:
                 track_moa_outcomes()
             except Exception as e:
                 log.error(f'moa_price_tracking_failed err={e}')

     ADD AFTER:
         # Check for pending MOA reviews (hourly)
         if settings.moa_review_enabled and cycle_count % 12 == 0:  # Every ~1 hour
             try:
                 # Expire old reviews
                 expired_count = expire_old_reviews()
                 if expired_count > 0:
                     log.info(f'expired_old_reviews count={expired_count}')

                 # Log pending reviews
                 pending = get_pending_reviews()
                 if pending:
                     log.info(
                         f'pending_moa_reviews count={len(pending)} '
                         f'oldest={pending[0].created_at if pending else 0}'
                     )
             except Exception as e:
                 log.debug(f'pending_review_check_failed err={e}')

  TEST:
  - Run bot with pending reviews
  - Verify log messages appear hourly

  OUTPUT: Modified runner.py with monitoring"

# Config Agent
claude-code agent create config-integration \
  --parent supervisor \
  --task "Add configuration settings for MOA review system:

  FILE 1: src/catalyst_bot/config.py

  LOCATION: Add to Settings dataclass (around line 100-200)

  ADD:
      # === MOA Keyword Review System ===

      # Enable review workflow (vs direct apply)
      moa_review_enabled: bool = _b('MOA_REVIEW_ENABLED', True)

      # Auto-apply high-confidence changes
      moa_auto_apply: bool = _b('MOA_AUTO_APPLY', False)

      # Minimum confidence for auto-approval (0.0-1.0)
      moa_min_confidence_auto: float = float(
          os.getenv('MOA_MIN_CONFIDENCE_AUTO', '0.9') or '0.9'
      )

      # Minimum confidence threshold (safety floor)
      moa_min_confidence_threshold: float = float(
          os.getenv('MOA_MIN_CONFIDENCE_THRESHOLD', '0.6') or '0.6'
      )

      # Review timeout in hours
      moa_review_timeout_hours: int = int(
          os.getenv('MOA_REVIEW_TIMEOUT_HOURS', '48') or '48'
      )

      # Review database path
      moa_review_db_path: str = os.getenv(
          'MOA_REVIEW_DB_PATH', 'data/keyword_review.db'
      )

  FILE 2: .env.example

  ADD at end of file:
      # === MOA Keyword Review System ===
      # Enable manual review workflow for keyword changes
      MOA_REVIEW_ENABLED=1

      # Auto-apply high-confidence changes (0=manual review, 1=auto for high confidence)
      MOA_AUTO_APPLY=0

      # Minimum confidence for auto-approval (0.0-1.0, recommended: 0.9)
      MOA_MIN_CONFIDENCE_AUTO=0.9

      # Minimum confidence to apply at all (safety threshold, recommended: 0.6)
      MOA_MIN_CONFIDENCE_THRESHOLD=0.6

      # Review timeout in hours (pending reviews expire after this)
      MOA_REVIEW_TIMEOUT_HOURS=48

      # Review database path
      MOA_REVIEW_DB_PATH=data/keyword_review.db

  OUTPUT: Modified config files"
```

---

### PHASE 4: Testing & Validation (Week 4-5)

#### Objective
Create comprehensive test suite and validation scripts.

#### Test Files to Create

| Test File | Purpose | Test Count | Agent |
|-----------|---------|------------|-------|
| `tests/test_keyword_review.py` | Core workflow unit tests | 15 | Unit Test Agent |
| `tests/test_moa_discord_reviewer.py` | Discord embed tests | 8 | Unit Test Agent |
| `tests/test_moa_interaction_handler.py` | Interaction handler tests | 10 | Unit Test Agent |
| `tests/test_moa_review_integration.py` | End-to-end integration | 5 | Integration Test Agent |
| `tests/test_keyword_review_db.py` | Database tests | 7 | Unit Test Agent |

#### Claude Code CLI Commands

```bash
# Unit Test Agent 1: Core Workflow Tests
claude-code agent create unit-test-core \
  --parent supervisor \
  --task "Create tests/test_keyword_review.py with pytest tests:

  TEST CASES:
  1. test_create_pending_review_basic()
     - Create review from recommendations
     - Assert review_id is generated
     - Assert state is PENDING
     - Assert all changes are PENDING status

  2. test_create_pending_review_auto_approve()
     - Create review with auto_approve=True
     - Assert high-confidence changes are APPROVED
     - Assert low-confidence changes are PENDING
     - Assert state is PARTIAL_APPROVED

  3. test_approve_changes()
     - Create pending review
     - Call approve_changes(review_id, 'admin123')
     - Assert state is APPROVED
     - Assert all changes are APPROVED
     - Assert reviewer_id is set

  4. test_reject_changes()
     - Create pending review
     - Call reject_changes(review_id, 'admin123', 'not needed')
     - Assert state is REJECTED
     - Assert review_notes contains reason

  5. test_approve_individual()
     - Create review with 5 keywords
     - Approve 2 specific keywords
     - Assert state is PARTIAL_APPROVED
     - Assert approved_count == 2
     - Assert 3 changes still PENDING

  6. test_apply_approved_changes()
     - Create and approve review
     - Call apply_approved_changes(review_id)
     - Read data/analyzer/keyword_stats.json
     - Assert weights were updated
     - Assert state is APPLIED

  7. test_apply_approved_changes_dry_run()
     - Create and approve review
     - Call apply_approved_changes(review_id, dry_run=True)
     - Assert no changes to keyword_stats.json
     - Assert state is still APPROVED

  8. test_expire_review()
     - Create review with old timestamp
     - Call expire_old_reviews()
     - Assert state is EXPIRED

  9. test_rollback_changes()
     - Create, approve, and apply review
     - Call rollback_changes(review_id, 'performance degraded')
     - Assert keyword_stats.json restored to snapshot
     - Assert state is ROLLED_BACK

  10. test_state_transition_validation()
      - Try invalid transitions (e.g., APPLIED → PENDING)
      - Assert error is raised

  11. test_conflict_detection()
      - Create two reviews with same keyword
      - Try to apply both
      - Assert conflict is detected

  12. test_snapshot_creation()
      - Apply approved changes
      - Verify snapshot exists in database
      - Verify snapshot contains correct data

  13. test_load_existing_weights()
      - Pre-populate keyword_stats.json
      - Create review
      - Assert old_weight values are correct

  14. test_min_confidence_filter()
      - Create review with low confidence change
      - Try to apply with min_confidence=0.8
      - Assert low confidence change is SKIPPED

  15. test_pending_reviews_query()
      - Create multiple reviews
      - Call get_pending_reviews()
      - Assert correct reviews returned

  FIXTURES:
  @pytest.fixture
  def clean_db():
      '''Clean database before each test'''
      db_path = Path('data/test_keyword_review.db')
      if db_path.exists():
          db_path.unlink()
      yield
      if db_path.exists():
          db_path.unlink()

  @pytest.fixture
  def mock_recommendations():
      '''Sample MOA recommendations'''
      return [
          {
              'keyword': 'breakthrough_therapy',
              'recommended_weight': 1.5,
              'confidence': 0.85,
              'evidence': {
                  'occurrences': 12,
                  'success_rate': 0.75,
                  'avg_return_pct': 18.3
              }
          },
          {
              'keyword': 'phase_3',
              'recommended_weight': 0.7,
              'confidence': 0.95,
              'evidence': {
                  'occurrences': 20,
                  'success_rate': 0.88,
                  'avg_return_pct': 22.1
              }
          }
      ]

  USE pytest-mock for:
  - Mocking keyword_stats.json reads/writes
  - Mocking database connections
  - Mocking Discord API calls

  RUN: pytest tests/test_keyword_review.py -v
  OUTPUT: Complete test file with all 15 tests passing"

# Unit Test Agent 2: Discord Tests
claude-code agent create unit-test-discord \
  --parent supervisor \
  --task "Create tests/test_moa_discord_reviewer.py:

  TEST CASES:
  1. test_build_review_embed()
     - Call build_review_embed() with sample data
     - Assert embed['title'] contains 'MOA Keyword Review'
     - Assert embed['color'] == 0x3498DB
     - Assert fields are present

  2. test_build_review_components()
     - Call build_review_components('test_id')
     - Assert 4 buttons returned
     - Assert custom_ids are correct format

  3. test_post_review_request_success()
     - Mock discord_transport.post_discord_with_backoff
     - Call post_review_request()
     - Assert Discord API called correctly

  4. test_post_review_request_failure()
     - Mock Discord API failure
     - Call post_review_request()
     - Assert error logged
     - Assert returns False

  5. test_build_approval_confirmation()
     - Call build_approval_confirmation()
     - Assert success message
     - Assert green color

  6. test_build_rejection_confirmation()
     - Call build_rejection_confirmation()
     - Assert rejection message
     - Assert red color

  7. test_embed_truncation()
     - Create review with 50 recommendations
     - Call build_review_embed()
     - Assert embed stays under 6000 char limit

  8. test_button_disable_after_action()
     - Simulate button click
     - Call update handler
     - Assert buttons are disabled

  OUTPUT: Complete Discord test file"

# Integration Test Agent
claude-code agent create integration-tests \
  --parent supervisor \
  --task "Create tests/test_moa_review_integration.py with end-to-end tests:

  TEST CASES:
  1. test_full_workflow_approve_all()
     STEPS:
     - Run MOA analysis
     - Verify review created in database
     - Verify Discord message posted
     - Simulate 'Approve All' button click
     - Verify changes applied to keyword_stats.json
     - Verify audit trail logged

     ASSERTIONS:
     - Review state transitions: PENDING → APPROVED → APPLIED
     - keyword_stats.json contains new weights
     - Snapshot exists in database
     - Audit trail complete

  2. test_full_workflow_reject_all()
     STEPS:
     - Run MOA analysis
     - Simulate 'Reject All' button click
     - Verify no changes to keyword_stats.json

     ASSERTIONS:
     - Review state: REJECTED
     - keyword_stats.json unchanged
     - Rejection logged in audit trail

  3. test_full_workflow_individual_review()
     STEPS:
     - Run MOA with 5 recommendations
     - Click 'Review Individual'
     - Approve 2, reject 3
     - Verify only 2 changes applied

     ASSERTIONS:
     - State: PARTIAL_APPROVED → APPLIED
     - Only approved keywords in keyword_stats.json

  4. test_concurrent_review_prevention()
     STEPS:
     - Create two reviews for same keyword
     - Try to approve both
     - Verify conflict detected

     ASSERTIONS:
     - Second apply fails with conflict error
     - First apply succeeds

  5. test_rollback_workflow()
     STEPS:
     - Create, approve, and apply review
     - Trigger rollback
     - Verify keyword_stats.json restored

     ASSERTIONS:
     - State: ROLLED_BACK
     - Original weights restored
     - Rollback reason logged

  SETUP:
  @pytest.fixture
  def integration_env(tmp_path, monkeypatch):
      '''Set up complete test environment'''
      # Create temp directories
      data_dir = tmp_path / 'data'
      data_dir.mkdir()

      # Create mock keyword_stats.json
      stats_file = data_dir / 'analyzer' / 'keyword_stats.json'
      stats_file.parent.mkdir(parents=True)
      stats_file.write_text(json.dumps({
          'weights': {'fda': 1.0, 'partnership': 0.5},
          'last_updated': datetime.now(timezone.utc).isoformat()
      }))

      # Mock environment variables
      monkeypatch.setenv('MOA_REVIEW_ENABLED', '1')
      monkeypatch.setenv('MOA_REVIEW_DB_PATH', str(tmp_path / 'review.db'))

      # Mock Discord webhook
      monkeypatch.setenv('DISCORD_ADMIN_WEBHOOK', 'https://mock.webhook')

      yield tmp_path

  OUTPUT: Complete integration tests with setup/teardown"

# Validation Agent
claude-code agent create validation-scripts \
  --parent supervisor \
  --task "Create validation script scripts/validate_moa_review.py:

  VALIDATIONS:
  1. Database Integrity
     - Check all required tables exist
     - Check foreign key constraints
     - Check indexes exist

  2. keyword_stats.json Integrity
     - Valid JSON structure
     - All weights are positive floats
     - last_updated timestamp is valid

  3. Audit Trail Completeness
     - Every APPLIED review has snapshot
     - Every approval has reviewer_id
     - Timestamps are sequential

  4. Pending Review Health
     - No stuck pending reviews >7 days
     - No orphaned reviews

  5. System Configuration
     - All required env vars present
     - Database file exists and is writable
     - Discord webhook configured

  SCRIPT STRUCTURE:
  def validate_database():
      '''Validate database schema'''
      conn = init_optimized_connection(DB_PATH)
      # Check tables
      # Check constraints
      # Return validation results

  def validate_keyword_stats():
      '''Validate keyword_stats.json'''
      # Load file
      # Check structure
      # Check weights
      # Return validation results

  def validate_audit_trail():
      '''Validate audit completeness'''
      # Load all reviews
      # Check each has required events
      # Return validation results

  def main():
      results = {
          'database': validate_database(),
          'keyword_stats': validate_keyword_stats(),
          'audit_trail': validate_audit_trail(),
          'system_config': validate_system_config()
      }

      # Print results
      all_passed = all(r['passed'] for r in results.values())

      if all_passed:
          print('✅ All validations passed')
          return 0
      else:
          print('❌ Some validations failed')
          return 1

  RUN: python scripts/validate_moa_review.py
  OUTPUT: Validation script that returns exit code 0 if all pass"
```

---

### PHASE 5: Documentation & Alpha Testing (Week 5)

#### Objective
Create user documentation, alpha testing guide, and deployment checklist.

#### Claude Code CLI Commands

```bash
# Documentation Agent
claude-code agent create documentation-final \
  --parent supervisor \
  --task "Create comprehensive user documentation:

  FILE 1: docs/MOA_REVIEW_USER_GUIDE.md

  SECTIONS:
  1. Overview
     - What is MOA keyword review
     - Why manual review is important
     - Feature comparison (auto vs manual)

  2. Configuration
     - Environment variables
     - Recommended settings
     - Auto-approve vs manual review

  3. Using the Review Interface
     - Accessing Discord reviews
     - Understanding recommendation details
     - Approving changes
     - Rejecting changes
     - Individual keyword review

  4. Monitoring & Maintenance
     - Checking pending reviews
     - Viewing audit trail
     - Rolling back changes
     - Health checks

  5. Troubleshooting
     - Common issues
     - Debug logging
     - Support contacts

  FILE 2: docs/MOA_REVIEW_ADMIN_GUIDE.md

  SECTIONS:
  1. Installation
     - Database setup
     - Configuration
     - Discord webhook setup

  2. Operations
     - Daily monitoring
     - Review workflows
     - Handling conflicts

  3. Maintenance
     - Database cleanup
     - Log rotation
     - Performance tuning

  4. Security
     - Access control
     - Audit compliance
     - Data retention

  OUTPUT: Complete user and admin guides"

# Alpha Testing Agent
claude-code agent create alpha-testing-guide \
  --parent supervisor \
  --task "Create alpha testing guide docs/ALPHA_TESTING_GUIDE.md:

  STRUCTURE:

  ## Alpha Testing Checklist

  ### Phase 1: System Setup (Day 1)
  - [ ] Install dependencies
  - [ ] Run database migrations
  - [ ] Configure environment variables
  - [ ] Start bot in test mode
  - [ ] Verify Discord webhook connection

  ### Phase 2: Basic Workflow (Day 2)
  - [ ] Trigger MOA analysis manually
  - [ ] Verify review created in database
  - [ ] Check Discord message posted
  - [ ] Click 'Approve All' button
  - [ ] Verify keyword_stats.json updated
  - [ ] Check audit trail logged

  ### Phase 3: Individual Review (Day 3)
  - [ ] Trigger MOA with multiple recommendations
  - [ ] Click 'Review Individual'
  - [ ] Approve some keywords
  - [ ] Reject some keywords
  - [ ] Verify partial application

  ### Phase 4: Edge Cases (Day 4)
  - [ ] Test review expiration
  - [ ] Test concurrent review attempts
  - [ ] Test low confidence handling
  - [ ] Test duplicate keyword handling

  ### Phase 5: Rollback (Day 5)
  - [ ] Apply changes
  - [ ] Trigger rollback
  - [ ] Verify restore worked
  - [ ] Check audit trail

  ### Phase 6: Production Simulation (Day 6-7)
  - [ ] Run bot for 48 hours
  - [ ] Review 3-5 MOA reports
  - [ ] Monitor system performance
  - [ ] Check for errors in logs

  ## Test Scenarios

  ### Scenario 1: Happy Path
  GIVEN MOA analysis generates 5 recommendations
  WHEN admin clicks 'Approve All'
  THEN all 5 keywords are applied to keyword_stats.json
  AND audit trail shows approval event
  AND Discord shows success confirmation

  ### Scenario 2: Rejection
  GIVEN MOA analysis generates 5 recommendations
  WHEN admin clicks 'Reject All'
  THEN no changes to keyword_stats.json
  AND audit trail shows rejection event
  AND review state is REJECTED

  ### Scenario 3: Individual Review
  GIVEN MOA analysis generates 5 recommendations
  WHEN admin clicks 'Review Individual'
  AND approves 3 keywords
  AND rejects 2 keywords
  THEN only 3 approved keywords are applied
  AND review state is PARTIAL_APPROVED then APPLIED

  ## Bug Report Template

  ### Issue Title:
  [Brief description]

  ### Steps to Reproduce:
  1. ...
  2. ...

  ### Expected Behavior:
  ...

  ### Actual Behavior:
  ...

  ### Logs:
  ```
  [paste relevant logs]
  ```

  ### Environment:
  - Bot version:
  - Python version:
  - OS:

  OUTPUT: Complete alpha testing guide"
```

---

## Supervisor Agent Orchestration

### Supervisor Responsibilities

The supervisor agent manages the entire implementation:

1. **Phase Coordination**
   - Ensure Phase 1 completes before Phase 2 starts
   - Validate deliverables at each checkpoint
   - Resolve cross-team dependencies

2. **Quality Gates**
   - Review architectural decisions
   - Approve integration points
   - Validate test coverage

3. **Risk Management**
   - Monitor for blocking issues
   - Escalate critical problems
   - Maintain rollback plans

4. **Progress Tracking**
   - Daily status updates
   - Milestone completion verification
   - Timeline management

### Supervisor Commands

```bash
# Initialize Supervisor
claude-code agent create moa-review-supervisor \
  --type supervisor \
  --task "Oversee complete MOA keyword review implementation" \
  --plan-file docs/MOA_KEYWORD_REVIEW_IMPLEMENTATION_PLAN.md \
  --phases "discovery,implementation,integration,testing,deployment" \
  --quality-gates "architecture-review,integration-review,test-coverage,alpha-testing"

# Supervisor launches Phase 1
supervisor> launch phase discovery

# Supervisor monitors progress
supervisor> status

# Supervisor reviews architectural decisions
supervisor> review architecture
[Reviews integration_points.md and workflow_design.md]

# Supervisor approves and moves to Phase 2
supervisor> approve phase discovery
supervisor> launch phase implementation

# Continue through all phases...
```

---

## Critical Integration Points

### 1. MOA Analyzer Integration (CRITICAL)

**File:** `src/catalyst_bot/moa_historical_analyzer.py`
**Function:** `update_keyword_stats_file()` at line 1053
**Priority:** P0

**Current Code:**
```python
# Line 1053
def update_keyword_stats_file(recommendations, min_confidence=0.6):
    # ... loads existing weights ...

    for rec in recommendations:
        keyword = rec["keyword"]
        weight = rec["recommended_weight"]
        confidence = rec.get("confidence", 0.5)

        if confidence >= min_confidence:
            existing_weights[keyword] = weight  # ← DIRECT APPLY

    # ... saves to file ...
```

**New Code:**
```python
# Line 1053
def update_keyword_stats_file(recommendations, min_confidence=0.6):
    from .config import get_settings
    from .keyword_review import create_pending_review, apply_approved_changes, ReviewState
    from .moa_discord_reviewer import post_review_request

    settings = get_settings()

    # NEW: Check if review system enabled
    if settings.moa_review_enabled:
        log.info("using_review_workflow")

        # Create pending review
        review = create_pending_review(
            recommendations=recommendations,
            moa_run_timestamp=int(time.time()),
            auto_approve=settings.moa_auto_apply,
            auto_approve_confidence=settings.moa_min_confidence_auto,
            timeout_hours=settings.moa_review_timeout_hours
        )

        log.info(f"created_review review_id={review.review_id} state={review.state}")

        # Post to Discord
        post_review_request(
            review_id=review.review_id,
            recommendations=recommendations,
            summary={"total": len(recommendations)}
        )

        # If fully auto-approved, apply immediately
        if review.state == ReviewState.APPROVED and settings.moa_auto_apply:
            success, error = apply_approved_changes(
                review.review_id,
                applied_by="moa_nightly_auto",
                min_confidence=min_confidence
            )

            if success:
                log.info(f"auto_applied review_id={review.review_id}")
                return Path("data/analyzer/keyword_stats.json")
            else:
                log.error(f"auto_apply_failed error={error}")

        # Return path to pending review
        return Path(f"pending_review:{review.review_id}")

    else:
        # LEGACY: Direct apply (backward compatibility)
        log.info("using_legacy_direct_apply")
        # ... keep existing code ...
```

**Testing:**
```bash
# Test the integration
python -c "
from catalyst_bot.moa_historical_analyzer import run_historical_moa_analysis
from catalyst_bot.keyword_review import get_pending_reviews
import os

os.environ['MOA_REVIEW_ENABLED'] = '1'
os.environ['MOA_AUTO_APPLY'] = '0'

result = run_historical_moa_analysis()
pending = get_pending_reviews()

print(f'Result: {result}')
print(f'Pending reviews: {len(pending)}')
assert len(pending) > 0, 'No pending review created!'
print('✅ Integration test passed')
"
```

---

### 2. Discord Routing Integration (CRITICAL)

**File:** `src/catalyst_bot/admin_interactions.py`
**Function:** `handle_admin_interaction()` at line 216
**Priority:** P0

**Current Code:**
```python
# Line 245
if interaction_type == INTERACTION_TYPE_COMPONENT:
    data = interaction_data.get("data", {})
    custom_id = data.get("custom_id", "")

    if not custom_id.startswith("admin_"):
        return error_response()

    # ... handle admin buttons ...
```

**New Code:**
```python
# Line 245
if interaction_type == INTERACTION_TYPE_COMPONENT:
    data = interaction_data.get("data", {})
    custom_id = data.get("custom_id", "")

    # NEW: Route MOA review interactions first
    if custom_id.startswith("moa_review_"):
        from .moa_interaction_handler import handle_moa_review_interaction
        return handle_moa_review_interaction(interaction_data)

    if not custom_id.startswith("admin_"):
        return error_response()

    # ... handle admin buttons ...
```

**Testing:**
```python
# Test Discord routing
def test_moa_review_routing():
    from catalyst_bot.admin_interactions import handle_admin_interaction

    mock_interaction = {
        "type": 3,  # COMPONENT
        "data": {
            "custom_id": "moa_review_approve_all_test123"
        },
        "member": {
            "user": {"id": "admin123", "username": "testadmin"}
        }
    }

    response = handle_admin_interaction(mock_interaction)

    assert response is not None
    assert response["type"] in [4, 7]  # MESSAGE or UPDATE_MESSAGE
    print("✅ Discord routing test passed")
```

---

### 3. Runner Monitoring Integration (IMPORTANT)

**File:** `src/catalyst_bot/runner.py`
**Lines:** 87 (import), ~3450 (monitoring loop)
**Priority:** P1

**Add Import (Line 87):**
```python
from .keyword_review import get_pending_reviews, expire_old_reviews
```

**Add Monitoring (Line ~3450):**
```python
# After MOA price tracking section
if settings.moa_review_enabled and cycle_count % 12 == 0:  # Hourly
    try:
        # Expire old reviews
        expired = expire_old_reviews()
        if expired > 0:
            log.info(f"expired_old_reviews count={expired}")

        # Log pending reviews
        pending = get_pending_reviews()
        if pending:
            oldest = pending[0] if pending else None
            log.info(
                f"pending_moa_reviews count={len(pending)} "
                f"oldest_age_hours={oldest.age_hours if oldest else 0}"
            )
    except Exception as e:
        log.debug(f"pending_review_check_failed err={e}")
```

---

## Data Schemas

### Review Record Schema

```python
@dataclass
class Review:
    review_id: str              # Format: "moa_review_{timestamp}_{uuid}"
    state: ReviewState          # PENDING, APPROVED, REJECTED, etc.
    moa_run_timestamp: int      # Unix timestamp of MOA run
    created_at: int             # Unix timestamp
    updated_at: int             # Unix timestamp
    expires_at: Optional[int]   # Unix timestamp or None

    changes: List[KeywordChange]  # List of keyword changes

    total_keywords: int
    approved_count: int = 0
    rejected_count: int = 0

    applied_at: Optional[int] = None
    applied_by: Optional[str] = None

    rolled_back_at: Optional[int] = None
    rollback_reason: Optional[str] = None

    reviewer_id: Optional[str] = None
    review_notes: Optional[str] = None
```

### Keyword Change Schema

```python
@dataclass
class KeywordChange:
    keyword: str
    old_weight: Optional[float]  # None if new keyword
    new_weight: float
    weight_delta: float          # new - old
    confidence: float            # 0.0 - 1.0
    occurrences: int            # Times seen in analysis
    success_rate: float         # 0.0 - 1.0
    avg_return_pct: float       # Average return percentage
    evidence: Dict[str, Any]    # Full evidence object
    status: ChangeStatus        # PENDING, APPROVED, REJECTED, SKIPPED
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[int] = None
```

### Discord Embed Schema

```json
{
  "title": "🔍 MOA Keyword Review Required",
  "description": "8 keyword weight changes recommended based on 147 missed opportunities",
  "color": 3447003,
  "fields": [
    {
      "name": "📊 Analysis Summary",
      "value": "**Period:** 30 days\n**Missed Opps:** 147 (28.1% miss rate)\n**Avg Return:** +18.5%",
      "inline": false
    },
    {
      "name": "🎯 Top 5 Recommendations",
      "value": "1. **breakthrough_therapy** → 1.50 (conf: 85%)\n   • 12 occurrences | 75% success | +18.3% avg\n...",
      "inline": false
    }
  ],
  "footer": {
    "text": "Use buttons below to approve or reject • Expires in 48 hours"
  },
  "timestamp": "2025-11-11T19:30:00Z"
}
```

### Button Components Schema

```json
[
  {
    "type": 1,
    "components": [
      {
        "type": 2,
        "style": 3,
        "label": "Approve All",
        "custom_id": "moa_review_approve_all_20251111_193000",
        "emoji": {"name": "✅"}
      },
      {
        "type": 2,
        "style": 4,
        "label": "Reject All",
        "custom_id": "moa_review_reject_all_20251111_193000",
        "emoji": {"name": "❌"}
      },
      {
        "type": 2,
        "style": 1,
        "label": "Review Individual",
        "custom_id": "moa_review_individual_20251111_193000",
        "emoji": {"name": "🔎"}
      },
      {
        "type": 2,
        "style": 2,
        "label": "View Details",
        "custom_id": "moa_review_details_20251111_193000",
        "emoji": {"name": "📊"}
      }
    ]
  }
]
```

---

## Configuration Guide

### Required Environment Variables

```bash
# === MOA Keyword Review System ===

# Enable manual review workflow (1=enabled, 0=disabled)
MOA_REVIEW_ENABLED=1

# Auto-apply high-confidence changes (1=auto, 0=always manual)
# RECOMMENDED: 0 for production (always require human approval)
MOA_AUTO_APPLY=0

# Minimum confidence for auto-approval (0.0-1.0)
# Only used if MOA_AUTO_APPLY=1
# RECOMMENDED: 0.9 (very high confidence only)
MOA_MIN_CONFIDENCE_AUTO=0.9

# Minimum confidence to apply at all (safety threshold)
# Changes below this are skipped even if approved
# RECOMMENDED: 0.6 (moderate confidence floor)
MOA_MIN_CONFIDENCE_THRESHOLD=0.6

# Review timeout in hours
# Pending reviews expire after this time
# RECOMMENDED: 48 (2 days)
MOA_REVIEW_TIMEOUT_HOURS=48

# Review database path
MOA_REVIEW_DB_PATH=data/keyword_review.db
```

### Recommended Settings by Environment

**Development:**
```bash
MOA_REVIEW_ENABLED=1
MOA_AUTO_APPLY=1  # Auto-approve for faster testing
MOA_MIN_CONFIDENCE_AUTO=0.7  # Lower threshold
MOA_REVIEW_TIMEOUT_HOURS=24
```

**Staging:**
```bash
MOA_REVIEW_ENABLED=1
MOA_AUTO_APPLY=0  # Manual review
MOA_MIN_CONFIDENCE_AUTO=0.9
MOA_REVIEW_TIMEOUT_HOURS=48
```

**Production:**
```bash
MOA_REVIEW_ENABLED=1
MOA_AUTO_APPLY=0  # Always manual
MOA_MIN_CONFIDENCE_AUTO=0.95  # Very high bar
MOA_MIN_CONFIDENCE_THRESHOLD=0.6
MOA_REVIEW_TIMEOUT_HOURS=72  # 3 days
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] All unit tests passing (`pytest tests/test_keyword_review*.py`)
- [ ] All integration tests passing (`pytest tests/test_moa_review_integration.py`)
- [ ] Validation script passes (`python scripts/validate_moa_review.py`)
- [ ] Documentation complete (user guide, admin guide)
- [ ] Alpha testing completed (all scenarios passed)
- [ ] Rollback plan documented
- [ ] Backup of current keyword_stats.json created

### Deployment Steps

1. **Create Backup**
   ```bash
   # Backup keyword_stats.json
   cp data/analyzer/keyword_stats.json \
      data/analyzer/keyword_stats.json.backup.$(date +%Y%m%d_%H%M%S)

   # Backup database if exists
   if [ -f "data/keyword_review.db" ]; then
       cp data/keyword_review.db \
          data/keyword_review.db.backup.$(date +%Y%m%d_%H%M%S)
   fi
   ```

2. **Deploy Code**
   ```bash
   # Pull latest code
   git pull origin main

   # Install dependencies
   pip install -r requirements.txt

   # Run database migrations
   python -m catalyst_bot.keyword_review_db migrate
   ```

3. **Configure Environment**
   ```bash
   # Add to .env
   echo "MOA_REVIEW_ENABLED=1" >> .env
   echo "MOA_AUTO_APPLY=0" >> .env
   echo "MOA_MIN_CONFIDENCE_AUTO=0.9" >> .env
   echo "MOA_MIN_CONFIDENCE_THRESHOLD=0.6" >> .env
   echo "MOA_REVIEW_TIMEOUT_HOURS=48" >> .env
   ```

4. **Validate Installation**
   ```bash
   # Run validation script
   python scripts/validate_moa_review.py

   # Check database
   sqlite3 data/keyword_review.db "SELECT name FROM sqlite_master WHERE type='table';"

   # Expected output:
   # keyword_reviews
   # keyword_changes
   # keyword_stats_snapshots
   # review_conflicts
   ```

5. **Test Discord Integration**
   ```bash
   # Send test review
   python -m catalyst_bot.cli review create-test

   # Check Discord for message
   # Click buttons to verify interaction
   ```

6. **Start Bot**
   ```bash
   # Start with logging
   python -m catalyst_bot.runner --log-level INFO

   # Monitor logs
   tail -f data/logs/bot.jsonl | grep -i "review"
   ```

### Post-Deployment Monitoring

**Day 1:**
- [ ] Monitor first MOA run
- [ ] Verify review created
- [ ] Verify Discord message posted
- [ ] Test approval workflow
- [ ] Check logs for errors

**Day 2-7:**
- [ ] Review 3-5 MOA reports
- [ ] Monitor system performance
- [ ] Check database growth
- [ ] Verify audit trail completeness

**Week 2+:**
- [ ] Analyze approval patterns
- [ ] Tune confidence thresholds
- [ ] Review rollback frequency
- [ ] Optimize Discord embeds

### Rollback Procedure

If critical issues occur:

1. **Disable Review System**
   ```bash
   # Set in .env
   MOA_REVIEW_ENABLED=0

   # Restart bot
   systemctl restart catalyst-bot
   ```

2. **Restore Backups**
   ```bash
   # Find latest backup
   ls -lt data/analyzer/keyword_stats.json.backup.*

   # Restore
   cp data/analyzer/keyword_stats.json.backup.YYYYMMDD_HHMMSS \
      data/analyzer/keyword_stats.json
   ```

3. **Verify Restoration**
   ```bash
   # Check file
   python -c "import json; print(json.load(open('data/analyzer/keyword_stats.json')))"

   # Run validation
   python scripts/validate_moa_review.py
   ```

---

## Success Metrics

### Technical Metrics

- **Review Creation Success Rate:** >99%
- **Discord Post Success Rate:** >95%
- **Approval Application Success Rate:** >99%
- **Database Write Success Rate:** >99.9%
- **Rollback Success Rate:** 100%

### Operational Metrics

- **Average Review Time:** <15 minutes
- **Reviews Pending >24h:** <5%
- **Reviews Expired:** <2%
- **False Positive Rate:** <10%

### User Satisfaction Metrics

- **Ease of Use:** >4/5
- **Clarity of Recommendations:** >4/5
- **Confidence in Changes:** >4/5

---

## Support & Troubleshooting

### Common Issues

**Issue 1: Review not created**
```bash
# Check logs
grep "created_review" data/logs/bot.jsonl

# Check MOA enabled
python -c "from catalyst_bot.config import get_settings; print(get_settings().moa_review_enabled)"

# Expected: True
```

**Issue 2: Discord message not posted**
```bash
# Check webhook configured
echo $DISCORD_ADMIN_WEBHOOK

# Test webhook
curl -X POST $DISCORD_ADMIN_WEBHOOK \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message"}'
```

**Issue 3: Button clicks not working**
```bash
# Check admin_interactions.py modified
grep "moa_review_" src/catalyst_bot/admin_interactions.py

# Check interaction handler exists
python -c "from catalyst_bot.moa_interaction_handler import handle_moa_review_interaction; print('OK')"
```

**Issue 4: Changes not applied**
```bash
# Check review state
sqlite3 data/keyword_review.db \
  "SELECT review_id, state FROM keyword_reviews ORDER BY created_at DESC LIMIT 5;"

# Check for errors
grep "apply_approved_changes" data/logs/bot.jsonl | grep -i error
```

### Debug Commands

```bash
# List all reviews
python -m catalyst_bot.cli review list

# Show review details
python -m catalyst_bot.cli review show <review_id>

# Check database health
python scripts/validate_moa_review.py --verbose

# View pending reviews
python -m catalyst_bot.cli review list-pending

# Force expire old reviews
python -m catalyst_bot.cli review expire-old --force
```

### Contact Support

- GitHub Issues: https://github.com/Amenzel91/catalyst-bot/issues
- Discord: #catalyst-bot-support
- Email: support@catalyst-bot.com

---

## Appendix

### A. Complete File Inventory

**New Files:**
- `src/catalyst_bot/keyword_review.py` (~800 lines)
- `src/catalyst_bot/keyword_review_db.py` (~300 lines)
- `src/catalyst_bot/keyword_review_rules.py` (~200 lines)
- `src/catalyst_bot/moa_discord_reviewer.py` (~400 lines)
- `src/catalyst_bot/moa_interaction_handler.py` (~600 lines)
- `tests/test_keyword_review.py` (~500 lines)
- `tests/test_moa_discord_reviewer.py` (~300 lines)
- `tests/test_moa_interaction_handler.py` (~400 lines)
- `tests/test_moa_review_integration.py` (~300 lines)
- `scripts/validate_moa_review.py` (~200 lines)
- `docs/MOA_REVIEW_USER_GUIDE.md`
- `docs/MOA_REVIEW_ADMIN_GUIDE.md`
- `docs/ALPHA_TESTING_GUIDE.md`

**Modified Files:**
- `src/catalyst_bot/moa_historical_analyzer.py` (lines 1053-1132)
- `src/catalyst_bot/moa_reporter.py` (add lines after 323)
- `src/catalyst_bot/admin_interactions.py` (lines 216-287)
- `src/catalyst_bot/runner.py` (lines 87, ~3450)
- `src/catalyst_bot/config.py` (add settings block)
- `.env.example` (add MOA review section)

**Total Lines of Code:** ~4,500 new lines + ~200 modified lines

### B. Dependencies

**No New External Dependencies**

All functionality uses existing libraries:
- `sqlite3` (stdlib)
- `json` (stdlib)
- `dataclasses` (stdlib)
- `enum` (stdlib)
- `pathlib` (stdlib)
- `typing` (stdlib)
- `datetime` (stdlib)

### C. Timeline Estimate

**Total Duration:** 5-6 weeks

- Phase 1 (Discovery): 1 week
- Phase 2 (Implementation): 2 weeks
- Phase 3 (Integration): 1 week
- Phase 4 (Testing): 1 week
- Phase 5 (Documentation): 1 week (parallel with Phase 4)
- Deployment & Monitoring: Ongoing

---

## Final Notes

This implementation plan is **complete and ready for Claude Code CLI execution**. All agents have clear tasks, file paths, line numbers, and success criteria.

Key features:
- ✅ Detailed integration points with exact line numbers
- ✅ Complete code examples for all critical functions
- ✅ Comprehensive test coverage specifications
- ✅ Clear supervisor orchestration structure
- ✅ Production-ready deployment checklist
- ✅ Rollback procedures documented

**Next Steps:**
1. Launch supervisor agent with this plan
2. Execute Phase 1 (Discovery & Design)
3. Review and approve Phase 1 deliverables
4. Proceed through remaining phases sequentially
5. Deploy to production with monitoring

---

**Document Version:** 1.0
**Last Updated:** 2025-11-11
**Author:** Claude Code Planning Team
**Status:** ✅ READY FOR IMPLEMENTATION
