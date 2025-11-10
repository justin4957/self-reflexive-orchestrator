"""Pattern detection for identifying recurring failures.

Analyzes failure history to identify patterns that warrant learning interventions.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import Database
from .logger import AuditLogger


@dataclass
class FailurePattern:
    """Represents a detected failure pattern."""

    pattern_id: str
    failure_type: str
    error_type: str
    occurrence_count: int
    first_seen: datetime
    last_seen: datetime
    failure_examples: List[Dict[str, Any]]
    success_examples: List[Dict[str, Any]]
    common_attributes: Dict[str, Any]
    severity: str  # "low", "medium", "high", "critical"


class PatternDetector:
    """Detects recurring failure patterns from analytics data.

    Responsibilities:
    - Query failed operations from database
    - Group failures by similarity
    - Identify patterns with 3+ occurrences
    - Compare failures with similar successes
    - Categorize pattern severity
    """

    def __init__(
        self,
        database: Database,
        logger: AuditLogger,
        min_occurrences: int = 3,
        lookback_days: int = 30,
    ):
        """Initialize pattern detector.

        Args:
            database: Database instance for querying analytics
            logger: Audit logger instance
            min_occurrences: Minimum occurrences to consider a pattern
            lookback_days: How far back to look for patterns
        """
        self.database = database
        self.logger = logger
        self.min_occurrences = min_occurrences
        self.lookback_days = lookback_days

    def detect_patterns(self) -> List[FailurePattern]:
        """Detect all failure patterns in recent history.

        Returns:
            List of detected failure patterns
        """
        self.logger.info(
            "pattern_detection_started",
            min_occurrences=self.min_occurrences,
            lookback_days=self.lookback_days,
        )

        # Get all failures in lookback period
        failures = self._get_recent_failures()

        if not failures:
            self.logger.info("pattern_detection_completed", patterns_found=0)
            return []

        # Group failures by similarity
        grouped_failures = self._group_failures(failures)

        # Identify patterns with enough occurrences
        patterns = []
        for group_key, failure_group in grouped_failures.items():
            if len(failure_group) >= self.min_occurrences:
                pattern = self._create_pattern(group_key, failure_group)
                patterns.append(pattern)

        self.logger.info(
            "pattern_detection_completed",
            patterns_found=len(patterns),
            total_failures=len(failures),
        )

        return patterns

    def _get_recent_failures(self) -> List[Dict[str, Any]]:
        """Get all failed operations in lookback period.

        Returns:
            List of failed operation records
        """
        since = (
            datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        ).strftime("%Y-%m-%d %H:%M:%S")

        results = self.database.execute(
            """
            SELECT
                id, operation_type, operation_id, started_at, completed_at,
                error_message, error_type, retry_count, context
            FROM operations
            WHERE success = 0
              AND started_at >= ?
            ORDER BY started_at DESC
            """,
            (since,),
        )

        return [dict(row) for row in results]

    def _group_failures(
        self, failures: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group failures by similarity.

        Groups based on: operation_type + error_type

        Args:
            failures: List of failure records

        Returns:
            Dictionary mapping group key to list of failures
        """
        grouped = defaultdict(list)

        for failure in failures:
            # Create group key from operation type and error type
            operation_type = failure.get("operation_type", "unknown")
            error_type = failure.get("error_type", "unknown")
            group_key = f"{operation_type}::{error_type}"

            grouped[group_key].append(failure)

        return dict(grouped)

    def _create_pattern(
        self, group_key: str, failures: List[Dict[str, Any]]
    ) -> FailurePattern:
        """Create a FailurePattern from grouped failures.

        Args:
            group_key: The grouping key
            failures: List of failure records in this group

        Returns:
            FailurePattern instance
        """
        operation_type, error_type = group_key.split("::", 1)

        # Get timestamps
        timestamps = [
            (
                datetime.strptime(f["started_at"], "%Y-%m-%d %H:%M:%S")
                if isinstance(f["started_at"], str)
                else f["started_at"]
            )
            for f in failures
        ]
        first_seen = min(timestamps)
        last_seen = max(timestamps)

        # Find common attributes
        common_attrs = self._find_common_attributes(failures)

        # Get success examples for comparison
        success_examples = self._get_similar_successes(operation_type, limit=5)

        # Determine severity
        severity = self._calculate_severity(len(failures), first_seen, last_seen)

        # Create pattern ID
        pattern_id = (
            f"pattern_{operation_type}_{error_type}_{int(first_seen.timestamp())}"
        )

        return FailurePattern(
            pattern_id=pattern_id,
            failure_type=operation_type,
            error_type=error_type,
            occurrence_count=len(failures),
            first_seen=first_seen,
            last_seen=last_seen,
            failure_examples=failures[:10],  # Limit to 10 examples
            success_examples=success_examples,
            common_attributes=common_attrs,
            severity=severity,
        )

    def _find_common_attributes(self, failures: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Find attributes common across all failures in group.

        Args:
            failures: List of failure records

        Returns:
            Dictionary of common attributes
        """
        common = {
            "error_messages": [],
            "retry_counts": [],
            "operation_ids": [],
        }

        for failure in failures:
            if failure.get("error_message"):
                common["error_messages"].append(failure["error_message"])
            if failure.get("retry_count") is not None:
                common["retry_counts"].append(failure["retry_count"])
            if failure.get("operation_id"):
                common["operation_ids"].append(failure["operation_id"])

        # Find most common error message pattern
        if common["error_messages"]:
            # Simple approach: take the first few words of most common message
            from collections import Counter

            message_patterns = [
                " ".join(msg.split()[:10]) for msg in common["error_messages"]
            ]
            most_common = Counter(message_patterns).most_common(1)[0][0]
            common["common_error_pattern"] = most_common

        # Calculate average retry count
        if common["retry_counts"]:
            common["avg_retry_count"] = sum(common["retry_counts"]) / len(
                common["retry_counts"]
            )

        return common

    def _get_similar_successes(
        self, operation_type: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get successful operations of the same type for comparison.

        Args:
            operation_type: Type of operation
            limit: Maximum number of successes to return

        Returns:
            List of successful operation records
        """
        results = self.database.execute(
            """
            SELECT
                id, operation_type, operation_id, started_at, completed_at,
                duration_seconds, context
            FROM operations
            WHERE success = 1
              AND operation_type = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (operation_type, limit),
        )

        return [dict(row) for row in results]

    def _calculate_severity(
        self, occurrence_count: int, first_seen: datetime, last_seen: datetime
    ) -> str:
        """Calculate severity of failure pattern.

        Args:
            occurrence_count: Number of occurrences
            first_seen: First occurrence timestamp
            last_seen: Last occurrence timestamp

        Returns:
            Severity string: "low", "medium", "high", "critical"
        """
        # Calculate failure rate (occurrences per day)
        time_span = (last_seen - first_seen).total_seconds() / 86400  # days
        if time_span < 0.1:  # Less than 2.4 hours
            time_span = 0.1  # Avoid division by zero

        failure_rate = occurrence_count / time_span

        # Determine severity
        if failure_rate >= 5:  # 5+ failures per day
            return "critical"
        elif failure_rate >= 2:  # 2-5 failures per day
            return "high"
        elif failure_rate >= 0.5:  # 0.5-2 failures per day
            return "medium"
        else:
            return "low"

    def get_pattern_details(self, pattern_id: str) -> Optional[FailurePattern]:
        """Get details for a specific pattern.

        Args:
            pattern_id: Pattern identifier

        Returns:
            FailurePattern if found, None otherwise
        """
        patterns = self.detect_patterns()
        for pattern in patterns:
            if pattern.pattern_id == pattern_id:
                return pattern
        return None

    def get_patterns_by_severity(self, severity: str) -> List[FailurePattern]:
        """Get all patterns of a specific severity.

        Args:
            severity: Severity level to filter by

        Returns:
            List of patterns matching severity
        """
        all_patterns = self.detect_patterns()
        return [p for p in all_patterns if p.severity == severity]

    def should_trigger_learning(self, pattern: FailurePattern) -> bool:
        """Determine if a pattern should trigger learning intervention.

        Args:
            pattern: Pattern to evaluate

        Returns:
            True if learning should be triggered
        """
        # Trigger for high or critical severity
        if pattern.severity in ["high", "critical"]:
            return True

        # Trigger if pattern is persistent (seen over multiple days)
        time_span = (pattern.last_seen - pattern.first_seen).total_seconds() / 86400
        if time_span >= 3 and pattern.occurrence_count >= self.min_occurrences:
            return True

        return False
