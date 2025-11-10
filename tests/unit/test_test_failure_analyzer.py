"""Unit tests for TestFailureAnalyzer."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from src.analyzers.test_failure_analyzer import (
    FailureAnalysis,
    FailureCategory,
    FixSuggestion,
    RootCause,
    TestFailureAnalyzer,
)
from src.core.logger import AuditLogger
from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentResponse,
    MultiAgentStrategy,
)
from src.integrations.test_runner import TestFailure, TestFramework, TestResult


class TestTestFailureAnalyzer(unittest.TestCase):
    """Test cases for TestFailureAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)
        self.repo_path = Path("/fake/repo")

        self.analyzer = TestFailureAnalyzer(
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
            repo_path=self.repo_path,
            min_confidence_threshold=0.6,
        )

    def test_initialization(self):
        """Test analyzer initialization."""
        self.assertEqual(self.analyzer.repo_path, self.repo_path)
        self.assertEqual(self.analyzer.multi_agent_client, self.multi_agent_client)
        self.assertEqual(self.analyzer.min_confidence_threshold, 0.6)
        self.assertEqual(self.analyzer.total_analyses, 0)

    def test_failure_category_enum(self):
        """Test FailureCategory enum values."""
        self.assertEqual(FailureCategory.ASSERTION_ERROR.value, "assertion_error")
        self.assertEqual(FailureCategory.IMPORT_ERROR.value, "import_error")
        self.assertEqual(FailureCategory.TYPE_ERROR.value, "type_error")

    def test_root_cause_to_dict(self):
        """Test RootCause to_dict conversion."""
        root_cause = RootCause(
            description="Missing import statement",
            category=FailureCategory.IMPORT_ERROR,
            confidence=0.9,
            affected_files=["src/main.py"],
            related_failures=["test_foo"],
        )

        root_dict = root_cause.to_dict()

        self.assertEqual(root_dict["description"], "Missing import statement")
        self.assertEqual(root_dict["category"], "import_error")
        self.assertEqual(root_dict["confidence"], 0.9)
        self.assertEqual(root_dict["affected_files"], ["src/main.py"])

    def test_fix_suggestion_to_dict(self):
        """Test FixSuggestion to_dict conversion."""
        fix = FixSuggestion(
            description="Add import statement",
            file_path="src/main.py",
            proposed_changes="import foo",
            success_probability=0.85,
            rationale="Missing import is clear from error",
        )

        fix_dict = fix.to_dict()

        self.assertEqual(fix_dict["description"], "Add import statement")
        self.assertEqual(fix_dict["file_path"], "src/main.py")
        self.assertEqual(fix_dict["success_probability"], 0.85)

    def test_failure_analysis_to_dict(self):
        """Test FailureAnalysis to_dict conversion."""
        failure = TestFailure(
            test_name="test_example",
            test_file="test_foo.py",
            error_message="ImportError: No module named 'foo'",
        )

        root_cause = RootCause(
            description="Missing import",
            category=FailureCategory.IMPORT_ERROR,
            confidence=0.9,
        )

        fix = FixSuggestion(
            description="Add import",
            file_path="src/main.py",
            proposed_changes="import foo",
            success_probability=0.85,
            rationale="Clear fix",
        )

        analysis = FailureAnalysis(
            test_failure=failure,
            root_causes=[root_cause],
            fix_suggestions=[fix],
            is_related_to_changes=True,
            analysis_confidence=0.88,
        )

        analysis_dict = analysis.to_dict()

        self.assertEqual(analysis_dict["is_related_to_changes"], True)
        self.assertEqual(analysis_dict["analysis_confidence"], 0.88)
        self.assertEqual(len(analysis_dict["root_causes"]), 1)
        self.assertEqual(len(analysis_dict["fix_suggestions"]), 1)

    def test_analyze_test_failures_empty(self):
        """Test analyzing test result with no failures."""
        test_result = TestResult(
            framework=TestFramework.PYTEST,
            total_tests=5,
            passed=5,
            failed=0,
            skipped=0,
            execution_time=1.0,
            failures=[],
        )

        analyses = self.analyzer.analyze_test_failures(test_result)

        self.assertEqual(len(analyses), 0)
        self.logger.debug.assert_called_with("No test failures to analyze")

    def test_run_parallel_analysis(self):
        """Test parallel analysis with multi-agent-coder."""
        failure = TestFailure(
            test_name="test_example",
            test_file="test_foo.py",
            error_message="AssertionError: 1 != 2",
            stack_trace="Traceback...",
        )

        mock_response = MultiAgentResponse(
            providers=["anthropic", "openai"],
            responses={
                "anthropic": "**Root Cause:** Logic error\n**Category:** assertion_error\n**Confidence:** 0.9",
                "openai": "**Root Cause:** Incorrect value\n**Category:** assertion_error\n**Confidence:** 0.85",
            },
            strategy="all",
            total_tokens=200,
            total_cost=0.003,
            success=True,
        )

        self.multi_agent_client.query.return_value = mock_response

        result = self.analyzer._run_parallel_analysis(
            failure=failure,
            framework=TestFramework.PYTEST,
            changed_files=["src/main.py"],
            codebase_context="Python project",
        )

        self.assertTrue(result.success)
        self.assertEqual(len(result.responses), 2)
        self.multi_agent_client.query.assert_called_once()

        # Check prompt contains key information
        call_args = self.multi_agent_client.query.call_args
        prompt = call_args[1]["prompt"]
        self.assertIn("test_example", prompt)
        self.assertIn("AssertionError: 1 != 2", prompt)
        self.assertIn("src/main.py", prompt)

    def test_extract_root_causes(self):
        """Test extraction of root causes from multi-agent response."""
        failure = TestFailure(
            test_name="test_foo",
            test_file="test_foo.py",
            error_message="Error",
        )

        multi_agent_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": """**Root Cause:** Missing import statement for module foo
