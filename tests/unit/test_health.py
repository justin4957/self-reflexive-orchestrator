"""Unit tests for health check system."""

import unittest
from unittest.mock import MagicMock, Mock, patch

import psutil

from src.core.health import HealthChecker, HealthCheckResult, HealthReport, HealthStatus
from src.core.logger import AuditLogger


class TestHealthCheckResult(unittest.TestCase):
    """Test cases for HealthCheckResult."""

    def test_to_dict(self):
        """Test HealthCheckResult to_dict conversion."""
        result = HealthCheckResult(
            name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
            details={"key": "value"},
            duration_ms=10.5,
        )

        result_dict = result.to_dict()

        self.assertEqual(result_dict["name"], "test_check")
        self.assertEqual(result_dict["status"], "healthy")
        self.assertEqual(result_dict["message"], "All good")
        self.assertEqual(result_dict["details"], {"key": "value"})
        self.assertEqual(result_dict["duration_ms"], 10.5)


class TestHealthReport(unittest.TestCase):
    """Test cases for HealthReport."""

    def test_to_dict(self):
        """Test HealthReport to_dict conversion."""
        checks = [
            HealthCheckResult("check1", HealthStatus.HEALTHY, "OK"),
            HealthCheckResult("check2", HealthStatus.DEGRADED, "Warning"),
        ]

        report = HealthReport(
            overall_status=HealthStatus.DEGRADED,
            checks=checks,
            summary="1 degraded",
        )

        report_dict = report.to_dict()

        self.assertEqual(report_dict["overall_status"], "degraded")
        self.assertEqual(len(report_dict["checks"]), 2)
        self.assertEqual(report_dict["summary"], "1 degraded")

    def test_healthy_count(self):
        """Test healthy_count property."""
        checks = [
            HealthCheckResult("check1", HealthStatus.HEALTHY, "OK"),
            HealthCheckResult("check2", HealthStatus.HEALTHY, "OK"),
            HealthCheckResult("check3", HealthStatus.DEGRADED, "Warning"),
        ]

        report = HealthReport(
            overall_status=HealthStatus.DEGRADED,
            checks=checks,
        )

        self.assertEqual(report.healthy_count, 2)
        self.assertEqual(report.degraded_count, 1)
        self.assertEqual(report.unhealthy_count, 0)


