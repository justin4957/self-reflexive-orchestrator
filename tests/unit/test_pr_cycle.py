"""Unit tests for PRCreator."""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime, timezone

from src.cycles.pr_cycle import PRCreator, PRDetails, PRCreationResult
from src.integrations.git_ops import GitOps
from src.integrations.github_client import GitHubClient
from src.core.logger import AuditLogger
from src.core.state import WorkItem
from src.analyzers.implementation_planner import (
    ImplementationPlan,
    ImplementationStep,
    TestStrategy,
    PlanConfidence,
)
from src.integrations.test_runner import TestResult, TestFramework, TestFailure


class TestPRCreator(unittest.TestCase):
    """Test cases for PRCreator."""

    def setUp(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.github_client = Mock(spec=GitHubClient)
        self.logger = Mock(spec=AuditLogger)

        self.pr_creator = PRCreator(
            git_ops=self.git_ops,
            github_client=self.github_client,
            logger=self.logger,
            default_base_branch="main",
            default_reviewers=["reviewer1", "reviewer2"],
        )

    def test_initialization(self):
        """Test PR creator initialization."""
        self.assertEqual(self.pr_creator.default_base_branch, "main")
        self.assertEqual(self.pr_creator.default_reviewers, ["reviewer1", "reviewer2"])
        self.assertEqual(self.pr_creator.total_prs_created, 0)

    def test_pr_details_to_dict(self):
        """Test PRDetails to_dict conversion."""
        details = PRDetails(
            title="Test PR",
            body="Test body",
            head_branch="feature/test",
            base_branch="main",
            draft=False,
            labels=["enhancement"],
            reviewers=["user1"],
            issue_number=42,
        )

        details_dict = details.to_dict()

        self.assertEqual(details_dict["title"], "Test PR")
        self.assertEqual(details_dict["head_branch"], "feature/test")
        self.assertEqual(details_dict["issue_number"], 42)
        self.assertEqual(details_dict["labels"], ["enhancement"])

    def test_pr_creation_result_to_dict(self):
        """Test PRCreationResult to_dict conversion."""
        details = PRDetails(
            title="Test",
            body="Body",
            head_branch="feature/test",
        )

        result = PRCreationResult(
            pr_number=123,
            pr_url="https://github.com/owner/repo/pull/123",
            success=True,
            branch_pushed=True,
            pr_details=details,
        )

        result_dict = result.to_dict()

        self.assertEqual(result_dict["pr_number"], 123)
        self.assertTrue(result_dict["success"])
        self.assertTrue(result_dict["branch_pushed"])

    def test_generate_pr_title(self):
        """Test PR title generation."""
        work_item = WorkItem(
            item_type="issue",
            item_id="42",
            state="in_progress",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata={"title": "[Phase 2] Implement Test Runner", "issue_number": 42},
        )

        plan = Mock(spec=ImplementationPlan)

        title = self.pr_creator._generate_pr_title(work_item, plan)

        self.assertIn("Phase 2", title)
        self.assertIn("Test Runner", title)

    def test_generate_pr_title_without_prefix(self):
        """Test PR title generation without phase prefix."""
        work_item = WorkItem(
            item_type="issue",
            item_id="42",
            state="in_progress",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "title": "Fix bug in analyzer",
                "issue_type": "bug",
                "issue_number": 42,
            },
        )

        plan = Mock(spec=ImplementationPlan)

        title = self.pr_creator._generate_pr_title(work_item, plan)

        self.assertIn("[Bug]", title)
        self.assertIn("Fix bug", title)

    def test_format_changes_made(self):
        """Test changes formatting."""
        plan = ImplementationPlan(
            issue_number=42,
            branch_name="feature/test",
            files_to_create=["src/new_file.py", "tests/test_new.py"],
            files_to_modify=["src/existing.py"],
            implementation_steps=[
                ImplementationStep(1, "Create new file", ["src/new_file.py"], 3),
                ImplementationStep(2, "Update existing", ["src/existing.py"], 2),
            ],
            test_strategy=TestStrategy(
                unit_tests_to_create=[],
                unit_tests_to_modify=[],
                integration_tests_to_create=[],
                test_fixtures_needed=[],
                coverage_requirements="80%",
            ),
            pr_title="Test PR",
            pr_description="Test plan",
            validation_criteria=[],
            estimated_total_complexity=5,
            provider_plans={},
            consensus_confidence=0.9,
            confidence_level=PlanConfidence.HIGH,
            total_tokens=100,
            total_cost=0.01,
            planning_success=True,
        )

        changes = self.pr_creator._format_changes_made(plan)

        self.assertIn("Files Created", changes)
        self.assertIn("src/new_file.py", changes)
        self.assertIn("Files Modified", changes)
        self.assertIn("src/existing.py", changes)
        self.assertIn("Implementation Steps", changes)

    def test_format_test_results_success(self):
        """Test formatting of successful test results."""
        test_result = TestResult(
            framework=TestFramework.PYTEST,
            total_tests=10,
            passed=10,
            failed=0,
            skipped=0,
            execution_time=1.5,
        )

        formatted = self.pr_creator._format_test_results(test_result)

        self.assertIn("✅", formatted)
        self.assertIn("10 passed", formatted)
        self.assertIn("0 failed", formatted)

    def test_format_test_results_failure(self):
        """Test formatting of failed test results."""
        failures = [
            TestFailure("test_one", "test_file.py", "AssertionError: 1 != 2"),
            TestFailure("test_two", "test_file.py", "ValueError: invalid value"),
        ]

        test_result = TestResult(
            framework=TestFramework.PYTEST,
            total_tests=10,
            passed=8,
            failed=2,
            skipped=0,
            execution_time=1.5,
            failures=failures,
        )

        formatted = self.pr_creator._format_test_results(test_result)

        self.assertIn("❌", formatted)
        self.assertIn("8 passed", formatted)
        self.assertIn("2 failed", formatted)
        self.assertIn("test_one", formatted)
        self.assertIn("AssertionError", formatted)

    def test_format_test_results_none(self):
        """Test formatting when no test results."""
        formatted = self.pr_creator._format_test_results(None)

        self.assertIn("⏭️", formatted)
        self.assertIn("not run", formatted)

    def test_determine_labels_feature(self):
        """Test label determination for feature."""
        work_item = WorkItem(
            item_type="issue",
            item_id="42",
            state="in_progress",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "issue_number": 42,
                "title": "[Phase 2] New Feature",
                "issue_type": "feature",
            },
        )

        labels = self.pr_creator._determine_labels(work_item)

        self.assertIn("enhancement", labels)
        self.assertIn("orchestrator", labels)
        self.assertIn("phase-2", labels)

    def test_determine_labels_bug(self):
        """Test label determination for bug."""
        work_item = WorkItem(
            item_type="issue",
            item_id="42",
            state="in_progress",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "issue_number": 42,
                "issue_type": "bug",
            },
        )

        labels = self.pr_creator._determine_labels(work_item)

        self.assertIn("bug", labels)
        self.assertIn("orchestrator", labels)

    def test_push_branch_success(self):
        """Test successful branch push."""
        self.git_ops.push_branch.return_value = None

        result = self.pr_creator._push_branch("feature/test")

        self.assertTrue(result)
        self.git_ops.push_branch.assert_called_once_with("feature/test", set_upstream=True)

    def test_push_branch_failure(self):
        """Test failed branch push."""
        self.git_ops.push_branch.side_effect = Exception("Push failed")

        result = self.pr_creator._push_branch("feature/test")

        self.assertFalse(result)

    def test_add_labels(self):
        """Test adding labels to PR."""
        mock_pr = Mock()
        self.github_client.get_pull_request.return_value = mock_pr

        self.pr_creator._add_labels(123, ["bug", "high-priority"])

        self.github_client.get_pull_request.assert_called_once_with(123)
        mock_pr.add_to_labels.assert_called_once_with("bug", "high-priority")

    def test_add_labels_failure(self):
        """Test label addition failure handling."""
        self.github_client.get_pull_request.side_effect = Exception("API error")

        # Should not raise, just log warning
        self.pr_creator._add_labels(123, ["bug"])

        self.logger.warning.assert_called()

    def test_request_reviews(self):
        """Test requesting reviews."""
        mock_pr = Mock()
        self.github_client.get_pull_request.return_value = mock_pr

        self.pr_creator._request_reviews(123, ["reviewer1", "reviewer2"])

        self.github_client.get_pull_request.assert_called_once_with(123)
        mock_pr.create_review_request.assert_called_once_with(reviewers=["reviewer1", "reviewer2"])

    def test_request_reviews_failure(self):
        """Test review request failure handling."""
        self.github_client.get_pull_request.side_effect = Exception("API error")

        # Should not raise, just log warning
        self.pr_creator._request_reviews(123, ["reviewer1"])

        self.logger.warning.assert_called()

    def test_create_pr_from_work_item_success(self):
        """Test successful PR creation from work item."""
        work_item = WorkItem(
            item_type="issue",
            item_id="42",
            state="in_progress",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "issue_number": 42,
                "title": "[Phase 2] Test Feature",
                "description": "Implement test feature",
                "issue_type": "feature",
            },
        )

        plan = ImplementationPlan(
            issue_number=42,
            branch_name="feature/test-42",
            files_to_create=["src/test.py"],
            files_to_modify=[],
            implementation_steps=[
                ImplementationStep(1, "Create test file", ["src/test.py"], 3)
            ],
            test_strategy=TestStrategy(
                unit_tests_to_create=[],
                unit_tests_to_modify=[],
                integration_tests_to_create=[],
                test_fixtures_needed=[],
                coverage_requirements="80%",
            ),
            pr_title="Test PR",
            pr_description="Test implementation",
            validation_criteria=[],
            estimated_total_complexity=3,
            provider_plans={},
            consensus_confidence=0.9,
            confidence_level=PlanConfidence.HIGH,
            total_tokens=100,
            total_cost=0.01,
            planning_success=True,
        )

        test_result = TestResult(
            framework=TestFramework.PYTEST,
            total_tests=5,
            passed=5,
            failed=0,
            skipped=0,
            execution_time=1.0,
        )

        # Mock successful operations
        self.git_ops.push_branch.return_value = None

        mock_pr = Mock()
        mock_pr.number = 100
        mock_pr.html_url = "https://github.com/owner/repo/pull/100"
        self.github_client.create_pull_request.return_value = mock_pr

        # Execute
        result = self.pr_creator.create_pr_from_work_item(
            work_item=work_item,
            plan=plan,
            test_result=test_result,
        )

        # Verify
        self.assertTrue(result.success)
        self.assertEqual(result.pr_number, 100)
        self.assertTrue(result.branch_pushed)
        self.assertIn("github.com", result.pr_url)

        # Verify PR creation was called
        self.github_client.create_pull_request.assert_called_once()
        call_args = self.github_client.create_pull_request.call_args
        self.assertIn("Phase 2", call_args[1]["title"])
        self.assertIn("Closes #42", call_args[1]["body"])

    def test_create_pr_from_work_item_push_failure(self):
        """Test PR creation when branch push fails."""
        work_item = WorkItem(
            item_type="issue",
            item_id="42",
            state="in_progress",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "issue_number": 42,
                "title": "Test",
            },
        )

        plan = ImplementationPlan(
            issue_number=42,
            branch_name="feature/test",
            files_to_create=[],
            files_to_modify=[],
            implementation_steps=[],
            test_strategy=TestStrategy(
                unit_tests_to_create=[],
                unit_tests_to_modify=[],
                integration_tests_to_create=[],
                test_fixtures_needed=[],
                coverage_requirements="80%",
            ),
            pr_title="Test PR",
            pr_description="Test",
            validation_criteria=[],
            estimated_total_complexity=1,
            provider_plans={},
            consensus_confidence=0.7,
            confidence_level=PlanConfidence.MEDIUM,
            total_tokens=100,
            total_cost=0.01,
            planning_success=True,
        )

        # Mock failed push
        self.git_ops.push_branch.side_effect = Exception("Push failed")

        result = self.pr_creator.create_pr_from_work_item(
            work_item=work_item,
            plan=plan,
        )

        self.assertFalse(result.success)
        self.assertFalse(result.branch_pushed)
        self.assertEqual(result.pr_number, 0)
        self.assertIn("push", result.error.lower())

    def test_create_pr_from_work_item_pr_creation_failure(self):
        """Test PR creation when GitHub API fails."""
        work_item = WorkItem(
            item_type="issue",
            item_id="42",
            state="in_progress",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "issue_number": 42,
                "title": "Test",
            },
        )

        plan = ImplementationPlan(
            issue_number=42,
            branch_name="feature/test",
            files_to_create=[],
            files_to_modify=[],
            implementation_steps=[],
            test_strategy=TestStrategy(
                unit_tests_to_create=[],
                unit_tests_to_modify=[],
                integration_tests_to_create=[],
                test_fixtures_needed=[],
                coverage_requirements="80%",
            ),
            pr_title="Test PR",
            pr_description="Test",
            validation_criteria=[],
            estimated_total_complexity=1,
            provider_plans={},
            consensus_confidence=0.7,
            confidence_level=PlanConfidence.MEDIUM,
            total_tokens=100,
            total_cost=0.01,
            planning_success=True,
        )

        # Mock successful push but failed PR creation
        self.git_ops.push_branch.return_value = None
        self.github_client.create_pull_request.side_effect = Exception("API error")

        result = self.pr_creator.create_pr_from_work_item(
            work_item=work_item,
            plan=plan,
        )

        self.assertFalse(result.success)
        self.assertTrue(result.branch_pushed)
        self.assertIn("API error", result.error)

    def test_get_statistics(self):
        """Test statistics retrieval."""
        self.pr_creator.total_prs_created = 10
        self.pr_creator.successful_prs = 8
        self.pr_creator.failed_prs = 2

        stats = self.pr_creator.get_statistics()

        self.assertEqual(stats["total_prs_created"], 10)
        self.assertEqual(stats["successful_prs"], 8)
        self.assertEqual(stats["failed_prs"], 2)
        self.assertEqual(stats["success_rate"], 80.0)

    def test_reset_statistics(self):
        """Test statistics reset."""
        self.pr_creator.total_prs_created = 5
        self.pr_creator.successful_prs = 4
        self.pr_creator.failed_prs = 1

        self.pr_creator.reset_statistics()

        self.assertEqual(self.pr_creator.total_prs_created, 0)
        self.assertEqual(self.pr_creator.successful_prs, 0)
        self.assertEqual(self.pr_creator.failed_prs, 0)

    def test_format_implementation_details(self):
        """Test implementation details formatting."""
        plan = ImplementationPlan(
            issue_number=42,
            branch_name="feature/test",
            files_to_create=[],
            files_to_modify=[],
            implementation_steps=[],
            test_strategy=TestStrategy(
                unit_tests_to_create=["tests/test_foo.py"],
                unit_tests_to_modify=[],
                integration_tests_to_create=[],
                test_fixtures_needed=[],
                coverage_requirements="Run all unit tests - 80% coverage required",
            ),
            pr_title="Test PR",
            pr_description="Detailed implementation plan",
            validation_criteria=[],
            estimated_total_complexity=7,
            provider_plans={},
            consensus_confidence=0.9,
            confidence_level=PlanConfidence.HIGH,
            total_tokens=100,
            total_cost=0.01,
            planning_success=True,
        )

        details = self.pr_creator._format_implementation_details(
            plan=plan,
            additional_context="Additional notes about the implementation",
        )

        self.assertIn("Detailed implementation plan", details)
        self.assertIn("Run all unit tests", details)
        self.assertIn("7/10", details)
        self.assertIn("high confidence", details)
        self.assertIn("Additional notes", details)


if __name__ == '__main__':
    unittest.main()
