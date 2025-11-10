"""Unit tests for RateLimiter."""

import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from src.core.logger import AuditLogger
from src.safety.rate_limiter import RateLimiter, RateLimitExceeded, RateLimitInfo


class TestRateLimiter(unittest.TestCase):
    """Test cases for RateLimiter."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)

        # Use temporary file for state
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "rate_limiter_test.json")

        self.rate_limiter = RateLimiter(
            logger=self.logger,
            enable_throttling=False,  # Disable throttling for tests
            state_file=self.state_file,
        )

    def tearDown(self):
        """Clean up test fixtures."""
        # Remove all temp files in directory
        import glob

        for file in glob.glob(os.path.join(self.temp_dir, "*")):
            if os.path.isfile(file):
                os.remove(file)

        # Remove temp directory
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_initialization(self):
        """Test rate limiter initialization."""
        self.assertEqual(self.rate_limiter.enable_throttling, False)
        self.assertEqual(len(self.rate_limiter.rate_limits), 0)

    def test_update_rate_limit(self):
        """Test updating rate limit information."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        self.rate_limiter.update_rate_limit(
            api="github",
            limit=5000,
            remaining=4500,
            reset_time=reset_time,
        )

        # Check that rate limit was updated
        self.assertIn("github", self.rate_limiter.rate_limits)
        limit_info = self.rate_limiter.rate_limits["github"]

        self.assertEqual(limit_info.limit, 5000)
        self.assertEqual(limit_info.remaining, 4500)
        self.assertEqual(limit_info.used, 500)
        self.assertEqual(limit_info.reset_time, reset_time)

    def test_check_rate_limit_ok(self):
        """Test checking rate limit when OK."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        self.rate_limiter.update_rate_limit(
            api="github",
            limit=5000,
            remaining=4500,
            reset_time=reset_time,
        )

        # Should not raise exception
        result = self.rate_limiter.check_rate_limit("github", required_requests=10)
        self.assertTrue(result)

    def test_check_rate_limit_exceeded(self):
        """Test checking rate limit when exceeded."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        self.rate_limiter.update_rate_limit(
            api="github",
            limit=5000,
            remaining=5,  # Very few remaining
            reset_time=reset_time,
        )

        # Should raise exception when requesting more than remaining
        with self.assertRaises(RateLimitExceeded):
            self.rate_limiter.check_rate_limit("github", required_requests=10)

    def test_check_rate_limit_no_info(self):
        """Test checking rate limit when no info available."""
        # Should not raise exception when no rate limit info
        result = self.rate_limiter.check_rate_limit("unknown_api")
        self.assertTrue(result)

    def test_track_request(self):
        """Test tracking a request."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        self.rate_limiter.update_rate_limit(
            api="github",
            limit=5000,
            remaining=4500,
            reset_time=reset_time,
        )

        # Track a request
        self.rate_limiter.track_request("github", requests_used=1)

        # Check that remaining decreased
        limit_info = self.rate_limiter.rate_limits["github"]
        self.assertEqual(limit_info.remaining, 4499)
        self.assertEqual(limit_info.used, 501)

    def test_get_status_single_api(self):
        """Test getting status for a single API."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        self.rate_limiter.update_rate_limit(
            api="github",
            limit=5000,
            remaining=4500,
            reset_time=reset_time,
        )

        status = self.rate_limiter.get_status("github")

        # Check status structure
        self.assertEqual(status["api"], "github")
        self.assertEqual(status["status"], "ok")
        self.assertIsNotNone(status["info"])

        info = status["info"]
        self.assertEqual(info["limit"], 5000)
        self.assertEqual(info["remaining"], 4500)

    def test_get_status_all_apis(self):
        """Test getting status for all APIs."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        self.rate_limiter.update_rate_limit(
            api="github",
            limit=5000,
            remaining=4500,
            reset_time=reset_time,
        )

        self.rate_limiter.update_rate_limit(
            api="anthropic",
            limit=10000,
            remaining=9000,
            reset_time=reset_time,
        )

        status = self.rate_limiter.get_status()

        # Check that both APIs are in status
        self.assertIn("apis", status)
        self.assertIn("github", status["apis"])
        self.assertIn("anthropic", status["apis"])
        self.assertEqual(status["throttling_enabled"], False)

    def test_rate_limit_info_percentage(self):
        """Test RateLimitInfo percentage calculation."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        limit_info = RateLimitInfo(
            limit=1000,
            remaining=800,
            used=200,
            reset_time=reset_time,
        )

        self.assertEqual(limit_info.percentage_used, 20.0)

    def test_rate_limit_info_time_until_reset(self):
        """Test RateLimitInfo time until reset."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        limit_info = RateLimitInfo(
            limit=1000,
            remaining=800,
            used=200,
            reset_time=reset_time,
        )

        # Should be approximately 3600 seconds
        self.assertGreater(limit_info.seconds_until_reset, 3500)
        self.assertLess(limit_info.seconds_until_reset, 3700)

    def test_state_persistence(self):
        """Test that state is persisted to disk."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        self.rate_limiter.update_rate_limit(
            api="github",
            limit=5000,
            remaining=4500,
            reset_time=reset_time,
        )

        # Create new limiter with same state file
        new_limiter = RateLimiter(
            logger=self.logger,
            enable_throttling=False,
            state_file=self.state_file,
        )

        # Should have loaded the previous state
        self.assertIn("github", new_limiter.rate_limits)
        limit_info = new_limiter.rate_limits["github"]
        self.assertEqual(limit_info.limit, 5000)
        self.assertEqual(limit_info.remaining, 4500)

    def test_rate_limit_info_to_dict(self):
        """Test RateLimitInfo to_dict conversion."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        limit_info = RateLimitInfo(
            limit=5000,
            remaining=4500,
            used=500,
            reset_time=reset_time,
        )

        info_dict = limit_info.to_dict()

        # Check all fields
        self.assertEqual(info_dict["limit"], 5000)
        self.assertEqual(info_dict["remaining"], 4500)
        self.assertEqual(info_dict["used"], 500)
        self.assertEqual(info_dict["percentage_used"], 10.0)
        self.assertIn("reset_time", info_dict)
        self.assertIn("seconds_until_reset", info_dict)

    @patch("time.sleep")
    def test_wait_if_needed_warning(self, mock_sleep):
        """Test throttling at warning threshold."""
        # Enable throttling for this test
        limiter = RateLimiter(
            logger=self.logger,
            enable_throttling=True,
            state_file=self.state_file + ".throttle",
        )

        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        # Set to warning threshold (80%)
        limiter.update_rate_limit(
            api="github",
            limit=1000,
            remaining=200,  # 80% used
            reset_time=reset_time,
        )

        # Should trigger warning throttle
        limiter.wait_if_needed("github")

        # Check that sleep was called
        mock_sleep.assert_called_once()

    @patch("time.sleep")
    def test_wait_if_needed_critical(self, mock_sleep):
        """Test throttling at critical threshold."""
        # Enable throttling for this test
        limiter = RateLimiter(
            logger=self.logger,
            enable_throttling=True,
            state_file=self.state_file + ".critical",
        )

        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        # Set to critical threshold (95%)
        limiter.update_rate_limit(
            api="github",
            limit=1000,
            remaining=50,  # 95% used
            reset_time=reset_time,
        )

        # Should trigger critical throttle
        limiter.wait_if_needed("github")

        # Check that sleep was called with higher delay
        mock_sleep.assert_called_once()
        call_args = mock_sleep.call_args[0]
        self.assertGreater(call_args[0], 1.0)  # Should be > warning delay

    def test_get_api_status(self):
        """Test getting API status string."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=1)

        # Test OK status
        self.rate_limiter.update_rate_limit(
            api="test_ok",
            limit=1000,
            remaining=900,
            reset_time=reset_time,
        )
        self.assertEqual(self.rate_limiter._get_api_status("test_ok"), "ok")

        # Test warning status (80%)
        self.rate_limiter.update_rate_limit(
            api="test_warning",
            limit=1000,
            remaining=190,
            reset_time=reset_time,
        )
        self.assertEqual(self.rate_limiter._get_api_status("test_warning"), "warning")

        # Test critical status (95%)
        self.rate_limiter.update_rate_limit(
            api="test_critical",
            limit=1000,
            remaining=40,
            reset_time=reset_time,
        )
        self.assertEqual(self.rate_limiter._get_api_status("test_critical"), "critical")

        # Test exceeded status (100%)
        self.rate_limiter.update_rate_limit(
            api="test_exceeded",
            limit=1000,
            remaining=0,
            reset_time=reset_time,
        )
        self.assertEqual(self.rate_limiter._get_api_status("test_exceeded"), "exceeded")


if __name__ == "__main__":
    unittest.main()
