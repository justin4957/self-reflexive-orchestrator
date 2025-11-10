"""Unit tests for analytics and tracking components."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.core.analytics import AnalyticsCollector, InsightsGenerator, OperationTracker
from src.core.database import Database
from src.core.logger import setup_logging


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_analytics.db"
        logger = setup_logging()
        db = Database(db_path=str(db_path), logger=logger)
        yield db


@pytest.fixture
def operation_tracker(temp_db):
    """Create operation tracker with temp database."""
    logger = setup_logging()
    return OperationTracker(database=temp_db, logger=logger)


@pytest.fixture
def analytics_collector(temp_db):
    """Create analytics collector with temp database."""
    logger = setup_logging()
    return AnalyticsCollector(database=temp_db, logger=logger)


@pytest.fixture
def insights_generator(analytics_collector):
    """Create insights generator."""
    logger = setup_logging()
    return InsightsGenerator(analytics=analytics_collector, logger=logger)


class TestOperationTracker:
    """Tests for OperationTracker."""

    def test_start_operation(self, operation_tracker):
        """Test starting an operation creates database record."""
        operation_id = operation_tracker.start_operation(
            operation_type="process_issue",
            operation_id="123",
            context={"test": "data"},
        )

        assert operation_id is not None
        assert isinstance(operation_id, int)
        assert operation_id > 0

    def test_complete_operation_success(self, operation_tracker, temp_db):
        """Test completing a successful operation."""
        # Start operation
        op_id = operation_tracker.start_operation(
            operation_type="test_operation",
            operation_id="test-1",
        )

        # Complete it
        operation_tracker.complete_operation(
            operation_db_id=op_id,
            success=True,
        )

        # Verify in database
        result = temp_db.execute(
            "SELECT * FROM operations WHERE id = ?",
            (op_id,),
            fetch_one=True,
        )

        assert result is not None
        assert result["success"] == 1
        assert result["completed_at"] is not None
        assert result["duration_seconds"] is not None

    def test_complete_operation_failure(self, operation_tracker, temp_db):
        """Test completing a failed operation."""
        # Start operation
        op_id = operation_tracker.start_operation(
            operation_type="test_operation",
            operation_id="test-2",
        )

        # Complete with failure
        operation_tracker.complete_operation(
            operation_db_id=op_id,
            success=False,
            error_message="Test error",
            error_type="TestError",
            retry_count=2,
        )

        # Verify in database
        result = temp_db.execute(
            "SELECT * FROM operations WHERE id = ?",
            (op_id,),
            fetch_one=True,
        )

        assert result is not None
        assert result["success"] == 0
        assert result["error_message"] == "Test error"
        assert result["error_type"] == "TestError"
        assert result["retry_count"] == 2

    def test_track_issue_processing(self, operation_tracker, temp_db):
        """Test tracking issue processing metrics."""
        # Start operation
        op_id = operation_tracker.start_operation(operation_type="process_issue")

        # Track issue processing
        operation_tracker.track_issue_processing(
            operation_db_id=op_id,
            issue_number=123,
            complexity=5,
            files_changed=3,
            lines_added=150,
            lines_deleted=50,
            tests_added=2,
            success=True,
            time_to_completion_seconds=300.0,
        )

        # Verify in database
        result = temp_db.execute(
            "SELECT * FROM issue_processing WHERE operation_id = ?",
            (op_id,),
            fetch_one=True,
        )

        assert result is not None
        assert result["issue_number"] == 123
        assert result["complexity"] == 5
        assert result["files_changed"] == 3
        assert result["lines_added"] == 150
        assert result["tests_added"] == 2
        assert result["success"] == 1

    def test_track_code_generation(self, operation_tracker, temp_db):
        """Test tracking code generation metrics."""
        # Start operation
        op_id = operation_tracker.start_operation(operation_type="generate_code")

        # Track code generation
        operation_tracker.track_code_generation(
            operation_db_id=op_id,
            provider="anthropic",
            model="claude-3-5-sonnet",
            issue_number=123,
            tokens_used=5000,
            cost=0.05,
            first_attempt_success=True,
            test_pass_rate=1.0,
        )

        # Verify in database
        result = temp_db.execute(
            "SELECT * FROM code_generation WHERE operation_id = ?",
            (op_id,),
            fetch_one=True,
        )

        assert result is not None
        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-3-5-sonnet"
        assert result["tokens_used"] == 5000
        assert result["cost"] == 0.05
        assert result["first_attempt_success"] == 1

    def test_track_pr_management(self, operation_tracker, temp_db):
        """Test tracking PR management metrics."""
        # Start operation
        op_id = operation_tracker.start_operation(operation_type="create_pr")

        # Track PR management
        operation_tracker.track_pr_management(
            operation_db_id=op_id,
            pr_number=456,
            issue_number=123,
            created=True,
            merged=True,
            ci_passed=True,
            review_approved=True,
            time_to_merge_seconds=7200.0,
            ci_failure_count=1,
        )

        # Verify in database
        result = temp_db.execute(
            "SELECT * FROM pr_management WHERE operation_id = ?",
            (op_id,),
            fetch_one=True,
        )

        assert result is not None
        assert result["pr_number"] == 456
        assert result["issue_number"] == 123
        assert result["merged"] == 1
        assert result["ci_passed"] == 1
        assert result["ci_failure_count"] == 1


class TestAnalyticsCollector:
    """Tests for AnalyticsCollector."""

    def test_get_success_rate_no_data(self, analytics_collector):
        """Test success rate with no data."""
        rate = analytics_collector.get_success_rate(days=30)
        assert rate == 0.0

    def test_get_success_rate_with_data(self, operation_tracker, analytics_collector):
        """Test success rate calculation with data."""
        # Create some operations
        for i in range(10):
            op_id = operation_tracker.start_operation(
                operation_type="test_op", operation_id=str(i)
            )
            # 7 successful, 3 failed
            operation_tracker.complete_operation(op_id, success=(i < 7))

        rate = analytics_collector.get_success_rate(days=30)
        assert rate == 70.0

    def test_get_success_rate_by_type(self, operation_tracker, analytics_collector):
        """Test success rate filtered by operation type."""
        # Create operations of different types
        for i in range(5):
            op_id = operation_tracker.start_operation(
                operation_type="type_a", operation_id=str(i)
            )
            operation_tracker.complete_operation(op_id, success=(i < 4))

        for i in range(5):
            op_id = operation_tracker.start_operation(
                operation_type="type_b", operation_id=str(i + 5)
            )
            operation_tracker.complete_operation(op_id, success=(i < 2))

        # Check type_a: 4/5 = 80%
        rate_a = analytics_collector.get_success_rate(operation_type="type_a", days=30)
        assert rate_a == 80.0

        # Check type_b: 2/5 = 40%
        rate_b = analytics_collector.get_success_rate(operation_type="type_b", days=30)
        assert rate_b == 40.0

    def test_get_average_duration(
        self, operation_tracker, analytics_collector, temp_db
    ):
        """Test average duration calculation."""
        # Create operations with known durations
        for i in range(3):
            op_id = operation_tracker.start_operation(operation_type="timed_op")
            # Manually set duration to test
            temp_db.execute(
                """
                UPDATE operations
                SET completed_at = datetime('now'),
                    duration_seconds = ?,
                    success = 1
                WHERE id = ?
                """,
                (float(100 + i * 100), op_id),
            )

        avg_duration = analytics_collector.get_average_duration(days=30)
        # Average of 100, 200, 300 = 200
        assert avg_duration == 200.0

    def test_get_operation_counts(self, operation_tracker, analytics_collector):
        """Test operation counts by type."""
        # Create operations
        for _ in range(5):
            op_id = operation_tracker.start_operation(operation_type="process_issue")
            operation_tracker.complete_operation(op_id, success=True)

        for _ in range(3):
            op_id = operation_tracker.start_operation(operation_type="create_pr")
            operation_tracker.complete_operation(op_id, success=True)

        counts = analytics_collector.get_operation_counts(days=30)
        assert counts["process_issue"] == 5
        assert counts["create_pr"] == 3

    def test_get_error_analysis(self, operation_tracker, analytics_collector):
        """Test error analysis."""
        # Create failed operations with errors
        for i in range(3):
            op_id = operation_tracker.start_operation(operation_type="test_op")
            operation_tracker.complete_operation(
                op_id,
                success=False,
                error_type="NetworkError",
                error_message="Connection failed",
            )

        for i in range(2):
            op_id = operation_tracker.start_operation(operation_type="test_op")
            operation_tracker.complete_operation(
                op_id,
                success=False,
                error_type="TimeoutError",
                error_message="Operation timed out",
            )

        errors = analytics_collector.get_error_analysis(days=30)

        assert len(errors) == 2
        # NetworkError should be first (count: 3)
        assert errors[0]["error_type"] == "NetworkError"
        assert errors[0]["count"] == 3
        assert errors[1]["error_type"] == "TimeoutError"
        assert errors[1]["count"] == 2

    def test_get_issue_processing_stats(self, operation_tracker, analytics_collector):
        """Test issue processing statistics."""
        # Create issue processing data
        for i in range(5):
            op_id = operation_tracker.start_operation(operation_type="process_issue")
            operation_tracker.track_issue_processing(
                operation_db_id=op_id,
                issue_number=i,
                complexity=5 + i,
                files_changed=2 + i,
                lines_added=100 + i * 50,
                tests_added=2,
                success=(i < 4),  # 4 successful, 1 failed
                time_to_completion_seconds=300.0,
            )

        stats = analytics_collector.get_issue_processing_stats(days=30)

        assert stats["total_issues"] == 5
        assert stats["success_rate"] == 80.0
        assert stats["avg_complexity"] == 7.0  # Average of 5,6,7,8,9
        assert stats["avg_tests_added"] == 2.0

    def test_get_pr_management_stats(self, operation_tracker, analytics_collector):
        """Test PR management statistics."""
        # Create PR data
        for i in range(4):
            op_id = operation_tracker.start_operation(operation_type="manage_pr")
            operation_tracker.track_pr_management(
                operation_db_id=op_id,
                pr_number=100 + i,
                merged=(i < 3),  # 3 merged, 1 not
                ci_passed=(i < 2),  # 2 passed CI
                time_to_merge_seconds=3600.0,
                ci_failure_count=i,
            )

        stats = analytics_collector.get_pr_management_stats(days=30)

        assert stats["total_prs"] == 4
        assert stats["merge_rate"] == 75.0  # 3/4
        assert stats["ci_pass_rate"] == 50.0  # 2/4
        assert stats["avg_time_to_merge"] == 3600.0


class TestInsightsGenerator:
    """Tests for InsightsGenerator."""

    def test_generate_summary_empty(self, insights_generator):
        """Test summary generation with no data."""
        summary = insights_generator.generate_summary(days=30)

        assert "period_days" in summary
        assert summary["period_days"] == 30
        assert "overall_success_rate" in summary
        assert summary["overall_success_rate"] == 0.0

    def test_identify_failure_patterns_low_success(
        self, operation_tracker, insights_generator
    ):
        """Test identifying low success rate pattern."""
        # Create mostly failed operations
        for i in range(10):
            op_id = operation_tracker.start_operation(operation_type="test_op")
            operation_tracker.complete_operation(op_id, success=(i < 3))  # 30% success

        patterns = insights_generator.identify_failure_patterns(days=30)

        # Should detect low success rate
        assert any(p["pattern"] == "low_success_rate" for p in patterns)

    def test_identify_recurring_error_pattern(
        self, operation_tracker, insights_generator
    ):
        """Test identifying recurring error pattern."""
        # Create many operations with same error
        for i in range(10):
            op_id = operation_tracker.start_operation(operation_type="test_op")
            operation_tracker.complete_operation(
                op_id,
                success=False,
                error_type="RecurringError",
                error_message="Same error",
            )

        patterns = insights_generator.identify_failure_patterns(days=30)

        # Should detect recurring error
        assert any(p["pattern"] == "recurring_error" for p in patterns)

    def test_recommend_optimizations_high_costs(
        self, operation_tracker, insights_generator
    ):
        """Test cost optimization recommendations."""
        # Create operations with high costs
        for i in range(5):
            op_id = operation_tracker.start_operation(operation_type="generate_code")
            operation_tracker.track_code_generation(
                operation_db_id=op_id,
                provider="anthropic",
                model="expensive-model",
                tokens_used=50000,
                cost=25.0,  # $25 per operation = $125 total
                first_attempt_success=True,
            )

        recommendations = insights_generator.recommend_optimizations(days=30)

        # Should recommend cost optimization
        assert any("cost" in rec.lower() for rec in recommendations)


class TestDatabaseIntegration:
    """Integration tests for database operations."""

    def test_complete_workflow(self, temp_db, operation_tracker):
        """Test complete operation tracking workflow."""
        # Start operation
        op_id = operation_tracker.start_operation(
            operation_type="full_workflow",
            operation_id="workflow-1",
            context={"goal": "test complete flow"},
        )

        # Track issue processing
        operation_tracker.track_issue_processing(
            operation_db_id=op_id,
            issue_number=999,
            complexity=7,
            files_changed=5,
            lines_added=250,
            lines_deleted=100,
            tests_added=3,
            success=True,
            time_to_completion_seconds=600.0,
        )

        # Track code generation
        operation_tracker.track_code_generation(
            operation_db_id=op_id,
            provider="anthropic",
            model="claude-3-5-sonnet",
            issue_number=999,
            tokens_used=10000,
            cost=0.10,
            first_attempt_success=True,
            test_pass_rate=1.0,
        )

        # Track PR
        operation_tracker.track_pr_management(
            operation_db_id=op_id,
            pr_number=888,
            issue_number=999,
            merged=True,
            ci_passed=True,
            time_to_merge_seconds=1800.0,
        )

        # Complete operation
        operation_tracker.complete_operation(op_id, success=True)

        # Verify all data is connected
        operation = temp_db.execute(
            "SELECT * FROM operations WHERE id = ?",
            (op_id,),
            fetch_one=True,
        )
        assert operation is not None
        assert operation["success"] == 1

        issue = temp_db.execute(
            "SELECT * FROM issue_processing WHERE operation_id = ?",
            (op_id,),
            fetch_one=True,
        )
        assert issue is not None
        assert issue["issue_number"] == 999

        code_gen = temp_db.execute(
            "SELECT * FROM code_generation WHERE operation_id = ?",
            (op_id,),
            fetch_one=True,
        )
        assert code_gen is not None
        assert code_gen["cost"] == 0.10

        pr = temp_db.execute(
            "SELECT * FROM pr_management WHERE operation_id = ?",
            (op_id,),
            fetch_one=True,
        )
        assert pr is not None
        assert pr["pr_number"] == 888


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
