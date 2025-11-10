"""Unit tests for CostTracker."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from src.core.logger import AuditLogger
from src.safety.cost_tracker import (CostLimitExceeded, CostTracker,
                                     DailyUsage, Provider, ProviderUsage)


class TestCostTracker(unittest.TestCase):
    """Test cases for CostTracker."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)

        # Use temporary file for state
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "cost_tracker_test.json")

        self.cost_tracker = CostTracker(
            max_daily_cost=10.0,
            logger=self.logger,
            state_file=self.state_file,
        )

    def tearDown(self):
        """Clean up test fixtures."""
        # Remove temp files
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
        os.rmdir(self.temp_dir)

    def test_initialization(self):
        """Test cost tracker initialization."""
        self.assertEqual(self.cost_tracker.max_daily_cost, 10.0)
        self.assertEqual(self.cost_tracker.daily_usage.total_cost, 0.0)
        self.assertEqual(self.cost_tracker.daily_usage.total_tokens, 0)

    def test_track_request(self):
        """Test tracking a single request."""
        self.cost_tracker.track_request(
            provider=Provider.ANTHROPIC,
            tokens_input=1000,
            tokens_output=500,
        )

        # Check that usage was tracked
        usage = self.cost_tracker.daily_usage.provider_usage[Provider.ANTHROPIC]
        self.assertEqual(usage.requests, 1)
        self.assertEqual(usage.tokens_input, 1000)
        self.assertEqual(usage.tokens_output, 500)
        self.assertEqual(usage.tokens_total, 1500)
        self.assertGreater(usage.cost, 0)

        # Check total cost
        self.assertGreater(self.cost_tracker.daily_usage.total_cost, 0)
        self.assertEqual(self.cost_tracker.daily_usage.total_tokens, 1500)

    def test_track_multiple_requests(self):
        """Test tracking multiple requests."""
        self.cost_tracker.track_request(
            provider=Provider.ANTHROPIC,
            tokens_input=1000,
            tokens_output=500,
        )

        self.cost_tracker.track_request(
            provider=Provider.DEEPSEEK,
            tokens_input=2000,
            tokens_output=1000,
        )

        # Check that both providers were tracked
        self.assertIn(Provider.ANTHROPIC, self.cost_tracker.daily_usage.provider_usage)
        self.assertIn(Provider.DEEPSEEK, self.cost_tracker.daily_usage.provider_usage)

        # Check totals
        self.assertEqual(self.cost_tracker.daily_usage.total_requests, 2)
        self.assertEqual(self.cost_tracker.daily_usage.total_tokens, 4500)

    def test_cost_limit_exceeded(self):
        """Test that cost limit is enforced."""
        # Track request that exceeds limit
        with self.assertRaises(CostLimitExceeded):
            self.cost_tracker.track_request(
                provider=Provider.ANTHROPIC,
                tokens_input=1000000,  # Large number to exceed $10 limit
                tokens_output=1000000,
            )

    def test_can_afford_operation(self):
        """Test checking if operation is affordable."""
        # Should be able to afford $5 operation with $10 limit
        self.assertTrue(self.cost_tracker.can_afford_operation(5.0))

        # Track $8 worth
        self.cost_tracker.track_request(
            provider=Provider.ANTHROPIC,
            tokens_input=500000,
            tokens_output=200000,
            cost=8.0,
        )

        # Should not be able to afford $5 more
        self.assertFalse(self.cost_tracker.can_afford_operation(5.0))

        # Should be able to afford $1 more
        self.assertTrue(self.cost_tracker.can_afford_operation(1.0))

    def test_estimate_multi_agent_cost(self):
        """Test multi-agent cost estimation."""
        estimated_cost = self.cost_tracker.estimate_multi_agent_cost(
            prompt_tokens=1000,
            expected_output_tokens=500,
            num_providers=4,
        )

        # Should return positive cost for 4 providers
        self.assertGreater(estimated_cost, 0)

        # Cost for 2 providers should be less than 4
        cost_2_providers = self.cost_tracker.estimate_multi_agent_cost(
            prompt_tokens=1000,
            expected_output_tokens=500,
            num_providers=2,
        )

        self.assertLess(cost_2_providers, estimated_cost)

    def test_get_remaining_budget(self):
        """Test getting remaining budget."""
        # Initially should have full budget
        self.assertEqual(self.cost_tracker.get_remaining_budget(), 10.0)

        # Track $3 worth
        self.cost_tracker.track_request(
            provider=Provider.ANTHROPIC,
            tokens_input=200000,
            tokens_output=100000,
            cost=3.0,
        )

        # Should have $7 remaining
        self.assertEqual(self.cost_tracker.get_remaining_budget(), 7.0)

    def test_get_usage_report(self):
        """Test generating usage report."""
        # Track some usage
        self.cost_tracker.track_request(
            provider=Provider.ANTHROPIC,
            tokens_input=1000,
            tokens_output=500,
        )

        report = self.cost_tracker.get_usage_report()

        # Check report structure
        self.assertIn("date", report)
        self.assertIn("daily_limit", report)
        self.assertIn("total_cost", report)
        self.assertIn("remaining_budget", report)
        self.assertIn("percentage_used", report)
        self.assertIn("total_tokens", report)
        self.assertIn("total_requests", report)
        self.assertIn("provider_breakdown", report)
        self.assertIn("status", report)

        # Check values
        self.assertEqual(report["daily_limit"], 10.0)
        self.assertEqual(report["total_requests"], 1)
        self.assertGreater(report["total_cost"], 0)
        self.assertEqual(report["status"], "OK")

    def test_track_multi_agent_call(self):
        """Test tracking multi-agent call."""
        provider_costs = {
            "anthropic": 0.05,
            "deepseek": 0.01,
            "openai": 0.08,
            "perplexity": 0.02,
        }

        provider_tokens = {
            "anthropic": {"input": 1000, "output": 500},
            "deepseek": {"input": 1000, "output": 500},
            "openai": {"input": 1000, "output": 500},
            "perplexity": {"input": 1000, "output": 500},
        }

        self.cost_tracker.track_multi_agent_call(
            provider_costs=provider_costs,
            provider_tokens=provider_tokens,
        )

        # Check that all providers were tracked
        self.assertEqual(len(self.cost_tracker.daily_usage.provider_usage), 4)

        # Check total cost
        expected_total = sum(provider_costs.values())
        self.assertAlmostEqual(
            self.cost_tracker.daily_usage.total_cost,
            expected_total,
            places=2,
        )

    def test_state_persistence(self):
        """Test that state is persisted to disk."""
        # Track some usage
        self.cost_tracker.track_request(
            provider=Provider.ANTHROPIC,
            tokens_input=1000,
            tokens_output=500,
        )

        # Create new tracker with same state file
        new_tracker = CostTracker(
            max_daily_cost=10.0,
            logger=self.logger,
            state_file=self.state_file,
        )

        # Should have loaded the previous state
        self.assertEqual(
            new_tracker.daily_usage.total_requests,
            self.cost_tracker.daily_usage.total_requests,
        )
        self.assertEqual(
            new_tracker.daily_usage.total_cost,
            self.cost_tracker.daily_usage.total_cost,
        )

    def test_daily_usage_to_dict(self):
        """Test DailyUsage to_dict conversion."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        usage = DailyUsage(
            date=today,
            total_cost=5.0,
            total_tokens=10000,
            total_requests=5,
            started_at=datetime.now(timezone.utc),
        )

        usage_dict = usage.to_dict()

        # Check all fields are present
        self.assertEqual(usage_dict["date"], today)
        self.assertEqual(usage_dict["total_cost"], 5.0)
        self.assertEqual(usage_dict["total_tokens"], 10000)
        self.assertEqual(usage_dict["total_requests"], 5)

    def test_provider_usage_to_dict(self):
        """Test ProviderUsage to_dict conversion."""
        usage = ProviderUsage(
            provider=Provider.ANTHROPIC,
            requests=5,
            tokens_input=5000,
            tokens_output=2500,
            tokens_total=7500,
            cost=0.25,
        )

        usage_dict = usage.to_dict()

        # Check all fields
        self.assertEqual(usage_dict["provider"], "anthropic")
        self.assertEqual(usage_dict["requests"], 5)
        self.assertEqual(usage_dict["tokens_input"], 5000)
        self.assertEqual(usage_dict["tokens_output"], 2500)
        self.assertEqual(usage_dict["tokens_total"], 7500)
        self.assertEqual(usage_dict["cost"], 0.25)


if __name__ == "__main__":
    unittest.main()