**Category:** import_error
**Confidence:** 0.95""",
                "deepseek": """**Root Cause:** Module not found in path
**Category:** import_error
**Confidence:** 0.80""",
            },
            strategy="all",
            total_tokens=150,
            total_cost=0.002,
            success=True,
        )

        root_causes = self.analyzer._extract_root_causes(
            failure=failure,
            multi_agent_response=multi_agent_response,
        )

        self.assertEqual(len(root_causes), 2)
        self.assertEqual(root_causes[0].category, FailureCategory.IMPORT_ERROR)
        self.assertEqual(root_causes[0].confidence, 0.95)
        self.assertIn("Missing import", root_causes[0].description)

    def test_extract_root_causes_unknown_category(self):
        """Test extraction with unknown category falls back to UNKNOWN."""
        failure = TestFailure(
            test_name="test_foo",
            test_file="test_foo.py",
            error_message="Error",
        )

        multi_agent_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """**Root Cause:** Some weird error
**Category:** weird_error
**Confidence:** 0.5""",
            },
            strategy="all",
            total_tokens=50,
            total_cost=0.001,
            success=True,
        )

        root_causes = self.analyzer._extract_root_causes(
            failure=failure,
            multi_agent_response=multi_agent_response,
        )

        self.assertEqual(len(root_causes), 1)
        self.assertEqual(root_causes[0].category, FailureCategory.UNKNOWN)

    def test_synthesize_fix_suggestions(self):
        """Test synthesis of fix suggestions using dialectical approach."""
        failure = TestFailure(
            test_name="test_example",
            test_file="test_foo.py",
            error_message="ImportError",
        )

        root_causes = [
            RootCause(
                description="Missing import",
                category=FailureCategory.IMPORT_ERROR,
                confidence=0.9,
            )
        ]

        parallel_analysis = MultiAgentResponse(
            providers=["anthropic", "openai"],
            responses={
                "anthropic": "Add import foo",
                "openai": "Install foo package",
            },
            strategy="all",
            total_tokens=100,
            total_cost=0.001,
            success=True,
        )

        synthesis_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """**Recommended Fix:** Add import statement