class TestHealthChecker(unittest.TestCase):
    """Test cases for HealthChecker."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.checker = HealthChecker(logger=self.logger)

    def test_initialization(self):
        """Test health checker initialization."""
        self.assertIsNotNone(self.checker.logger)
        self.assertEqual(self.checker.memory_threshold, 90.0)
        self.assertEqual(self.checker.disk_threshold, 90.0)

    @patch("src.core.health.psutil.virtual_memory")
    def test_check_memory_healthy(self, mock_memory):
        """Test memory check when healthy."""
        mock_mem = Mock()
        mock_mem.percent = 50.0
        mock_mem.total = 16 * 1024**3  # 16 GB
        mock_mem.available = 8 * 1024**3  # 8 GB
        mock_mem.used = 8 * 1024**3  # 8 GB
        mock_memory.return_value = mock_mem

        result = self.checker._check_memory()

        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertIn("50.0%", result.message)
        self.assertEqual(result.details["percent_used"], 50.0)

    @patch("src.core.health.psutil.virtual_memory")
    def test_check_memory_degraded(self, mock_memory):
        """Test memory check when degraded."""
        mock_mem = Mock()
        mock_mem.percent = 92.0
        mock_mem.total = 16 * 1024**3
        mock_mem.available = 1 * 1024**3
        mock_mem.used = 15 * 1024**3
        mock_memory.return_value = mock_mem

        result = self.checker._check_memory()

        self.assertEqual(result.status, HealthStatus.DEGRADED)
        self.assertIn("high", result.message.lower())

    @patch("src.core.health.psutil.virtual_memory")
    def test_check_memory_unhealthy(self, mock_memory):
        """Test memory check when unhealthy."""
        mock_mem = Mock()
        mock_mem.percent = 96.0
        mock_mem.total = 16 * 1024**3
        mock_mem.available = 0.5 * 1024**3
        mock_mem.used = 15.5 * 1024**3
        mock_memory.return_value = mock_mem

        result = self.checker._check_memory()

        self.assertEqual(result.status, HealthStatus.UNHEALTHY)
        self.assertIn("critical", result.message.lower())

    @patch("src.core.health.psutil.disk_usage")
    def test_check_disk_space_healthy(self, mock_disk):
        """Test disk space check when healthy."""
        mock_disk_usage = Mock()
        mock_disk_usage.percent = 60.0
        mock_disk_usage.total = 1000 * 1024**3  # 1 TB
        mock_disk_usage.free = 400 * 1024**3  # 400 GB
        mock_disk_usage.used = 600 * 1024**3  # 600 GB
        mock_disk.return_value = mock_disk_usage

        result = self.checker._check_disk_space()

        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertIn("60.0%", result.message)

    @patch("src.core.health.psutil.cpu_percent")
    @patch("src.core.health.psutil.cpu_count")
    def test_check_cpu_healthy(self, mock_cpu_count, mock_cpu_percent):
        """Test CPU check when healthy."""
        mock_cpu_percent.return_value = 45.0
        mock_cpu_count.return_value = 8

        result = self.checker._check_cpu()

        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertIn("45.0%", result.message)
        self.assertEqual(result.details["cpu_count"], 8)

    @patch("src.core.health.psutil.cpu_percent")
    @patch("src.core.health.psutil.cpu_count")
    def test_check_cpu_degraded(self, mock_cpu_count, mock_cpu_percent):
        """Test CPU check when degraded."""
        mock_cpu_percent.return_value = 85.0
        mock_cpu_count.return_value = 4

        result = self.checker._check_cpu()

        self.assertEqual(result.status, HealthStatus.DEGRADED)
        self.assertIn("high", result.message.lower())

    def test_check_github_api_healthy(self):
        """Test GitHub API check when healthy."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_core = Mock()
        mock_core.remaining = 4000
        mock_core.limit = 5000
        mock_core.reset.isoformat.return_value = "2024-01-15T12:00:00"
        mock_rate_limit.core = mock_core
        mock_github.get_rate_limit.return_value = mock_rate_limit

        checker = HealthChecker(logger=self.logger, github_client=mock_github)
        result = checker._check_github_api()

        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertIn("4000", result.message)

    def test_check_github_api_degraded(self):
        """Test GitHub API check when rate limit low."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_core = Mock()
        mock_core.remaining = 500
        mock_core.limit = 5000
        mock_core.reset.isoformat.return_value = "2024-01-15T12:00:00"
        mock_rate_limit.core = mock_core
        mock_github.get_rate_limit.return_value = mock_rate_limit

        checker = HealthChecker(logger=self.logger, github_client=mock_github)
        result = checker._check_github_api()

        self.assertEqual(result.status, HealthStatus.DEGRADED)
        self.assertIn("low", result.message.lower())

    def test_check_github_api_unhealthy(self):
        """Test GitHub API check when unreachable."""
        mock_github = Mock()
        mock_github.get_rate_limit.side_effect = Exception("API error")

        checker = HealthChecker(logger=self.logger, github_client=mock_github)
        result = checker._check_github_api()

        self.assertEqual(result.status, HealthStatus.UNHEALTHY)
        self.assertIn("unreachable", result.message.lower())

    @patch("src.core.health.subprocess.run")
    def test_check_git_healthy(self, mock_run):
        """Test git check when healthy."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "git version 2.40.0"
        mock_run.return_value = mock_result

        result = self.checker._check_git()

        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertIn("git version", result.message.lower())

    @patch("src.core.health.subprocess.run")
    def test_check_git_unhealthy(self, mock_run):
        """Test git check when not found."""
        mock_run.side_effect = FileNotFoundError()

        result = self.checker._check_git()

        self.assertEqual(result.status, HealthStatus.UNHEALTHY)
        self.assertIn("not found", result.message.lower())

    @patch("src.core.health.os.path.exists")
    @patch("src.core.health.subprocess.run")
    def test_check_multi_agent_coder_healthy(self, mock_run, mock_exists):
        """Test multi-agent-coder check when healthy."""
        mock_exists.return_value = True
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "multi-agent-coder v1.0.0"
        mock_run.return_value = mock_result

        checker = HealthChecker(
            logger=self.logger,
            multi_agent_coder_path="/usr/local/bin/multi-agent-coder",
        )
        result = checker._check_multi_agent_coder()

        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertIn("available", result.message.lower())

    @patch("src.core.health.os.path.exists")
    def test_check_multi_agent_coder_not_found(self, mock_exists):
        """Test multi-agent-coder check when not found."""
        mock_exists.return_value = False

        checker = HealthChecker(
            logger=self.logger,
            multi_agent_coder_path="/usr/local/bin/multi-agent-coder",
        )
        result = checker._check_multi_agent_coder()

        self.assertEqual(result.status, HealthStatus.UNHEALTHY)
        self.assertIn("not found", result.message.lower())

    def test_determine_overall_status_all_healthy(self):
        """Test overall status when all checks healthy."""
        checks = [
            HealthCheckResult("check1", HealthStatus.HEALTHY, "OK"),
            HealthCheckResult("check2", HealthStatus.HEALTHY, "OK"),
        ]

        status = self.checker._determine_overall_status(checks)

        self.assertEqual(status, HealthStatus.HEALTHY)

    def test_determine_overall_status_one_degraded(self):
        """Test overall status when one check degraded."""
        checks = [
            HealthCheckResult("check1", HealthStatus.HEALTHY, "OK"),
            HealthCheckResult("check2", HealthStatus.DEGRADED, "Warning"),
        ]

        status = self.checker._determine_overall_status(checks)

        self.assertEqual(status, HealthStatus.DEGRADED)

    def test_determine_overall_status_one_unhealthy(self):
        """Test overall status when one check unhealthy."""
        checks = [
            HealthCheckResult("check1", HealthStatus.HEALTHY, "OK"),
            HealthCheckResult("check2", HealthStatus.UNHEALTHY, "Error"),
        ]

        status = self.checker._determine_overall_status(checks)

        self.assertEqual(status, HealthStatus.UNHEALTHY)

    @patch("src.core.health.psutil.virtual_memory")
    @patch("src.core.health.psutil.disk_usage")
    @patch("src.core.health.psutil.cpu_percent")
    @patch("src.core.health.psutil.cpu_count")
    @patch("src.core.health.subprocess.run")
    def test_check_health_integration(
        self,
        mock_subprocess,
        mock_cpu_count,
        mock_cpu_percent,
        mock_disk,
        mock_memory,
    ):
        """Test full health check integration."""
        # Mock all system checks as healthy
        mock_mem = Mock()
        mock_mem.percent = 50.0
        mock_mem.total = 16 * 1024**3
        mock_mem.available = 8 * 1024**3
        mock_mem.used = 8 * 1024**3
        mock_memory.return_value = mock_mem

        mock_disk_usage = Mock()
        mock_disk_usage.percent = 60.0
        mock_disk_usage.total = 1000 * 1024**3
        mock_disk_usage.free = 400 * 1024**3
        mock_disk_usage.used = 600 * 1024**3
        mock_disk.return_value = mock_disk_usage

        mock_cpu_percent.return_value = 45.0
        mock_cpu_count.return_value = 8

        mock_git_result = Mock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = "git version 2.40.0"
        mock_subprocess.return_value = mock_git_result

        report = self.checker.check_health()

        self.assertEqual(report.overall_status, HealthStatus.HEALTHY)
        self.assertGreater(len(report.checks), 0)
        self.assertGreater(report.healthy_count, 0)


if __name__ == "__main__":
    unittest.main()
