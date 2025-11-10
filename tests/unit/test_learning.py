"""Unit tests for learning system components."""

import tempfile
from pathlib import Path

import pytest

from src.core.analytics import OperationTracker
from src.core.database import Database
from src.core.learning_engine import LearningEngine
from src.core.logger import setup_logging
from src.core.pattern_detector import PatternDetector
from src.core.prompt_library import PromptLibrary


@pytest.fixture
def temp_db():
    """Create temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_learning.db"
        logger = setup_logging()
        db = Database(db_path=str(db_path), logger=logger)
        yield db


@pytest.fixture
def prompt_library():
    """Create temporary prompt library."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prompts_file = Path(tmpdir) / "prompts.json"
        logger = setup_logging()
        library = PromptLibrary(prompts_file=str(prompts_file), logger=logger)
        yield library


class TestPatternDetector:
    """Tests for PatternDetector."""

    def test_detect_patterns_no_failures(self, temp_db):
        """Test pattern detection with no failures."""
        logger = setup_logging()
        detector = PatternDetector(database=temp_db, logger=logger, min_occurrences=3)

        patterns = detector.detect_patterns()
        assert patterns == []

    def test_detect_patterns_with_failures(self, temp_db):
        """Test pattern detection with failures."""
        logger = setup_logging()
        tracker = OperationTracker(database=temp_db, logger=logger)

        # Create 5 similar failures
        for i in range(5):
            op_id = tracker.start_operation(
                operation_type="test_op", operation_id=f"test-{i}"
            )
            tracker.complete_operation(
                op_id,
                success=False,
                error_type="TestError",
                error_message="Test failed",
            )

        # Detect patterns
        detector = PatternDetector(database=temp_db, logger=logger, min_occurrences=3)
        patterns = detector.detect_patterns()

        assert len(patterns) == 1
        assert patterns[0].failure_type == "test_op"
        assert patterns[0].error_type == "TestError"
        assert patterns[0].occurrence_count == 5

    def test_should_trigger_learning_high_severity(self, temp_db):
        """Test learning trigger for high severity patterns."""
        logger = setup_logging()
        tracker = OperationTracker(database=temp_db, logger=logger)

        # Create 10 failures in short time (high severity)
        for i in range(10):
            op_id = tracker.start_operation(operation_type="critical_op")
            tracker.complete_operation(op_id, success=False, error_type="CriticalError")

        detector = PatternDetector(database=temp_db, logger=logger, min_occurrences=3)
        patterns = detector.detect_patterns()

        assert len(patterns) == 1
        assert detector.should_trigger_learning(patterns[0])


class TestPromptLibrary:
    """Tests for PromptLibrary."""

    def test_get_default_prompt(self, prompt_library):
        """Test getting default prompt."""
        prompt = prompt_library.get_prompt("issue_analysis")
        assert prompt is not None
        assert "Issue" in prompt

    def test_update_prompt(self, prompt_library):
        """Test updating a prompt."""
        new_template = "New improved prompt template"
        prompt_library.update_prompt("issue_analysis", new_template, "Test improvement")

        updated = prompt_library.get_prompt("issue_analysis")
        assert updated == new_template

    def test_prompt_history(self, prompt_library):
        """Test prompt history tracking."""
        original = prompt_library.get_prompt("issue_analysis")

        # Make updates
        prompt_library.update_prompt("issue_analysis", "Version 2", "Improvement 1")
        prompt_library.update_prompt("issue_analysis", "Version 3", "Improvement 2")

        history = prompt_library.get_prompt_history("issue_analysis")
        assert len(history) == 2
        assert history[0]["reason"] == "Improvement 1"
        assert history[1]["reason"] == "Improvement 2"

    def test_rollback_prompt(self, prompt_library):
        """Test rolling back prompt to previous version."""
        original = prompt_library.get_prompt("issue_analysis")

        # Update
        prompt_library.update_prompt("issue_analysis", "Version 2", "Test update")

        # Rollback
        success = prompt_library.rollback_prompt("issue_analysis", 1)
        assert success is False  # Version 1 has no previous version

        # Multiple updates and rollback
        prompt_library.update_prompt("issue_analysis", "Version 3", "Update 2")
        success = prompt_library.rollback_prompt("issue_analysis", 2)
        assert success


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
