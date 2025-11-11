"""Metrics collection and tracking for orchestrator operations.

Tracks operational metrics including work items processed, success rates,
API calls, response times, and error counts.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class MetricType(Enum):
    """Types of metrics."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class Metric:
    """A single metric data point."""

    name: str
    value: float
    metric_type: MetricType
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "tags": self.tags,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class MetricsSummary:
    """Summary of collected metrics."""

    work_items_processed: int = 0
    work_items_succeeded: int = 0
    work_items_failed: int = 0
    success_rate: float = 0.0
    api_calls_total: int = 0
    api_calls_by_provider: Dict[str, int] = field(default_factory=dict)
    errors_total: int = 0
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    avg_response_time_ms: float = 0.0
    total_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "work_items_processed": self.work_items_processed,
            "work_items_succeeded": self.work_items_succeeded,
            "work_items_failed": self.work_items_failed,
            "success_rate": self.success_rate,
            "api_calls_total": self.api_calls_total,
            "api_calls_by_provider": self.api_calls_by_provider,
            "errors_total": self.errors_total,
            "errors_by_type": self.errors_by_type,
            "avg_response_time_ms": self.avg_response_time_ms,
            "total_cost": self.total_cost,
        }


class MetricsCollector:
    """Collects and aggregates operational metrics.

    Tracks:
    - Work item processing (success/failure)
    - API calls by provider
    - Response times
    - Error rates and types
    - Cost tracking
    """

    def __init__(self):
        """Initialize metrics collector."""
        self.metrics: List[Metric] = []

        # Counters
        self.counters: Dict[str, float] = defaultdict(float)

        # Gauges (current values)
        self.gauges: Dict[str, float] = {}

        # Histograms (lists of values)
        self.histograms: Dict[str, List[float]] = defaultdict(list)

        # Timers (response times)
        self.timers: Dict[str, List[float]] = defaultdict(list)
        self._active_timers: Dict[str, float] = {}

    def increment(
        self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None
    ):
        """Increment a counter metric.

        Args:
            name: Metric name
            value: Value to increment by (default 1.0)
            tags: Optional tags
        """
        self.counters[name] += value

        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.COUNTER,
            tags=tags or {},
        )
        self.metrics.append(metric)

    def gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Set a gauge metric (current value).

        Args:
            name: Metric name
            value: Current value
            tags: Optional tags
        """
        self.gauges[name] = value

        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            tags=tags or {},
        )
        self.metrics.append(metric)

    def histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record a histogram value.

        Args:
            name: Metric name
            value: Value to record
            tags: Optional tags
        """
        self.histograms[name].append(value)

        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.HISTOGRAM,
            tags=tags or {},
        )
        self.metrics.append(metric)

    def start_timer(self, name: str) -> str:
        """Start a timer.

        Args:
            name: Timer name

        Returns:
            Timer ID for stopping
        """
        timer_id = f"{name}_{time.time()}"
        self._active_timers[timer_id] = time.time()
        return timer_id

    def stop_timer(self, timer_id: str, tags: Optional[Dict[str, str]] = None) -> float:
        """Stop a timer and record duration.

        Args:
            timer_id: Timer ID from start_timer
            tags: Optional tags

        Returns:
            Duration in milliseconds
        """
        if timer_id not in self._active_timers:
            return 0.0

        start_time = self._active_timers.pop(timer_id)
        duration_ms = (time.time() - start_time) * 1000

        # Extract name from timer_id
        name = timer_id.rsplit("_", 1)[0]

        self.timers[name].append(duration_ms)

        metric = Metric(
            name=name,
            value=duration_ms,
            metric_type=MetricType.TIMER,
            tags=tags or {},
        )
        self.metrics.append(metric)

        return duration_ms

    def record_work_item_success(self, work_item_id: str):
        """Record successful work item completion.

        Args:
            work_item_id: Work item ID
        """
        self.increment("work_items_processed", tags={"status": "success"})
        self.increment("work_items_succeeded")

    def record_work_item_failure(self, work_item_id: str, error_type: str):
        """Record work item failure.

        Args:
            work_item_id: Work item ID
            error_type: Type of error
        """
        self.increment("work_items_processed", tags={"status": "failure"})
        self.increment("work_items_failed")
        self.increment("errors_total", tags={"type": error_type})

    def record_api_call(self, provider: str, success: bool = True):
        """Record API call.

        Args:
            provider: API provider name
            success: Whether call succeeded
        """
        self.increment("api_calls_total", tags={"provider": provider})
        self.increment(
            f"api_calls_{provider}",
            tags={"success": str(success).lower()},
        )

    def record_error(self, error_type: str, severity: str = "error"):
        """Record an error.

        Args:
            error_type: Type of error
            severity: Error severity (error, warning, critical)
        """
        self.increment("errors_total", tags={"type": error_type, "severity": severity})

    def record_cost(self, amount: float, provider: str, operation: str):
        """Record operation cost.

        Args:
            amount: Cost amount in USD
            provider: Provider name
            operation: Operation type
        """
        self.histogram(
            "operation_cost",
            amount,
            tags={"provider": provider, "operation": operation},
        )
        self.increment("total_cost", value=amount, tags={"provider": provider})

    def get_summary(self, time_window_hours: Optional[int] = None) -> MetricsSummary:
        """Get metrics summary.

        Args:
            time_window_hours: Optional time window in hours (None = all time)

        Returns:
            MetricsSummary
        """
        # Filter metrics by time window if specified
        metrics = self.metrics
        if time_window_hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
            metrics = [m for m in metrics if m.timestamp > cutoff]

        # Calculate work items
        work_items_processed = int(self.counters.get("work_items_processed", 0))
        work_items_succeeded = int(self.counters.get("work_items_succeeded", 0))
        work_items_failed = int(self.counters.get("work_items_failed", 0))

        # Calculate success rate
        if work_items_processed > 0:
            success_rate = work_items_succeeded / work_items_processed
        else:
            success_rate = 0.0

        # Calculate API calls by provider
        api_calls_by_provider = {}
        api_calls_total = int(self.counters.get("api_calls_total", 0))

        for key, value in self.counters.items():
            if key.startswith("api_calls_") and key != "api_calls_total":
                provider = key.replace("api_calls_", "")
                api_calls_by_provider[provider] = int(value)

        # Calculate errors by type
        errors_total = int(self.counters.get("errors_total", 0))
        errors_by_type: Dict[str, int] = {}

        for metric in metrics:
            if metric.name == "errors_total" and "type" in metric.tags:
                error_type = metric.tags["type"]
                errors_by_type[error_type] = errors_by_type.get(error_type, 0) + 1

        # Calculate average response time
        all_timers = []
        for timer_values in self.timers.values():
            all_timers.extend(timer_values)

        avg_response_time_ms = sum(all_timers) / len(all_timers) if all_timers else 0.0

        # Calculate total cost
        total_cost = self.counters.get("total_cost", 0.0)

        return MetricsSummary(
            work_items_processed=work_items_processed,
            work_items_succeeded=work_items_succeeded,
            work_items_failed=work_items_failed,
            success_rate=success_rate,
            api_calls_total=api_calls_total,
            api_calls_by_provider=api_calls_by_provider,
            errors_total=errors_total,
            errors_by_type=errors_by_type,
            avg_response_time_ms=avg_response_time_ms,
            total_cost=total_cost,
        )

    def get_counter(self, name: str) -> float:
        """Get counter value.

        Args:
            name: Counter name

        Returns:
            Counter value
        """
        return self.counters.get(name, 0.0)

    def get_gauge(self, name: str) -> Optional[float]:
        """Get gauge value.

        Args:
            name: Gauge name

        Returns:
            Gauge value or None
        """
        return self.gauges.get(name)

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """Get histogram statistics.

        Args:
            name: Histogram name

        Returns:
            Dict with min, max, avg, p50, p95, p99
        """
        values = self.histograms.get(name, [])

        if not values:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }

        sorted_values = sorted(values)
        count = len(sorted_values)

        return {
            "count": count,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "avg": sum(sorted_values) / count,
            "p50": sorted_values[int(count * 0.5)],
            "p95": sorted_values[int(count * 0.95)] if count > 1 else sorted_values[-1],
            "p99": sorted_values[int(count * 0.99)] if count > 1 else sorted_values[-1],
        }

    def reset(self):
        """Reset all metrics."""
        self.metrics.clear()
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()
        self.timers.clear()
        self._active_timers.clear()
