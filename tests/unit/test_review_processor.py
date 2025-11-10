"""Unit tests for ReviewFeedbackProcessor."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from src.core.config import LLMConfig
from src.core.logger import AuditLogger
from src.cycles.review_processor import (FeedbackItem, ReviewFeedbackProcessor,
                                         ReviewProcessingResult)
from src.integrations.git_ops import GitOps
from src.integrations.multi_agent_coder_client import (PRReviewResult,
                                                       ReviewComment)


class TestReviewFeedbackProcessor(unittest.TestCase):
    """Test cases for ReviewFeedbackProcessor."""

    def setUp(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.logger = Mock(spec=AuditLogger)
        self.llm_config = LLMConfig(
            api_key="test-key", model="claude-sonnet-4-5-20250929"
        )

        self.processor = ReviewFeedbackProcessor(
            git_ops=self.git_ops,
            logger=self.logger,
            llm_config=self.llm_config,
            max_iterations=3,
            address_warnings=True,
            address_suggestions=False,
        )

    def test_initialization(self):
        """Test processor initialization."""
        self.assertEqual(self.processor.max_iterations, 3)
        self.assertTrue(self.processor.address_warnings)
        self.assertFalse(self.processor.address_suggestions)
        self.assertEqual(self.processor.total_feedback_processed, 0)

    def test_categorize_feedback_by_severity(self):
        """Test feedback categorization by severity."""
        comments = [
            ReviewComment(
                message="Critical security issue",
                provider="anthropic",
                severity="error",
            ),
            ReviewComment(
                message="Performance warning", provider="deepseek", severity="warning"
            ),
            ReviewComment(
                message="Consider refactoring", provider="openai", severity="info"
            ),
        ]

        items = self.processor._categorize_feedback(comments)

        self.assertEqual(len(items), 3)
        # Should be sorted by priority (blocking first)
        self.assertEqual(items[0].priority, 1)  # error
        self.assertEqual(items[1].priority, 2)  # warning
        self.assertEqual(items[2].priority, 3)  # info

    def test_filter_items_to_address_blocking_only(self):
        """Test filtering when only blocking issues should be addressed."""
        processor = ReviewFeedbackProcessor(
            git_ops=self.git_ops,
            logger=self.logger,
            llm_config=self.llm_config,
            address_warnings=False,
            address_suggestions=False,
        )

        feedback_items = [
            FeedbackItem(
                comment=ReviewComment(message="Error", provider="a", severity="error"),
                priority=1,
            ),
            FeedbackItem(
                comment=ReviewComment(
                    message="Warning", provider="b", severity="warning"
                ),
                priority=2,
            ),
            FeedbackItem(
                comment=ReviewComment(message="Info", provider="c", severity="info"),
                priority=3,
            ),
        ]

        filtered = processor._filter_items_to_address(feedback_items)

        # Should only include blocking (priority 1)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].priority, 1)

    def test_filter_items_to_address_with_warnings(self):
        """Test filtering when warnings should also be addressed."""
        feedback_items = [
            FeedbackItem(
                comment=ReviewComment(message="Error", provider="a", severity="error"),
                priority=1,
            ),
            FeedbackItem(
                comment=ReviewComment(
                    message="Warning", provider="b", severity="warning"
                ),
                priority=2,
            ),
            FeedbackItem(
                comment=ReviewComment(message="Info", provider="c", severity="info"),
                priority=3,
            ),
        ]

        filtered = self.processor._filter_items_to_address(feedback_items)

        # Should include blocking and warnings (not suggestions)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0].priority, 1)
        self.assertEqual(filtered[1].priority, 2)

    def test_process_feedback_no_items(self):
        """Test processing when there are no feedback items."""
        review_result = PRReviewResult(
            pr_number=123,
            approved=True,
            reviewer="multi-agent-coder",
            comments=[],
            summary="All good",
            providers_reviewed=["anthropic"],
            approval_count=1,
            total_reviewers=1,
        )

        result = self.processor.process_feedback(
            pr_number=123, review_result=review_result
        )

        self.assertTrue(result.success)
        self.assertEqual(result.total_feedback_items, 0)
        self.assertEqual(result.items_addressed, 0)
        self.assertFalse(result.changes_made)

    def test_process_feedback_max_iterations_exceeded(self):
        """Test processing when max iterations exceeded."""
        review_result = PRReviewResult(
            pr_number=123,
            approved=False,
            reviewer="multi-agent-coder",
            comments=[
                ReviewComment(
                    message="Still needs work",
                    provider="anthropic",
                    severity="error",
                )
            ],
            summary="Changes requested",
            providers_reviewed=["anthropic"],
            approval_count=0,
            total_reviewers=1,
        )

        result = self.processor.process_feedback(
            pr_number=123, review_result=review_result, iteration=4  # Exceeds max of 3
        )

        self.assertFalse(result.success)
        self.assertIn("Exceeded max review iterations", result.error)
        self.assertEqual(self.processor.escalations, 1)

    @patch.object(Path, "exists")
    def test_generate_and_apply_fix_with_file(self, mock_exists):
        """Test fix generation with file reference."""
        mock_exists.return_value = True

        item = FeedbackItem(
            comment=ReviewComment(
                message="Add type hints",
                provider="anthropic",
                file="src/foo.py",
                line=42,
                severity="warning",
            ),
            priority=2,
        )

        success = self.processor._generate_and_apply_fix(item, pr_number=123)

        self.assertTrue(success)
        self.assertTrue(item.fix_generated)
        self.assertIn("src/foo.py:42", item.fix_description)
        self.assertIn("Add type hints", item.fix_description)

    @patch.object(Path, "exists")
    def test_generate_and_apply_fix_file_not_found(self, mock_exists):
        """Test fix generation when file doesn't exist."""
        mock_exists.return_value = False

        item = FeedbackItem(
            comment=ReviewComment(
                message="Fix issue",
                provider="anthropic",
                file="nonexistent.py",
                line=10,
                severity="error",
            ),
            priority=1,
        )

        success = self.processor._generate_and_apply_fix(item, pr_number=123)

        self.assertFalse(success)
        self.assertIsNotNone(item.error)
        self.assertIn("File not found", item.error)

    def test_generate_and_apply_fix_general_feedback(self):
        """Test fix generation for general feedback without file."""
        item = FeedbackItem(
            comment=ReviewComment(
                message="Consider using dependency injection",
                provider="deepseek",
                severity="info",
            ),
            priority=3,
        )

        success = self.processor._generate_and_apply_fix(item, pr_number=123)

        self.assertTrue(success)
        self.assertTrue(item.fix_generated)
        self.assertIn("dependency injection", item.fix_description)

    def test_generate_fix_description(self):
        """Test fix description generation."""
        # Blocking issue
        item1 = FeedbackItem(
            comment=ReviewComment(
                message="SQL injection vulnerability",
                provider="anthropic",
                file="src/auth.py",
                line=25,
                severity="error",
            ),
            priority=1,
        )

        desc1 = self.processor._generate_fix_description(item1)
        self.assertIn("CRITICAL FIX NEEDED", desc1)
        self.assertIn("src/auth.py:25", desc1)
        self.assertIn("SQL injection", desc1)

        # Warning
        item2 = FeedbackItem(
            comment=ReviewComment(
                message="Performance issue",
                provider="deepseek",
                file="src/utils.py",
                severity="warning",
            ),
            priority=2,
        )

        desc2 = self.processor._generate_fix_description(item2)
        self.assertIn("Improvement", desc2)
        self.assertIn("src/utils.py", desc2)

        # General suggestion
        item3 = FeedbackItem(
            comment=ReviewComment(
                message="Consider refactoring", provider="openai", severity="info"
            ),
            priority=3,
        )

        desc3 = self.processor._generate_fix_description(item3)
        self.assertIn("Suggestion", desc3)
        self.assertIn("General", desc3)

    def test_generate_commit_message(self):
        """Test commit message generation."""
        feedback_items = [
            FeedbackItem(
                comment=ReviewComment(message="Error", provider="a", severity="error"),
                priority=1,
                fix_generated=True,
            ),
            FeedbackItem(
                comment=ReviewComment(
                    message="Error 2", provider="a", severity="error"
                ),
                priority=1,
                fix_generated=True,
            ),
            FeedbackItem(
                comment=ReviewComment(
                    message="Warning", provider="b", severity="warning"
                ),
                priority=2,
                fix_generated=True,
            ),
        ]

        message = self.processor._generate_commit_message(
            pr_number=123, iteration=1, items_addressed=3, feedback_items=feedback_items
        )

        self.assertIn("iteration 1", message)
        self.assertIn("2 critical issues", message)
        self.assertIn("1 warning", message)

    def test_commit_feedback_changes(self):
        """Test committing feedback changes."""
        # Configure mock to return different values for each call
        self.git_ops.run_command = Mock(
            side_effect=[
                "",  # git add -A
                "[feature/test abc1234] Commit message",  # git commit
            ]
        )

        feedback_items = [
            FeedbackItem(
                comment=ReviewComment(message="Fix", provider="a", severity="error"),
                priority=1,
                fix_generated=True,
            )
        ]

        commit_sha = self.processor._commit_feedback_changes(
            pr_number=123, iteration=1, items_addressed=1, feedback_items=feedback_items
        )

        # Should have called git commands
        self.assertEqual(self.git_ops.run_command.call_count, 2)
        self.assertIn("git add", self.git_ops.run_command.call_args_list[0][0][0])
        self.assertIn("git commit", self.git_ops.run_command.call_args_list[1][0][0])

    def test_process_feedback_with_blocking_issues(self):
        """Test processing feedback with blocking issues."""
        review_result = PRReviewResult(
            pr_number=123,
            approved=False,
            reviewer="multi-agent-coder",
            comments=[
                ReviewComment(
                    message="Critical security issue",
                    provider="anthropic",
                    file="src/auth.py",
                    line=25,
                    severity="error",
                ),
                ReviewComment(
                    message="Performance warning",
                    provider="deepseek",
                    file="src/utils.py",
                    line=10,
                    severity="warning",
                ),
            ],
            summary="Changes requested",
            providers_reviewed=["anthropic", "deepseek"],
            approval_count=0,
            total_reviewers=2,
        )

        with patch.object(Path, "exists", return_value=True):
            result = self.processor.process_feedback(
                pr_number=123, review_result=review_result, iteration=1
            )

        self.assertTrue(result.success)
        self.assertEqual(result.total_feedback_items, 2)
        # Both error and warning should be addressed (address_warnings=True)
        self.assertEqual(result.items_addressed, 2)
        self.assertTrue(result.changes_made)

    def test_get_statistics(self):
        """Test statistics retrieval."""
        # Manually set statistics
        self.processor.total_feedback_processed = 10
        self.processor.total_fixes_applied = 8
        self.processor.total_iterations = 3
        self.processor.escalations = 1

        stats = self.processor.get_statistics()

        self.assertEqual(stats["total_feedback_processed"], 10)
        self.assertEqual(stats["total_fixes_applied"], 8)
        self.assertEqual(stats["total_iterations"], 3)
        self.assertEqual(stats["escalations"], 1)

    def test_reset_statistics(self):
        """Test statistics reset."""
        self.processor.total_feedback_processed = 10
        self.processor.total_fixes_applied = 5
        self.processor.total_iterations = 2
        self.processor.escalations = 1

        self.processor.reset_statistics()

        self.assertEqual(self.processor.total_feedback_processed, 0)
        self.assertEqual(self.processor.total_fixes_applied, 0)
        self.assertEqual(self.processor.total_iterations, 0)
        self.assertEqual(self.processor.escalations, 0)

    def test_feedback_item_dataclass(self):
        """Test FeedbackItem dataclass."""
        comment = ReviewComment(message="Test", provider="anthropic", severity="error")

        item = FeedbackItem(
            comment=comment,
            priority=1,
            fix_generated=True,
            fix_applied=True,
            fix_description="Fixed the issue",
        )

        item_dict = item.to_dict()
        self.assertEqual(item_dict["priority"], 1)
        self.assertTrue(item_dict["fix_generated"])
        self.assertTrue(item_dict["fix_applied"])
        self.assertEqual(item_dict["fix_description"], "Fixed the issue")

    def test_review_processing_result_dataclass(self):
        """Test ReviewProcessingResult dataclass."""
        result = ReviewProcessingResult(
            pr_number=123,
            iteration=1,
            total_feedback_items=5,
            items_addressed=4,
            items_failed=1,
            changes_made=True,
            commit_sha="abc1234",
        )

        result_dict = result.to_dict()
        self.assertEqual(result_dict["pr_number"], 123)
        self.assertEqual(result_dict["iteration"], 1)
        self.assertEqual(result_dict["total_feedback_items"], 5)
        self.assertEqual(result_dict["items_addressed"], 4)
        self.assertEqual(result_dict["items_failed"], 1)
        self.assertTrue(result_dict["changes_made"])
        self.assertEqual(result_dict["commit_sha"], "abc1234")
        self.assertIn("processed_at", result_dict)


if __name__ == "__main__":
    unittest.main()
