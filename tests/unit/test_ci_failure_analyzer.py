"""Unit tests for CI Failure Analyzer."""

import unittest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone

from src.analyzers.ci_failure_analyzer import (
    CIFailureAnalyzer,
    CIFailureCategory,
    CIFailureDetails,
    CIFixSuggestion,
    CIFailureAnalysis,
)
from src.cycles.pr_cycle import CICheckStatus, CIStatus
from src.integrations.multi_agent_coder_client import MultiAgentCoderClient
from src.core.logger import AuditLogger


class TestCIFailureAnalyzer(unittest.TestCase):
    """Test cases for CIFailureAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.multi_agent = Mock(spec=MultiAgentCoderClient)
        self.logger = Mock(spec=AuditLogger)

        self.analyzer = CIFailureAnalyzer(
            multi_agent_client=self.multi_agent,
            logger=self.logger,
        )

    def test_initialization(self):
        """Test analyzer initialization."""
        self.assertEqual(self.analyzer.total_analyses, 0)
        self.assertEqual(self.analyzer.fixable_failures, 0)
        self.assertEqual(self.analyzer.escalated_failures, 0)

    def test_categorize_failure_lint(self):
        """Test categorization of lint failures."""
        category = self.analyzer._categorize_failure("Lint / black", "")
        self.assertEqual(category, CIFailureCategory.LINT_ERROR)

        category = self.analyzer._categorize_failure("Code Format", "")
        self.assertEqual(category, CIFailureCategory.LINT_ERROR)

    def test_categorize_failure_type_check(self):
        """Test categorization of type check failures."""
        category = self.analyzer._categorize_failure("Type Check / mypy", "")
        self.assertEqual(category, CIFailureCategory.TYPE_ERROR)

        category = self.analyzer._categorize_failure("pyright", "")
        self.assertEqual(category, CIFailureCategory.TYPE_ERROR)

    def test_categorize_failure_build(self):
        """Test categorization of build failures."""
        category = self.analyzer._categorize_failure("Build", "SyntaxError: invalid syntax")
        self.assertEqual(category, CIFailureCategory.BUILD_ERROR)

    def test_categorize_failure_test(self):
        """Test categorization of test failures."""
        category = self.analyzer._categorize_failure("Test / pytest", "")
        self.assertEqual(category, CIFailureCategory.TEST_FAILURE)

    def test_categorize_failure_import_from_log(self):
        """Test categorization of import errors from log content."""
        log = "ImportError: cannot import name 'Foo' from 'bar'"
        category = self.analyzer._categorize_failure("Build", log)
        self.assertEqual(category, CIFailureCategory.IMPORT_ERROR)

    def test_categorize_failure_timeout(self):
        """Test categorization of timeout failures."""
        log = "Error: The operation timed out after 300 seconds"
        category = self.analyzer._categorize_failure("Test", log)
        self.assertEqual(category, CIFailureCategory.TIMEOUT)

    def test_categorize_failure_permission(self):
        """Test categorization of permission failures."""
        log = "Error: Permission denied to access resource"
        category = self.analyzer._categorize_failure("Deploy", log)
        self.assertEqual(category, CIFailureCategory.PERMISSION)

    def test_extract_error_messages(self):
        """Test extraction of error messages from logs."""
        log = """
