"""Analytics and tracking for orchestrator operations.

Provides functionality to record operations, track success/failure patterns,
and generate insights from historical data.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import Database
from .logger import AuditLogger


class OperationTracker:
    """Tracks operation execution and outcomes.

    Responsibilities:
    - Record operation start/end times
    - Track success/failure status
    - Store error information
    - Link operations to specific resources (issues, PRs, etc.)
    """

    def __init__(self, database: Database, logger: AuditLogger):
        """Initialize operation tracker.

        Args:
            database: Database instance for storage
            logger: Audit logger instance
        """
        self.database = database
        self.logger = logger

    def start_operation(
        self,
        operation_type: str,
        operation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record the start of an operation.

        Args:
            operation_type: Type of operation (e.g., "process_issue", "create_pr")
            operation_id: Optional identifier (e.g., issue number, PR number)
            context: Optional context data as dictionary

        Returns:
            Database ID of the created operation record
        """
        import json

        # Format timestamp for SQLite (YYYY-MM-DD HH:MM:SS)
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        context_json = json.dumps(context) if context else None

        operation_db_id = self.database.execute(
            """
            INSERT INTO operations (
                operation_type, operation_id, started_at, success, context
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (operation_type, operation_id, started_at, False, context_json),
        )

        self.logger.info(
            "operation_started",
            operation_type=operation_type,
            operation_id=operation_id,
            db_id=operation_db_id,
        )

        return operation_db_id

    def complete_operation(
        self,
        operation_db_id: int,
        success: bool,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        retry_count: int = 0,
    ):
        """Record the completion of an operation.

        Args:
            operation_db_id: Database ID from start_operation
            success: Whether the operation succeeded
            error_message: Error message if failed
            error_type: Type of error if failed
            retry_count: Number of retries attempted
        """
        # Format timestamp for SQLite (YYYY-MM-DD HH:MM:SS)
        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Calculate duration
        result = self.database.execute(
            "SELECT started_at FROM operations WHERE id = ?",
            (operation_db_id,),
            fetch_one=True,
        )

        if result:
            # started_at might be returned as datetime or string
            started_at_val = result["started_at"]
            if isinstance(started_at_val, str):
                started_at = datetime.strptime(started_at_val, "%Y-%m-%d %H:%M:%S")
            else:
                started_at = started_at_val
            completed_at_dt = datetime.strptime(completed_at, "%Y-%m-%d %H:%M:%S")
            duration = (completed_at_dt - started_at).total_seconds()
        else:
            duration = None

        self.database.execute(
            """
            UPDATE operations
            SET completed_at = ?,
                duration_seconds = ?,
                success = ?,
                error_message = ?,
                error_type = ?,
                retry_count = ?
            WHERE id = ?
            """,
            (
                completed_at,
                duration,
                success,
                error_message,
                error_type,
                retry_count,
                operation_db_id,
            ),
        )

        self.logger.info(
            "operation_completed",
            operation_db_id=operation_db_id,
            success=success,
            duration_seconds=duration,
            retry_count=retry_count,
        )

    def track_issue_processing(
        self,
        operation_db_id: int,
        issue_number: int,
        complexity: Optional[int] = None,
        files_changed: Optional[int] = None,
        lines_added: Optional[int] = None,
        lines_deleted: Optional[int] = None,
        tests_added: Optional[int] = None,
        success: bool = False,
        failure_reason: Optional[str] = None,
        time_to_completion_seconds: Optional[float] = None,
    ):
        """Track metrics for issue processing.

        Args:
            operation_db_id: Parent operation ID
            issue_number: GitHub issue number
            complexity: Issue complexity score (0-10)
            files_changed: Number of files changed
            lines_added: Lines of code added
            lines_deleted: Lines of code deleted
            tests_added: Number of tests added
            success: Whether issue was successfully processed
            failure_reason: Reason if failed
            time_to_completion_seconds: Total time to complete
        """
        self.database.execute(
            """
            INSERT INTO issue_processing (
                operation_id, issue_number, complexity,
                files_changed, lines_added, lines_deleted, tests_added,
                success, failure_reason, time_to_completion_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_db_id,
                issue_number,
                complexity,
                files_changed,
                lines_added,
                lines_deleted,
                tests_added,
                success,
                failure_reason,
                time_to_completion_seconds,
            ),
        )

        self.logger.info(
            "issue_processing_tracked",
            operation_db_id=operation_db_id,
            issue_number=issue_number,
            success=success,
        )

    def track_code_generation(
        self,
        operation_db_id: int,
        provider: str,
        model: str,
        issue_number: Optional[int] = None,
        tokens_used: Optional[int] = None,
        cost: Optional[float] = None,
        first_attempt_success: bool = False,
        retry_count: int = 0,
        test_pass_rate: Optional[float] = None,
        error_type: Optional[str] = None,
    ):
        """Track metrics for code generation.

        Args:
            operation_db_id: Parent operation ID
            provider: LLM provider (e.g., "anthropic", "openai")
            model: Model name (e.g., "claude-3-5-sonnet")
            issue_number: Related issue number if any
            tokens_used: Total tokens consumed
            cost: Cost in USD
            first_attempt_success: Whether first attempt succeeded
            retry_count: Number of retries needed
            test_pass_rate: Percentage of tests passing (0.0-1.0)
            error_type: Type of error if failed
        """
        self.database.execute(
            """
            INSERT INTO code_generation (
                operation_id, issue_number, provider, model,
                tokens_used, cost, first_attempt_success, retry_count,
                test_pass_rate, error_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_db_id,
                issue_number,
                provider,
                model,
                tokens_used,
                cost,
                first_attempt_success,
                retry_count,
                test_pass_rate,
                error_type,
            ),
        )

        self.logger.info(
            "code_generation_tracked",
            operation_db_id=operation_db_id,
            provider=provider,
            model=model,
            first_attempt_success=first_attempt_success,
        )

    def track_pr_management(
        self,
        operation_db_id: int,
        pr_number: int,
        issue_number: Optional[int] = None,
        created: bool = True,
        merged: bool = False,
        ci_passed: Optional[bool] = None,
        review_approved: Optional[bool] = None,
        time_to_merge_seconds: Optional[float] = None,
        ci_failure_count: int = 0,
    ):
        """Track metrics for PR management.

        Args:
            operation_db_id: Parent operation ID
            pr_number: GitHub PR number
            issue_number: Related issue number if any
            created: Whether PR was created
            merged: Whether PR was merged
            ci_passed: Whether CI checks passed
            review_approved: Whether review was approved
            time_to_merge_seconds: Time from creation to merge
            ci_failure_count: Number of CI failures
        """
        self.database.execute(
            """
            INSERT INTO pr_management (
                operation_id, pr_number, issue_number, created, merged,
                ci_passed, review_approved, time_to_merge_seconds, ci_failure_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_db_id,
                pr_number,
                issue_number,
                created,
                merged,
                ci_passed,
                review_approved,
                time_to_merge_seconds,
                ci_failure_count,
            ),
        )

        self.logger.info(
            "pr_management_tracked",
            operation_db_id=operation_db_id,
            pr_number=pr_number,
            merged=merged,
        )

    def track_roadmap(
        self,
        operation_db_id: int,
        proposals_generated: int = 0,
        proposals_validated: int = 0,
        proposals_approved: int = 0,
        issues_created: int = 0,
        issues_implemented: int = 0,
        average_proposal_quality: Optional[float] = None,
    ):
        """Track metrics for roadmap generation.

        Args:
            operation_db_id: Parent operation ID
            proposals_generated: Number of proposals generated
            proposals_validated: Number validated by multi-agent-coder
            proposals_approved: Number approved by humans
            issues_created: Number of issues created from proposals
            issues_implemented: Number of those issues implemented
            average_proposal_quality: Average quality score (0.0-1.0)
        """
        self.database.execute(
            """
            INSERT INTO roadmap_tracking (
                operation_id, proposals_generated, proposals_validated,
                proposals_approved, issues_created, issues_implemented,
                average_proposal_quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_db_id,
                proposals_generated,
                proposals_validated,
                proposals_approved,
                issues_created,
                issues_implemented,
                average_proposal_quality,
            ),
        )

        self.logger.info(
            "roadmap_tracked",
            operation_db_id=operation_db_id,
            proposals_generated=proposals_generated,
        )


class AnalyticsCollector:
    """Collects and aggregates analytics from the database.

    Responsibilities:
    - Query operation history
    - Calculate success rates
    - Aggregate metrics by time period
    - Generate summary statistics
    """

    def __init__(self, database: Database, logger: AuditLogger):
        """Initialize analytics collector.

        Args:
            database: Database instance
            logger: Audit logger instance
        """
        self.database = database
        self.logger = logger

    def get_success_rate(
        self, operation_type: Optional[str] = None, days: int = 30
    ) -> float:
        """Calculate success rate for operations.

        Args:
            operation_type: Filter by operation type, or None for all
            days: Number of days to look back

        Returns:
            Success rate as percentage (0.0-100.0)
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        if operation_type:
            total = self.database.execute(
                """
                SELECT COUNT(*) as count FROM operations
                WHERE operation_type = ? AND started_at >= ?
                """,
                (operation_type, since),
                fetch_one=True,
            )
            successful = self.database.execute(
                """
                SELECT COUNT(*) as count FROM operations
                WHERE operation_type = ? AND started_at >= ? AND success = 1
                """,
                (operation_type, since),
                fetch_one=True,
            )
        else:
            total = self.database.execute(
                """
                SELECT COUNT(*) as count FROM operations
                WHERE started_at >= ?
                """,
                (since,),
                fetch_one=True,
            )
            successful = self.database.execute(
                """
                SELECT COUNT(*) as count FROM operations
                WHERE started_at >= ? AND success = 1
                """,
                (since,),
                fetch_one=True,
            )

        total_count = total["count"] if total else 0
        success_count = successful["count"] if successful else 0

        if total_count == 0:
            return 0.0

        return (success_count / total_count) * 100.0

    def get_average_duration(
        self, operation_type: Optional[str] = None, days: int = 30
    ) -> Optional[float]:
        """Calculate average operation duration.

        Args:
            operation_type: Filter by operation type, or None for all
            days: Number of days to look back

        Returns:
            Average duration in seconds, or None if no data
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        if operation_type:
            result = self.database.execute(
                """
                SELECT AVG(duration_seconds) as avg_duration
                FROM operations
                WHERE operation_type = ? AND started_at >= ?
                  AND duration_seconds IS NOT NULL
                """,
                (operation_type, since),
                fetch_one=True,
            )
        else:
            result = self.database.execute(
                """
                SELECT AVG(duration_seconds) as avg_duration
                FROM operations
                WHERE started_at >= ? AND duration_seconds IS NOT NULL
                """,
                (since,),
                fetch_one=True,
            )

        if result and result["avg_duration"] is not None:
            return float(result["avg_duration"])
        return None

    def get_operation_counts(self, days: int = 30) -> Dict[str, int]:
        """Get operation counts by type.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary mapping operation type to count
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        results = self.database.execute(
            """
            SELECT operation_type, COUNT(*) as count
            FROM operations
            WHERE started_at >= ?
            GROUP BY operation_type
            ORDER BY count DESC
            """,
            (since,),
        )

        return {row["operation_type"]: row["count"] for row in results}

    def get_error_analysis(self, days: int = 30) -> List[Dict[str, Any]]:
        """Analyze common errors.

        Args:
            days: Number of days to look back

        Returns:
            List of error types with counts and examples
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        results = self.database.execute(
            """
            SELECT error_type, COUNT(*) as count,
                   operation_type, error_message
            FROM operations
            WHERE started_at >= ? AND success = 0 AND error_type IS NOT NULL
            GROUP BY error_type, operation_type
            ORDER BY count DESC
            LIMIT 20
            """,
            (since,),
        )

        return [
            {
                "error_type": row["error_type"],
                "count": row["count"],
                "operation_type": row["operation_type"],
                "example_message": row["error_message"],
            }
            for row in results
        ]

    def get_issue_processing_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get statistics for issue processing.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with issue processing statistics
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        result = self.database.execute(
            """
            SELECT
                COUNT(*) as total_issues,
                SUM(CASE WHEN ip.success = 1 THEN 1 ELSE 0 END) as successful,
                AVG(complexity) as avg_complexity,
                AVG(files_changed) as avg_files_changed,
                AVG(lines_added) as avg_lines_added,
                AVG(tests_added) as avg_tests_added,
                AVG(time_to_completion_seconds) as avg_completion_time
            FROM issue_processing ip
            JOIN operations o ON ip.operation_id = o.id
            WHERE o.started_at >= ?
            """,
            (since,),
            fetch_one=True,
        )

        if not result or result["total_issues"] == 0:
            return {
                "total_issues": 0,
                "success_rate": 0.0,
                "avg_complexity": 0.0,
                "avg_files_changed": 0.0,
                "avg_lines_added": 0.0,
                "avg_tests_added": 0.0,
                "avg_completion_time": 0.0,
            }

        return {
            "total_issues": result["total_issues"],
            "success_rate": (result["successful"] / result["total_issues"]) * 100.0,
            "avg_complexity": result["avg_complexity"] or 0.0,
            "avg_files_changed": result["avg_files_changed"] or 0.0,
            "avg_lines_added": result["avg_lines_added"] or 0.0,
            "avg_tests_added": result["avg_tests_added"] or 0.0,
            "avg_completion_time": result["avg_completion_time"] or 0.0,
        }

    def get_pr_management_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get statistics for PR management.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with PR management statistics
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        result = self.database.execute(
            """
            SELECT
                COUNT(*) as total_prs,
                SUM(CASE WHEN merged = 1 THEN 1 ELSE 0 END) as merged,
                SUM(CASE WHEN ci_passed = 1 THEN 1 ELSE 0 END) as ci_passed,
                AVG(time_to_merge_seconds) as avg_time_to_merge,
                AVG(ci_failure_count) as avg_ci_failures
            FROM pr_management pm
            JOIN operations o ON pm.operation_id = o.id
            WHERE o.started_at >= ?
            """,
            (since,),
            fetch_one=True,
        )

        if not result or result["total_prs"] == 0:
            return {
                "total_prs": 0,
                "merge_rate": 0.0,
                "ci_pass_rate": 0.0,
                "avg_time_to_merge": 0.0,
                "avg_ci_failures": 0.0,
            }

        total = result["total_prs"]
        return {
            "total_prs": total,
            "merge_rate": (
                (result["merged"] / total) * 100.0 if result["merged"] else 0.0
            ),
            "ci_pass_rate": (
                (result["ci_passed"] / total) * 100.0 if result["ci_passed"] else 0.0
            ),
            "avg_time_to_merge": result["avg_time_to_merge"] or 0.0,
            "avg_ci_failures": result["avg_ci_failures"] or 0.0,
        }

    def get_cost_analysis(self, days: int = 30) -> Dict[str, Any]:
        """Analyze LLM usage costs.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with cost analysis
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        result = self.database.execute(
            """
            SELECT
                SUM(cost) as total_cost,
                SUM(tokens_used) as total_tokens,
                provider, model,
                COUNT(*) as request_count
            FROM code_generation cg
            JOIN operations o ON cg.operation_id = o.id
            WHERE o.started_at >= ?
            GROUP BY provider, model
            ORDER BY total_cost DESC
            """,
            (since,),
        )

        provider_costs = [
            {
                "provider": row["provider"],
                "model": row["model"],
                "total_cost": row["total_cost"] or 0.0,
                "total_tokens": row["total_tokens"] or 0,
                "request_count": row["request_count"],
            }
            for row in result
        ]

        total_cost = sum(p["total_cost"] for p in provider_costs)
        total_tokens = sum(p["total_tokens"] for p in provider_costs)

        return {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "by_provider": provider_costs,
        }


class InsightsGenerator:
    """Generates insights and recommendations from analytics.

    Responsibilities:
    - Identify patterns and trends
    - Detect anomalies
    - Generate recommendations
    - Predict future performance
    """

    def __init__(self, analytics: AnalyticsCollector, logger: AuditLogger):
        """Initialize insights generator.

        Args:
            analytics: AnalyticsCollector instance
            logger: Audit logger instance
        """
        self.analytics = analytics
        self.logger = logger

    def generate_summary(self, days: int = 30) -> Dict[str, Any]:
        """Generate a comprehensive summary of operations.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with summary insights
        """
        summary = {
            "period_days": days,
            "overall_success_rate": self.analytics.get_success_rate(days=days),
            "operation_counts": self.analytics.get_operation_counts(days=days),
            "issue_processing": self.analytics.get_issue_processing_stats(days=days),
            "pr_management": self.analytics.get_pr_management_stats(days=days),
            "cost_analysis": self.analytics.get_cost_analysis(days=days),
            "common_errors": self.analytics.get_error_analysis(days=days)[:5],
        }

        self.logger.info("insights_generated", period_days=days)
        return summary

    def identify_failure_patterns(self, days: int = 30) -> List[Dict[str, Any]]:
        """Identify patterns in failures.

        Args:
            days: Number of days to analyze

        Returns:
            List of identified patterns with recommendations
        """
        patterns = []

        # Check for common error types
        errors = self.analytics.get_error_analysis(days=days)
        if errors:
            top_error = errors[0]
            if top_error["count"] > 5:
                patterns.append(
                    {
                        "pattern": "recurring_error",
                        "error_type": top_error["error_type"],
                        "count": top_error["count"],
                        "recommendation": f"Investigate and fix recurring {top_error['error_type']} errors",
                    }
                )

        # Check for low success rates
        success_rate = self.analytics.get_success_rate(days=days)
        if success_rate < 70.0:
            patterns.append(
                {
                    "pattern": "low_success_rate",
                    "success_rate": success_rate,
                    "recommendation": "Overall success rate is low. Review recent failures and adjust configuration.",
                }
            )

        # Check for CI failures
        pr_stats = self.analytics.get_pr_management_stats(days=days)
        if pr_stats["avg_ci_failures"] > 2.0:
            patterns.append(
                {
                    "pattern": "high_ci_failures",
                    "avg_failures": pr_stats["avg_ci_failures"],
                    "recommendation": "Average CI failures per PR is high. Improve code quality or test coverage.",
                }
            )

        return patterns

    def recommend_optimizations(self, days: int = 30) -> List[str]:
        """Generate optimization recommendations.

        Args:
            days: Number of days to analyze

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Cost optimization
        cost_analysis = self.analytics.get_cost_analysis(days=days)
        if cost_analysis["total_cost"] > 100.0:
            recommendations.append(
                f"High LLM costs detected (${cost_analysis['total_cost']:.2f}). "
                "Consider using cheaper models or reducing token usage."
            )

        # Issue complexity
        issue_stats = self.analytics.get_issue_processing_stats(days=days)
        if issue_stats["avg_complexity"] > 7.0:
            recommendations.append(
                f"Average issue complexity is high ({issue_stats['avg_complexity']:.1f}). "
                "Consider breaking down complex issues or adjusting complexity ceiling."
            )

        # PR merge time
        pr_stats = self.analytics.get_pr_management_stats(days=days)
        if pr_stats["avg_time_to_merge"] > 86400:  # More than 1 day
            hours = pr_stats["avg_time_to_merge"] / 3600
            recommendations.append(
                f"Average PR merge time is high ({hours:.1f} hours). "
                "Review approval process or increase automation."
            )

        # Success rate
        success_rate = self.analytics.get_success_rate(days=days)
        if success_rate < 80.0:
            recommendations.append(
                f"Success rate is below target ({success_rate:.1f}%). "
                "Review error patterns and adjust safety guards."
            )

        return recommendations
