"""
Comprehensive Test Suite for 3 Patch Waves (11/5/2025)
Testing against 27 real-world alerts to validate:
- Wave 1: Retrospective sentiment filter
- Wave 2: .env configuration changes
- Wave 3: SEC filing format improvements

NOTE: This test suite validates EXPECTED behavior after patches are applied.
Run this as BASELINE (before patches) to identify current gaps.
Run this as VALIDATION (after patches) to confirm fixes.
"""

import pytest
import os
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
from catalyst_bot.classify import classify
from catalyst_bot.config import get_settings

# Import functions - with fallback if not yet implemented
try:
    from catalyst_bot.classify import is_retrospective_sentiment
    RETROSPECTIVE_FILTER_EXISTS = True
except (ImportError, AttributeError):
    RETROSPECTIVE_FILTER_EXISTS = False

    def is_retrospective_sentiment(title, description):
        """Fallback implementation for baseline testing"""
        return False  # Will cause baseline tests to show current state

try:
    from catalyst_bot.sec_filing_adapter import SecFilingAdapter
    SEC_ADAPTER_EXISTS = True
except ImportError:
    SEC_ADAPTER_EXISTS = False

    class SecFilingAdapter:
        """Fallback for baseline testing"""
        def format_filing(self, filing):
            return str(filing)


# ============================================================================
# TEST DATA: 27 Real Alerts from 11/5/2025
# ============================================================================

RETROSPECTIVE_ALERTS = [
    {
        "ticker": "MX",
        "title": "Why Magnachip (MX) Stock Is Trading Lower Today",
        "description": "Stock down after earnings miss",
        "published": "2025-11-05T10:00:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "CLOV",
        "title": "Why Clover Health (CLOV) Stock Is Falling Today",
        "description": "Shares falling on guidance cut",
        "published": "2025-11-05T09:30:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "PAYO",
        "title": "Why Payoneer (PAYO) Stock Is Trading Lower Today",
        "description": "Trading lower after analyst downgrade",
        "published": "2025-11-05T11:15:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "HTZ",
        "title": "Why Hertz (HTZ) Shares Are Getting Obliterated Today",
        "description": "Shares obliterated on bankruptcy concerns",
        "published": "2025-11-05T10:45:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "GT",
        "title": "Goodyear (GT) Soars 7.85 as Restructuring to Slash $2.2-Billion Debt",
        "description": "Stock soaring on restructuring news",
        "published": "2025-11-05T12:00:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "NVTS",
        "title": "Navitas (NVTS) Falls 14.6% as Earnings Disappoint",
        "description": "Falling on earnings disappointment",
        "published": "2025-11-05T09:00:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "WRD",
        "title": "WeRide (WRD) Loses 13.7% Ahead of HK Listing",
        "description": "Losing value ahead of listing",
        "published": "2025-11-05T08:30:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "SVCO",
        "title": "Silvaco Group, Inc. (SVCO) May Report Negative Earnings",
        "description": "May report negative earnings tomorrow",
        "published": "2025-11-05T14:00:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "SMSI",
        "title": "Will Smith Micro Software, Inc. (SMSI) Report Negative Q3 Earnings?",
        "description": "Speculation about upcoming earnings",
        "published": "2025-11-05T13:30:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "ALVO",
        "title": "Analysts Estimate Alvotech (ALVO) to Report a Decline in Earnings",
        "description": "Analyst estimates show decline",
        "published": "2025-11-05T11:00:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "HNST",
        "title": "The Honest Company (NASDAQ:HNST) Misses Q3 Sales Expectations, Stock Drops 12.6%",
        "description": "Missing expectations and dropping",
        "published": "2025-11-05T10:30:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "CVRX",
        "title": "CVRx: Q3 Earnings Snapshot",
        "description": "Q3 earnings summary",
        "published": "2025-11-05T09:45:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "RLJ",
        "title": "RLJ Lodging: Q3 Earnings Snapshot",
        "description": "Q3 earnings summary",
        "published": "2025-11-05T10:15:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "SNAP",
        "title": "Snap Stock Surges on Earnings",
        "description": "Surging after strong Q3",
        "published": "2025-11-05T11:30:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "EOLS",
        "title": "Evolus, Inc. (EOLS) Reports Q3 Loss, Beats Revenue Estimates",
        "description": "Q3 results mixed",
        "published": "2025-11-05T12:30:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "MQ",
        "title": "Marqeta (MQ) Reports Q3 Loss, Beats Revenue Estimates",
        "description": "Q3 results mixed",
        "published": "2025-11-05T13:00:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "COOK",
        "title": "Traeger (COOK) Reports Q3 Loss, Beats Revenue Estimates",
        "description": "Q3 results mixed",
        "published": "2025-11-05T14:30:00Z",
        "expected": "BLOCK"
    },
    {
        "ticker": "COTY",
        "title": "Coty (COTY) Q1 Earnings and Revenues Lag Estimates",
        "description": "Q1 results disappointing",
        "published": "2025-11-05T15:00:00Z",
        "expected": "BLOCK"
    },
]