Running tests...
Error: Module not found
ERROR: Test failed at line 42
FAIL: AssertionError in test_foo
✗ Type mismatch in function bar
        """
        errors = self.analyzer._extract_error_messages(log)

        self.assertGreater(len(errors), 0)
        self.assertIn("Module not found", errors)
        self.assertIn("Test failed at line 42", errors)

    def test_extract_error_messages_empty_log(self):
        """Test error extraction with empty log."""
        errors = self.analyzer._extract_error_messages("")
        self.assertEqual(errors, [])

    def test_is_auto_fixable_lint(self):
        """Test auto-fixable determination for lint errors."""
        is_fixable = self.analyzer._is_auto_fixable(
            CIFailureCategory.LINT_ERROR,
            ["E501 line too long"]
        )
        self.assertTrue(is_fixable)

    def test_is_auto_fixable_build(self):
        """Test auto-fixable determination for build errors."""
        is_fixable = self.analyzer._is_auto_fixable(
            CIFailureCategory.BUILD_ERROR,
            ["SyntaxError: invalid syntax"]
        )
        self.assertTrue(is_fixable)

    def test_is_auto_fixable_infrastructure(self):
        """Test auto-fixable determination for infrastructure failures."""
        is_fixable = self.analyzer._is_auto_fixable(
            CIFailureCategory.INFRASTRUCTURE,
            []
        )
        self.assertFalse(is_fixable)

    def test_is_auto_fixable_permission(self):
        """Test auto-fixable determination for permission errors."""
        is_fixable = self.analyzer._is_auto_fixable(
            CIFailureCategory.PERMISSION,
            []
        )
        self.assertFalse(is_fixable)

    def test_get_log_excerpt_with_errors(self):
        """Test log excerpt extraction with error messages."""
        log = "Some log content " * 1000
        errors = ["Error 1", "Error 2", "Error 3"]

        excerpt = self.analyzer._get_log_excerpt(log, errors)

        self.assertIn("Error 1", excerpt)
        self.assertLessEqual(len(excerpt), 1000)

    def test_get_log_excerpt_without_errors(self):
        """Test log excerpt extraction without error messages."""
        log = "Some log content " * 100
        errors = []

        excerpt = self.analyzer._get_log_excerpt(log, errors)

        self.assertLessEqual(len(excerpt), 1000)
        self.assertIn("Some log content", excerpt)

    def test_estimate_confidence_with_errors(self):
        """Test confidence estimation with error messages."""
        confidence = self.analyzer._estimate_confidence(
            CIFailureCategory.LINT_ERROR,
            ["Error 1", "Error 2"],
            "Some log content " * 50
        )

        self.assertGreater(confidence, 0.5)
        self.assertLessEqual(confidence, 1.0)

    def test_estimate_confidence_unknown_category(self):
        """Test confidence estimation for unknown category."""
        confidence = self.analyzer._estimate_confidence(
            CIFailureCategory.UNKNOWN,
            [],
            ""
        )

        self.assertLess(confidence, 0.5)

    def test_analyze_single_check_lint(self):
        """Test analysis of a single lint check failure."""
        check = CICheckStatus(
            name="Lint / black",
            status="completed",
            conclusion="failure",
        )
        log = "Error: Line 42: E501 line too long (88 > 79 characters)"

        details = self.analyzer._analyze_single_check(check, log)

        self.assertEqual(details.check_name, "Lint / black")
        self.assertEqual(details.failure_category, CIFailureCategory.LINT_ERROR)
        self.assertTrue(details.is_auto_fixable)
        self.assertGreater(len(details.error_messages), 0)

    def test_analyze_single_check_type_error(self):
        """Test analysis of type check failure."""
        check = CICheckStatus(
            name="Type Check / mypy",
            status="completed",
            conclusion="failure",
        )
        log = "error: Incompatible types in assignment"

        details = self.analyzer._analyze_single_check(check, log)

        self.assertEqual(details.failure_category, CIFailureCategory.TYPE_ERROR)
        self.assertTrue(details.is_auto_fixable)

    def test_generate_fix_suggestions_lint(self):
        """Test fix suggestion generation for lint errors."""
        failure = CIFailureDetails(
            check_name="Lint / black",
            failure_category=CIFailureCategory.LINT_ERROR,
            error_messages=["E501 line too long"],
            log_excerpt="...",
            is_auto_fixable=True,
            confidence=0.9,
        )

        suggestions = self.analyzer._generate_fix_suggestions(failure)

        self.assertGreater(len(suggestions), 0)
        self.assertEqual(suggestions[0].fix_category, "lint")
        self.assertGreater(suggestions[0].success_probability, 0.5)

    def test_generate_fix_suggestions_import(self):
        """Test fix suggestion generation for import errors."""
        failure = CIFailureDetails(
            check_name="Build",
            failure_category=CIFailureCategory.IMPORT_ERROR,
            error_messages=["ImportError: cannot import Foo"],
            log_excerpt="...",
            is_auto_fixable=True,
            confidence=0.7,
        )

        suggestions = self.analyzer._generate_fix_suggestions(failure)

        self.assertGreater(len(suggestions), 0)
        self.assertEqual(suggestions[0].fix_category, "import")

    def test_analyze_ci_failures_no_failures(self):
        """Test analysis when there are no failures."""
        ci_status = CIStatus(
            overall_status="passed",
            checks=[],
            total_checks=0,
            passing_checks=0,
        )

        analysis = self.analyzer.analyze_ci_failures(123, ci_status)

        self.assertEqual(analysis.pr_number, 123)
        self.assertEqual(len(analysis.failures), 0)
        self.assertTrue(analysis.overall_fixable)
        self.assertFalse(analysis.escalation_needed)

    def test_analyze_ci_failures_single_fixable(self):
        """Test analysis with single fixable failure."""
        check = CICheckStatus(
            name="Lint / black",
            status="completed",
            conclusion="failure",
        )
        ci_status = CIStatus(
            overall_status="failed",
            checks=[check],
            total_checks=1,
            failing_checks=1,
        )
        check_logs = {
            "Lint / black": "Error: E501 line too long"
        }

        analysis = self.analyzer.analyze_ci_failures(123, ci_status, check_logs)

        self.assertEqual(len(analysis.failures), 1)
        self.assertTrue(analysis.overall_fixable)
        self.assertFalse(analysis.escalation_needed)
        self.assertGreater(len(analysis.fix_suggestions), 0)
        self.assertEqual(self.analyzer.fixable_failures, 1)

    def test_analyze_ci_failures_non_fixable(self):
        """Test analysis with non-fixable failure."""
        check = CICheckStatus(
            name="Deploy",
            status="completed",
            conclusion="failure",
        )
        ci_status = CIStatus(
            overall_status="failed",
            checks=[check],
            total_checks=1,
            failing_checks=1,
        )
        check_logs = {
            "Deploy": "Error: Permission denied"
        }

        analysis = self.analyzer.analyze_ci_failures(123, ci_status, check_logs)

        self.assertEqual(len(analysis.failures), 1)
        self.assertFalse(analysis.overall_fixable)
        self.assertTrue(analysis.escalation_needed)
        self.assertIsNotNone(analysis.escalation_reason)
        self.assertEqual(self.analyzer.escalated_failures, 1)

    def test_analyze_ci_failures_mixed(self):
        """Test analysis with mix of fixable and non-fixable failures."""
        check1 = CICheckStatus(name="Lint", status="completed", conclusion="failure")
        check2 = CICheckStatus(name="Deploy", status="completed", conclusion="failure")

        ci_status = CIStatus(
            overall_status="failed",
            checks=[check1, check2],
            total_checks=2,
            failing_checks=2,
        )
        check_logs = {
            "Lint": "Error: E501 line too long",
            "Deploy": "Error: Permission denied"
        }

        analysis = self.analyzer.analyze_ci_failures(123, ci_status, check_logs)

        self.assertEqual(len(analysis.failures), 2)
        self.assertTrue(analysis.overall_fixable)  # At least one is fixable
        self.assertTrue(analysis.escalation_needed)  # But one needs escalation

    def test_failure_details_to_dict(self):
        """Test CIFailureDetails to_dict conversion."""
        details = CIFailureDetails(
            check_name="Test Check",
            failure_category=CIFailureCategory.LINT_ERROR,
            error_messages=["Error 1", "Error 2"],
            log_excerpt="Log excerpt...",
            is_auto_fixable=True,
            confidence=0.8,
        )

        result = details.to_dict()

        self.assertEqual(result["check_name"], "Test Check")
        self.assertEqual(result["failure_category"], "lint_error")
        self.assertTrue(result["is_auto_fixable"])
        self.assertEqual(result["confidence"], 0.8)

    def test_fix_suggestion_to_dict(self):
        """Test CIFixSuggestion to_dict conversion."""
        suggestion = CIFixSuggestion(
            description="Fix lint errors",
            file_paths=["src/file.py"],
            proposed_changes="Run black",
            success_probability=0.9,
            rationale="Lint errors are auto-fixable",
            fix_category="lint",
        )

        result = suggestion.to_dict()

        self.assertEqual(result["description"], "Fix lint errors")
        self.assertEqual(result["fix_category"], "lint")
        self.assertEqual(result["success_probability"], 0.9)

    def test_failure_analysis_to_dict(self):
        """Test CIFailureAnalysis to_dict conversion."""
        analysis = CIFailureAnalysis(
            pr_number=123,
            ci_status=CIStatus(overall_status="failed"),
            failures=[],
            fix_suggestions=[],
            overall_fixable=True,
            escalation_needed=False,
            analysis_confidence=0.85,
        )

        result = analysis.to_dict()

        self.assertEqual(result["pr_number"], 123)
        self.assertTrue(result["overall_fixable"])
        self.assertFalse(result["escalation_needed"])
        self.assertEqual(result["analysis_confidence"], 0.85)

    def test_get_statistics(self):
        """Test statistics retrieval."""
        self.analyzer.total_analyses = 10
        self.analyzer.fixable_failures = 7
        self.analyzer.escalated_failures = 3

        stats = self.analyzer.get_statistics()

        self.assertEqual(stats["total_analyses"], 10)
        self.assertEqual(stats["fixable_failures"], 7)
        self.assertEqual(stats["escalated_failures"], 3)
        self.assertEqual(stats["fixable_rate"], 70.0)
        self.assertEqual(stats["escalation_rate"], 30.0)

    def test_get_statistics_no_analyses(self):
        """Test statistics with no analyses."""
        stats = self.analyzer.get_statistics()

        self.assertEqual(stats["total_analyses"], 0)
        self.assertEqual(stats["fixable_rate"], 0.0)
        self.assertEqual(stats["escalation_rate"], 0.0)

    def test_reset_statistics(self):
        """Test statistics reset."""
        self.analyzer.total_analyses = 10
        self.analyzer.fixable_failures = 7
        self.analyzer.escalated_failures = 3

        self.analyzer.reset_statistics()

        self.assertEqual(self.analyzer.total_analyses, 0)
        self.assertEqual(self.analyzer.fixable_failures, 0)
        self.assertEqual(self.analyzer.escalated_failures, 0)


if __name__ == '__main__':
    unittest.main()
