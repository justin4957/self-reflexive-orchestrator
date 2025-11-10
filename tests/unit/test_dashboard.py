"""Unit tests for dashboard and reports."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.core.analytics import AnalyticsCollector, InsightsGenerator, OperationTracker
from src.core.dashboard import Dashboard, DashboardMetrics
from src.core.database import Database
from src.core.logger import setup_logging
from src.core.reports import ReportGenerator


@pytest.fixture
def temp_db():
    """Create temporary database with sample data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        logger = setup_logging()
        db = Database(db_path=str(db_path), logger=logger)

        # Add sample data
        tracker = OperationTracker(database=db, logger=logger)

        # Add some successful operations
        for i in range(10):
            op_id = tracker.start_operation("process_issue", f"issue-{i}")
            tracker.complete_operation(op_id, success=True)

        # Add some failed operations
        for i in range(3):
            op_id = tracker.start_operation("process_issue", f"issue-fail-{i}")
            tracker.complete_operation(op_id, success=False, error_type="TestError")

        yield db


@pytest.fixture
def analytics(temp_db):
    """Create analytics collector."""
    logger = setup_logging()
    return AnalyticsCollector(database=temp_db, logger=logger)


@pytest.fixture
def insights(analytics):
    """Create insights generator."""
    logger = setup_logging()
    return InsightsGenerator(analytics=analytics, logger=logger)


@pytest.fixture
def dashboard(temp_db, analytics, insights):
    """Create dashboard."""
    logger = setup_logging()
    return Dashboard(
        database=temp_db,
        analytics=analytics,
        insights=insights,
        cache_manager=None,
        logger=logger,
    )


@pytest.fixture
def reporter(temp_db, analytics, insights):
    """Create report generator."""
    logger = setup_logging()
    return ReportGenerator(
        database=temp_db, analytics=analytics, insights=insights, logger=logger
    )


