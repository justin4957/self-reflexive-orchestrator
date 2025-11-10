"""Unit tests for failure analyzer."""

import unittest
from unittest.mock import MagicMock, Mock

from src.core.logger import AuditLogger
from src.integrations.multi_agent_coder_client import (MultiAgentCoderClient,
                                                       MultiAgentResponse)
from src.safety.failure_analyzer import (FailureAnalysis, FailureAnalyzer,
                                         LessonsLearned)


class TestFailureAnalyzer(unittest.TestCase):
    """Test cases for FailureAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)
        self.analyzer = FailureAnalyzer(
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
        )

    def test_initialization(self):
        """Test analyzer initialization."""
        self.assertIsNotNone(self.analyzer.multi_agent_client)
        self.assertIsNotNone(self.analyzer.logger)

    def test_analyze_failure_success(self):
        """Test successful failure analysis."""
        # Mock multi-agent response
        mock_response = MultiAgentResponse(
            providers=["anthropic", "openai"],
            responses={
                "anthropic": """
**Root Cause Analysis**:
The function failed due to null pointer exception in data processing.

**Why Wasn't This Caught Earlier?**:
Our guards didn't check for null inputs in this edge case.

**Prevention Measures**:
- Add null checking guard
- Implement input validation
- Add unit tests for edge cases

**Recommendations**:
Should we add a new safety guard? YES
Guard pattern: Check for null/undefined inputs before processing
Should we adjust complexity limits? NO

**Summary**: Null pointer exception due to missing input validation.
                """,
                "openai": """
**Root Cause**: Null input not handled properly.

**Why not caught**: Guards missed this pattern.

**Prevention**:
- Input validation
- Null checks
- Better tests

**Recommendations**:
Add guard? YES
Complexity limits? NO

**Summary**: Need input validation guards.
                """,
            },
            strategy="dialectical",
            total_tokens=1500,
            total_cost=0.02,
            success=True,
        )
        self.multi_agent_client.query.return_value = mock_response

        analysis = self.analyzer.analyze_failure(
            failure_id="fail-123",
            work_item_description="Add user registration feature",
            changes_summary="Created registration endpoint",
            failure_reason="Null pointer exception in user validation",
            test_output="NullPointerException at line 42",
        )

        # Verify analysis
        self.assertEqual(analysis.failure_id, "fail-123")
        self.assertEqual(
            analysis.work_item_description, "Add user registration feature"
        )
        self.assertIn("null", analysis.lessons_learned.root_cause.lower())
        self.assertGreater(len(analysis.lessons_learned.prevention_measures), 0)
        self.assertTrue(analysis.lessons_learned.should_add_guard)
        self.assertFalse(analysis.lessons_learned.should_update_complexity_threshold)
        self.assertIn("anthropic", analysis.provider_perspectives)
        self.assertIn("openai", analysis.provider_perspectives)

    def test_analyze_failure_with_threshold_recommendation(self):
        """Test failure analysis recommending threshold update."""
        mock_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """
**Root Cause**: Complexity exceeded safe handling limits.

**Why Not Caught**: Guards did not catch this level.

**Prevention**:
- Lower complexity limits
- Add more granular complexity checks

**Recommendations**:
Should adjust complexity threshold? YES
Set threshold to 50

**Summary**: Complexity limits too permissive.
                """
            },
            strategy="dialectical",
            total_tokens=800,
            total_cost=0.01,
            success=True,
        )
        self.multi_agent_client.query.return_value = mock_response

        analysis = self.analyzer.analyze_failure(
            failure_id="fail-124",
            work_item_description="Refactor authentication system",
            changes_summary="Rewrote auth module",
            failure_reason="Integration tests failed",
        )

        # Verify threshold recommendation
        self.assertTrue(analysis.lessons_learned.should_update_complexity_threshold)
        self.assertEqual(analysis.lessons_learned.recommended_threshold, 50)

    def test_analyze_failure_multi_agent_failure(self):
        """Test failure analysis when multi-agent query fails."""
        # Mock failed response
        mock_response = MultiAgentResponse(
            providers=[],
            responses={},
            strategy="dialectical",
            total_tokens=0,
            total_cost=0.0,
            success=False,
            error="Timeout",
        )
        self.multi_agent_client.query.return_value = mock_response

        analysis = self.analyzer.analyze_failure(
            failure_id="fail-125",
            work_item_description="Fix bug in payment processing",
            changes_summary="Updated payment handler",
            failure_reason="Transaction validation failed",
        )

        # Should return basic analysis on failure
        self.assertEqual(analysis.failure_id, "fail-125")
        self.assertFalse(analysis.consensus_reached)
        self.assertEqual(analysis.lessons_learned.root_cause, "Analysis failed")
        self.assertEqual(len(analysis.provider_perspectives), 0)

    def test_analyze_failure_patterns(self):
        """Test analyzing patterns across multiple failures."""
        recent_failures = [
            {
                "work_item_description": "Add user login",
                "failure_reason": "Null pointer in validation",
                "changes_summary": "Created login endpoint",
            },
            {
                "work_item_description": "Add password reset",
                "failure_reason": "Null pointer in email validation",
                "changes_summary": "Created reset endpoint",
            },
            {
                "work_item_description": "Add user profile",
                "failure_reason": "Null pointer in profile save",
                "changes_summary": "Created profile endpoint",
            },
        ]

        # Mock pattern analysis response
        mock_response = MultiAgentResponse(
            providers=["anthropic", "openai"],
            responses={
                "anthropic": """