GOOD_ALERTS = [
    {
        "ticker": "ANIK",
        "title": "Anika Therapeutics Reports Filing of Final PMA Module for Hyalofast",
        "description": "Clinical trial milestone achieved",
        "published": "2025-11-05T10:00:00Z",
        "expected": "PASS"
    },
    {
        "ticker": "AMOD",
        "title": "Alpha Modus Files Patent-Infringement Lawsuit",
        "description": "Legal action against competitor",
        "published": "2025-11-05T11:00:00Z",
        "expected": "PASS"
    },
    {
        "ticker": "ATAI",
        "title": "8-K - Completion of Acquisition",
        "description": "SEC filing announcing acquisition completion",
        "published": "2025-11-05T12:00:00Z",
        "expected": "PASS",
        "is_sec": True,
        "filing_type": "8-K"
    },
    {
        "ticker": "RUBI",
        "title": "Rubico Announces Pricing of $7.5 Million Underwritten Public Offering",
        "description": "Public offering priced at $2.50/share",
        "published": "2025-11-05T13:00:00Z",
        "expected": "PASS"
    },
    {
        "ticker": "TVGN",
        "title": "Tevogen Reports Major Clinical Milestone",
        "description": "Phase 2 trial shows positive results",
        "published": "2025-11-05T14:00:00Z",
        "expected": "PASS"
    },
    {
        "ticker": "CCC",
        "title": "CCC Intelligent Solutions Announces Proposed Secondary Offering",
        "description": "Secondary offering announced",
        "published": "2025-11-05T15:00:00Z",
        "expected": "PASS"
    },
    {
        "ticker": "ASST",
        "title": "Strive Announces Pricing of Upsized Initial Public Offering",
        "description": "IPO priced at $12/share",
        "published": "2025-11-05T16:00:00Z",
        "expected": "PASS"
    },
]

BORDERLINE_ALERTS = [
    {
        "ticker": "SLDP",
        "title": "Solid Power Inc (SLDP) Q3 2025 Earnings Call Highlights",
        "description": "Earnings call highlights, 6 hours old, inline results",
        "published": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat() + "Z",
        "expected": "BORDERLINE"
    },
    {
        "ticker": "LFVN",
        "title": "Lifevantage Corp (LFVN) Q1 2026 Earnings Call Highlights",
        "description": "Earnings call highlights, 6 hours old, acquisition mentioned",
        "published": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat() + "Z",
        "expected": "BORDERLINE"
    },
]


# ============================================================================
# TEST 1: Retrospective Filter Validation
# ============================================================================

