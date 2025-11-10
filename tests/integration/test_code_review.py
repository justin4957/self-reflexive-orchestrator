"""Integration tests for code review workflow."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

from src.core.logger import AuditLogger
from src.core.state import WorkItem
from src.cycles.pr_cycle import CodeReviewer, CodeReviewResult
from src.integrations.git_ops import GitOps
from src.integrations.github_client import GitHubClient
from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    PRReviewResult,
    ReviewComment,
)


class TestCodeReviewIntegration(unittest.TestCase):
    """Integration tests for end-to-end code review workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.github_client = Mock(spec=GitHubClient)
        self.git_ops = Mock(spec=GitOps)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)

        self.reviewer = CodeReviewer(
            multi_agent_client=self.multi_agent_client,
            github_client=self.github_client,
            git_ops=self.git_ops,
            logger=self.logger,
            review_timeout=600,
        )

    def test_review_pull_request_approved(self):
        """Test successful PR review with approval."""
        # Setup mock PR
        mock_pr = MagicMock()
        mock_pr.body = "Add new authentication feature"
        mock_pr.diff_url = "https://github.com/test/repo/pull/123.diff"
        self.github_client.get_pull_request.return_value = mock_pr

        # Setup mock diff response
        mock_diff_response = MagicMock()
        mock_diff_response.text = (
            "diff --git a/src/auth.py b/src/auth.py\n+def login():\n+    pass"
        )
        mock_diff_response.raise_for_status = Mock()

        # Setup mock files
        mock_file = MagicMock()
        mock_file.filename = "src/auth.py"
        mock_pr.get_files.return_value = [mock_file]

        # Setup mock review result
        review_comments = [
            ReviewComment(
                message="Consider adding rate limiting",
                provider="anthropic",
                file="src/auth.py",
                line=10,
                severity="warning",
            )
        ]

        mock_review_result = PRReviewResult(
            pr_number=123,
            approved=True,
            reviewer="multi-agent-coder",
            comments=review_comments,
            summary="Good implementation overall",
            providers_reviewed=["anthropic", "deepseek"],
            approval_count=2,
            total_reviewers=2,
            total_tokens=8000,
            total_cost=0.08,
        )

        self.multi_agent_client.review_pull_request.return_value = mock_review_result

        # Mock PR comment creation
        mock_pr.create_issue_comment = Mock()

        # Execute review
        with patch("requests.get", return_value=mock_diff_response):
            result = self.reviewer.review_pull_request(
                pr_number=123,
                post_comment=True,
            )

        # Verify result
        self.assertTrue(result.success)
        self.assertEqual(result.pr_number, 123)
        self.assertTrue(result.review_result.approved)
        self.assertTrue(result.github_comment_posted)

        # Verify multi-agent-coder was called correctly
        self.multi_agent_client.review_pull_request.assert_called_once()
        call_kwargs = self.multi_agent_client.review_pull_request.call_args[1]
        self.assertEqual(call_kwargs["pr_number"], 123)
        self.assertIn("src/auth.py", call_kwargs["files_changed"])

        # Verify GitHub comment was posted
        mock_pr.create_issue_comment.assert_called_once()
        comment_text = mock_pr.create_issue_comment.call_args[0][0]
        self.assertIn("APPROVED", comment_text)
        self.assertIn("anthropic", comment_text)
        self.assertIn("deepseek", comment_text)

        # Verify audit log
        self.logger.audit.assert_called()

    def test_review_pull_request_changes_requested(self):
        """Test PR review with changes requested."""
        # Setup mocks
        mock_pr = MagicMock()
        mock_pr.body = "Update security module"
        mock_pr.diff_url = "https://github.com/test/repo/pull/456.diff"
        self.github_client.get_pull_request.return_value = mock_pr

        mock_diff_response = MagicMock()
        mock_diff_response.text = "diff --git a/src/security.py b/src/security.py"
        mock_diff_response.raise_for_status = Mock()

        mock_file = MagicMock()
        mock_file.filename = "src/security.py"
        mock_pr.get_files.return_value = [mock_file]

        # Setup review with issues
        review_comments = [
            ReviewComment(
                message="Critical: SQL injection vulnerability",
                provider="anthropic",
                file="src/security.py",
                line=25,
                severity="error",
            ),
            ReviewComment(
                message="Missing input validation",
                provider="deepseek",
                file="src/security.py",
                line=30,
                severity="warning",
            ),
        ]

        mock_review_result = PRReviewResult(
            pr_number=456,
            approved=False,
            reviewer="multi-agent-coder",
            comments=review_comments,
            summary="Security issues found",
            providers_reviewed=["anthropic", "deepseek"],
            approval_count=0,
            total_reviewers=2,
            total_tokens=6000,
            total_cost=0.06,
        )

        self.multi_agent_client.review_pull_request.return_value = mock_review_result
        mock_pr.create_issue_comment = Mock()

        # Execute review
        with patch("requests.get", return_value=mock_diff_response):
            result = self.reviewer.review_pull_request(
                pr_number=456,
                post_comment=True,
            )

        # Verify result
        self.assertTrue(result.success)
        self.assertFalse(result.review_result.approved)

        # Verify comment contains issues
        comment_text = mock_pr.create_issue_comment.call_args[0][0]
        self.assertIn("CHANGES REQUESTED", comment_text)
        self.assertIn("SQL injection", comment_text)
        self.assertIn("src/security.py:25", comment_text)

    def test_review_pull_request_with_work_item(self):
        """Test PR review with work item update."""
        # Setup mocks
        mock_pr = MagicMock()
        mock_pr.body = "Feature implementation"
        mock_pr.diff_url = "https://github.com/test/repo/pull/789.diff"
        self.github_client.get_pull_request.return_value = mock_pr

        mock_diff_response = MagicMock()
        mock_diff_response.text = "diff content"
        mock_diff_response.raise_for_status = Mock()

        mock_file = MagicMock()
        mock_file.filename = "src/feature.py"
        mock_pr.get_files.return_value = [mock_file]

        mock_review_result = PRReviewResult(
            pr_number=789,
            approved=True,
            reviewer="multi-agent-coder",
            comments=[],
            summary="Approved",
            providers_reviewed=["anthropic"],
            approval_count=1,
            total_reviewers=1,
            total_tokens=4000,
            total_cost=0.04,
        )

        self.multi_agent_client.review_pull_request.return_value = mock_review_result
        mock_pr.create_issue_comment = Mock()

        # Create work item
        work_item = WorkItem(
            item_type="issue",
            item_id="issue-123",
            state="in_progress",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            metadata={"issue_number": 123},
        )

        # Execute review with work item
        with patch("requests.get", return_value=mock_diff_response):
            result = self.reviewer.review_pull_request(
                pr_number=789,
                work_item=work_item,
                post_comment=True,
            )

        # Verify work item was updated
        self.assertTrue(result.work_item_updated)
        self.assertEqual(work_item.metadata["review_status"], "approved")
        self.assertEqual(work_item.metadata["review_providers"], ["anthropic"])
        self.assertEqual(work_item.metadata["review_approval_count"], 1)
        self.assertEqual(work_item.metadata["review_cost"], 0.04)

    def test_review_pull_request_error_handling(self):
        """Test error handling during PR review."""
        # Setup mock to raise exception
        self.github_client.get_pull_request.side_effect = Exception("API Error")

        # Execute review
        result = self.reviewer.review_pull_request(pr_number=999)

        # Verify error handling
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("API Error", result.error)

        # Verify statistics
        self.assertEqual(self.reviewer.failed_reviews, 1)

    def test_format_review_comment_with_all_severities(self):
        """Test review comment formatting with all severity levels."""
        comments = [
            ReviewComment(
                message="Critical security issue",
                provider="anthropic",
                file="src/auth.py",
                line=10,
                severity="error",
            ),
            ReviewComment(
                message="Performance warning",
                provider="deepseek",
                file="src/utils.py",
                line=20,
                severity="warning",
            ),
            ReviewComment(
                message="Consider refactoring",
                provider="openai",
                severity="info",
            ),
        ]

        review_result = PRReviewResult(
            pr_number=123,
            approved=False,
            reviewer="multi-agent-coder",
            comments=comments,
            summary="Mixed feedback",
            providers_reviewed=["anthropic", "deepseek", "openai"],
            approval_count=1,
            total_reviewers=3,
            total_tokens=7000,
            total_cost=0.07,
        )

        comment = self.reviewer._format_review_comment(review_result)

        # Verify structure
        self.assertIn("⚠️", comment)  # Changes requested emoji
        self.assertIn("CHANGES REQUESTED", comment)
        self.assertIn("1/3 providers approved", comment)

        # Verify severity sections
        self.assertIn("🔴 Issues", comment)
        self.assertIn("🟡 Warnings", comment)
        self.assertIn("💡 Suggestions", comment)

        # Verify file references
        self.assertIn("`src/auth.py:10`", comment)
        self.assertIn("`src/utils.py:20`", comment)

        # Verify cost information
        self.assertIn("$0.0700", comment)
        self.assertIn("7,000", comment)

    def test_get_statistics(self):
        """Test code review statistics tracking."""
        # Manually set statistics
        self.reviewer.total_reviews = 10
        self.reviewer.approved_reviews = 7
        self.reviewer.rejected_reviews = 2
        self.reviewer.failed_reviews = 1

        stats = self.reviewer.get_statistics()

        self.assertEqual(stats["total_reviews"], 10)
        self.assertEqual(stats["approved_reviews"], 7)
        self.assertEqual(stats["rejected_reviews"], 2)
        self.assertEqual(stats["failed_reviews"], 1)
        self.assertEqual(stats["approval_rate"], 70.0)

    def test_reset_statistics(self):
        """Test resetting code review statistics."""
        self.reviewer.total_reviews = 10
        self.reviewer.approved_reviews = 5
        self.reviewer.rejected_reviews = 3
        self.reviewer.failed_reviews = 2

        self.reviewer.reset_statistics()

        self.assertEqual(self.reviewer.total_reviews, 0)
        self.reviewer.approved_reviews = 0
        self.assertEqual(self.reviewer.rejected_reviews, 0)
        self.assertEqual(self.reviewer.failed_reviews, 0)


if __name__ == "__main__":
    unittest.main()
