# Master Deduplication Plan
**Project:** Catalyst Bot Codebase Cleanup
**Repository:** /home/user/catalyst-bot
**Created:** 2025-12-14
**Status:** Planning Phase

---

## Executive Summary

The catalyst-bot codebase has accumulated significant duplication across utility functions, configuration management, type definitions, and service patterns. This master plan outlines a systematic, risk-mitigated approach to consolidate duplicate code, remove dead code, and organize the root-level directory structure.

### Goals
1. **Eliminate Duplication**: Consolidate 9+ implementations of critical utilities (GPU detection, token estimation, webhook masking, repo root finding)
2. **Improve Maintainability**: Reduce cognitive load by having single sources of truth
3. **Enhance Reliability**: Remove dead code that creates confusion and potential bugs
4. **Organize Structure**: Clean up 89 root-level files into logical subdirectories
5. **Preserve Functionality**: Ensure zero feature regression through careful testing

### Principles
- **Safety First**: Every wave includes comprehensive testing before merge
- **Incremental Progress**: Small, reviewable changes organized into logical waves
- **Reversibility**: All changes made via git with clear rollback procedures
- **Documentation**: Each wave documented with rationale, changes, and verification steps
- **Dependency Awareness**: Waves ordered to handle dependencies correctly

---

## Risk Mitigation Strategy

### Pre-Change Safeguards
1. **Git Branch Isolation**: Each wave implemented on dedicated feature branch
2. **Comprehensive Testing**: Run full test suite before and after changes
3. **Manual Verification**: Test affected features through UI/CLI when applicable
4. **Code Review**: All changes reviewed before merge
5. **Dependency Mapping**: Document all import relationships before refactoring

### During Implementation
1. **Incremental Commits**: Logical, atomic commits that can be individually reviewed
2. **Import Analysis**: Use `grep` to find all usages before moving/removing code
3. **Backward Compatibility**: Maintain old imports temporarily with deprecation warnings when needed
4. **Logging**: Add temporary logging to verify new code paths are executing

### Post-Change Validation
1. **Automated Tests**: Full pytest suite must pass
2. **Integration Tests**: Verify end-to-end workflows (trading, monitoring, heartbeat)
3. **Performance Check**: Ensure no performance degradation
4. **Deployment Test**: Test in staging environment before production

### Risk Assessment Criteria
- **Low Risk**: Isolated utilities, clear single usage, comprehensive tests exist
- **Medium Risk**: Multiple usages across modules, some tests exist, well-understood behavior
- **High Risk**: Core trading logic, async/sync variants, limited test coverage, complex dependencies

---

## Wave Overview Table

| Wave | Name | Files Affected | Risk Level | Complexity | Dependencies | Status |
|------|------|----------------|------------|------------|--------------|--------|
| 1 | Critical Utility Duplicates | 15-20 | Medium | High | None | Planned |
| 2 | Position Manager Consolidation | 5-8 | High | High | Wave 1 | Planned |
| 3 | Configuration Cleanup | 8-12 | Medium | Medium | None | Planned |
| 4 | Dead Code Removal | 10-15 | Low | Low | Wave 2, 3 | Planned |
| 5 | Root-Level Script Organization | 89+ | Low | Medium | Wave 1, 3 | Planned |
| 6 | Service Pattern Consolidation | 12-18 | Medium | High | Wave 1 | Planned |
| 7 | Type Definitions Consolidation | 8-12 | Medium | Medium | Wave 2 | Planned |

**Total Estimated Files Affected**: 147-184 files
**Estimated Timeline**: 7-10 weeks (1-2 weeks per wave including testing)

---

## Wave Descriptions

### Wave 1: Critical Utility Duplicates
**Priority**: Highest | **Risk**: Medium | **Complexity**: High

Consolidate 9+ duplicate implementations of critical utility functions that appear throughout the codebase. This includes GPU detection/cleanup (found in multiple trading modules), token estimation utilities (duplicated across LLM integration points), webhook payload masking (security-critical, inconsistently implemented), and repository root path detection (scattered across config and startup scripts). These duplicates create maintenance burden and potential bugs when fixes are applied to only some implementations.

**Key Deliverables**: Single canonical implementation for each utility in `/utils/` with comprehensive tests, migration of all call sites, deprecation warnings for old paths.

### Wave 2: Position Manager Consolidation
**Priority**: High | **Risk**: High | **Complexity**: High

Unify async and sync position manager variants that have diverged over time, creating confusion about which to use and duplicating core position management logic. The codebase currently maintains parallel implementations for synchronous and asynchronous contexts, leading to inconsistent behavior and doubled maintenance burden. This wave requires careful analysis of threading/async requirements and comprehensive testing of trading workflows.