**File to Modify:** src/main.py
**Proposed Changes:** import foo
**Success Probability:** 0.85
**Rationale:** Clear import error""",
            },
            strategy="dialectical",
            total_tokens=150,
            total_cost=0.002,
            success=True,
        )

        self.multi_agent_client.query.return_value = synthesis_response

        fix_suggestions = self.analyzer._synthesize_fix_suggestions(
            failure=failure,
            root_causes=root_causes,
            parallel_analysis=parallel_analysis,
        )

        self.assertEqual(len(fix_suggestions), 1)
        self.assertEqual(fix_suggestions[0].file_path, "src/main.py")
        self.assertEqual(fix_suggestions[0].success_probability, 0.85)
        self.assertIn("import", fix_suggestions[0].proposed_changes.lower())

    def test_synthesize_fix_suggestions_failed_synthesis(self):
        """Test synthesis when dialectical synthesis fails."""
        failure = TestFailure(
            test_name="test_example",
            test_file="test_foo.py",
            error_message="Error",
        )

        parallel_analysis = MultiAgentResponse(
            providers=["anthropic"],
            responses={"anthropic": "Analysis"},
            strategy="all",
            total_tokens=50,
            total_cost=0.001,
            success=True,
        )

        synthesis_response = MultiAgentResponse(
            providers=[],
            responses={},
            strategy="dialectical",
            total_tokens=0,
            total_cost=0.0,
            success=False,
            error="Synthesis failed",
        )

        self.multi_agent_client.query.return_value = synthesis_response

        fix_suggestions = self.analyzer._synthesize_fix_suggestions(
            failure=failure,
            root_causes=[],
            parallel_analysis=parallel_analysis,
        )

        self.assertEqual(len(fix_suggestions), 0)

    def test_is_failure_related_to_changes_test_file_changed(self):
        """Test detection when test file itself was changed."""
        failure = TestFailure(
            test_name="test_foo",
            test_file="tests/test_foo.py",
            error_message="Error",
        )

        is_related = self.analyzer._is_failure_related_to_changes(
            failure=failure,
            changed_files=["tests/test_foo.py", "src/main.py"],
        )

        self.assertTrue(is_related)

    def test_is_failure_related_to_changes_stack_trace_match(self):
        """Test detection via stack trace reference."""
        failure = TestFailure(
            test_name="test_foo",
            test_file="tests/test_foo.py",
            error_message="Error",
            stack_trace="File 'main.py', line 42\n    raise ValueError",
        )

        is_related = self.analyzer._is_failure_related_to_changes(
            failure=failure,
            changed_files=["src/main.py"],
        )

        self.assertTrue(is_related)

    def test_is_failure_related_to_changes_no_match(self):
        """Test detection when no relation to changes."""
        failure = TestFailure(
            test_name="test_foo",
            test_file="tests/test_foo.py",
            error_message="Error",
            stack_trace="File 'other.py', line 10",
        )

        is_related = self.analyzer._is_failure_related_to_changes(
            failure=failure,
            changed_files=["src/main.py"],
        )

        self.assertFalse(is_related)

    def test_is_failure_related_to_changes_no_changed_files(self):
        """Test detection with no changed files."""
        failure = TestFailure(
            test_name="test_foo",
            test_file="tests/test_foo.py",
            error_message="Error",
        )

        is_related = self.analyzer._is_failure_related_to_changes(
            failure=failure,
            changed_files=[],
        )

        self.assertFalse(is_related)

    def test_calculate_analysis_confidence(self):
        """Test analysis confidence calculation."""
        root_causes = [
            RootCause("Cause 1", FailureCategory.ASSERTION_ERROR, 0.9),
            RootCause("Cause 2", FailureCategory.ASSERTION_ERROR, 0.8),
        ]

        fix_suggestions = [
            FixSuggestion("Fix 1", "file.py", "changes", 0.85, "rationale"),
            FixSuggestion("Fix 2", "file.py", "changes", 0.75, "rationale"),
        ]

        confidence = self.analyzer._calculate_analysis_confidence(
            root_causes=root_causes,
            fix_suggestions=fix_suggestions,
            provider_count=3,
        )

        # Should be weighted average of root cause confidence (0.85),
        # fix probability (0.80), and provider factor (1.0 since 3 providers)
        # = 0.85 * 0.4 + 0.80 * 0.4 + 1.0 * 0.2 = 0.86
        self.assertAlmostEqual(confidence, 0.86, places=2)

    def test_calculate_analysis_confidence_no_results(self):
        """Test confidence calculation with no results."""
        confidence = self.analyzer._calculate_analysis_confidence(
            root_causes=[],
            fix_suggestions=[],
            provider_count=2,
        )

        self.assertEqual(confidence, 0.0)

    def test_should_attempt_auto_fix_high_confidence(self):
        """Test auto-fix decision with high confidence."""
        failure = TestFailure("test", "file.py", "error")
        fix = FixSuggestion("Fix", "file.py", "changes", 0.9, "rationale")

        analysis = FailureAnalysis(
            test_failure=failure,
            root_causes=[],
            fix_suggestions=[fix],
            is_related_to_changes=True,
            analysis_confidence=0.85,
        )

        should_fix = self.analyzer.should_attempt_auto_fix(analysis)

        self.assertTrue(should_fix)

    def test_should_attempt_auto_fix_low_confidence(self):
        """Test auto-fix decision with low confidence."""
        failure = TestFailure("test", "file.py", "error")
        fix = FixSuggestion("Fix", "file.py", "changes", 0.4, "rationale")

        analysis = FailureAnalysis(
            test_failure=failure,
            root_causes=[],
            fix_suggestions=[fix],
            is_related_to_changes=True,
            analysis_confidence=0.4,
        )

        should_fix = self.analyzer.should_attempt_auto_fix(analysis)

        self.assertFalse(should_fix)

    def test_should_attempt_auto_fix_no_suggestions(self):
        """Test auto-fix decision with no fix suggestions."""
        failure = TestFailure("test", "file.py", "error")

        analysis = FailureAnalysis(
            test_failure=failure,
            root_causes=[],
            fix_suggestions=[],
            is_related_to_changes=True,
            analysis_confidence=0.9,
        )

        should_fix = self.analyzer.should_attempt_auto_fix(analysis)

        self.assertFalse(should_fix)

    def test_get_best_fix(self):
        """Test getting best fix suggestion."""
        failure = TestFailure("test", "file.py", "error")
        fix1 = FixSuggestion("Fix 1", "file.py", "changes", 0.7, "rationale")
        fix2 = FixSuggestion("Fix 2", "file.py", "changes", 0.9, "rationale")
        fix3 = FixSuggestion("Fix 3", "file.py", "changes", 0.6, "rationale")

        analysis = FailureAnalysis(
            test_failure=failure,
            root_causes=[],
            fix_suggestions=[fix1, fix2, fix3],
            is_related_to_changes=True,
            analysis_confidence=0.8,
        )

        best_fix = self.analyzer.get_best_fix(analysis)

        self.assertEqual(best_fix.description, "Fix 2")
        self.assertEqual(best_fix.success_probability, 0.9)

    def test_get_best_fix_no_suggestions(self):
        """Test getting best fix with no suggestions."""
        failure = TestFailure("test", "file.py", "error")

        analysis = FailureAnalysis(
            test_failure=failure,
            root_causes=[],
            fix_suggestions=[],
            is_related_to_changes=False,
            analysis_confidence=0.0,
        )

        best_fix = self.analyzer.get_best_fix(analysis)

        self.assertIsNone(best_fix)

    def test_get_statistics(self):
        """Test statistics retrieval."""
        self.analyzer.total_analyses = 10
        self.analyzer.successful_analyses = 8
        self.analyzer.failed_analyses = 2

        stats = self.analyzer.get_statistics()

        self.assertEqual(stats["total_analyses"], 10)
        self.assertEqual(stats["successful_analyses"], 8)
        self.assertEqual(stats["failed_analyses"], 2)
        self.assertEqual(stats["success_rate"], 0.8)

    def test_reset_statistics(self):
        """Test statistics reset."""
        self.analyzer.total_analyses = 10
        self.analyzer.successful_analyses = 8
        self.analyzer.failed_analyses = 2

        self.analyzer.reset_statistics()

        self.assertEqual(self.analyzer.total_analyses, 0)
        self.assertEqual(self.analyzer.successful_analyses, 0)
        self.assertEqual(self.analyzer.failed_analyses, 0)

    def test_analyze_single_failure_integration(self):
        """Test complete single failure analysis workflow."""
        failure = TestFailure(
            test_name="test_addition",
            test_file="tests/test_math.py",
            error_message="AssertionError: assert 3 == 4",
            stack_trace="tests/test_math.py:10: AssertionError\n  File 'math_utils.py', line 5",
        )

        # Mock parallel analysis response
        parallel_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": """**Root Cause:** Incorrect addition logic