class TestRetrospectiveFilter:
    """Test Wave 1: Retrospective sentiment filter against 18 real examples"""

    def test_retrospective_detection_coverage(self):
        """Should block 81-89% of retrospective alerts (15-16 out of 18)"""
        if not RETROSPECTIVE_FILTER_EXISTS:
            pytest.skip("Wave 1 not implemented yet - is_retrospective_sentiment function missing")

        blocked_count = 0
        results = []

        for alert in RETROSPECTIVE_ALERTS:
            # Test the is_retrospective_sentiment function
            is_retro = is_retrospective_sentiment(
                alert["title"],
                alert.get("description", "")
            )

            results.append({
                "ticker": alert["ticker"],
                "title": alert["title"],
                "blocked": is_retro,
                "expected": alert["expected"]
            })

            if is_retro:
                blocked_count += 1

        # Report results
        print("\n" + "="*80)
        print("RETROSPECTIVE FILTER TEST RESULTS")
        print("="*80)
        for r in results:
            status = "[BLOCKED]" if r["blocked"] else "[PASSED] "
            print(f"{status} [{r['ticker']}] {r['title'][:60]}")

        print(f"\nBlocked: {blocked_count}/18 ({blocked_count/18*100:.1f}%)")
        print(f"Target: 15-16/18 (81-89%)")

        # Assert: Should block at least 15 out of 18
        assert blocked_count >= 15, f"Expected ≥15 blocked, got {blocked_count}"
        assert blocked_count <= 18, f"Should not block all, got {blocked_count}"

    def test_individual_retrospective_patterns(self):
        """Test specific retrospective patterns"""
        if not RETROSPECTIVE_FILTER_EXISTS:
            pytest.skip("Wave 1 not implemented yet - is_retrospective_sentiment function missing")

        test_cases = [
            ("Why Stock Is Trading Lower Today", True),
            ("Stock Is Falling Today", True),
            ("Shares Are Getting Obliterated", True),
            ("Soars 7.85 as Restructuring", True),
            ("Falls 14.6% as Earnings Disappoint", True),
            ("May Report Negative Earnings", True),
            ("Will Report Negative Q3 Earnings?", True),
            ("Analysts Estimate Decline", True),
            ("Misses Q3 Sales Expectations, Stock Drops", True),
            ("Q3 Earnings Snapshot", True),
            ("Stock Surges on Earnings", True),
            ("Reports Q3 Loss, Beats Revenue", True),
            ("Earnings and Revenues Lag Estimates", True),
        ]

        for text, should_block in test_cases:
            is_retro = is_retrospective_sentiment(text, "")
            assert is_retro == should_block, f"Failed for: {text}"


# ============================================================================
# TEST 2: Good Alert Preservation
# ============================================================================

class TestGoodAlertPreservation:
    """Test that good alerts are NOT blocked by retrospective filter"""

    def test_good_alerts_pass_through(self):
        """Should allow 100% of good alerts (7 out of 7)"""
        if not RETROSPECTIVE_FILTER_EXISTS:
            pytest.skip("Wave 1 not implemented yet - is_retrospective_sentiment function missing")

        passed_count = 0
        results = []

        for alert in GOOD_ALERTS:
            # Test the is_retrospective_sentiment function
            is_retro = is_retrospective_sentiment(
                alert["title"],
                alert.get("description", "")
            )

            results.append({
                "ticker": alert["ticker"],
                "title": alert["title"],
                "passed": not is_retro,
                "expected": alert["expected"]
            })

            if not is_retro:
                passed_count += 1

        # Report results
        print("\n" + "="*80)
        print("GOOD ALERT PRESERVATION TEST RESULTS")
        print("="*80)
        for r in results:
            status = "[PASSED] " if r["passed"] else "[BLOCKED]"
            print(f"{status} [{r['ticker']}] {r['title'][:60]}")

        print(f"\nPassed: {passed_count}/7 ({passed_count/7*100:.1f}%)")
        print(f"Target: 7/7 (100%)")

        # Assert: Should pass ALL good alerts
        assert passed_count == 7, f"Expected 7 passed, got {passed_count}"

    def test_false_positive_rate(self):
        """Calculate false positive rate (good alerts blocked)"""
        if not RETROSPECTIVE_FILTER_EXISTS:
            pytest.skip("Wave 1 not implemented yet - is_retrospective_sentiment function missing")

        false_positives = 0

        for alert in GOOD_ALERTS:
            is_retro = is_retrospective_sentiment(
                alert["title"],
                alert.get("description", "")
            )
            if is_retro:
                false_positives += 1

        false_positive_rate = (false_positives / len(GOOD_ALERTS)) * 100
        print(f"\nFalse Positive Rate: {false_positive_rate:.1f}%")

        # Should be 0%
        assert false_positive_rate == 0.0, f"Too many false positives: {false_positive_rate}%"


# ============================================================================
# TEST 3: Environment Configuration
# ============================================================================