class TestDashboard:
    """Tests for Dashboard."""

    def test_get_metrics(self, dashboard):
        """Test getting dashboard metrics."""
        metrics = dashboard.get_metrics()

        assert isinstance(metrics, DashboardMetrics)
        assert metrics.status == "running"
        assert metrics.mode == "autonomous"
        assert metrics.uptime_seconds >= 0
        assert metrics.success_rate_7d >= 0
        assert metrics.success_rate_30d >= 0

    def test_today_activity(self, dashboard):
        """Test today's activity calculation."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        activity = dashboard._get_today_activity(today_start)

        assert "total" in activity
        assert "success" in activity
        assert "failed" in activity
        assert "prs_merged" in activity
        assert "cost" in activity
        assert activity["total"] >= 0

    def test_performance_metrics(self, dashboard):
        """Test performance metrics calculation."""
        perf = dashboard._get_performance_metrics()

        assert "avg_duration" in perf
        assert "cache_hit_rate" in perf
        assert "error_rate" in perf
        assert perf["avg_duration"] >= 0
        assert 0 <= perf["cache_hit_rate"] <= 1
        assert 0 <= perf["error_rate"] <= 1

    def test_cost_metrics(self, dashboard):
        """Test cost metrics calculation."""
        costs = dashboard._get_cost_metrics()

        assert "cost_7d" in costs
        assert "cost_30d" in costs
        assert "cost_per_operation" in costs
        assert "monthly_projection" in costs
        assert costs["cost_7d"] >= 0
        assert costs["monthly_projection"] >= 0

    def test_quality_metrics(self, dashboard):
        """Test quality metrics calculation."""
        quality = dashboard._get_quality_metrics()

        assert "test_pass_rate" in quality
        assert "avg_complexity" in quality
        assert 0 <= quality["test_pass_rate"] <= 1

    def test_active_operations(self, dashboard):
        """Test getting active operations."""
        active = dashboard._get_active_operations()

        assert isinstance(active, list)
        # May be empty if all operations completed

    def test_recent_operations(self, dashboard):
        """Test getting recent operations."""
        recent = dashboard._get_recent_operations(limit=5)

        assert isinstance(recent, list)
        assert len(recent) <= 5
        if recent:
            assert "type" in recent[0]
            assert "success" in recent[0]
            assert "duration" in recent[0]

    def test_format_cli(self, dashboard):
        """Test CLI formatting."""
        metrics = dashboard.get_metrics()
        output = dashboard.format_cli(metrics)

        assert isinstance(output, str)
        assert "Self-Reflexive Orchestrator Dashboard" in output
        assert "Status:" in output
        assert "Uptime:" in output
        assert "Today:" in output
        assert "Performance" in output
        assert "Costs:" in output

    def test_format_uptime(self, dashboard):
        """Test uptime formatting."""
        assert dashboard._format_uptime(120) == "2m"
        assert dashboard._format_uptime(3600) == "1h 0m"
        assert dashboard._format_uptime(90000) == "1d 1h 0m"


class TestReportGenerator:
    """Tests for ReportGenerator."""

    def test_generate_summary_report(self, reporter):
        """Test generating summary report."""
        report = reporter.generate_summary_report(days=7)

        assert report["report_type"] == "summary"
        assert report["period_days"] == 7
        assert "generated_at" in report
        assert "overall" in report
        assert "operations" in report
        assert "costs" in report
        assert "issues" in report
        assert "pull_requests" in report
        assert "insights" in report

    def test_generate_detailed_report(self, reporter):
        """Test generating detailed report."""
        report = reporter.generate_detailed_report(days=7)

        assert report["report_type"] == "detailed"
        assert "detailed" in report
        assert "operations_by_day" in report["detailed"]
        assert "costs_by_day" in report["detailed"]
        assert "errors_by_type" in report["detailed"]

    def test_cost_summary(self, reporter):
        """Test cost summary calculation."""
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        costs = reporter._get_cost_summary(since)

        assert "total_cost" in costs
        assert "total_tokens" in costs
        assert "operations" in costs
        assert "avg_cost_per_operation" in costs
        assert costs["total_cost"] >= 0

    def test_issue_summary(self, reporter):
        """Test issue summary calculation."""
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        issues = reporter._get_issue_summary(since)

        assert "total_processed" in issues
        assert "success_count" in issues
        assert "success_rate" in issues
        assert "avg_duration" in issues
        assert 0 <= issues["success_rate"] <= 1

    def test_pr_summary(self, reporter):
        """Test PR summary calculation."""
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        prs = reporter._get_pr_summary(since)

        assert "total_created" in prs
        assert "total_merged" in prs
        assert "merge_rate" in prs
        assert 0 <= prs["merge_rate"] <= 1

    def test_operations_by_day(self, reporter):
        """Test operations by day calculation."""
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        ops = reporter._get_operations_by_day(since)

        assert isinstance(ops, list)
        if ops:
            assert "day" in ops[0]
            assert "operations" in ops[0]
            assert "successes" in ops[0]

    def test_costs_by_day(self, reporter):
        """Test costs by day calculation."""
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        costs = reporter._get_costs_by_day(since)

        assert isinstance(costs, list)
        # May be empty if no cost data

    def test_errors_by_type(self, reporter):
        """Test errors by type calculation."""
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        errors = reporter._get_errors_by_type(since)

        assert isinstance(errors, dict)
        if errors:
            assert "TestError" in errors

    def test_export_json(self, reporter):
        """Test JSON export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "report.json"
            report = reporter.generate_summary_report(days=7)

            reporter.export_json(report, str(output_file))

            assert output_file.exists()
            import json

            with open(output_file) as f:
                loaded = json.load(f)
            assert loaded["report_type"] == "summary"

    def test_export_markdown(self, reporter):
        """Test Markdown export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "report.md"
            report = reporter.generate_summary_report(days=7)

            reporter.export_markdown(report, str(output_file))

            assert output_file.exists()
            content = output_file.read_text()
            assert "# Orchestrator Report" in content
            assert "## Overall Metrics" in content
            assert "## Operations" in content


class TestIntegration:
    """Integration tests for dashboard and reports."""

    def test_full_workflow(self, temp_db, analytics, insights):
        """Test complete workflow from data to dashboard to report."""
        logger = setup_logging()

        # Create dashboard
        dash = Dashboard(
            database=temp_db,
            analytics=analytics,
            insights=insights,
            cache_manager=None,
            logger=logger,
        )

        # Get metrics
        metrics = dash.get_metrics()
        assert metrics.issues_processed_today >= 0

        # Format for CLI
        cli_output = dash.format_cli(metrics)
        assert len(cli_output) > 0

        # Generate report
        reporter = ReportGenerator(
            database=temp_db, analytics=analytics, insights=insights, logger=logger
        )

        report = reporter.generate_summary_report(days=7)
        assert report["overall"]["total_operations"] >= 0

        # Export report
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "report.md"
            reporter.export_markdown(report, str(output_file))
            assert output_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
