"""Unit tests for PRMerger."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

from src.core.config import PRManagementConfig, SafetyConfig
from src.core.logger import AuditLogger
from src.cycles.pr_merger import (
    MergeResult,
    MergeStrategy,
    MergeValidation,
    MergeValidationError,
    PRMerger,
)
from src.integrations.git_ops import GitOps
from src.integrations.github_client import GitHubClient


class TestPRMerger(unittest.TestCase):
    """Test cases for PRMerger."""

    def setUp(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.github_client = Mock(spec=GitHubClient)
        self.logger = Mock(spec=AuditLogger)

        self.pr_config = PRManagementConfig(
            auto_merge=True,
            merge_strategy="squash",
            require_reviews=1,
            ci_timeout=1800,
        )

        self.safety_config = SafetyConfig(
            human_approval_required=["merge_to_main"],
            rollback_on_test_failure=True,
        )

        self.merger = PRMerger(
            git_ops=self.git_ops,
            github_client=self.github_client,
            logger=self.logger,
            pr_config=self.pr_config,
            safety_config=self.safety_config,
        )

    def test_initialization(self):
        """Test merger initialization."""
        self.assertEqual(self.merger.total_merges, 0)
        self.assertEqual(self.merger.failed_merges, 0)
        self.assertEqual(self.merger.validation_failures, 0)
        self.assertEqual(self.merger.pr_config.merge_strategy, "squash")

    def test_validate_merge_preconditions_all_pass(self):
        """Test validation when all preconditions pass."""
        # Mock PR object
        mock_pr = Mock()
        mock_pr.mergeable_state = "clean"

        # Mock review
        mock_review = Mock()
        mock_review.state = "APPROVED"
        mock_pr.get_reviews.return_value = [mock_review]

        # Mock checks
        self.github_client.get_pr_checks.return_value = {"overall": "passed"}

        validation = self.merger._validate_merge_preconditions(123, mock_pr)

        self.assertTrue(validation.checks_passed)
        self.assertTrue(validation.reviews_approved)
        self.assertTrue(validation.required_reviews_met)
        self.assertTrue(validation.no_conflicts)
        self.assertTrue(validation.branch_up_to_date)
        self.assertTrue(validation.all_valid)
        self.assertEqual(len(validation.errors), 0)

    def test_validate_merge_preconditions_checks_failed(self):
        """Test validation when CI checks fail."""
        mock_pr = Mock()
        mock_pr.mergeable_state = "clean"
        mock_review = Mock()
        mock_review.state = "APPROVED"
        mock_pr.get_reviews.return_value = [mock_review]

        # Checks failed
        self.github_client.get_pr_checks.return_value = {"overall": "failed"}

        validation = self.merger._validate_merge_preconditions(123, mock_pr)

        self.assertFalse(validation.checks_passed)
        self.assertFalse(validation.all_valid)
        self.assertIn("CI checks not passed", validation.errors[0])

    def test_validate_merge_preconditions_no_reviews(self):
        """Test validation when no reviews are present."""
        mock_pr = Mock()
        mock_pr.mergeable_state = "clean"
        mock_pr.get_reviews.return_value = []  # No reviews

        self.github_client.get_pr_checks.return_value = {"overall": "passed"}

        validation = self.merger._validate_merge_preconditions(123, mock_pr)

        self.assertFalse(validation.reviews_approved)
        self.assertFalse(validation.required_reviews_met)
        self.assertFalse(validation.all_valid)
        self.assertIn("Required reviews not met", validation.errors[0])

    def test_validate_merge_preconditions_merge_conflicts(self):
        """Test validation when there are merge conflicts."""
        mock_pr = Mock()
        mock_pr.mergeable_state = "dirty"  # Indicates conflicts
        mock_review = Mock()
        mock_review.state = "APPROVED"
        mock_pr.get_reviews.return_value = [mock_review]

        self.github_client.get_pr_checks.return_value = {"overall": "passed"}

        validation = self.merger._validate_merge_preconditions(123, mock_pr)

        self.assertFalse(validation.no_conflicts)
        self.assertFalse(validation.all_valid)
        self.assertIn("merge conflicts", validation.errors[0])

    def test_validate_merge_preconditions_branch_not_up_to_date(self):
        """Test validation when branch is not up to date."""
        mock_pr = Mock()
        mock_pr.mergeable_state = "blocked"
        mock_review = Mock()
        mock_review.state = "APPROVED"
        mock_pr.get_reviews.return_value = [mock_review]

        self.github_client.get_pr_checks.return_value = {"overall": "passed"}

        validation = self.merger._validate_merge_preconditions(123, mock_pr)

        self.assertFalse(validation.branch_up_to_date)
        self.assertFalse(validation.all_valid)
        self.assertIn("not up to date", validation.errors[0])

    def test_create_rollback_tag_success(self):
        """Test successful rollback tag creation."""
        mock_pr = Mock()
        mock_pr.number = 123

        self.git_ops.run_command.return_value = ""

        tag = self.merger._create_rollback_tag(123, mock_pr)

        self.assertEqual(tag, "pre-merge-123")
        self.assertEqual(self.git_ops.run_command.call_count, 2)

        # Verify tag command
        calls = self.git_ops.run_command.call_args_list
        self.assertIn("git tag", calls[0][0][0])
        self.assertIn("pre-merge-123", calls[0][0][0])

        # Verify push command
        self.assertIn("git push", calls[1][0][0])
        self.assertIn("pre-merge-123", calls[1][0][0])

    def test_create_rollback_tag_failure(self):
        """Test rollback tag creation failure."""
        mock_pr = Mock()
        mock_pr.number = 123

        self.git_ops.run_command.side_effect = Exception("Git error")

        tag = self.merger._create_rollback_tag(123, mock_pr)

        # Should return tag name even if creation failed
        self.assertEqual(tag, "pre-merge-123 (creation failed)")

    def test_execute_merge_success(self):
        """Test successful merge execution."""
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.merge_commit_sha = "abc1234"

        # Mock merge success
        self.github_client.merge_pull_request.return_value = True
        self.github_client.get_pull_request.return_value = mock_pr

        commit_sha = self.merger._execute_merge(123, mock_pr)

        self.assertEqual(commit_sha, "abc1234")
        self.github_client.merge_pull_request.assert_called_once_with(
            pr_number=123,
            merge_method="squash",
        )

    def test_execute_merge_failure(self):
        """Test merge execution failure."""
        mock_pr = Mock()
        mock_pr.number = 123

        # Mock merge failure
        self.github_client.merge_pull_request.return_value = False

        with self.assertRaises(MergeValidationError):
            self.merger._execute_merge(123, mock_pr)

    def test_close_linked_issues(self):
        """Test closing linked issues."""
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.body = """
        ## Summary
        This PR implements feature X.

        Closes #45
        Fixes #67
        Resolves #89
        """

        linked_issues = self.merger._close_linked_issues(123, mock_pr)

        # Should find all three linked issues
        self.assertEqual(len(linked_issues), 3)
        self.assertIn(45, linked_issues)
        self.assertIn(67, linked_issues)
        self.assertIn(89, linked_issues)

    def test_close_linked_issues_no_links(self):
        """Test when PR has no linked issues."""
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.body = "This PR has no linked issues."

        linked_issues = self.merger._close_linked_issues(123, mock_pr)

        self.assertEqual(len(linked_issues), 0)

    def test_close_linked_issues_duplicates(self):
        """Test handling duplicate issue references."""
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.body = """
        Closes #45
        Fixes #45
        Also closes #45
        """

        linked_issues = self.merger._close_linked_issues(123, mock_pr)

        # Should only include issue once
        self.assertEqual(len(linked_issues), 1)
        self.assertEqual(linked_issues[0], 45)

    def test_add_closing_comment(self):
        """Test adding closing comment to PR."""
        mock_pr = Mock()
        mock_pr.number = 123

        self.merger._add_closing_comment(123, mock_pr)

        self.github_client.create_comment.assert_called_once()
        call_args = self.github_client.create_comment.call_args
        self.assertEqual(call_args[0][0], 123)
        self.assertIn("PR Merged Successfully", call_args[0][1])
        self.assertIn("squash", call_args[0][1])

    def test_merge_pull_request_success(self):
        """Test complete successful merge flow."""
        # Mock PR
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.mergeable_state = "clean"
        mock_pr.merge_commit_sha = "abc1234"
        mock_pr.body = "Closes #45"

        # Mock review
        mock_review = Mock()
        mock_review.state = "APPROVED"
        mock_pr.get_reviews.return_value = [mock_review]

        self.github_client.get_pull_request.return_value = mock_pr
        self.github_client.get_pr_checks.return_value = {"overall": "passed"}
        self.github_client.merge_pull_request.return_value = True
        self.git_ops.run_command.return_value = ""

        result = self.merger.merge_pull_request(123, require_approval=False)

        self.assertTrue(result.success)
        self.assertEqual(result.pr_number, 123)
        self.assertEqual(result.merge_commit_sha, "abc1234")
        self.assertEqual(result.rollback_tag, "pre-merge-123")
        self.assertIn(45, result.linked_issues_closed)
        self.assertIsNone(result.error)
        self.assertEqual(self.merger.total_merges, 1)

    def test_merge_pull_request_validation_failure(self):
        """Test merge with validation failure."""
        # Mock PR with failed checks
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.mergeable_state = "clean"
        mock_pr.get_reviews.return_value = []

        self.github_client.get_pull_request.return_value = mock_pr
        self.github_client.get_pr_checks.return_value = {"overall": "failed"}

        result = self.merger.merge_pull_request(123, require_approval=False)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("Validation failed", result.error)
        self.assertEqual(self.merger.validation_failures, 1)
        self.assertEqual(self.merger.total_merges, 0)

    def test_merge_pull_request_with_human_approval_required(self):
        """Test merge requiring human approval."""
        # Mock PR
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.mergeable_state = "clean"
        mock_review = Mock()
        mock_review.state = "APPROVED"
        mock_pr.get_reviews.return_value = [mock_review]

        self.github_client.get_pull_request.return_value = mock_pr
        self.github_client.get_pr_checks.return_value = {"overall": "passed"}

        # Test with auto_merge disabled (require human approval)
        self.merger.pr_config.auto_merge = False

        result = self.merger.merge_pull_request(123, require_approval=True)

        # Should fail because auto_merge is False
        self.assertFalse(result.success)
        self.assertIn("approval denied", result.error.lower())

    def test_merge_pull_request_with_auto_approval(self):
        """Test merge with auto approval enabled."""
        # Mock PR
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.mergeable_state = "clean"
        mock_pr.merge_commit_sha = "abc1234"
        mock_pr.body = ""
        mock_review = Mock()
        mock_review.state = "APPROVED"
        mock_pr.get_reviews.return_value = [mock_review]

        self.github_client.get_pull_request.return_value = mock_pr
        self.github_client.get_pr_checks.return_value = {"overall": "passed"}
        self.github_client.merge_pull_request.return_value = True
        self.git_ops.run_command.return_value = ""

        # auto_merge is True by default
        result = self.merger.merge_pull_request(123, require_approval=True)

        self.assertTrue(result.success)

    def test_merge_pull_request_exception_handling(self):
        """Test exception handling during merge."""
        self.github_client.get_pull_request.side_effect = Exception("API error")

        result = self.merger.merge_pull_request(123, require_approval=False)

        self.assertFalse(result.success)
        self.assertIn("API error", result.error)
        self.assertEqual(self.merger.failed_merges, 1)

    def test_get_statistics(self):
        """Test statistics retrieval."""
        self.merger.total_merges = 5
        self.merger.failed_merges = 1
        self.merger.validation_failures = 2

        stats = self.merger.get_statistics()

        self.assertEqual(stats["total_merges"], 5)
        self.assertEqual(stats["failed_merges"], 1)
        self.assertEqual(stats["validation_failures"], 2)

    def test_reset_statistics(self):
        """Test statistics reset."""
        self.merger.total_merges = 5
        self.merger.failed_merges = 1
        self.merger.validation_failures = 2

        self.merger.reset_statistics()

        self.assertEqual(self.merger.total_merges, 0)
        self.assertEqual(self.merger.failed_merges, 0)
        self.assertEqual(self.merger.validation_failures, 0)

    def test_merge_validation_dataclass(self):
        """Test MergeValidation dataclass."""
        validation = MergeValidation(
            checks_passed=True,
            reviews_approved=True,
            no_conflicts=True,
            branch_up_to_date=True,
            required_reviews_met=True,
            all_valid=True,
        )

        result_dict = validation.to_dict()
        self.assertTrue(result_dict["checks_passed"])
        self.assertTrue(result_dict["all_valid"])
        self.assertEqual(len(result_dict["errors"]), 0)

    def test_merge_result_dataclass(self):
        """Test MergeResult dataclass."""
        validation = MergeValidation(all_valid=True)
        result = MergeResult(
            pr_number=123,
            success=True,
            merge_commit_sha="abc1234",
            rollback_tag="pre-merge-123",
            validation=validation,
            linked_issues_closed=[45, 67],
        )

        result_dict = result.to_dict()
        self.assertEqual(result_dict["pr_number"], 123)
        self.assertTrue(result_dict["success"])
        self.assertEqual(result_dict["merge_commit_sha"], "abc1234")
        self.assertEqual(result_dict["rollback_tag"], "pre-merge-123")
        self.assertIsNotNone(result_dict["validation"])
        self.assertEqual(len(result_dict["linked_issues_closed"]), 2)


if __name__ == "__main__":
    unittest.main()