**Key Deliverables**: Unified position manager with proper async/sync abstraction, migration of all trading engine integration points, verification that both async and sync trading paths work correctly.

### Wave 3: Configuration Cleanup
**Priority**: High | **Risk**: Medium | **Complexity**: Medium

Consolidate fragmented configuration management spread across `config.py`, `config_extras.py`, various feature flag modules, and scattered environment variable helpers. The current state creates uncertainty about where configuration should live and how to properly override settings. Establish clear patterns for configuration hierarchy (environment variables → config files → defaults) and consolidate feature flag logic.

**Key Deliverables**: Single configuration module with clear hierarchy, feature flags centralized, environment helpers consolidated, all config access points updated.

### Wave 4: Dead Code Removal
**Priority**: Medium | **Risk**: Low | **Complexity**: Low

Remove confirmed dead code including `paper_trader.py` (superseded by newer trading engine), `quickchart_integration.py` (functionality moved elsewhere), unused monitoring modules, and other abandoned experiments. Dead code creates confusion for developers, increases cognitive load during codebase navigation, and may contain security vulnerabilities that won't be patched. This wave requires thorough grep analysis to confirm code is truly unused.

**Key Deliverables**: Removal of confirmed dead code, documentation of what was removed and why, verification that no imports reference removed modules.

### Wave 5: Root-Level Script Organization
**Priority**: Medium | **Risk**: Low | **Complexity**: Medium

Organize 89 root-level files into logical subdirectory structure (`/scripts/`, `/tools/`, `/docs/`, `/tests/`). The current flat structure makes it difficult to understand the codebase organization and find relevant files. This wave requires careful categorization of each file's purpose and updating any hardcoded paths that reference these files.

**Key Deliverables**: Organized directory structure, all files categorized appropriately, paths updated throughout codebase, README updated with new structure.

### Wave 6: Service Pattern Consolidation
**Priority**: Medium | **Risk**: Medium | **Complexity**: High

Consolidate duplicate HTTP client implementations, caching strategies, and retry logic patterns scattered across API integration modules. Different services have independently implemented similar patterns (rate limiting, exponential backoff, request caching), leading to inconsistent behavior and duplicated code. Establish canonical service patterns that can be reused.

**Key Deliverables**: Reusable HTTP client base class, unified caching decorator, standard retry/backoff utilities, migration of all API clients to use shared patterns.

### Wave 7: Type Definitions Consolidation
**Priority**: Low | **Risk**: Medium | **Complexity**: Medium

Consolidate duplicate type definitions for Position classes, ManagedPosition variants, ClosedPosition representations, and related trading types. Multiple modules define similar or identical types, creating import confusion and type checking challenges. Some types have subtle differences that need to be reconciled.

**Key Deliverables**: Canonical type definitions in `/types/` or `/models/`, migration of all type references, mypy/type checking verification, documentation of type hierarchy.

---

## Testing Strategy

### Pre-Wave Testing Baseline
Before starting each wave:
1. **Capture Test Results**: Run full test suite and document passing/failing tests
   ```bash
   pytest --tb=short --cov=. --cov-report=term > baseline_tests.txt
   ```
2. **Document Current Behavior**: For high-risk waves, document expected behavior of affected features
3. **Identify Critical Paths**: List the most important user-facing features that could be affected

### Per-Wave Testing Protocol

#### Unit Tests
- **Requirement**: All new canonical implementations must have unit tests
- **Coverage Target**: Minimum 80% coverage for newly consolidated code
- **Test Cases**: Include edge cases from all duplicate implementations being removed

#### Integration Tests
- **Scope**: Test affected modules in realistic usage scenarios
- **Examples**:
  - Wave 1: Test GPU detection in actual training context
  - Wave 2: Execute full trading cycle (open → monitor → close position)
  - Wave 3: Test configuration loading with various env var combinations
  - Wave 6: Test API clients with mock server responses

#### Manual Testing Checklist
For each wave, verify:
- [ ] Application starts successfully
- [ ] No import errors or warnings
- [ ] Core features function correctly (trading, monitoring, heartbeat)
- [ ] Logs show expected behavior
- [ ] Performance is comparable to pre-change baseline

#### Regression Testing
- **Full Suite**: Run complete pytest suite
- **Critical Paths**: Manually test most important workflows
- **Performance**: Compare execution time of key operations

### Continuous Integration
- All tests must pass before merge
- No new linting errors introduced
- Type checking (mypy) must pass if applicable
- Code coverage should not decrease

