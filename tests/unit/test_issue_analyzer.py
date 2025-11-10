"""Unit tests for IssueAnalyzer."""

import unittest
from unittest.mock import Mock, MagicMock
from github.Issue import Issue

from src.analyzers.issue_analyzer import (
    IssueAnalyzer,
    IssueType,
    IssueAnalysis,
)
from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentResponse,
)
from src.core.logger import AuditLogger


class TestIssueAnalyzer(unittest.TestCase):
    """Test cases for IssueAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)

        self.analyzer = IssueAnalyzer(
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
            max_complexity_threshold=7,
        )

    def test_initialization(self):
        """Test analyzer initialization."""
        self.assertEqual(self.analyzer.max_complexity_threshold, 7)
        self.assertEqual(self.analyzer.analyses_performed, 0)
        self.assertEqual(self.analyzer.actionable_count, 0)

    def test_extract_issue_type_bug(self):
        """Test bug type extraction."""
        text = "This is clearly a bug that needs to be fixed."
        issue_type = self.analyzer._extract_issue_type(text)
        self.assertEqual(issue_type, IssueType.BUG)

    def test_extract_issue_type_feature(self):
        """Test feature type extraction."""
        text = "New feature request for enhanced functionality."
        issue_type = self.analyzer._extract_issue_type(text)
        self.assertEqual(issue_type, IssueType.FEATURE)

    def test_extract_issue_type_refactor(self):
        """Test refactor type extraction."""
        text = "We should refactor this code for better maintainability."
        issue_type = self.analyzer._extract_issue_type(text)
        self.assertEqual(issue_type, IssueType.REFACTOR)

    def test_extract_complexity_score(self):
        """Test complexity score extraction."""
        test_cases = [
            ("Complexity: 7 out of 10", 7),
            ("Score: 5", 5),
            ("Complexity score is 8/10", 8),
            ("This has complexity 3", 3),
        ]

        for text, expected in test_cases:
            score = self.analyzer._extract_complexity_score(text)
            self.assertEqual(score, expected, f"Failed for: {text}")

    def test_extract_complexity_score_clamping(self):
        """Test complexity score is clamped to 0-10."""
        text = "Complexity: 15"
        score = self.analyzer._extract_complexity_score(text)
        self.assertEqual(score, 10)  # Should be clamped to MAX_COMPLEXITY

    def test_extract_actionability_yes(self):
        """Test actionability extraction - yes."""
        text = "Actionability: yes. The requirements are clear."
        actionable, reason = self.analyzer._extract_actionability(text)
        self.assertTrue(actionable)
        self.assertIn("clear", reason.lower())

    def test_extract_actionability_no(self):
        """Test actionability extraction - no."""
        text = "Actionability: no. Requirements are unclear."
        actionable, reason = self.analyzer._extract_actionability(text)
        self.assertFalse(actionable)

    def test_extract_requirements(self):
        """Test requirements extraction."""
        text = """
Key Requirements:
1. Implement user authentication
2. Add database schema
3. Create API endpoints
4. Write comprehensive tests
"""
        requirements = self.analyzer._extract_requirements(text)

        self.assertGreater(len(requirements), 0)
        self.assertTrue(any("authentication" in req.lower() for req in requirements))
        self.assertTrue(any("database" in req.lower() for req in requirements))

    def test_extract_affected_files(self):
        """Test affected files extraction."""
        text = """
Affected files:
- src/auth/login.py
- src/models/user.py
- tests/test_auth.py
"""
        files = self.analyzer._extract_affected_files(text)

        self.assertGreater(len(files), 0)
        # Should extract Python file paths
        self.assertTrue(any(".py" in f for f in files))

    def test_extract_risks(self):
        """Test risks extraction."""
        text = """
