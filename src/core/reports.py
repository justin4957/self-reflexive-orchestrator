"""Report generation for orchestrator metrics and analytics.

Generates exportable reports in various formats.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from .analytics import AnalyticsCollector, InsightsGenerator
from .database import Database
from .logger import AuditLogger


class ReportGenerator:
    """Generates reports from orchestrator data.

    Responsibilities:
    - Generate summary reports
    - Generate detailed reports
    - Export in multiple formats (JSON, CSV, Markdown)
    - Calculate trends and insights
    """

    def __init__(
        self,
        database: Database,
        analytics: AnalyticsCollector,
        insights: InsightsGenerator,
        logger: AuditLogger,
    ):
        """Initialize report generator.

        Args:
            database: Database instance
            analytics: Analytics collector
            insights: Insights generator
            logger: Audit logger
        """
        self.database = database
        self.analytics = analytics
        self.insights = insights
        self.logger = logger

    def generate_summary_report(self, days: int = 7) -> Dict[str, Any]:
        """Generate summary report for specified period.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with summary report data
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")

        # Get overall metrics
        success_rate = self.analytics.get_success_rate(days=days)

        # Get operation stats manually
        operation_stats = self._get_operation_stats(since_str)

        # Get cost summary
        cost_summary = self._get_cost_summary(since_str)

        # Get issue processing summary
        issue_summary = self._get_issue_summary(since_str)

        # Get PR summary
        pr_summary = self._get_pr_summary(since_str)

        # Get insights
        insights_data = self.insights.generate_summary(days=days)

        report = {
            "report_type": "summary",
            "period_days": days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall": {
                "success_rate": success_rate,
                "total_operations": sum(
                    stats["count"] for stats in operation_stats.values()
                ),
            },
            "operations": operation_stats,
            "costs": cost_summary,
            "issues": issue_summary,
            "pull_requests": pr_summary,
            "insights": insights_data,
        }

        self.logger.info("summary_report_generated", days=days)
        return report

    def generate_detailed_report(self, days: int = 7) -> Dict[str, Any]:
        """Generate detailed report with all metrics.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with detailed report data
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")

        # Get summary data
        summary = self.generate_summary_report(days)

        # Add detailed breakdowns
        summary["detailed"] = {
            "operations_by_day": self._get_operations_by_day(since_str),
            "costs_by_day": self._get_costs_by_day(since_str),
            "errors_by_type": self._get_errors_by_type(since_str),
            "slowest_operations": self._get_slowest_operations(since_str),
            "most_expensive_operations": self._get_most_expensive_operations(since_str),
        }

        summary["report_type"] = "detailed"
        self.logger.info("detailed_report_generated", days=days)
        return summary

    def export_json(self, report: Dict[str, Any], output_file: str):
        """Export report as JSON.

        Args:
            report: Report data
            output_file: Output file path
        """
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

        self.logger.info("report_exported_json", file=output_file)

    def export_markdown(self, report: Dict[str, Any], output_file: str):
        """Export report as Markdown.

        Args:
            report: Report data
            output_file: Output file path
        """
        lines = []

        # Title
        lines.append(f"# Orchestrator Report - {report['period_days']} Days")
        lines.append(f"\nGenerated: {report['generated_at']}")
        lines.append("")

        # Overall metrics
        lines.append("## Overall Metrics")
        lines.append("")
        overall = report["overall"]
        lines.append(f"- Success Rate: {overall['success_rate']:.1%}")
        lines.append(f"- Total Operations: {overall['total_operations']}")
        lines.append("")

        # Operations
        lines.append("## Operations")
        lines.append("")
        lines.append("| Operation | Count | Success Rate | Avg Duration |")
        lines.append("|-----------|-------|--------------|--------------|")
        for op_type, stats in report["operations"].items():
            success_rate = (
                stats["success_count"] / stats["count"] if stats["count"] > 0 else 0
            )
            lines.append(
                f"| {op_type} | {stats['count']} | {success_rate:.1%} | {stats['avg_duration']:.1f}s |"
            )
        lines.append("")

        # Costs
        lines.append("## Costs")
        lines.append("")
        costs = report["costs"]
        lines.append(f"- Total Cost: ${costs['total_cost']:.2f}")
        lines.append(f"- Average per Operation: ${costs['avg_cost_per_operation']:.2f}")
        lines.append(f"- Total Tokens: {costs['total_tokens']:,}")
        lines.append("")

        # Issues
        lines.append("## Issues")
        lines.append("")
        issues = report["issues"]
        lines.append(f"- Processed: {issues['total_processed']}")
        lines.append(f"- Success Rate: {issues['success_rate']:.1%}")
        lines.append(f"- Average Duration: {issues['avg_duration']:.1f}s")
        lines.append("")

        # Pull Requests
        lines.append("## Pull Requests")
        lines.append("")
        prs = report["pull_requests"]
        lines.append(f"- Created: {prs['total_created']}")
        lines.append(f"- Merged: {prs['total_merged']}")
        lines.append(f"- Merge Rate: {prs['merge_rate']:.1%}")
        lines.append("")

        # Insights
        if "insights" in report and "recommendations" in report["insights"]:
            lines.append("## Recommendations")
            lines.append("")
            for rec in report["insights"]["recommendations"]:
                lines.append(f"- {rec}")
            lines.append("")

        # Write to file
        with open(output_file, "w") as f:
            f.write("\n".join(lines))

        self.logger.info("report_exported_markdown", file=output_file)

    def _get_operation_stats(self, since: str) -> Dict[str, Dict[str, Any]]:
        """Get operation statistics.

        Args:
            since: Start timestamp

        Returns:
            Dictionary mapping operation type to stats
        """
        results = self.database.execute(
            """
            SELECT
                operation_type,
                COUNT(*) as count,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                AVG(CASE WHEN duration_seconds IS NOT NULL
                    THEN duration_seconds ELSE 0 END) as avg_duration
            FROM operations
            WHERE started_at >= ?
            GROUP BY operation_type
        """,
            (since,),
        )

        stats = {}
        for row in results:
            op_type = (
                row.get("operation_type", "unknown")
                if hasattr(row, "get")
                else row["operation_type"]
            )
            count = row.get("count", 0) if hasattr(row, "get") else row["count"]
            success_count = (
                row.get("success_count", 0)
                if hasattr(row, "get")
                else row["success_count"]
            )
            avg_duration = (
                row.get("avg_duration", 0.0)
                if hasattr(row, "get")
                else row["avg_duration"]
            )

            stats[op_type] = {
                "count": count or 0,
                "success_count": success_count or 0,
                "avg_duration": avg_duration or 0.0,
            }

        return stats

    def _get_cost_summary(self, since: str) -> Dict[str, Any]:
        """Get cost summary.

        Args:
            since: Start timestamp

        Returns:
            Cost summary data
        """
        results = self.database.execute(
            """
            SELECT
                SUM(llm_cost) as total_cost,
                SUM(tokens_used) as total_tokens,
                COUNT(*) as operations
            FROM code_generation
            WHERE started_at >= ?
        """,
            (since,),
        )

        if results and results[0]:
            row = results[0]
            total_cost = row.get("total_cost", 0.0) or 0.0
            total_tokens = row.get("tokens_used", 0) or 0
            operations = row.get("operations", 0) or 0
            avg_cost = total_cost / operations if operations > 0 else 0.0

            return {
                "total_cost": total_cost,
                "total_tokens": total_tokens,
                "operations": operations,
                "avg_cost_per_operation": avg_cost,
            }

        return {
            "total_cost": 0.0,
            "total_tokens": 0,
            "operations": 0,
            "avg_cost_per_operation": 0.0,
        }

    def _get_issue_summary(self, since: str) -> Dict[str, Any]:
        """Get issue processing summary.

        Args:
            since: Start timestamp

        Returns:
            Issue summary data
        """
        results = self.database.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success,
                AVG(CASE WHEN duration_seconds IS NOT NULL
                    THEN duration_seconds ELSE 0 END) as avg_duration
            FROM issue_processing
            WHERE started_at >= ?
        """,
            (since,),
        )

        if results and results[0]:
            row = results[0]
            total = row.get("total", 0) or 0
            success = row.get("success", 0) or 0
            avg_duration = row.get("avg_duration", 0.0) or 0.0
            success_rate = success / total if total > 0 else 0.0

            return {
                "total_processed": total,
                "success_count": success,
                "success_rate": success_rate,
                "avg_duration": avg_duration,
            }

        return {
            "total_processed": 0,
            "success_count": 0,
            "success_rate": 0.0,
            "avg_duration": 0.0,
        }

    def _get_pr_summary(self, since: str) -> Dict[str, Any]:
        """Get PR summary.

        Args:
            since: Start timestamp

        Returns:
            PR summary data
        """
        results = self.database.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN merged = 1 THEN 1 ELSE 0 END) as merged
            FROM pr_management
            WHERE created_at >= ?
        """,
            (since,),
        )

        if results and results[0]:
            row = results[0]
            total = row.get("total", 0) or 0
            merged = row.get("merged", 0) or 0
            merge_rate = merged / total if total > 0 else 0.0

            return {
                "total_created": total,
                "total_merged": merged,
                "merge_rate": merge_rate,
            }

        return {
            "total_created": 0,
            "total_merged": 0,
            "merge_rate": 0.0,
        }

    def _get_operations_by_day(self, since: str) -> List[Dict[str, Any]]:
        """Get operations grouped by day.

        Args:
            since: Start timestamp

        Returns:
            List of daily operation counts
        """
        results = self.database.execute(
            """
            SELECT
                DATE(started_at) as day,
                COUNT(*) as operations,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
            FROM operations
            WHERE started_at >= ?
            GROUP BY DATE(started_at)
            ORDER BY day DESC
        """,
            (since,),
        )

        return [
            {
                "day": row.get("day", ""),
                "operations": row.get("operations", 0) or 0,
                "successes": row.get("successes", 0) or 0,
            }
            for row in results
        ]

    def _get_costs_by_day(self, since: str) -> List[Dict[str, Any]]:
        """Get costs grouped by day.

        Args:
            since: Start timestamp

        Returns:
            List of daily costs
        """
        results = self.database.execute(
            """
            SELECT
                DATE(started_at) as day,
                SUM(llm_cost) as cost,
                SUM(tokens_used) as tokens
            FROM code_generation
            WHERE started_at >= ?
            GROUP BY DATE(started_at)
            ORDER BY day DESC
        """,
            (since,),
        )

        return [
            {
                "day": row.get("day", ""),
                "cost": row.get("cost", 0.0) or 0.0,
                "tokens": row.get("tokens", 0) or 0,
            }
            for row in results
        ]

    def _get_errors_by_type(self, since: str) -> Dict[str, int]:
        """Get error counts by type.

        Args:
            since: Start timestamp

        Returns:
            Dictionary mapping error type to count
        """
        results = self.database.execute(
            """
            SELECT
                error_type,
                COUNT(*) as count
            FROM operations
            WHERE success = 0
              AND error_type IS NOT NULL
              AND started_at >= ?
            GROUP BY error_type
            ORDER BY count DESC
        """,
            (since,),
        )

        return {
            row.get("error_type", "unknown"): row.get("count", 0) for row in results
        }

    def _get_slowest_operations(
        self, since: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get slowest operations.

        Args:
            since: Start timestamp
            limit: Maximum number of results

        Returns:
            List of slowest operations
        """
        results = self.database.execute(
            """
            SELECT
                operation_type,
                operation_id,
                duration_seconds,
                started_at
            FROM operations
            WHERE duration_seconds IS NOT NULL
              AND started_at >= ?
            ORDER BY duration_seconds DESC
            LIMIT ?
        """,
            (since, limit),
        )

        return [
            {
                "type": row.get("operation_type", "unknown"),
                "id": row.get("operation_id", ""),
                "duration": row.get("duration_seconds", 0.0) or 0.0,
                "started_at": row.get("started_at", ""),
            }
            for row in results
        ]

    def _get_most_expensive_operations(
        self, since: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get most expensive operations.

        Args:
            since: Start timestamp
            limit: Maximum number of results

        Returns:
            List of most expensive operations
        """
        results = self.database.execute(
            """
            SELECT
                cg.operation_id,
                cg.llm_cost,
                cg.tokens_used,
                cg.started_at
            FROM code_generation cg
            WHERE cg.llm_cost IS NOT NULL
              AND cg.started_at >= ?
            ORDER BY cg.llm_cost DESC
            LIMIT ?
        """,
            (since, limit),
        )

        return [
            {
                "id": row.get("operation_id", ""),
                "cost": row.get("llm_cost", 0.0) or 0.0,
                "tokens": row.get("tokens_used", 0) or 0,
                "started_at": row.get("started_at", ""),
            }
            for row in results
        ]
