"""Unit tests for metrics collector."""

import unittest
import time
from src.core.metrics import MetricsCollector, Metric, MetricType, MetricsSummary


class TestMetric(unittest.TestCase):
    """Test cases for Metric."""

    def test_to_dict(self):
        """Test Metric to_dict conversion."""
        metric = Metric(
            name="test_metric",
            value=42.0,
            metric_type=MetricType.COUNTER,
            tags={"env": "test"},
        )

        metric_dict = metric.to_dict()

        self.assertEqual(metric_dict["name"], "test_metric")
        self.assertEqual(metric_dict["value"], 42.0)
        self.assertEqual(metric_dict["type"], "counter")
        self.assertEqual(metric_dict["tags"], {"env": "test"})


class TestMetricsSummary(unittest.TestCase):
    """Test cases for MetricsSummary."""

    def test_to_dict(self):
        """Test MetricsSummary to_dict conversion."""
        summary = MetricsSummary(
            work_items_processed=100,
            work_items_succeeded=90,
            work_items_failed=10,
            success_rate=0.9,
            api_calls_total=500,
        )

        summary_dict = summary.to_dict()

        self.assertEqual(summary_dict["work_items_processed"], 100)
        self.assertEqual(summary_dict["work_items_succeeded"], 90)
        self.assertEqual(summary_dict["success_rate"], 0.9)