**Common Root Causes**:
- Null pointer exceptions
- Missing input validation
- Inadequate null checks

**Guard Gaps**:
- No null input validation guard
- Missing edge case detection

**Process Improvements**:
- Implement comprehensive input validation
- Add null checking to code standards
- Require validation tests for all endpoints

**Complexity Calibration**: Current threshold appears appropriate.
                """,
                "openai": """
**Common Causes**:
- Null handling issues across endpoints

**Guard Gaps**:
- Input validation missing

**Process**:
- Add validation layer

**Complexity**: Threshold seems fine.
                """,
            },
            strategy="all",
            total_tokens=2000,
            total_cost=0.025,
            success=True,
        )
        self.multi_agent_client.query.return_value = mock_response

        patterns = self.analyzer.analyze_failure_patterns(recent_failures)

        # Verify pattern extraction
        self.assertIn("common_causes", patterns)
        self.assertIn("guard_gaps", patterns)
        self.assertIn("process_improvements", patterns)
        self.assertGreater(len(patterns["common_causes"]), 0)

    def test_extract_section(self):
        """Test extracting content from a section."""
        text = """
**Root Cause Analysis**:
This is the root cause.
It spans multiple lines.
More details here.

**Next Section**:
Something else.
        """

        section = self.analyzer._extract_section(text, "root cause")
        self.assertIn("root cause", section.lower())

    def test_extract_list_items(self):
        """Test extracting list items from text."""
        text = """
**Prevention Measures**:
- Add input validation
- Implement null checks
- Create unit tests
- Add integration tests
- Update documentation

**Next Section**:
- This shouldn't be included
        """

        items = self.analyzer._extract_list_items(text, "prevention")

        # Should extract up to 5 items
        self.assertLessEqual(len(items), 5)
        self.assertGreater(len(items), 0)
        self.assertIn("validation", items[0].lower())

    def test_check_consensus(self):
        """Test consensus checking."""
        # Strong consensus - need at least 5 common terms with 6+ chars mentioned by 2+ providers
        mock_response = MultiAgentResponse(
            providers=["anthropic", "openai", "deepseek"],
            responses={
                "anthropic": "validation complexity threshold pattern missing guards implementation requirements detected",
                "openai": "validation complexity threshold pattern missing guards implementation requirements analysis",
                "deepseek": "validation complexity threshold pattern missing guards implementation requirements review",
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        consensus = self.analyzer._check_consensus(mock_response)
        self.assertTrue(consensus)

        # Weak consensus
        mock_response_weak = MultiAgentResponse(
            providers=["anthropic", "openai"],
            responses={
                "anthropic": "The issue is complex and multifaceted.",
                "openai": "Different perspective on the problem.",
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        consensus_weak = self.analyzer._check_consensus(mock_response_weak)
        self.assertFalse(consensus_weak)

    def test_build_analysis_prompt(self):
        """Test building analysis prompt."""
        prompt = self.analyzer._build_analysis_prompt(
            work_item_description="Add feature X",
            changes_summary="Created X module",
            failure_reason="Tests failed",
            test_output="AssertionError: expected True got False",
            additional_context={"complexity": 7},
        )

        # Verify prompt contains key sections
        self.assertIn("Add feature X", prompt)
        self.assertIn("Created X module", prompt)
        self.assertIn("Tests failed", prompt)
        self.assertIn("AssertionError", prompt)
        self.assertIn("complexity", prompt.lower())
        self.assertIn("Root Cause", prompt)
        self.assertIn("Prevention", prompt)

    def test_lessons_learned_to_dict(self):
        """Test LessonsLearned to_dict conversion."""
        lessons = LessonsLearned(
            root_cause="Null pointer exception",
            why_not_caught="Guards didn't check nulls",
            prevention_measures=["Add null checks", "Input validation"],
            should_update_complexity_threshold=True,
            recommended_threshold=50,
            should_add_guard=True,
            guard_definition="Check for null inputs",
            summary="Need null validation",
            confidence=0.85,
        )

        lessons_dict = lessons.to_dict()

        self.assertEqual(lessons_dict["root_cause"], "Null pointer exception")
        self.assertTrue(lessons_dict["should_add_guard"])
        self.assertEqual(lessons_dict["recommended_threshold"], 50)
        self.assertEqual(lessons_dict["confidence"], 0.85)

    def test_failure_analysis_to_dict(self):
        """Test FailureAnalysis to_dict conversion."""
        lessons = LessonsLearned(
            root_cause="Test failure",
            why_not_caught="Unknown",
            prevention_measures=["Add tests"],
            summary="Need more tests",
        )

        analysis = FailureAnalysis(
            failure_id="fail-126",
            work_item_description="Test feature",
            failure_reason="Tests failed",
            lessons_learned=lessons,
            provider_perspectives={"anthropic": "Response"},
            consensus_reached=True,
        )

        analysis_dict = analysis.to_dict()

        self.assertEqual(analysis_dict["failure_id"], "fail-126")
        self.assertTrue(analysis_dict["consensus_reached"])
        self.assertIn("lessons_learned", analysis_dict)
        self.assertIn("provider_perspectives", analysis_dict)


if __name__ == "__main__":
    unittest.main()