class TestEnvironmentConfiguration:
    """Test Wave 2: .env configuration changes"""

    def test_env_settings_changed(self):
        """Verify all 9 .env settings are properly configured"""

        # Load config
        config = get_settings()

        # Expected changes from .env.example
        expected_changes = {
            "MIN_RVOL": None,  # Should be disabled
            "PRICE_CHANGE_THRESHOLD": 0.0,  # Changed from 0.02
            "VOLUME_MULTIPLE": 0.0,  # Changed from 1.5
            "SCAN_INTERVAL": 300,  # 5 minutes (changed from 900)
            "CHART_CYCLE": 300,  # 5 minutes (changed from 1800)
            "FEED_CYCLE": 180,  # 3 minutes (changed from 600)
            "SEC_FEED_CYCLE": 300,  # 5 minutes (changed from 900)
            "ARTICLE_FRESHNESS_HOURS": 12,  # Changed from 3
            "MAX_TICKERS_PER_ALERT": 3,  # Changed from 5
        }

        results = []
        all_correct = True

        print("\n" + "="*80)
        print("ENVIRONMENT CONFIGURATION TEST RESULTS")
        print("="*80)

        for key, expected_value in expected_changes.items():
            actual_value = getattr(config, key, None)

            # Special handling for None (disabled)
            if expected_value is None:
                is_correct = actual_value is None or actual_value == ""
            else:
                is_correct = actual_value == expected_value

            status = "[OK]" if is_correct else "[X] "
            results.append({
                "setting": key,
                "expected": expected_value,
                "actual": actual_value,
                "correct": is_correct
            })

            print(f"{status} {key}: {actual_value} (expected: {expected_value})")

            if not is_correct:
                all_correct = False

        correct_count = sum(1 for r in results if r["correct"])
        print(f"\nCorrect: {correct_count}/9")

        # Should have all 9 correct
        assert all_correct, "Not all .env settings are correct"

    def test_rvol_multiplier_disabled(self):
        """Verify RVOL multiplier is disabled"""
        config = get_settings()
        min_rvol = getattr(config, "MIN_RVOL", None)

        # Should be None, empty string, or 0
        assert min_rvol is None or min_rvol == "" or min_rvol == 0, \
            f"MIN_RVOL should be disabled, got: {min_rvol}"

    def test_cycle_times_reduced(self):
        """Verify cycle times are reduced"""
        config = get_settings()

        # All should be ≤ 5 minutes (300 seconds)
        assert getattr(config, "SCAN_INTERVAL", 999) <= 300, "SCAN_INTERVAL too high"
        assert getattr(config, "CHART_CYCLE", 999) <= 300, "CHART_CYCLE too high"
        assert getattr(config, "FEED_CYCLE", 999) <= 300, "FEED_CYCLE too high"
        assert getattr(config, "SEC_FEED_CYCLE", 999) <= 300, "SEC_FEED_CYCLE too high"

    def test_freshness_window_expanded(self):
        """Verify freshness window expanded to 12 hours"""
        config = get_settings()
        freshness = getattr(config, "ARTICLE_FRESHNESS_HOURS", 0)

        assert freshness == 12, f"Expected 12 hours, got {freshness}"


# ============================================================================
# TEST 4: Integration Test
# ============================================================================

class TestIntegration:
    """Test full alert pipeline with test data"""

    @pytest.mark.integration
    def test_end_to_end_pipeline(self):
        """Run full alert pipeline with test data"""
        if not RETROSPECTIVE_FILTER_EXISTS:
            pytest.skip("Wave 1 not implemented yet - is_retrospective_sentiment function missing")

        # Mock the necessary components
        from catalyst_bot.classify import classify_alert

        passed_alerts = []
        blocked_alerts = []
        errors = []

        print("\n" + "="*80)
        print("INTEGRATION TEST: FULL PIPELINE")
        print("="*80)

        # Process all alerts through pipeline
        all_alerts = RETROSPECTIVE_ALERTS + GOOD_ALERTS + BORDERLINE_ALERTS

        for alert in all_alerts:
            try:
                # Mock alert object
                mock_alert = Mock()
                mock_alert.ticker = alert["ticker"]
                mock_alert.title = alert["title"]
                mock_alert.description = alert.get("description", "")
                mock_alert.published = alert["published"]

                # Check retrospective filter
                is_retro = is_retrospective_sentiment(
                    alert["title"],
                    alert.get("description", "")
                )

                if is_retro:
                    blocked_alerts.append(alert)
                    print(f"[BLOCKED] [{alert['ticker']}] {alert['title'][:50]}")
                else:
                    passed_alerts.append(alert)
                    print(f"[PASSED]  [{alert['ticker']}] {alert['title'][:50]}")

            except Exception as e:
                errors.append({
                    "alert": alert,
                    "error": str(e)
                })
                print(f"[ERROR]   [{alert['ticker']}] {str(e)}")

        print(f"\nResults:")
        print(f"  Passed: {len(passed_alerts)}")
        print(f"  Blocked: {len(blocked_alerts)}")
        print(f"  Errors: {len(errors)}")

        # Assert: Should have no errors
        assert len(errors) == 0, f"Pipeline errors: {errors}"

        # Assert: Should block most retrospective (15-16 out of 18)
        retro_blocked = sum(1 for a in blocked_alerts if a in RETROSPECTIVE_ALERTS)
        assert retro_blocked >= 15, f"Expected ≥15 retrospective blocked, got {retro_blocked}"

        # Assert: Should pass all good alerts (7 out of 7)
        good_passed = sum(1 for a in passed_alerts if a in GOOD_ALERTS)
        assert good_passed == 7, f"Expected 7 good alerts passed, got {good_passed}"

    @pytest.mark.integration
    def test_scoring_without_rvol(self):
        """Verify scoring works without RVOL multiplier"""

        from catalyst_bot.models import NewsItem

        # Mock alert with no RVOL data
        test_cases = [
            {
                "title": "Company Announces Major Clinical Trial Success",
                "description": "Phase 3 trial met primary endpoint",
                "expected_positive": True
            },
            {
                "title": "Stock Falls on Earnings Miss",
                "description": "Q3 results disappoint",
                "expected_positive": False  # Should be negative
            },
        ]

        print("\n" + "="*80)
        print("SCORING WITHOUT RVOL TEST")
        print("="*80)

        for tc in test_cases:
            # Create mock news item
            news_item = NewsItem(
                title=tc["title"],
                description=tc["description"],
                link="https://example.com/test",
                published="2025-11-05T10:00:00Z",
                source="Test Source",
                tickers=["TEST"]
            )

            # Classify without RVOL
            result = classify(news_item)

            if result:
                score = result.sentiment
                passed = (score > 0) == tc["expected_positive"]
                status = "[OK]" if passed else "[X] "
                print(f"{status} Score: {score:.2f} for '{tc['title'][:40]}'")

                assert passed, f"Scoring failed for: {tc['title']}"
            else:
                print(f"[WARN] No result for '{tc['title'][:40]}'")
                # Don't fail if classification returns None