Risks:
1. Database migration complexity
2. Backward compatibility issues
3. Performance degradation
"""
        risks = self.analyzer._extract_risks(text)

        self.assertGreater(len(risks), 0)
        self.assertTrue(any("database" in risk.lower() for risk in risks))

    def test_consensus_issue_type(self):
        """Test consensus issue type determination."""
        types = [IssueType.BUG, IssueType.BUG, IssueType.FEATURE]
        consensus = self.analyzer._consensus_issue_type(types)
        self.assertEqual(consensus, IssueType.BUG)  # Majority vote

    def test_consensus_issue_type_empty(self):
        """Test consensus with no types."""
        types = []
        consensus = self.analyzer._consensus_issue_type(types)
        self.assertEqual(consensus, IssueType.UNKNOWN)

    def test_average_complexity(self):
        """Test complexity averaging."""
        scores = [7, 6, 8]
        average = self.analyzer._average_complexity(scores)
        self.assertEqual(average, 7)  # Should be rounded average

    def test_average_complexity_empty(self):
        """Test complexity averaging with no scores."""
        scores = []
        average = self.analyzer._average_complexity(scores)
        self.assertEqual(average, 5)  # Default to moderate

    def test_consensus_actionability_yes(self):
        """Test actionability consensus - yes."""
        votes = [
            (True, "Clear requirements"),
            (True, "Well defined"),
            (False, "Some concerns"),
        ]
        actionable, reason = self.analyzer._consensus_actionability(votes)

        self.assertTrue(actionable)  # Majority yes
        self.assertIsNotNone(reason)

    def test_consensus_actionability_no(self):
        """Test actionability consensus - no."""
        votes = [
            (False, "Unclear"),
            (False, "Too vague"),
            (True, "Could work"),
        ]
        actionable, reason = self.analyzer._consensus_actionability(votes)

        self.assertFalse(actionable)  # Majority no

    def test_merge_requirements(self):
        """Test requirements merging."""
        req_sets = [
            ["Auth system", "Database schema"],
            ["Database schema", "API endpoints"],
            ["Auth system", "Tests"],
        ]
        merged = self.analyzer._merge_requirements(req_sets)

        # Should deduplicate while preserving order
        self.assertLessEqual(len(merged), 5)  # Max 5
        # Each requirement should appear only once (case-insensitive)
        unique_lower = [r.lower() for r in merged]
        self.assertEqual(len(unique_lower), len(set(unique_lower)))

    def test_calculate_consensus_confidence(self):
        """Test consensus confidence calculation."""
        # All providers responded to all categories
        confidence = self.analyzer._calculate_consensus_confidence(
            type_count=3,
            complexity_count=3,
            actionability_count=3,
            total_providers=3,
        )
        self.assertEqual(confidence, 1.0)  # 100% response rate

        # Partial responses
        confidence = self.analyzer._calculate_consensus_confidence(
            type_count=2,
            complexity_count=3,
            actionability_count=2,
            total_providers=3,
        )
        self.assertAlmostEqual(confidence, 0.778, places=2)  # (2/3 + 3/3 + 2/3) / 3

    def test_calculate_consensus_confidence_no_providers(self):
        """Test confidence calculation with no providers."""
        confidence = self.analyzer._calculate_consensus_confidence(
            type_count=0,
            complexity_count=0,
            actionability_count=0,
            total_providers=0,
        )
        self.assertEqual(confidence, 0.0)

    def test_analyze_issue_success(self):
        """Test successful issue analysis."""
        # Create mock issue
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 42
        mock_issue.title = "Fix authentication bug"
        mock_issue.body = "Users cannot log in"
        mock_issue.labels = [Mock(name="bug"), Mock(name="priority-high")]

        # Mock multi-agent response
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": """
                Issue Type: BUG
                Complexity Score: 7
                Actionability: yes
                Key Requirements:
                1. Fix login endpoint
                2. Add error handling
                Affected Files: src/auth/login.py
                Risks: Database access issues
                Recommended Approach: Debug login flow
                """,
                "deepseek": """
                Issue Type: BUG
                Complexity: 6
                Actionable: yes
                Requirements:
                - Fix authentication
                - Add tests
                """,
            },
            strategy="all",
            total_tokens=5000,
            total_cost=0.04,
            success=True,
        )
        self.multi_agent_client.analyze_issue.return_value = mock_response

        # Analyze issue
        analysis = self.analyzer.analyze_issue(mock_issue)

        # Verify analysis
        self.assertTrue(analysis.analysis_success)
        self.assertEqual(analysis.issue_number, 42)
        self.assertEqual(analysis.issue_type, IssueType.BUG)
        self.assertGreater(analysis.complexity_score, 0)
        self.assertTrue(analysis.is_actionable)
        self.assertGreater(len(analysis.key_requirements), 0)
        self.assertEqual(analysis.total_tokens, 5000)
        self.assertEqual(analysis.total_cost, 0.04)

        # Verify statistics updated
        self.assertEqual(self.analyzer.analyses_performed, 1)
        self.assertEqual(self.analyzer.actionable_count, 1)

    def test_analyze_issue_failure(self):
        """Test issue analysis with multi-agent failure."""
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 42
        mock_issue.title = "Test issue"
        mock_issue.body = "Test body"
        mock_issue.labels = []

        # Mock failed response
        mock_response = MultiAgentResponse(
            providers=[],
            responses={},
            strategy="all",
            total_tokens=0,
            total_cost=0.0,
            success=False,
            error="API timeout",
        )
        self.multi_agent_client.analyze_issue.return_value = mock_response

        # Analyze issue
        analysis = self.analyzer.analyze_issue(mock_issue)

        # Verify failed analysis
        self.assertFalse(analysis.analysis_success)
        self.assertEqual(analysis.complexity_score, 10)  # Max complexity
        self.assertFalse(analysis.is_actionable)
        self.assertIn("failed", analysis.actionability_reason.lower())

    def test_synthesize_analyses_consensus(self):
        """Test synthesis of multiple provider analyses."""
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek", "openai"],
            responses={
                "anthropic": "Issue Type: BUG\nComplexity: 7\nActionability: yes",
                "deepseek": "Type: BUG\nScore: 6\nActionable: yes",
                "openai": "Classification: FEATURE\nComplexity: 8\nActionability: no",
            },
            strategy="all",
            total_tokens=8000,
            total_cost=0.06,
            success=True,
        )

        analysis = self.analyzer._synthesize_analyses(42, mock_response)

        # Should favor BUG (2/3 providers)
        self.assertEqual(analysis.issue_type, IssueType.BUG)
        # Should average complexity (7+6+8)/3 = 7
        self.assertEqual(analysis.complexity_score, 7)
        # Should favor yes for actionability (2/3 yes)
        self.assertTrue(analysis.is_actionable)
        # Confidence should reflect 100% response rate
        self.assertGreater(analysis.consensus_confidence, 0.8)

    def test_get_statistics(self):
        """Test statistics retrieval."""
        # Set some statistics
        self.analyzer.analyses_performed = 10
        self.analyzer.actionable_count = 8
        self.analyzer.complexity_rejected_count = 2

        # Mock multi-agent stats
        self.multi_agent_client.get_statistics.return_value = {
            "total_calls": 10,
            "total_cost": 0.50,
        }

        stats = self.analyzer.get_statistics()

        self.assertEqual(stats["analyses_performed"], 10)
        self.assertEqual(stats["actionable_count"], 8)
        self.assertEqual(stats["actionable_percentage"], 80.0)
        self.assertEqual(stats["complexity_rejected_count"], 2)
        self.assertIn("multi_agent_stats", stats)

    def test_reset_statistics(self):
        """Test statistics reset."""
        self.analyzer.analyses_performed = 10
        self.analyzer.actionable_count = 5
        self.analyzer.complexity_rejected_count = 2

        self.analyzer.reset_statistics()

        self.assertEqual(self.analyzer.analyses_performed, 0)
        self.assertEqual(self.analyzer.actionable_count, 0)
        self.assertEqual(self.analyzer.complexity_rejected_count, 0)
        self.multi_agent_client.reset_statistics.assert_called_once()

    def test_issue_type_enum(self):
        """Test IssueType enum values."""
        self.assertEqual(IssueType.BUG.value, "bug")
        self.assertEqual(IssueType.FEATURE.value, "feature")
        self.assertEqual(IssueType.REFACTOR.value, "refactor")
        self.assertEqual(IssueType.DOCUMENTATION.value, "documentation")
        self.assertEqual(IssueType.UNKNOWN.value, "unknown")

    def test_issue_analysis_to_dict(self):
        """Test IssueAnalysis to_dict conversion."""
        analysis = IssueAnalysis(
            issue_number=42,
            issue_type=IssueType.BUG,
            complexity_score=7,
            is_actionable=True,
            actionability_reason="Clear requirements",
            key_requirements=["Fix auth", "Add tests"],
            affected_files=["src/auth.py"],
            risks=["Database migration"],
            recommended_approach="Debug auth flow",
            provider_analyses={"anthropic": "text"},
            consensus_confidence=0.9,
            total_tokens=5000,
            total_cost=0.04,
            analysis_success=True,
        )

        result = analysis.to_dict()

        self.assertEqual(result["issue_number"], 42)
        self.assertEqual(result["issue_type"], "bug")  # Enum value
        self.assertEqual(result["complexity_score"], 7)
        self.assertTrue(result["is_actionable"])
        self.assertEqual(len(result["key_requirements"]), 2)

    def test_complexity_threshold_rejection(self):
        """Test that complexity above threshold is tracked."""
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 42
        mock_issue.title = "Complex refactor"
        mock_issue.body = "Very complex task"
        mock_issue.labels = []

        # Mock response with high complexity
        mock_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={"anthropic": "Complexity: 9\nActionability: yes"},
            strategy="all",
            total_tokens=2000,
            total_cost=0.02,
            success=True,
        )
        self.multi_agent_client.analyze_issue.return_value = mock_response

        analysis = self.analyzer.analyze_issue(mock_issue)

        # Verify complexity rejection tracked
        self.assertEqual(analysis.complexity_score, 9)
        self.assertEqual(self.analyzer.complexity_rejected_count, 1)


if __name__ == "__main__":
    unittest.main()
