"""Unit tests for CodeExecutor."""

import unittest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from src.cycles.code_executor import (
    CodeExecutor,
    ExecutionStatus,
    CodeChange,
    StepExecution,
    ExecutionResult,
)
from src.analyzers.implementation_planner import (
    ImplementationPlan,
    ImplementationStep,
    TestStrategy,
    PlanConfidence,
)
from src.integrations.git_ops import GitOps, CommitInfo
from src.integrations.multi_agent_coder_client import MultiAgentCoderClient, MultiAgentResponse
from src.core.logger import AuditLogger
from src.core.state import WorkItem, OrchestratorState
from datetime import datetime, timezone


class TestCodeExecutor(unittest.TestCase):
    """Test cases for CodeExecutor."""

    def setUp(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)
        self.logger = Mock(spec=AuditLogger)
        self.repo_path = "/fake/repo"

        self.executor = CodeExecutor(
            git_ops=self.git_ops,
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
            repo_path=self.repo_path,
            enable_validation=True,
        )

    def test_initialization(self):
        """Test executor initialization."""
        self.assertEqual(self.executor.total_executions, 0)
        self.assertEqual(self.executor.successful_executions, 0)
        self.assertEqual(self.executor.failed_executions, 0)
        self.assertTrue(self.executor.enable_validation)

    def test_code_change_to_dict(self):
        """Test CodeChange to_dict conversion."""
        change = CodeChange(
            file_path="src/test.py",
            change_type="create",
            content="print('hello')",
            description="Create test file",
        )

        change_dict = change.to_dict()

        self.assertEqual(change_dict["file_path"], "src/test.py")
        self.assertEqual(change_dict["change_type"], "create")
        self.assertEqual(change_dict["content_length"], 14)  # "print('hello')" is 14 chars

    def test_execution_status_enum(self):
        """Test ExecutionStatus enum values."""
        self.assertEqual(ExecutionStatus.PENDING.value, "pending")
        self.assertEqual(ExecutionStatus.IN_PROGRESS.value, "in_progress")
        self.assertEqual(ExecutionStatus.COMPLETED.value, "completed")
        self.assertEqual(ExecutionStatus.FAILED.value, "failed")

    def test_generate_commit_message(self):
        """Test commit message generation delegation."""
        step = ImplementationStep(
            step_number=1,
            description="Create analyzer class",
            files_affected=["src/analyzer.py"],
            estimated_complexity=5,
        )

        plan = Mock(issue_number=42)
        changes = [CodeChange("src/analyzer.py", "create", "content")]

        self.git_ops.generate_commit_message.return_value = "Test message"

        message = self.executor._generate_commit_message(step, plan, changes)

        self.git_ops.generate_commit_message.assert_called_once_with(
            issue_number=42,
            step_description="Create analyzer class",
            files_changed=["src/analyzer.py"],
        )
        self.assertEqual(message, "Test message")

    @patch('builtins.open', create=True)
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.mkdir')
    def test_apply_changes_create_file(self, mock_mkdir, mock_exists, mock_open):
        """Test applying code changes for new file."""
        mock_exists.return_value = False

        changes = [
            CodeChange(
                file_path="src/new.py",
                change_type="create",
                content="# New file\npass\n",
                description="Create new file",
            )
        ]

        self.executor._apply_changes(changes)

        # Verify file was written
        mock_open.assert_called_once()
        handle = mock_open.return_value.__enter__.return_value
        handle.write.assert_called_once_with("# New file\npass\n")

    @patch('builtins.open', create=True)
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.exists')
    def test_apply_changes_modify_file(self, mock_exists, mock_mkdir, mock_open):
        """Test applying code changes for existing file."""
        mock_exists.return_value = True

        changes = [
            CodeChange(
                file_path="src/existing.py",
                change_type="modify",
                content="# Modified content\n",
                description="Modify existing file",
            )
        ]

        self.executor._apply_changes(changes)

        mock_open.assert_called_once()

    def test_validate_changes(self):
        """Test code validation with multi-agent-coder."""
        step = ImplementationStep(
            step_number=1,
            description="Add validation logic",
            files_affected=[],
            estimated_complexity=3,
        )

        changes = [
            CodeChange("src/validator.py", "create", "def validate(): pass")
        ]

        mock_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={"anthropic": "Code looks good"},
            strategy="all",
            total_tokens=100,
            total_cost=0.001,
            success=True,
        )

        self.multi_agent_client.review_code.return_value = mock_response

        response = self.executor._validate_changes(changes, step)

        self.assertTrue(response.success)
        self.multi_agent_client.review_code.assert_called_once()

    def test_validate_changes_failure(self):
        """Test validation when multi-agent fails."""
        step = ImplementationStep(1, "Test", [], 3)
        changes = [CodeChange("test.py", "create", "code")]

        self.multi_agent_client.review_code.side_effect = Exception("API error")

        response = self.executor._validate_changes(changes, step)

        self.assertFalse(response.success)
        self.assertIn("API error", response.error)

    def test_create_execution_branch_new(self):
        """Test creating new execution branch."""
        plan = Mock()
        plan.branch_name = "orchestrator/issue-42-test"

        self.git_ops.branch_exists.return_value = False
        self.git_ops.create_branch.return_value = "orchestrator/issue-42-test"

        branch = self.executor._create_execution_branch(plan)

        self.assertEqual(branch, "orchestrator/issue-42-test")
        self.git_ops.create_branch.assert_called_once_with("orchestrator/issue-42-test")

    def test_create_execution_branch_exists(self):
        """Test switching to existing branch."""
        plan = Mock()
        plan.branch_name = "orchestrator/issue-42-test"

        self.git_ops.branch_exists.return_value = True

        branch = self.executor._create_execution_branch(plan)

        self.assertEqual(branch, "orchestrator/issue-42-test")
        self.git_ops.switch_branch.assert_called_once_with("orchestrator/issue-42-test")

    def test_get_statistics(self):
        """Test statistics retrieval."""
        self.executor.total_executions = 10
        self.executor.successful_executions = 8
        self.executor.failed_executions = 2

        self.multi_agent_client.get_statistics.return_value = {
            "total_calls": 10,
            "total_cost": 0.50,
        }

        stats = self.executor.get_statistics()

        self.assertEqual(stats["total_executions"], 10)
        self.assertEqual(stats["successful_executions"], 8)
        self.assertEqual(stats["failed_executions"], 2)
        self.assertEqual(stats["success_rate"], 80.0)

    def test_reset_statistics(self):
        """Test statistics reset."""
        self.executor.total_executions = 5
        self.executor.successful_executions = 3
        self.executor.failed_executions = 2

        self.executor.reset_statistics()

        self.assertEqual(self.executor.total_executions, 0)
        self.assertEqual(self.executor.successful_executions, 0)
        self.assertEqual(self.executor.failed_executions, 0)
        self.multi_agent_client.reset_statistics.assert_called_once()

    def test_step_execution_to_dict(self):
        """Test StepExecution to_dict conversion."""
        step = ImplementationStep(1, "Test step", ["file.py"], 5)
        commit = CommitInfo(
            commit_hash="abc123",
            message="Test",
            author="Author",
            timestamp=datetime.now(timezone.utc),
            files_changed=["file.py"],
        )

        step_exec = StepExecution(
            step=step,
            status=ExecutionStatus.COMPLETED,
            changes_applied=[CodeChange("file.py", "create", "content")],
            commit_info=commit,
            attempts=1,
        )

        step_dict = step_exec.to_dict()

        self.assertEqual(step_dict["step_number"], 1)
        self.assertEqual(step_dict["status"], "completed")
        self.assertEqual(step_dict["commit_hash"], "abc123")
        self.assertEqual(step_dict["attempts"], 1)

    def test_execution_result_to_dict(self):
        """Test ExecutionResult to_dict conversion."""
        plan = Mock()
        plan.issue_number = 42

        result = ExecutionResult(
            plan=plan,
            step_executions=[],
            overall_status=ExecutionStatus.COMPLETED,
            branch_name="test-branch",
            commits_created=[],
            total_files_changed=5,
            errors=[],
        )

        result_dict = result.to_dict()

        self.assertEqual(result_dict["issue_number"], 42)
        self.assertEqual(result_dict["overall_status"], "completed")
        self.assertEqual(result_dict["branch_name"], "test-branch")
        self.assertEqual(result_dict["total_files_changed"], 5)


if __name__ == '__main__':
    unittest.main()