class TestMetricsCollector(unittest.TestCase):
    """Test cases for MetricsCollector."""

    def setUp(self):
        """Set up test fixtures."""
        self.collector = MetricsCollector()

    def test_initialization(self):
        """Test collector initialization."""
        self.assertIsNotNone(self.collector.counters)
        self.assertIsNotNone(self.collector.gauges)
        self.assertIsNotNone(self.collector.histograms)
        self.assertIsNotNone(self.collector.timers)

    def test_increment_counter(self):
        """Test incrementing a counter."""
        self.collector.increment("test_counter", value=5.0)

        self.assertEqual(self.collector.get_counter("test_counter"), 5.0)

        # Increment again
        self.collector.increment("test_counter", value=3.0)

        self.assertEqual(self.collector.get_counter("test_counter"), 8.0)

    def test_increment_counter_default_value(self):
        """Test incrementing counter with default value."""
        self.collector.increment("test_counter")

        self.assertEqual(self.collector.get_counter("test_counter"), 1.0)

    def test_gauge(self):
        """Test setting a gauge."""
        self.collector.gauge("memory_usage", 75.5)

        self.assertEqual(self.collector.get_gauge("memory_usage"), 75.5)

        # Update gauge
        self.collector.gauge("memory_usage", 80.0)

        self.assertEqual(self.collector.get_gauge("memory_usage"), 80.0)

    def test_histogram(self):
        """Test recording histogram values."""
        self.collector.histogram("response_time", 100.0)
        self.collector.histogram("response_time", 150.0)
        self.collector.histogram("response_time", 200.0)

        stats = self.collector.get_histogram_stats("response_time")

        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["min"], 100.0)
        self.assertEqual(stats["max"], 200.0)
        self.assertEqual(stats["avg"], 150.0)

    def test_histogram_empty(self):
        """Test histogram stats when empty."""
        stats = self.collector.get_histogram_stats("nonexistent")

        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["min"], 0.0)
        self.assertEqual(stats["max"], 0.0)

    def test_timer(self):
        """Test timer functionality."""
        timer_id = self.collector.start_timer("operation")

        # Simulate some work
        time.sleep(0.01)

        duration = self.collector.stop_timer(timer_id)

        self.assertGreater(duration, 0.0)
        self.assertIn("operation", self.collector.timers)

    def test_timer_invalid_id(self):
        """Test stopping timer with invalid ID."""
        duration = self.collector.stop_timer("invalid_timer_id")

        self.assertEqual(duration, 0.0)

    def test_record_work_item_success(self):
        """Test recording work item success."""
        self.collector.record_work_item_success("work-123")

        self.assertEqual(self.collector.get_counter("work_items_processed"), 1.0)
        self.assertEqual(self.collector.get_counter("work_items_succeeded"), 1.0)

    def test_record_work_item_failure(self):
        """Test recording work item failure."""
        self.collector.record_work_item_failure("work-123", "validation_error")

        self.assertEqual(self.collector.get_counter("work_items_processed"), 1.0)
        self.assertEqual(self.collector.get_counter("work_items_failed"), 1.0)
        self.assertEqual(self.collector.get_counter("errors_total"), 1.0)

    def test_record_api_call(self):
        """Test recording API call."""
        self.collector.record_api_call("anthropic", success=True)
        self.collector.record_api_call("openai", success=True)

        self.assertEqual(self.collector.get_counter("api_calls_total"), 2.0)
        self.assertEqual(self.collector.get_counter("api_calls_anthropic"), 1.0)
        self.assertEqual(self.collector.get_counter("api_calls_openai"), 1.0)

    def test_record_error(self):
        """Test recording errors."""
        self.collector.record_error("timeout", severity="error")
        self.collector.record_error("rate_limit", severity="warning")

        self.assertEqual(self.collector.get_counter("errors_total"), 2.0)

    def test_record_cost(self):
        """Test recording operation cost."""
        self.collector.record_cost(0.05, "anthropic", "code_generation")
        self.collector.record_cost(0.03, "anthropic", "code_review")

        self.assertEqual(self.collector.get_counter("total_cost"), 0.08)

    def test_get_summary(self):
        """Test getting metrics summary."""
        # Record some metrics
        self.collector.record_work_item_success("work-1")
        self.collector.record_work_item_success("work-2")
        self.collector.record_work_item_failure("work-3", "test_error")

        self.collector.record_api_call("anthropic")
        self.collector.record_api_call("openai")

        self.collector.record_cost(0.05, "anthropic", "generation")

        summary = self.collector.get_summary()

        self.assertEqual(summary.work_items_processed, 3)
        self.assertEqual(summary.work_items_succeeded, 2)
        self.assertEqual(summary.work_items_failed, 1)
        self.assertAlmostEqual(summary.success_rate, 2 / 3)
        self.assertEqual(summary.api_calls_total, 2)
        self.assertEqual(summary.total_cost, 0.05)

    def test_get_summary_success_rate_zero(self):
        """Test success rate when no work items."""
        summary = self.collector.get_summary()

        self.assertEqual(summary.success_rate, 0.0)

    def test_get_summary_api_calls_by_provider(self):
        """Test API calls breakdown by provider."""
        self.collector.record_api_call("anthropic")
        self.collector.record_api_call("anthropic")
        self.collector.record_api_call("openai")

        summary = self.collector.get_summary()

        self.assertEqual(summary.api_calls_total, 3)
        self.assertIn("anthropic", summary.api_calls_by_provider)
        self.assertEqual(summary.api_calls_by_provider["anthropic"], 2)

    def test_reset(self):
        """Test resetting all metrics."""
        # Add some metrics
        self.collector.increment("test_counter", 10.0)
        self.collector.gauge("test_gauge", 50.0)
        self.collector.histogram("test_histogram", 100.0)

        # Reset
        self.collector.reset()

        # Verify all cleared
        self.assertEqual(self.collector.get_counter("test_counter"), 0.0)
        self.assertIsNone(self.collector.get_gauge("test_gauge"))
        stats = self.collector.get_histogram_stats("test_histogram")
        self.assertEqual(stats["count"], 0)

    def test_metrics_with_tags(self):
        """Test metrics with tags."""
        self.collector.increment("requests", tags={"endpoint": "/api/v1"})
        self.collector.increment("requests", tags={"endpoint": "/api/v2"})

        # Both should increment the same counter
        self.assertEqual(self.collector.get_counter("requests"), 2.0)

    def test_histogram_percentiles(self):
        """Test histogram percentile calculations."""
        # Add 100 values
        for i in range(100):
            self.collector.histogram("latency", float(i))

        stats = self.collector.get_histogram_stats("latency")

        self.assertEqual(stats["count"], 100)
        self.assertEqual(stats["min"], 0.0)
        self.assertEqual(stats["max"], 99.0)
        self.assertAlmostEqual(stats["avg"], 49.5, delta=0.1)
        self.assertAlmostEqual(stats["p50"], 50.0, delta=1.0)
        self.assertAlmostEqual(stats["p95"], 95.0, delta=1.0)
        self.assertAlmostEqual(stats["p99"], 99.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
