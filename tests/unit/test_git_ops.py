"""Unit tests for GitOps."""

import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

from src.core.logger import AuditLogger
from src.integrations.git_ops import (
    CommitInfo,
    GitBranchError,
    GitCommitError,
    GitOps,
    GitOpsError,
    GitStatus,
)


class TestGitOps(unittest.TestCase):
    """Test cases for GitOps."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.repo_path = "/fake/repo"

        # Mock Path.exists to simulate git repository
        with patch("src.integrations.git_ops.Path") as mock_path:
            mock_path.return_value.resolve.return_value = Path(self.repo_path)
            mock_path.return_value.__truediv__.return_value.exists.return_value = True

            # Create GitOps with mocked repository check
            with patch.object(Path, "exists", return_value=True):
                self.git_ops = GitOps(
                    repo_path=self.repo_path,
                    logger=self.logger,
                    base_branch="main",
                )

    @patch("src.integrations.git_ops.subprocess.run")
    def test_get_status(self, mock_run):
        """Test getting git status."""
        # Mock git command outputs
        mock_run.side_effect = [
            MagicMock(stdout="feature-branch\n"),  # current branch
            MagicMock(stdout="file1.py\nfile2.py\n"),  # staged files
            MagicMock(stdout="file3.py\n"),  # unstaged files
            MagicMock(stdout="file4.py\n"),  # untracked files
        ]

        status = self.git_ops.get_status()

        self.assertEqual(status.current_branch, "feature-branch")
        self.assertTrue(status.has_uncommitted_changes)
        self.assertEqual(status.staged_files, ["file1.py", "file2.py"])
        self.assertEqual(status.unstaged_files, ["file3.py"])
        self.assertEqual(status.untracked_files, ["file4.py"])

    @patch("src.integrations.git_ops.subprocess.run")
    def test_get_status_clean_repo(self, mock_run):
        """Test git status for clean repository."""
        mock_run.side_effect = [
            MagicMock(stdout="main\n"),
            MagicMock(stdout=""),  # no staged
            MagicMock(stdout=""),  # no unstaged
            MagicMock(stdout=""),  # no untracked
        ]

        status = self.git_ops.get_status()

        self.assertEqual(status.current_branch, "main")
        self.assertFalse(status.has_uncommitted_changes)
        self.assertEqual(status.staged_files, [])

    @patch("src.integrations.git_ops.subprocess.run")
    def test_create_branch(self, mock_run):
        """Test creating a new branch."""
        mock_run.return_value = MagicMock(stdout="")

        branch_name = self.git_ops.create_branch("feature-123")

        self.assertEqual(branch_name, "feature-123")

        # Verify git commands called
        calls = mock_run.call_args_list
        self.assertEqual(len(calls), 3)
        # checkout main, pull, checkout -b feature
        self.assertIn("checkout", calls[0][0][0])
        self.assertIn("pull", calls[1][0][0])
        self.assertIn("checkout", calls[2][0][0])
        self.assertIn("-b", calls[2][0][0])

    @patch("src.integrations.git_ops.subprocess.run")
    def test_create_branch_failure(self, mock_run):
        """Test branch creation failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "checkout", "-b", "feature"],
            stderr="Branch already exists",
        )

        with self.assertRaises(GitBranchError):
            self.git_ops.create_branch("feature-123")

    @patch("src.integrations.git_ops.subprocess.run")
    def test_switch_branch(self, mock_run):
        """Test switching branches."""
        mock_run.return_value = MagicMock(stdout="")

        self.git_ops.switch_branch("develop")

        mock_run.assert_called_once()
        self.assertIn("checkout", mock_run.call_args[0][0])
        self.assertIn("develop", mock_run.call_args[0][0])

    @patch("src.integrations.git_ops.subprocess.run")
    def test_stage_files(self, mock_run):
        """Test staging files."""
        mock_run.return_value = MagicMock(stdout="")

        files = ["file1.py", "file2.py", "file3.py"]
        self.git_ops.stage_files(files)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("add", cmd)
        for file in files:
            self.assertIn(file, cmd)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_stage_files_empty_list(self, mock_run):
        """Test staging empty file list."""
        self.git_ops.stage_files([])

        mock_run.assert_not_called()

    @patch("src.integrations.git_ops.subprocess.run")
    def test_commit(self, mock_run):
        """Test creating a commit."""
        # Mock git commands for commit and get_last_commit
        # Note: commit() calls stage_files() first if file_paths provided
        mock_run.side_effect = [
            MagicMock(stdout=""),  # git add (from stage_files)
            MagicMock(stdout=""),  # git commit
            MagicMock(stdout="abc123\n"),  # git rev-parse HEAD
            MagicMock(stdout="Test commit message\n"),  # git log message
            MagicMock(stdout="John Doe <john@example.com>\n"),  # git log author
            MagicMock(stdout="2025-11-08T10:00:00-08:00\n"),  # git log timestamp
            MagicMock(stdout="file1.py\nfile2.py\n"),  # git diff-tree
        ]

        commit_info = self.git_ops.commit(
            message="Test commit",
            file_paths=["file1.py"],
            add_signature=True,
        )

        self.assertIsNotNone(commit_info)
        self.assertEqual(commit_info.commit_hash, "abc123")
        self.assertIn("Test commit", commit_info.message)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_commit_with_signature(self, mock_run):
        """Test commit includes orchestrator signature."""
        # Capture the actual call to verify signature
        actual_calls = []

        def capture_call(*args, **kwargs):
            result = MagicMock(stdout="")
            # Capture commit command
            if args and args[0] and "commit" in args[0]:
                actual_calls.append(args[0])
            return result

        mock_run.side_effect = [
            MagicMock(stdout=""),  # git commit
            MagicMock(stdout="abc123\n"),  # get_last_commit calls
            MagicMock(stdout="Test message\n"),
            MagicMock(stdout="Author\n"),
            MagicMock(stdout="2025-11-08T10:00:00-08:00\n"),
            MagicMock(stdout="file.py\n"),
        ]

        self.git_ops.commit(
            message="Test commit",
            add_signature=True,
        )

        # Check that commit was called with signature
        # Find the commit call
        commit_calls = [
            call
            for call in mock_run.call_args_list
            if call[0] and "commit" in str(call[0][0])
        ]
        self.assertGreater(len(commit_calls), 0)

        # Check the command arguments (cmd, cwd=..., capture_output=True, text=True, check=True)
        commit_cmd = commit_calls[0][0][0]  # First positional arg is the command list
        # commit_cmd is like ['git', 'commit', '-m', 'message with signature']
        commit_message = commit_cmd[3] if len(commit_cmd) > 3 else ""
        self.assertIn("Self-Reflexive Orchestrator", commit_message)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_commit_failure(self, mock_run):
        """Test commit failure handling."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["git", "commit"], stderr="Nothing to commit"
        )

        with self.assertRaises(GitCommitError):
            self.git_ops.commit(message="Test")

    @patch("src.integrations.git_ops.subprocess.run")
    def test_get_last_commit(self, mock_run):
        """Test getting last commit info."""
        mock_run.side_effect = [
            MagicMock(stdout="abc123def456\n"),  # hash
            MagicMock(stdout="Commit message here\n"),  # message
            MagicMock(stdout="Jane Doe <jane@example.com>\n"),  # author
            MagicMock(stdout="2025-11-08T12:34:56-08:00\n"),  # timestamp
            MagicMock(stdout="src/file1.py\nsrc/file2.py\n"),  # files
        ]

        commit_info = self.git_ops.get_last_commit()

        self.assertEqual(commit_info.commit_hash, "abc123def456")
        self.assertEqual(commit_info.message, "Commit message here")
        self.assertEqual(commit_info.author, "Jane Doe <jane@example.com>")
        self.assertEqual(len(commit_info.files_changed), 2)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_push_branch(self, mock_run):
        """Test pushing branch to remote."""
        mock_run.return_value = MagicMock(stdout="")

        self.git_ops.push_branch(set_upstream=True)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("push", cmd)
        self.assertIn("-u", cmd)
        self.assertIn("origin", cmd)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_push_branch_without_upstream(self, mock_run):
        """Test pushing branch without setting upstream."""
        mock_run.return_value = MagicMock(stdout="")

        self.git_ops.push_branch(set_upstream=False)

        cmd = mock_run.call_args[0][0]
        self.assertNotIn("-u", cmd)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_has_uncommitted_changes_true(self, mock_run):
        """Test detecting uncommitted changes."""
        mock_run.side_effect = [
            MagicMock(stdout="main\n"),
            MagicMock(stdout="file.py\n"),  # staged
            MagicMock(stdout=""),
            MagicMock(stdout=""),
        ]

        has_changes = self.git_ops.has_uncommitted_changes()

        self.assertTrue(has_changes)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_has_uncommitted_changes_false(self, mock_run):
        """Test clean repository."""
        mock_run.side_effect = [
            MagicMock(stdout="main\n"),
            MagicMock(stdout=""),
            MagicMock(stdout=""),
            MagicMock(stdout=""),
        ]

        has_changes = self.git_ops.has_uncommitted_changes()

        self.assertFalse(has_changes)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_get_current_branch(self, mock_run):
        """Test getting current branch name."""
        mock_run.side_effect = [
            MagicMock(stdout="feature-xyz\n"),
            MagicMock(stdout=""),
            MagicMock(stdout=""),
            MagicMock(stdout=""),
        ]

        branch = self.git_ops.get_current_branch()

        self.assertEqual(branch, "feature-xyz")

    @patch("src.integrations.git_ops.subprocess.run")
    def test_branch_exists_true(self, mock_run):
        """Test checking if branch exists."""
        mock_run.return_value = MagicMock(stdout="")

        exists = self.git_ops.branch_exists("feature-123")

        self.assertTrue(exists)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_branch_exists_false(self, mock_run):
        """Test checking non-existent branch."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["git", "rev-parse"], stderr="Branch not found"
        )

        exists = self.git_ops.branch_exists("nonexistent")

        self.assertFalse(exists)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_delete_branch(self, mock_run):
        """Test deleting a branch."""
        mock_run.return_value = MagicMock(stdout="")

        self.git_ops.delete_branch("feature-old")

        cmd = mock_run.call_args[0][0]
        self.assertIn("branch", cmd)
        self.assertIn("-d", cmd)
        self.assertIn("feature-old", cmd)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_delete_branch_force(self, mock_run):
        """Test force deleting a branch."""
        mock_run.return_value = MagicMock(stdout="")

        self.git_ops.delete_branch("feature-old", force=True)

        cmd = mock_run.call_args[0][0]
        self.assertIn("-D", cmd)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_get_diff(self, mock_run):
        """Test getting git diff."""
        mock_run.return_value = MagicMock(stdout="diff content here")

        diff = self.git_ops.get_diff()

        self.assertEqual(diff, "diff content here")
        cmd = mock_run.call_args[0][0]
        self.assertIn("diff", cmd)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_get_diff_staged(self, mock_run):
        """Test getting staged diff."""
        mock_run.return_value = MagicMock(stdout="staged diff")

        diff = self.git_ops.get_diff(staged=True)

        cmd = mock_run.call_args[0][0]
        self.assertIn("--cached", cmd)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_get_diff_specific_file(self, mock_run):
        """Test getting diff for specific file."""
        mock_run.return_value = MagicMock(stdout="file diff")

        diff = self.git_ops.get_diff(file_path="src/main.py")

        cmd = mock_run.call_args[0][0]
        self.assertIn("src/main.py", cmd)

    @patch("src.integrations.git_ops.subprocess.run")
    def test_reset_hard(self, mock_run):
        """Test hard reset."""
        mock_run.return_value = MagicMock(stdout="")

        self.git_ops.reset_hard("HEAD~1")

        cmd = mock_run.call_args[0][0]
        self.assertIn("reset", cmd)
        self.assertIn("--hard", cmd)
        self.assertIn("HEAD~1", cmd)

    def test_generate_commit_message(self):
        """Test commit message generation."""
        message = self.git_ops.generate_commit_message(
            issue_number=42,
            step_description="Create new analyzer class for issue processing",
            files_changed=["src/analyzers/new.py", "tests/test_new.py"],
        )

        self.assertIn("Create new analyzer class", message)
        self.assertIn("#42", message)
        self.assertIn("src/analyzers/new.py", message)

    def test_generate_commit_message_long_file_list(self):
        """Test commit message with many files."""
        files = [f"file{i}.py" for i in range(10)]

        message = self.git_ops.generate_commit_message(
            issue_number=100,
            step_description="Update multiple files",
            files_changed=files,
        )

        self.assertIn("#100", message)
        # Should truncate long file list
        self.assertIn("... and", message)

    def test_determine_scope(self):
        """Test scope determination from file paths."""
        # Analyzer scope
        scope = self.git_ops._determine_scope(["src/analyzers/test.py"])
        self.assertEqual(scope, "analyzers")

        # Cycles scope
        scope = self.git_ops._determine_scope(["src/cycles/executor.py"])
        self.assertEqual(scope, "cycles")

        # Tests scope
        scope = self.git_ops._determine_scope(["tests/unit/test_git.py"])
        self.assertEqual(scope, "tests")

        # No clear scope
        scope = self.git_ops._determine_scope(["random/file.py"])
        self.assertIsNone(scope)

    def test_git_status_to_dict(self):
        """Test GitStatus to_dict conversion."""
        status = GitStatus(
            current_branch="main",
            has_uncommitted_changes=True,
            staged_files=["file1.py"],
            unstaged_files=["file2.py"],
            untracked_files=["file3.py"],
        )

        status_dict = status.to_dict()

        self.assertEqual(status_dict["current_branch"], "main")
        self.assertTrue(status_dict["has_uncommitted_changes"])
        self.assertEqual(len(status_dict["staged_files"]), 1)

    def test_commit_info_to_dict(self):
        """Test CommitInfo to_dict conversion."""
        commit = CommitInfo(
            commit_hash="abc123",
            message="Test commit",
            author="Test Author",
            timestamp=datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc),
            files_changed=["file1.py", "file2.py"],
        )

        commit_dict = commit.to_dict()

        self.assertEqual(commit_dict["commit_hash"], "abc123")
        self.assertEqual(commit_dict["message"], "Test commit")
        self.assertIn("2025-11-08", commit_dict["timestamp"])
        self.assertEqual(len(commit_dict["files_changed"]), 2)


if __name__ == "__main__":
    unittest.main()
