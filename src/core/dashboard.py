"""Performance dashboard for monitoring orchestrator operations.

Provides real-time and historical metrics visualization via CLI.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .analytics import AnalyticsCollector, InsightsGenerator
from .cache import CacheManager
from .database import Database
from .logger import AuditLogger


@dataclass
class DashboardMetrics:
    """Aggregated metrics for dashboard display."""

    # Overview
    status: str
    mode: str
    uptime_seconds: float

    # Activity (today)
    issues_processed_today: int
    issues_success_today: int
    issues_failed_today: int
    prs_merged_today: int
    api_cost_today: float

    # Success rates
    success_rate_7d: float
    success_rate_30d: float

    # Performance
    avg_operation_duration: float
    cache_hit_rate: float
    error_rate: float

    # Costs
    total_cost_7d: float
    total_cost_30d: float
    cost_per_operation: float
    monthly_projection: float

    # Quality
    test_pass_rate: float
    avg_complexity: float

    # Current work
    active_operations: List[Dict[str, Any]]
    recent_operations: List[Dict[str, Any]]


class Dashboard:
    """Performance dashboard for orchestrator monitoring.

    Responsibilities:
    - Aggregate metrics from multiple sources
    - Format data for CLI display
    - Calculate KPIs and trends
    - Provide real-time status
    """

    def __init__(
        self,
        database: Database,
        analytics: AnalyticsCollector,
        insights: InsightsGenerator,
        cache_manager: Optional[CacheManager],
        logger: AuditLogger,
        start_time: Optional[datetime] = None,
    ):
        """Initialize dashboard.

        Args:
            database: Database instance
            analytics: Analytics collector
            insights: Insights generator
            cache_manager: Optional cache manager for cache metrics
            logger: Audit logger
            start_time: Orchestrator start time (for uptime)
        """
        self.database = database
        self.analytics = analytics
        self.insights = insights
        self.cache_manager = cache_manager
        self.logger = logger
        self.start_time = start_time or datetime.now(timezone.utc)

    def get_metrics(self) -> DashboardMetrics:
        """Get all dashboard metrics.

        Returns:
            DashboardMetrics with aggregated data
        """
        now = datetime.now(timezone.utc)

        # Calculate uptime
        uptime = (now - self.start_time).total_seconds()

        # Get today's activity
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_activity = self._get_today_activity(today_start)

        # Get success rates
        success_rate_7d = self.analytics.get_success_rate(days=7)
        success_rate_30d = self.analytics.get_success_rate(days=30)

        # Get performance metrics
        perf_metrics = self._get_performance_metrics()

        # Get cost metrics
        cost_metrics = self._get_cost_metrics()

        # Get quality metrics
        quality_metrics = self._get_quality_metrics()

        # Get current and recent operations
        active_ops = self._get_active_operations()
        recent_ops = self._get_recent_operations(limit=5)

        return DashboardMetrics(
            status="running",
            mode="autonomous",
            uptime_seconds=uptime,
            issues_processed_today=today_activity["total"],
            issues_success_today=today_activity["success"],
            issues_failed_today=today_activity["failed"],
            prs_merged_today=today_activity["prs_merged"],
            api_cost_today=today_activity["cost"],
            success_rate_7d=success_rate_7d,
            success_rate_30d=success_rate_30d,
            avg_operation_duration=perf_metrics["avg_duration"],
            cache_hit_rate=perf_metrics["cache_hit_rate"],
            error_rate=perf_metrics["error_rate"],
            total_cost_7d=cost_metrics["cost_7d"],
            total_cost_30d=cost_metrics["cost_30d"],
            cost_per_operation=cost_metrics["cost_per_operation"],
            monthly_projection=cost_metrics["monthly_projection"],
            test_pass_rate=quality_metrics["test_pass_rate"],
            avg_complexity=quality_metrics["avg_complexity"],
            active_operations=active_ops,
            recent_operations=recent_ops,
        )

    def _get_today_activity(self, today_start: datetime) -> Dict[str, Any]:
        """Get today's activity statistics.

        Args:
            today_start: Start of today

        Returns:
            Dictionary with today's activity
        """
        today_str = today_start.strftime("%Y-%m-%d %H:%M:%S")

        # Get issue processing stats
        results = self.database.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed
            FROM issue_processing
            WHERE created_at >= ?
        """,
            (today_str,),
        )

        row = results[0] if results else {}
        total = row["total"] if row else 0
        success = row["success"] if row and row["success"] else 0
        failed = row["failed"] if row and row["failed"] else 0

        # Get PR merges (assuming stored in pr_management table)
        pr_results = self.database.execute(
            """
            SELECT COUNT(*) as merged
            FROM pr_management
            WHERE merged = 1 AND created_at >= ?
        """,
            (today_str,),
        )

        prs_merged = (
            pr_results[0]["merged"] if pr_results and pr_results[0]["merged"] else 0
        )

        # Get API costs
        cost_results = self.database.execute(
            """
            SELECT SUM(cost) as total_cost
            FROM code_generation
            WHERE created_at >= ?
        """,
            (today_str,),
        )

        cost = (
            cost_results[0]["total_cost"]
            if cost_results and cost_results[0]["total_cost"]
            else 0.0
        )

        return {
            "total": total or 0,
            "success": success or 0,
            "failed": failed or 0,
            "prs_merged": prs_merged or 0,
            "cost": cost or 0.0,
        }

    def _get_performance_metrics(self) -> Dict[str, float]:
        """Get performance metrics.

        Returns:
            Dictionary with performance data
        """
        # Get average operation duration
        results = self.database.execute(
            """
            SELECT AVG(duration_seconds) as avg_duration
            FROM operations
            WHERE duration_seconds IS NOT NULL
              AND started_at >= datetime('now', '-7 days')
        """,
            (),
        )

        avg_duration = (
            results[0]["avg_duration"]
            if results and results[0]["avg_duration"]
            else 0.0
        )

        # Get cache hit rate
        cache_hit_rate = 0.0
        if self.cache_manager:
            metrics = self.cache_manager.get_metrics("dashboard")
            cache_hit_rate = metrics.hit_rate

        # Get error rate
        error_results = self.database.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors
            FROM operations
            WHERE started_at >= datetime('now', '-7 days')
        """,
            (),
        )

        if error_results and error_results[0]["total"]:
            total = error_results[0]["total"]
            errors = error_results[0]["errors"] if error_results[0]["errors"] else 0
            error_rate = errors / total
        else:
            error_rate = 0.0

        return {
            "avg_duration": avg_duration or 0.0,
            "cache_hit_rate": cache_hit_rate,
            "error_rate": error_rate,
        }

    def _get_cost_metrics(self) -> Dict[str, float]:
        """Get cost metrics.

        Returns:
            Dictionary with cost data
        """
        # Get 7-day cost
        results_7d = self.database.execute(
            """
            SELECT SUM(cost) as total_cost, COUNT(*) as operations
            FROM code_generation
            WHERE created_at >= datetime('now', '-7 days')
        """,
            (),
        )

        cost_7d = (
            results_7d[0]["total_cost"]
            if results_7d and results_7d[0]["total_cost"]
            else 0.0
        )
        ops_7d = (
            results_7d[0]["operations"]
            if results_7d and results_7d[0]["operations"]
            else 0
        )

        # Get 30-day cost
        results_30d = self.database.execute(
            """
            SELECT SUM(cost) as total_cost
            FROM code_generation
            WHERE created_at >= datetime('now', '-30 days')
        """,
            (),
        )

        cost_30d = (
            results_30d[0]["total_cost"]
            if results_30d and results_30d[0]["total_cost"]
            else 0.0
        )

        # Calculate cost per operation
        cost_per_op = (cost_7d / ops_7d) if ops_7d > 0 else 0.0

        # Project monthly cost (based on last 7 days)
        daily_avg = cost_7d / 7.0 if cost_7d else 0.0
        monthly_projection = daily_avg * 30.0

        return {
            "cost_7d": cost_7d or 0.0,
            "cost_30d": cost_30d or 0.0,
            "cost_per_operation": cost_per_op,
            "monthly_projection": monthly_projection,
        }

    def _get_quality_metrics(self) -> Dict[str, float]:
        """Get quality metrics.

        Returns:
            Dictionary with quality data
        """
        # Get test pass rate from code_generation using test_pass_rate column
        test_results = self.database.execute(
            """
            SELECT
                COUNT(*) as total,
                AVG(test_pass_rate) as avg_pass_rate
            FROM code_generation
            WHERE test_pass_rate IS NOT NULL
              AND created_at >= datetime('now', '-7 days')
        """,
            (),
        )

        if test_results and test_results[0]["total"]:
            test_pass_rate = test_results[0]["avg_pass_rate"] or 0.0
        else:
            test_pass_rate = 0.0

        # Get average complexity from issue_processing using complexity column
        complexity_results = self.database.execute(
            """
            SELECT AVG(complexity) as avg_complexity
            FROM issue_processing
            WHERE complexity IS NOT NULL
              AND created_at >= datetime('now', '-7 days')
        """,
            (),
        )

        avg_complexity = (
            complexity_results[0]["avg_complexity"]
            if complexity_results and complexity_results[0]["avg_complexity"]
            else 0.0
        )

        return {
            "test_pass_rate": test_pass_rate,
            "avg_complexity": avg_complexity or 0.0,
        }

    def _get_active_operations(self) -> List[Dict[str, Any]]:
        """Get currently active operations.

        Returns:
            List of active operation details
        """
        # In a real implementation, this would track in-progress operations
        # For now, we'll return recently started operations that haven't completed
        results = self.database.execute(
            """
            SELECT
                operation_type,
                operation_id,
                started_at,
                context
            FROM operations
            WHERE completed_at IS NULL
              AND started_at >= datetime('now', '-1 hour')
            ORDER BY started_at DESC
            LIMIT 5
        """,
            (),
        )

        operations = []
        for row in results:
            operations.append(
                {
                    "type": row["operation_type"] or "unknown",
                    "id": row["operation_id"] or "",
                    "started_at": row["started_at"] or "",
                    "context": row["context"] or "",
                }
            )

        return operations

    def _get_recent_operations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recently completed operations.

        Args:
            limit: Maximum number of operations to return

        Returns:
            List of recent operation details
        """
        results = self.database.execute(
            """
            SELECT
                operation_type,
                operation_id,
                started_at,
                completed_at,
                success,
                duration_seconds
            FROM operations
            WHERE completed_at IS NOT NULL
            ORDER BY completed_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        operations = []
        for row in results:
            operations.append(
                {
                    "type": row["operation_type"] or "unknown",
                    "id": row["operation_id"] or "",
                    "started_at": row["started_at"] or "",
                    "completed_at": row["completed_at"] or "",
                    "success": bool(row["success"]),
                    "duration": row["duration_seconds"] or 0.0,
                }
            )

        return operations

    def format_cli(self, metrics: DashboardMetrics) -> str:
        """Format metrics for CLI display.

        Args:
            metrics: Dashboard metrics

        Returns:
            Formatted string for CLI output
        """
        # Calculate uptime string
        uptime_str = self._format_uptime(metrics.uptime_seconds)

        # Format health status
        health = "✅ All systems operational"
        if metrics.error_rate > 0.2:
            health = "⚠️  High error rate detected"
        elif metrics.success_rate_7d < 0.7:
            health = "⚠️  Success rate below target"

        # Build dashboard
        lines = []
        lines.append(
            "┌─ Self-Reflexive Orchestrator Dashboard ────────────────────────┐"
        )
        lines.append(
            f"│ Status: {metrics.status.capitalize():20s} Mode: {metrics.mode} │"
        )
        lines.append(f"│ Uptime: {uptime_str:53s} │")
        lines.append(
            "│                                                                 │"
        )
        lines.append(
            "│ Today:                                                          │"
        )
        lines.append(
            f"│  • Issues processed: {metrics.issues_processed_today:2d} "
            f"({metrics.issues_success_today:2d} success, {metrics.issues_failed_today:2d} failed)       │"
        )
        lines.append(
            f"│  • PRs merged: {metrics.prs_merged_today:2d}                                            │"
        )
        lines.append(
            f"│  • API cost: ${metrics.api_cost_today:6.2f} / $50.00                        │"
        )
        lines.append(
            "│                                                                 │"
        )
        lines.append(
            "│ Performance (7 days):                                           │"
        )
        lines.append(
            f"│  • Success rate: {metrics.success_rate_7d*100:5.1f}%                                    │"
        )
        lines.append(
            f"│  • Avg operation time: {metrics.avg_operation_duration:5.1f}s                          │"
        )
        lines.append(
            f"│  • Cache hit rate: {metrics.cache_hit_rate*100:5.1f}%                                  │"
        )
        lines.append(
            f"│  • Error rate: {metrics.error_rate*100:5.1f}%                                         │"
        )
        lines.append(
            "│                                                                 │"
        )
        lines.append(
            "│ Costs:                                                          │"
        )
        lines.append(
            f"│  • Last 7 days: ${metrics.total_cost_7d:6.2f}                                   │"
        )
        lines.append(
            f"│  • Last 30 days: ${metrics.total_cost_30d:6.2f}                                  │"
        )
        lines.append(
            f"│  • Monthly projection: ${metrics.monthly_projection:6.2f}                           │"
        )
        lines.append(
            "│                                                                 │"
        )

        # Show active operations
        if metrics.active_operations:
            lines.append(
                "│ Current Work:                                                   │"
            )
            for op in metrics.active_operations[:2]:  # Show max 2
                op_type = op["type"][:20]
                op_id = op["id"][:15] if op["id"] else "N/A"
                lines.append(f"│  • {op_type}: {op_id:15s}                       │")
        else:
            lines.append(
                "│ Current Work: None                                              │"
            )

        lines.append(
            "│                                                                 │"
        )
        lines.append(f"│ Health: {health:56s}│")
        lines.append(
            "└─────────────────────────────────────────────────────────────────┘"
        )

        return "\n".join(lines)

    def _format_uptime(self, seconds: float) -> str:
        """Format uptime as human-readable string.

        Args:
            seconds: Uptime in seconds

        Returns:
            Formatted uptime string
        """
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)

        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
