"""Unit tests for ImplementationPlanner."""

import unittest
from unittest.mock import MagicMock, Mock

from github.Issue import Issue

from src.analyzers.implementation_planner import (ImplementationPlan,
                                                  ImplementationPlanner,
                                                  ImplementationStep,
                                                  PlanConfidence, TestStrategy)
from src.analyzers.issue_analyzer import IssueAnalysis, IssueType
from src.core.logger import AuditLogger
from src.integrations.multi_agent_coder_client import (MultiAgentCoderClient,
                                                       MultiAgentResponse)


class TestImplementationPlanner(unittest.TestCase):
    """Test cases for ImplementationPlanner."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)

        self.planner = ImplementationPlanner(
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
        )

    def test_initialization(self):
        """Test planner initialization."""
        self.assertEqual(self.planner.plans_generated, 0)
        self.assertEqual(self.planner.high_confidence_plans, 0)
        self.assertEqual(self.planner.low_confidence_plans, 0)

    def test_generate_branch_name(self):
        """Test branch name generation."""
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 42
        mock_issue.title = "Fix Authentication Bug!"

        branch_name = self.planner._generate_branch_name(mock_issue)

        self.assertEqual(branch_name, "orchestrator/issue-42-fix-authentication-bug")

    def test_generate_branch_name_long_title(self):
        """Test branch name generation with very long title."""
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 100
        mock_issue.title = "This is a very long issue title that should be truncated to ensure the branch name is not too long for git"

        branch_name = self.planner._generate_branch_name(mock_issue)

        self.assertTrue(branch_name.startswith("orchestrator/issue-100-"))
        self.assertLessEqual(
            len(branch_name), 80
        )  # Allow for "orchestrator/issue-100-" prefix

    def test_generate_branch_name_special_chars(self):
        """Test branch name generation with special characters."""
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 5
        mock_issue.title = "Add @user/feature & remove #tags!"

        branch_name = self.planner._generate_branch_name(mock_issue)

        # Special chars should be removed
        self.assertNotIn("@", branch_name)
        self.assertNotIn("&", branch_name)
        self.assertNotIn("#", branch_name)
        self.assertNotIn("!", branch_name)

    def test_extract_files_to_modify(self):
        """Test extracting files to modify from responses."""
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": """
                Files to Modify:
                - `src/auth/login.py`
                - `src/models/user.py`
                """,
                "deepseek": """
                Modify: `src/auth/login.py`
                Modify: `tests/unit/test_auth.py`
                """,
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        files = self.planner._extract_files_to_modify(mock_response)

        self.assertIn("src/auth/login.py", files)
        self.assertIn("src/models/user.py", files)
        self.assertIn("tests/unit/test_auth.py", files)

    def test_extract_files_to_create(self):
        """Test extracting files to create from responses."""
        mock_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """
                Files to Create:
                - `src/analyzers/new_analyzer.py`
                Create: `tests/unit/test_new_analyzer.py`
                """
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        files = self.planner._extract_files_to_create(mock_response)

        self.assertIn("src/analyzers/new_analyzer.py", files)
        self.assertIn("tests/unit/test_new_analyzer.py", files)

    def test_extract_implementation_steps(self):
        """Test extracting implementation steps from responses."""
        mock_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """
                Implementation Steps:
                1. Create base analyzer class in `src/analyzers/base.py` (complexity: 3)
                2. Implement analysis logic (complexity: 7)
                3. Add unit tests in `tests/unit/test_analyzer.py`
                """
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        steps = self.planner._extract_implementation_steps(mock_response)

        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0].step_number, 1)
        self.assertEqual(steps[0].estimated_complexity, 3)
        self.assertIn("src/analyzers/base.py", steps[0].files_affected)

    def test_merge_similar_steps(self):
        """Test merging similar steps from different providers."""
        all_steps = [
            {
                "step_number": 1,
                "description": "Create analyzer class",
                "files_affected": ["src/analyzer.py"],
                "complexity": 5,
                "provider": "anthropic",
            },
            {
                "step_number": 1,
                "description": "Create analyzer class with validation",
                "files_affected": ["src/analyzer.py", "src/validator.py"],
                "complexity": 6,
                "provider": "deepseek",
            },
            {
                "step_number": 2,
                "description": "Add tests",
                "files_affected": ["tests/test_analyzer.py"],
                "complexity": 3,
                "provider": "anthropic",
            },
        ]

        merged = self.planner._merge_similar_steps(all_steps)

        self.assertEqual(len(merged), 2)
        # Step 1 should have both files
        self.assertEqual(merged[0].step_number, 1)
        self.assertIn("src/analyzer.py", merged[0].files_affected)
        self.assertIn("src/validator.py", merged[0].files_affected)

    def test_extract_test_strategy(self):
        """Test extracting test strategy from responses."""
        mock_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """
                Test Strategy:
                - Create test_planner.py
                - Create test_executor.py
                - Integration: test_full_cycle
                - Fixtures: sample issues, mock responses
                - Coverage: > 90%
                """
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        strategy = self.planner._extract_test_strategy(mock_response)

        self.assertIn("tests/unit/test_planner.py", strategy.unit_tests_to_create)
        self.assertIn("tests/unit/test_executor.py", strategy.unit_tests_to_create)
        self.assertIn(
            "tests/integration/test_full_cycle.py", strategy.integration_tests_to_create
        )

    def test_extract_validation_criteria(self):
        """Test extracting validation criteria from responses."""
        mock_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """
                Validation:
                - All unit tests pass
                - Integration tests pass
                - No regressions in existing functionality
                - Code coverage maintained
                """
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        criteria = self.planner._extract_validation_criteria(mock_response)

        self.assertGreater(len(criteria), 0)
        self.assertTrue(any("tests pass" in c.lower() for c in criteria))

    def test_calculate_confidence_high(self):
        """Test confidence calculation - high confidence scenario."""
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek", "openai"],
            responses={
                "anthropic": "Detailed response " * 500,
                "deepseek": "Detailed response " * 500,
                "openai": "Detailed response " * 500,
            },
            strategy="all",
            total_tokens=10000,
            total_cost=0.10,
            success=True,
        )

        confidence = self.planner._calculate_confidence(
            mock_response,
            num_files_modify=5,
            num_files_create=3,
            num_steps=8,
        )

        self.assertGreater(confidence, 0.8)  # Should be high confidence

    def test_calculate_confidence_low(self):
        """Test confidence calculation - low confidence scenario."""
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "Short response",
            },
            strategy="all",
            total_tokens=100,
            total_cost=0.001,
            success=True,
        )

        confidence = self.planner._calculate_confidence(
            mock_response,
            num_files_modify=0,
            num_files_create=0,
            num_steps=0,
        )

        self.assertLess(confidence, 0.6)  # Should be low confidence

    def test_get_confidence_level(self):
        """Test confidence level enum mapping."""
        self.assertEqual(
            self.planner._get_confidence_level(0.95), PlanConfidence.VERY_HIGH
        )
        self.assertEqual(self.planner._get_confidence_level(0.85), PlanConfidence.HIGH)
        self.assertEqual(
            self.planner._get_confidence_level(0.70), PlanConfidence.MEDIUM
        )
        self.assertEqual(self.planner._get_confidence_level(0.40), PlanConfidence.LOW)

    def test_calculate_total_complexity(self):
        """Test total complexity calculation."""
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "Overall complexity: 7",
                "deepseek": "Total complexity: 6",
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        steps = [
            ImplementationStep(1, "Step 1", [], 5),
            ImplementationStep(2, "Step 2", [], 7),
        ]

        complexity = self.planner._calculate_total_complexity(mock_response, steps)

        self.assertGreaterEqual(complexity, 0)
        self.assertLessEqual(complexity, 10)

    def test_generate_pr_template(self):
        """Test PR title and description generation."""
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 42
        mock_issue.title = "[Phase 2] Implement Feature X"

        mock_analysis = IssueAnalysis(
            issue_number=42,
            issue_type=IssueType.FEATURE,
            complexity_score=6,
            is_actionable=True,
            actionability_reason="Clear requirements",
            key_requirements=["Req 1", "Req 2"],
            affected_files=[],
            risks=[],
            recommended_approach="Implement incrementally",
            provider_analyses={},
            consensus_confidence=0.85,
            total_tokens=1000,
            total_cost=0.01,
            analysis_success=True,
        )

        steps = [
            ImplementationStep(1, "Create base class", ["src/base.py"], 3),
            ImplementationStep(2, "Add tests", ["tests/test_base.py"], 2),
        ]

        pr_title, pr_description = self.planner._generate_pr_template(
            mock_issue, mock_analysis, steps
        )

        self.assertEqual(pr_title, "[Phase 2] Implement Feature X")
        self.assertIn("#42", pr_description)
        self.assertIn("feature", pr_description.lower())
        self.assertIn("Fixes #42", pr_description)

    def test_generate_plan_success(self):
        """Test successful plan generation."""
        # Create mock issue
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 10
        mock_issue.title = "Add authentication"
        mock_issue.body = "Add user authentication"
        mock_issue.labels = []

        # Create mock analysis
        mock_analysis = IssueAnalysis(
            issue_number=10,
            issue_type=IssueType.FEATURE,
            complexity_score=6,
            is_actionable=True,
            actionability_reason="Requirements clear",
            key_requirements=["Add auth module", "Add tests"],
            affected_files=["src/auth.py"],
            risks=["Security considerations"],
            recommended_approach="Use JWT tokens",
            provider_analyses={},
            consensus_confidence=0.85,
            total_tokens=2000,
            total_cost=0.02,
            analysis_success=True,
        )

        # Mock multi-agent response
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": """
                Files to Modify:
                - `src/auth.py`

                Files to Create:
                - `src/auth/jwt_handler.py`
                - `tests/unit/test_auth.py`

                Implementation Steps:
                1. Create JWT handler class (complexity: 5)
                2. Integrate with existing auth module (complexity: 6)
                3. Add comprehensive tests (complexity: 4)

                Test Strategy:
                - Create test_jwt_handler.py
                - Create test_auth_integration.py

                Validation:
                - All tests pass
                - Security review completed

                Overall complexity: 6
                """,
                "deepseek": """
                Modify: src/auth.py

                Create:
                - src/auth/jwt_handler.py
                - tests/unit/test_auth.py

                Steps:
                1. Implement JWT class (complexity: 5)
                2. Add auth endpoints (complexity: 7)
                3. Write tests (complexity: 3)

                Total complexity: 6
                """,
            },
            strategy="all",
            total_tokens=5000,
            total_cost=0.04,
            success=True,
        )

        self.multi_agent_client.query.return_value = mock_response

        # Generate plan
        plan = self.planner.generate_plan(mock_issue, mock_analysis)

        # Verify plan
        self.assertTrue(plan.planning_success)
        self.assertEqual(plan.issue_number, 10)
        self.assertIn("orchestrator/issue-10-", plan.branch_name)
        self.assertGreater(len(plan.files_to_create), 0)
        self.assertGreater(len(plan.implementation_steps), 0)
        self.assertGreater(plan.consensus_confidence, 0.0)
        self.assertEqual(plan.total_tokens, 5000)
        self.assertEqual(plan.total_cost, 0.04)

        # Verify statistics updated
        self.assertEqual(self.planner.plans_generated, 1)

    def test_generate_plan_multi_agent_failure(self):
        """Test plan generation when multi-agent-coder fails."""
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 20
        mock_issue.title = "Fix bug"

        mock_analysis = IssueAnalysis(
            issue_number=20,
            issue_type=IssueType.BUG,
            complexity_score=4,
            is_actionable=True,
            actionability_reason="Bug is reproducible",
            key_requirements=["Fix error"],
            affected_files=["src/main.py"],
            risks=[],
            recommended_approach="Debug and fix",
            provider_analyses={},
            consensus_confidence=0.70,
            total_tokens=1000,
            total_cost=0.01,
            analysis_success=True,
        )

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

        self.multi_agent_client.query.return_value = mock_response

        # Generate plan
        plan = self.planner.generate_plan(mock_issue, mock_analysis)

        # Verify fallback plan created
        self.assertFalse(plan.planning_success)
        self.assertEqual(plan.issue_number, 20)
        self.assertEqual(plan.confidence_level, PlanConfidence.LOW)
        self.assertLessEqual(plan.consensus_confidence, 0.5)

    def test_format_list(self):
        """Test list formatting."""
        items = ["Item 1", "Item 2", "Item 3"]
        formatted = self.planner._format_list(items)

        self.assertIn("- Item 1", formatted)
        self.assertIn("- Item 2", formatted)
        self.assertIn("- Item 3", formatted)

    def test_format_list_empty(self):
        """Test formatting empty list."""
        formatted = self.planner._format_list([])
        self.assertEqual(formatted, "- None")

    def test_format_list_nested(self):
        """Test formatting nested lists."""
        items = [["Item 1", "Item 2"], ["Item 3"]]
        formatted = self.planner._format_list(items)

        self.assertIn("- Item 1", formatted)
        self.assertIn("- Item 2", formatted)
        self.assertIn("- Item 3", formatted)

    def test_get_statistics(self):
        """Test statistics retrieval."""
        self.planner.plans_generated = 10
        self.planner.high_confidence_plans = 7
        self.planner.low_confidence_plans = 2

        self.multi_agent_client.get_statistics.return_value = {
            "total_calls": 10,
            "total_cost": 0.50,
        }

        stats = self.planner.get_statistics()

        self.assertEqual(stats["plans_generated"], 10)
        self.assertEqual(stats["high_confidence_plans"], 7)
        self.assertEqual(stats["low_confidence_plans"], 2)
        self.assertEqual(stats["high_confidence_percentage"], 70.0)
        self.assertIn("multi_agent_stats", stats)

    def test_reset_statistics(self):
        """Test statistics reset."""
        self.planner.plans_generated = 10
        self.planner.high_confidence_plans = 5
        self.planner.low_confidence_plans = 2

        self.planner.reset_statistics()

        self.assertEqual(self.planner.plans_generated, 0)
        self.assertEqual(self.planner.high_confidence_plans, 0)
        self.assertEqual(self.planner.low_confidence_plans, 0)
        self.multi_agent_client.reset_statistics.assert_called_once()

    def test_implementation_step_dataclass(self):
        """Test ImplementationStep dataclass."""
        step = ImplementationStep(
            step_number=1,
            description="Create base class",
            files_affected=["src/base.py"],
            estimated_complexity=5,
            dependencies=[],
        )

        step_dict = step.to_dict()

        self.assertEqual(step_dict["step_number"], 1)
        self.assertEqual(step_dict["description"], "Create base class")
        self.assertEqual(step_dict["files_affected"], ["src/base.py"])
        self.assertEqual(step_dict["estimated_complexity"], 5)

    def test_test_strategy_dataclass(self):
        """Test TestStrategy dataclass."""
        strategy = TestStrategy(
            unit_tests_to_create=["test_a.py"],
            unit_tests_to_modify=["test_b.py"],
            integration_tests_to_create=["test_integration.py"],
            test_fixtures_needed=["fixture1"],
            coverage_requirements="> 90%",
        )

        strategy_dict = strategy.to_dict()

        self.assertIn("unit_tests_to_create", strategy_dict)
        self.assertEqual(strategy_dict["coverage_requirements"], "> 90%")

    def test_plan_to_dict(self):
        """Test ImplementationPlan to_dict conversion."""
        plan = ImplementationPlan(
            issue_number=1,
            branch_name="orchestrator/issue-1-test",
            files_to_modify=["src/main.py"],
            files_to_create=["src/new.py"],
            implementation_steps=[ImplementationStep(1, "Step 1", [], 3)],
            test_strategy=TestStrategy([], [], [], [], "Maintain coverage"),
            pr_title="Test PR",
            pr_description="Test description",
            validation_criteria=["Tests pass"],
            estimated_total_complexity=5,
            provider_plans={"anthropic": "plan"},
            consensus_confidence=0.85,
            confidence_level=PlanConfidence.HIGH,
            total_tokens=1000,
            total_cost=0.01,
            planning_success=True,
        )

        plan_dict = plan.to_dict()

        self.assertEqual(plan_dict["issue_number"], 1)
        self.assertEqual(plan_dict["confidence_level"], "high")
        self.assertIn("implementation_steps", plan_dict)
        self.assertIn("test_strategy", plan_dict)

    def test_plan_confidence_enum(self):
        """Test PlanConfidence enum values."""
        self.assertEqual(PlanConfidence.LOW.value, "low")
        self.assertEqual(PlanConfidence.MEDIUM.value, "medium")
        self.assertEqual(PlanConfidence.HIGH.value, "high")
        self.assertEqual(PlanConfidence.VERY_HIGH.value, "very_high")


if __name__ == "__main__":
    unittest.main()
