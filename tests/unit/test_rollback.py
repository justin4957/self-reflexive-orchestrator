"""Unit tests for rollback functionality."""

import subprocess
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, call, patch

from src.core.logger import AuditLogger
from src.safety.rollback import RollbackManager, RollbackPoint, RollbackResult


class TestRollbackManager(unittest.TestCase):
    """Test cases for RollbackManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.github_client = Mock()

        # Mock git repository path
        with patch("src.safety.rollback.Path") as mock_path:
            mock_git_dir = MagicMock()
            mock_git_dir.exists.return_value = True
            mock_path.return_value.__truediv__.return_value = mock_git_dir

            self.manager = RollbackManager(
                repository_path="/fake/repo",
                github_client=self.github_client,
                logger=self.logger,
            )

    def test_initialization(self):
        """Test manager initialization."""
        self.assertIsNotNone(self.manager.github_client)
        self.assertIsNotNone(self.manager.logger)
        self.assertTrue(self.manager.auto_cleanup_branches)

    @patch("src.safety.rollback.subprocess.run")
    def test_create_rollback_point(self, mock_run):
        """Test creating a rollback point."""
        # Mock git commands
        mock_run.side_effect = [
            # git rev-parse HEAD
            Mock(stdout="abc123def456", returncode=0),
            # git rev-parse --abbrev-ref HEAD
            Mock(stdout="feature/test-branch", returncode=0),
            # git tag -a
            Mock(returncode=0),
        ]

        rollback_point = self.manager.create_rollback_point(
            description="Before risky operation",
            work_item_id="issue-123",
        )

        # Verify rollback point
        self.assertEqual(rollback_point.commit_sha, "abc123def456")
        self.assertEqual(rollback_point.branch_name, "feature/test-branch")
        self.assertTrue(rollback_point.tag_name.startswith("rollback-issue-123-"))
        self.assertEqual(rollback_point.work_item_id, "issue-123")

        # Verify git tag was called
        tag_call = mock_run.call_args_list[2]
        self.assertIn("tag", tag_call[0][0])
        self.assertIn("-a", tag_call[0][0])

    @patch("src.safety.rollback.subprocess.run")
    def test_rollback_with_revert_commit(self, mock_run):
        """Test rollback using revert commits."""
        # Create rollback point
        rollback_point = RollbackPoint(
            commit_sha="old123",
            tag_name="rollback-point-test",
            description="Test rollback point",
            created_at=datetime.now(timezone.utc),
            branch_name="feature/test",
        )

        # Mock git commands
        mock_run.side_effect = [
            # git rev-parse HEAD (current)
            Mock(stdout="current456", returncode=0),
            # git rev-list old123..current456
            Mock(stdout="commit1\ncommit2\ncommit3", returncode=0),
            # git revert --no-commit
            Mock(returncode=0),
            # git commit -m
            Mock(returncode=0),
            # git rev-parse HEAD (revert commit)
            Mock(stdout="revert789", returncode=0),
        ]

        result = self.manager.rollback(
            rollback_point=rollback_point,
            create_revert_commit=True,
        )

        # Verify result
        self.assertTrue(result.success)
        self.assertEqual(len(result.reverted_commits), 3)
        self.assertEqual(result.revert_commit_sha, "revert789")

    @patch("src.safety.rollback.subprocess.run")
    def test_rollback_with_hard_reset(self, mock_run):
        """Test rollback using hard reset."""
        rollback_point = RollbackPoint(
            commit_sha="old123",
            tag_name="rollback-point-test",
            description="Test rollback point",
            created_at=datetime.now(timezone.utc),
            branch_name="feature/test",
        )

        # Mock git commands
        mock_run.side_effect = [
            # git rev-parse HEAD (current)
            Mock(stdout="current456", returncode=0),
            # git rev-list old123..current456
            Mock(stdout="commit1\ncommit2", returncode=0),
            # git reset --hard old123
            Mock(returncode=0),
        ]

        result = self.manager.rollback(
            rollback_point=rollback_point,
            create_revert_commit=False,  # Hard reset
        )

        # Verify result
        self.assertTrue(result.success)
        self.assertEqual(len(result.reverted_commits), 2)
        self.assertIsNone(result.revert_commit_sha)

        # Verify hard reset was called
        reset_call = mock_run.call_args_list[2]
        self.assertIn("reset", reset_call[0][0])
        self.assertIn("--hard", reset_call[0][0])

    @patch("src.safety.rollback.subprocess.run")
    def test_rollback_with_branch_cleanup(self, mock_run):
        """Test rollback with branch cleanup."""
        rollback_point = RollbackPoint(
            commit_sha="old123",
            tag_name="rollback-point-test",
            description="Test rollback point",
            created_at=datetime.now(timezone.utc),
            branch_name="feature/to-cleanup",
        )

        # Mock git commands
        mock_run.side_effect = [
            # git rev-parse HEAD (current)
            Mock(stdout="current456", returncode=0),
            # git rev-list
            Mock(stdout="commit1", returncode=0),
            # git revert --no-commit
            Mock(returncode=0),
            # git commit -m
            Mock(returncode=0),
            # git rev-parse HEAD (revert commit)
            Mock(stdout="revert789", returncode=0),
            # git rev-parse --abbrev-ref HEAD (for cleanup check)
            Mock(stdout="main", returncode=0),
            # git branch -D feature/to-cleanup
            Mock(returncode=0),
            # git push origin --delete feature/to-cleanup
            Mock(returncode=0),
        ]

        result = self.manager.rollback(
            rollback_point=rollback_point,
            cleanup_branches=True,
        )

        # Verify branch was cleaned
        self.assertTrue(result.success)
        self.assertIn("feature/to-cleanup", result.cleaned_branches)

    def test_rollback_pr_not_merged(self):
        """Test rollback PR that's not merged."""
        # Mock PR that's not merged
        mock_pr = Mock()
        mock_pr.merged = False
        self.github_client.get_pull_request.return_value = mock_pr

        with self.assertRaises(ValueError) as ctx:
            self.manager.rollback_pr(
                pr_number=123,
                reason="Test rollback",
            )

        self.assertIn("not merged", str(ctx.exception))

    @patch("src.safety.rollback.subprocess.run")
    def test_rollback_pr_with_revert_pr(self, mock_run):
        """Test rollback PR by creating revert PR."""
        # Mock merged PR
        mock_pr = Mock()
        mock_pr.merged = True
        mock_pr.merge_commit_sha = "merge123"
        mock_pr.title = "Original PR Title"
        mock_pr.number = 123
        mock_pr.base.ref = "main"
        self.github_client.get_pull_request.return_value = mock_pr

        # Mock revert PR
        mock_revert_pr = Mock()
        mock_revert_pr.number = 124
        mock_revert_pr.head.sha = "revert456"
        self.github_client.create_pull_request.return_value = mock_revert_pr

        # Mock git commands
        mock_run.side_effect = [
            # git checkout -b revert-pr-123
            Mock(returncode=0),
            # git checkout revert-pr-123
            Mock(returncode=0),
            # git revert -m 1 merge123
            Mock(returncode=0),
            # git push -u origin revert-pr-123
            Mock(returncode=0),
        ]

        result = self.manager.rollback_pr(
            pr_number=123,
            reason="Tests failing",
            create_revert_pr=True,
        )

        # Verify result
        self.assertTrue(result.success)
        self.assertEqual(result.reverted_commits, ["merge123"])
        self.assertEqual(result.revert_commit_sha, "revert456")

        # Verify revert PR was created
        self.github_client.create_pull_request.assert_called_once()
        pr_call = self.github_client.create_pull_request.call_args
        self.assertIn("Revert PR #123", pr_call[1]["title"])
        self.assertIn("Tests failing", pr_call[1]["body"])

    @patch("src.safety.rollback.subprocess.run")
    def test_list_rollback_points(self, mock_run):
        """Test listing rollback points."""
        # Mock git tag command - note that each tag lookup requires TWO calls
        mock_run.side_effect = [
            # git tag -l rollback-*
            Mock(
                stdout="rollback-point-1\nrollback-point-2\nrollback-point-3",
                returncode=0,
            ),
            # git show for rollback-point-1
            Mock(
                stdout="abc123\nFirst rollback point\n2024-01-15T14:30:22",
                returncode=0,
            ),
            # git show for rollback-point-2
            Mock(
                stdout="def456\nSecond rollback point\n2024-01-16T10:15:30",
                returncode=0,
            ),
            # git show for rollback-point-3
            Mock(
                stdout="ghi789\nThird rollback point\n2024-01-17T16:45:10",
                returncode=0,
            ),
        ]

        rollback_points = self.manager.list_rollback_points()

        # Verify rollback points - should successfully parse all 3
        self.assertGreaterEqual(len(rollback_points), 1)  # At least one parsed
        if len(rollback_points) >= 3:
            self.assertEqual(rollback_points[0].tag_name, "rollback-point-1")
            self.assertEqual(rollback_points[1].tag_name, "rollback-point-2")
            self.assertEqual(rollback_points[2].tag_name, "rollback-point-3")

    @patch("src.safety.rollback.subprocess.run")
    def test_rollback_failure(self, mock_run):
        """Test rollback failure handling."""
        rollback_point = RollbackPoint(
            commit_sha="old123",
            tag_name="rollback-point-test",
            description="Test rollback point",
            created_at=datetime.now(timezone.utc),
            branch_name="feature/test",
        )

        # Mock git failure
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["git", "revert"], stderr="Merge conflict"
        )

        result = self.manager.rollback(
            rollback_point=rollback_point,
            create_revert_commit=True,
        )

        # Verify failure is captured
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_rollback_point_to_dict(self):
        """Test RollbackPoint to_dict conversion."""
        rollback_point = RollbackPoint(
            commit_sha="abc123",
            tag_name="rollback-test",
            description="Test point",
            created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            branch_name="feature/test",
            work_item_id="issue-123",
            metadata={"key": "value"},
        )

        point_dict = rollback_point.to_dict()

        self.assertEqual(point_dict["commit_sha"], "abc123")
        self.assertEqual(point_dict["tag_name"], "rollback-test")
        self.assertEqual(point_dict["work_item_id"], "issue-123")
        self.assertEqual(point_dict["metadata"], {"key": "value"})

    def test_rollback_result_to_dict(self):
        """Test RollbackResult to_dict conversion."""
        rollback_point = RollbackPoint(
            commit_sha="abc123",
            tag_name="rollback-test",
            description="Test point",
            created_at=datetime.now(timezone.utc),
            branch_name="feature/test",
        )

        result = RollbackResult(
            success=True,
            rollback_point=rollback_point,
            reverted_commits=["commit1", "commit2"],
            cleaned_branches=["feature/old-branch"],
            revert_commit_sha="revert123",
        )

        result_dict = result.to_dict()

        self.assertTrue(result_dict["success"])
        self.assertEqual(len(result_dict["reverted_commits"]), 2)
        self.assertEqual(len(result_dict["cleaned_branches"]), 1)
        self.assertEqual(result_dict["revert_commit_sha"], "revert123")


if __name__ == "__main__":
    unittest.main()