# ============================================================================
# TEST 5: SEC Filing Format
# ============================================================================

class TestSecFilingFormat:
    """Test Wave 3: SEC filing format improvements"""

    def test_metadata_removed(self):
        """Verify SEC filing metadata is removed"""
        if not SEC_ADAPTER_EXISTS:
            pytest.skip("Wave 3 not implemented yet - SecFilingAdapter missing")

        # Sample SEC filing data with metadata
        raw_filing = {
            "ticker": "ATAI",
            "filing_type": "8-K",
            "title": "8-K - Completion of Acquisition",
            "description": "Item 1.01: Entry into Material Agreement\nItem 2.01: Completion of Acquisition\n\nATAI Life Sciences has completed the acquisition of XYZ Company for $100M.",
            "metadata": {
                "cik": "0001234567",
                "accession": "0001234567-25-000123",
                "filed_at": "2025-11-05T16:00:00Z"
            }
        }

        adapter = SecFilingAdapter()
        formatted = adapter.format_filing(raw_filing)

        # Should not contain metadata fields
        assert "cik" not in formatted.lower(), "CIK should be removed"
        assert "accession" not in formatted.lower(), "Accession should be removed"
        assert "filed_at" not in formatted, "Filed_at should be removed"

        print("\n" + "="*80)
        print("SEC FILING FORMAT TEST")
        print("="*80)
        print("[OK] Metadata removed")

    def test_bullet_formatting(self):
        """Verify bullet formatting is applied"""
        if not SEC_ADAPTER_EXISTS:
            pytest.skip("Wave 3 not implemented yet - SecFilingAdapter missing")

        # Sample SEC filing with items
        raw_filing = {
            "ticker": "ATAI",
            "filing_type": "8-K",
            "title": "8-K - Completion of Acquisition",
            "description": "Item 1.01: Entry into Material Agreement. Item 2.01: Completion of Acquisition. Item 9.01: Financial Statements.",
        }

        adapter = SecFilingAdapter()
        formatted = adapter.format_filing(raw_filing)

        # Should contain bullet points (using * or - instead of emoji bullet)
        assert "*" in formatted or "-" in formatted or "\n  " in formatted, \
            "Should have bullet formatting"

        print("[OK] Bullet formatting applied")

    def test_no_parsing_errors(self):
        """Verify no parsing errors with ATAI 8-K example"""
        if not SEC_ADAPTER_EXISTS:
            pytest.skip("Wave 3 not implemented yet - SecFilingAdapter missing")

        atai_alert = next(a for a in GOOD_ALERTS if a["ticker"] == "ATAI")

        try:
            adapter = SecFilingAdapter()
            formatted = adapter.format_filing(atai_alert)
            print("[OK] No parsing errors")
            assert True
        except Exception as e:
            pytest.fail(f"Parsing error: {e}")