---

## Rollback Procedures

### Immediate Rollback (Same Session)
If issues discovered during implementation:
1. **Unstage Changes**: `git reset --soft HEAD~1` to undo last commit
2. **Discard Working Changes**: `git checkout -- .` to discard unstaged changes
3. **Return to Clean State**: Verify `git status` shows clean working directory
4. **Document Issue**: Record what went wrong before attempting again

### Branch-Level Rollback
If issues discovered after merge to feature branch:
1. **Identify Problem Commit**: `git log --oneline` to find the problematic commit
2. **Revert Specific Commit**: `git revert <commit-hash>` to create inverse commit
3. **Alternative - Hard Reset**: `git reset --hard <commit-before-problem>` if not shared
4. **Verify Functionality**: Run tests to confirm system back to working state

### Wave-Level Rollback
If entire wave needs to be undone:
1. **Identify Wave Start**: Find first commit of the wave from wave documentation
2. **Create Revert Branch**: `git checkout -b revert-wave-X main`
3. **Revert Commit Range**: `git revert <first-commit>^..<last-commit>`
4. **Test Reverted State**: Verify system works after revert
5. **Document Reason**: Update wave documentation with rollback reason

### Production Rollback
If issues discovered after deployment:
1. **Immediate**: Revert to previous deployment/container
2. **Git Level**: Create hotfix branch from last known good commit
3. **Deploy**: Fast-track deployment of rollback
4. **Post-Mortem**: Document what happened and update testing strategy

### Rollback Decision Criteria
Trigger rollback if:
- **Critical Functionality Broken**: Trading, position management, or monitoring fails
- **Data Loss Risk**: Any indication of potential data corruption
- **Performance Degradation**: >20% performance decrease in critical paths
- **Security Issue**: Any security vulnerability introduced
- **Cascading Failures**: Issues that cause multiple systems to fail

---

## Documentation Standards

### Wave-Specific Documentation Format
Each wave should have a detailed document: `docs/deduplication/0X-WAVE-<NAME>.md`

#### Required Sections
1. **Overview**: Purpose, scope, and goals of the wave
2. **Analysis**: Current state, identified duplicates/issues, proposed solution
3. **Changes**: Detailed list of all changes made
   - Files modified/moved/deleted
   - Functions consolidated
   - Import paths updated
4. **Migration Guide**: How developers should update their code if needed
5. **Testing**: Tests added, test results, verification steps performed
6. **Risks & Mitigations**: Known risks and how they were addressed
7. **Rollback Info**: Wave-specific rollback considerations

#### Code Documentation
When consolidating code:
- **Add Docstrings**: Every consolidated function gets comprehensive docstring
- **Note Provenance**: Comment indicating which duplicate implementations were merged
- **Document Decisions**: If choosing between implementation variants, document why
- **Type Hints**: Add full type hints to consolidated code

#### Commit Message Format
```
wave-X(<scope>): <short description>

<detailed description of changes>

- Specific change 1
- Specific change 2

Wave: <wave-number>
Risk: <Low/Medium/High>
```

Example:
```
wave-1(utils): consolidate GPU cleanup implementations

Merged 4 duplicate GPU cleanup functions into single canonical
implementation in utils/gpu_utils.py

- Kept most robust implementation from trading/gpu_manager.py
- Added memory clearing from monitoring/resource_cleanup.py
- Migrated 12 call sites to new location
- Added comprehensive unit tests

Wave: 1
Risk: Medium
```

### Documentation Review Checklist
Before marking wave as complete:
- [ ] Wave document created with all required sections
- [ ] All code changes have clear docstrings
- [ ] Commit messages follow standard format
- [ ] Migration guide provided if needed
- [ ] Testing results documented
- [ ] Known issues/limitations noted
- [ ] Master plan updated with wave status

---

## Progress Tracking

### Wave Status Definitions
- **Planned**: Wave defined, not yet started
- **In Progress**: Active development underway
- **Testing**: Implementation complete, undergoing verification
- **Complete**: Tested, merged, and verified in production
- **Blocked**: Cannot proceed due to dependencies or issues
- **Deferred**: Postponed to later phase

### Metrics to Track
For each wave, document:
- **Files Changed**: Actual count vs estimate
- **Lines Removed**: Net lines of code eliminated
- **Test Coverage**: Before and after coverage percentage
- **Duration**: Actual time spent vs estimate
- **Issues Found**: Bugs discovered during implementation
- **Performance Impact**: Any measurable performance changes