**Category:** assertion_error
**Confidence:** 0.9
**Fix Strategy:** Fix the add function
**Related to Changes:** yes""",
                "deepseek": """**Root Cause:** Off-by-one error
**Category:** assertion_error
**Confidence:** 0.85
**Fix Strategy:** Check addition implementation
**Related to Changes:** yes""",
            },
            strategy="all",
            total_tokens=200,
            total_cost=0.003,
            success=True,
        )

        # Mock synthesis response
        synthesis_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """**Recommended Fix:** Correct the addition function
**File to Modify:** src/math_utils.py
**Proposed Changes:** return a + b  # was: return a + b + 1
**Success Probability:** 0.95
**Rationale:** Clear off-by-one error in addition
**Alternatives:** Rewrite function from scratch""",
            },
            strategy="dialectical",
            total_tokens=150,
            total_cost=0.002,
            success=True,
        )

        # Set up mock to return different responses for different strategies
        def query_side_effect(prompt, strategy, timeout):
            if strategy == MultiAgentStrategy.ALL:
                return parallel_response
            elif strategy == MultiAgentStrategy.DIALECTICAL:
                return synthesis_response

        self.multi_agent_client.query.side_effect = query_side_effect

        # Run analysis
        analysis = self.analyzer.analyze_single_failure(
            failure=failure,
            framework=TestFramework.PYTEST,
            changed_files=["src/math_utils.py"],
            codebase_context="Python math library",
        )

        # Verify analysis results
        self.assertEqual(analysis.test_failure, failure)
        self.assertGreater(len(analysis.root_causes), 0)
        self.assertGreater(len(analysis.fix_suggestions), 0)
        self.assertTrue(analysis.is_related_to_changes)
        self.assertGreater(analysis.analysis_confidence, 0.7)

        # Verify root causes
        self.assertEqual(
            analysis.root_causes[0].category, FailureCategory.ASSERTION_ERROR
        )

        # Verify fix suggestions
        best_fix = self.analyzer.get_best_fix(analysis)
        self.assertIsNotNone(best_fix)
        self.assertEqual(best_fix.file_path, "src/math_utils.py")
        self.assertGreater(best_fix.success_probability, 0.9)


if __name__ == "__main__":
    unittest.main()