# ============================================================================
# TEST 6: Metrics Reporting
# ============================================================================

class TestMetricsReporting:
    """Generate comprehensive metrics report"""

    def test_generate_metrics_report(self):
        """Generate full metrics report"""

        print("\n" + "="*80)
        print("COMPREHENSIVE METRICS REPORT - 3 PATCH WAVES")
        print("="*80)

        # Wave 1: Retrospective Filter
        if RETROSPECTIVE_FILTER_EXISTS:
            # Calculate metrics
            retro_blocked = sum(
                1 for a in RETROSPECTIVE_ALERTS
                if is_retrospective_sentiment(a["title"], a.get("description", ""))
            )

            good_passed = sum(
                1 for a in GOOD_ALERTS
                if not is_retrospective_sentiment(a["title"], a.get("description", ""))
            )

            total_retrospective = len(RETROSPECTIVE_ALERTS)
            total_good = len(GOOD_ALERTS)

            # False positive rate (good alerts incorrectly blocked)
            false_positives = total_good - good_passed
            false_positive_rate = (false_positives / total_good * 100) if total_good > 0 else 0

            # False negative rate (retrospective alerts incorrectly passed)
            false_negatives = total_retrospective - retro_blocked
            false_negative_rate = (false_negatives / total_retrospective * 100) if total_retrospective > 0 else 0

            # Precision and Recall
            true_positives = retro_blocked
            precision = (true_positives / (true_positives + false_positives)) * 100 if (true_positives + false_positives) > 0 else 0
            recall = (true_positives / total_retrospective) * 100

            # F1 Score
            f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0

            print(f"\n[WAVE 1] RETROSPECTIVE FILTER PERFORMANCE")
            print(f"   Blocked: {retro_blocked}/{total_retrospective} ({retro_blocked/total_retrospective*100:.1f}%)")
            print(f"   Target:  15-16/18 (81-89%)")
            print(f"   Status:  {'[PASS]' if retro_blocked >= 15 else '[FAIL]'}")

            print(f"\n   Good Alert Preservation:")
            print(f"   Passed: {good_passed}/{total_good} ({good_passed/total_good*100:.1f}%)")
            print(f"   Target: 7/7 (100%)")
            print(f"   Status: {'[PASS]' if good_passed == 7 else '[FAIL]'}")

            print(f"\n   Error Rates:")
            print(f"   False Positive Rate: {false_positive_rate:.1f}% (good alerts blocked)")
            print(f"   False Negative Rate: {false_negative_rate:.1f}% (retrospective passed)")

            print(f"\n   Classification Metrics:")
            print(f"   Precision: {precision:.1f}%")
            print(f"   Recall:    {recall:.1f}%")
            print(f"   F1 Score:  {f1_score:.1f}")

            wave1_pass = retro_blocked >= 15 and good_passed == 7
        else:
            print(f"\n[WAVE 1] RETROSPECTIVE FILTER")
            print(f"   Status: [NOT IMPLEMENTED]")
            print(f"   Missing: is_retrospective_sentiment() function in classify.py")
            wave1_pass = False

        # Wave 2: Config Changes
        print(f"\n[WAVE 2] CONFIGURATION CHANGES")
        print(f"   See Test 3 (test_env_settings_changed) for details")
        print(f"   Status: [PENDING] RUN test_env_settings_changed")

        # Wave 3: SEC Format
        print(f"\n[WAVE 3] SEC FILING FORMAT")
        if SEC_ADAPTER_EXISTS:
            print(f"   Status: [IMPLEMENTED]")
            print(f"   Module: sec_filing_adapter.py exists")
        else:
            print(f"   Status: [NOT IMPLEMENTED]")
            print(f"   Missing: SecFilingAdapter class")

        # Overall assessment
        print(f"\n[OVERALL ASSESSMENT]")
        print(f"   Wave 1 (Retrospective Filter): {'[PASS]' if wave1_pass else '[FAIL/NOT IMPLEMENTED]'}")
        print(f"   Wave 2 (Config Changes):       [MANUAL CHECK REQUIRED]")
        print(f"   Wave 3 (SEC Format):           {'[EXISTS]' if SEC_ADAPTER_EXISTS else '[MISSING]'}")

        print("="*80 + "\n")


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