### Completion Criteria
A wave is considered complete when:
1. All code changes merged to main branch
2. All tests passing in CI/CD
3. Wave documentation complete and reviewed
4. No known issues or all issues documented as acceptable
5. Deployed to staging and manually verified
6. Master plan updated with completion status

---

## Dependencies & Order

### Wave Execution Order
The waves should generally be executed in numerical order, but some parallelization is possible:

**Phase 1** (Can run in parallel):
- Wave 1: Critical Utility Duplicates
- Wave 3: Configuration Cleanup

**Phase 2** (Requires Phase 1):
- Wave 2: Position Manager Consolidation (requires Wave 1 utils)
- Wave 6: Service Pattern Consolidation (requires Wave 1 utils)

**Phase 3** (Requires Phase 1 & 2):
- Wave 4: Dead Code Removal (safer after Wave 2 & 3)
- Wave 5: Root-Level Script Organization (requires Wave 1 & 3 for path updates)
- Wave 7: Type Definitions Consolidation (requires Wave 2)

### Cross-Wave Dependencies
- **Wave 1 → Wave 2**: Position manager uses consolidated utilities
- **Wave 1 → Wave 5**: Script organization needs finalized utility paths
- **Wave 1 → Wave 6**: Service patterns use consolidated utilities
- **Wave 2 → Wave 4**: Dead code removal safer after position manager consolidation
- **Wave 2 → Wave 7**: Type consolidation depends on unified position manager
- **Wave 3 → Wave 4**: Dead code removal safer after config cleanup
- **Wave 3 → Wave 5**: Script organization needs finalized config paths

---

## Success Metrics

### Quantitative Goals
- **Code Reduction**: Remove 15-25% of duplicate/dead code
- **File Organization**: Reduce root-level files from 89 to <20
- **Test Coverage**: Maintain or improve current coverage (target: 80%+)
- **Zero Regressions**: No functionality lost during consolidation
- **Performance**: No degradation in critical paths (trading, monitoring)

### Qualitative Goals
- **Developer Experience**: Easier to find and understand code
- **Maintainability**: Single place to fix bugs in consolidated code
- **Onboarding**: New developers can navigate codebase more easily
- **Confidence**: Team confident in making changes without breaking things

### Review Points
- **After Wave 2**: Review progress, adjust timeline if needed
- **After Wave 4**: Mid-project checkpoint, validate approach
- **After Wave 7**: Final review and retrospective

---

## Notes & Assumptions

### Assumptions
1. Full test suite exists and passes before starting
2. Git workflow allows feature branches
3. Staging environment available for integration testing
4. Code review process in place
5. Ability to rollback deployments if issues found

### Known Challenges
1. **Async/Sync Complexity**: Wave 2 position manager consolidation is complex
2. **Import Dependencies**: Many files import utilities; grep analysis critical
3. **Configuration Cascade**: Wave 3 config changes may have wide impact
4. **Path Hardcoding**: Wave 5 may reveal hardcoded paths that need updating

### Future Considerations
After completing all 7 waves:
- Consider establishing linting rules to prevent duplication
- Set up pre-commit hooks to catch new duplicate patterns
- Create coding standards document
- Implement architectural decision records (ADRs) for major patterns

---

## Document Index

| Document | Description |
|----------|-------------|
| [00-MASTER-DEDUPE-PLAN.md](./00-MASTER-DEDUPE-PLAN.md) | This document - Master plan and overview |
| [01-WAVE-CRITICAL-UTILITIES.md](./01-WAVE-CRITICAL-UTILITIES.md) | GPU cleanup, token estimation, webhook masking, repo root |
| [02-WAVE-POSITION-MANAGERS.md](./02-WAVE-POSITION-MANAGERS.md) | Async/sync position manager consolidation |
| [03-WAVE-CONFIG-CLEANUP.md](./03-WAVE-CONFIG-CLEANUP.md) | Configuration and feature flag consolidation |
| [04-WAVE-DEAD-CODE.md](./04-WAVE-DEAD-CODE.md) | Dead code removal and cleanup |
| [05-WAVE-ROOT-SCRIPTS.md](./05-WAVE-ROOT-SCRIPTS.md) | Root-level script organization |
| [06-WAVE-SERVICE-PATTERNS.md](./06-WAVE-SERVICE-PATTERNS.md) | HTTP clients, caching, retry logic |
| [07-WAVE-TYPE-DEFINITIONS.md](./07-WAVE-TYPE-DEFINITIONS.md) | Type and class consolidation |

---

**Document Version**: 1.0
**Last Updated**: 2025-12-14
**Next Review**: After Wave 2 completion
