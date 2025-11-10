"""Health check and monitoring system for orchestrator.

Provides comprehensive health checks for system resources, APIs,
integrations, and operational metrics.
"""

import os
import psutil
import subprocess
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .logger import AuditLogger


class HealthStatus(Enum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
            "duration_ms": self.duration_ms,
        }


@dataclass
class HealthReport:
    """Comprehensive health report."""

    overall_status: HealthStatus
    checks: List[HealthCheckResult]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall_status": self.overall_status.value,
            "checks": [check.to_dict() for check in self.checks],
            "timestamp": self.timestamp.isoformat(),
            "summary": self.summary,
        }

    @property
    def healthy_count(self) -> int:
        """Count of healthy checks."""
        return sum(1 for c in self.checks if c.status == HealthStatus.HEALTHY)

    @property
    def degraded_count(self) -> int:
        """Count of degraded checks."""
        return sum(1 for c in self.checks if c.status == HealthStatus.DEGRADED)

    @property
    def unhealthy_count(self) -> int:
        """Count of unhealthy checks."""
        return sum(1 for c in self.checks if c.status == HealthStatus.UNHEALTHY)


class HealthChecker:
    """Performs comprehensive health checks on orchestrator components.

    Checks:
    - System resources (memory, disk, CPU)
    - API connectivity (GitHub, Anthropic)
    - Integration availability (git, multi-agent-coder)
    - Operational health (error rates, stuck operations)
    """

    def __init__(
        self,
        logger: AuditLogger,
        github_client: Optional[Any] = None,
        anthropic_client: Optional[Any] = None,
        multi_agent_coder_path: Optional[str] = None,
        memory_threshold_percent: float = 90.0,
        disk_threshold_percent: float = 90.0,
        error_rate_threshold: float = 0.5,
    ):
        """Initialize health checker.

        Args:
            logger: Audit logger
            github_client: GitHub client for API checks
            anthropic_client: Anthropic client for API checks
            multi_agent_coder_path: Path to multi-agent-coder executable
            memory_threshold_percent: Memory usage threshold
            disk_threshold_percent: Disk usage threshold
            error_rate_threshold: Acceptable error rate (0.0-1.0)
        """
        self.logger = logger
        self.github_client = github_client
        self.anthropic_client = anthropic_client
        self.multi_agent_coder_path = multi_agent_coder_path
        self.memory_threshold = memory_threshold_percent
        self.disk_threshold = disk_threshold_percent
        self.error_rate_threshold = error_rate_threshold

        self.logger.info("health_checker_initialized")

    def check_health(self) -> HealthReport:
        """Perform all health checks.

        Returns:
            HealthReport with all check results
        """
        self.logger.info("health_check_started")

        checks = []

        # System health checks
        checks.append(self._check_memory())
        checks.append(self._check_disk_space())
        checks.append(self._check_cpu())

        # API health checks
        if self.github_client:
            checks.append(self._check_github_api())

        if self.anthropic_client:
            checks.append(self._check_anthropic_api())

        # Integration health checks
        checks.append(self._check_git())

        if self.multi_agent_coder_path:
            checks.append(self._check_multi_agent_coder())

        # Determine overall status
        overall_status = self._determine_overall_status(checks)

        # Build summary
        summary = self._build_summary(checks, overall_status)

        report = HealthReport(
            overall_status=overall_status,
            checks=checks,
            summary=summary,
        )

        self.logger.info(
            "health_check_completed",
            overall_status=overall_status.value,
            healthy=report.healthy_count,
            degraded=report.degraded_count,
            unhealthy=report.unhealthy_count,
        )

        return report

    def _check_memory(self) -> HealthCheckResult:
        """Check system memory usage."""
        start_time = time.time()

        try:
            memory = psutil.virtual_memory()
            percent_used = memory.percent

            if percent_used < self.memory_threshold:
                status = HealthStatus.HEALTHY
                message = f"Memory usage: {percent_used:.1f}%"
            elif percent_used < 95.0:
                status = HealthStatus.DEGRADED
                message = f"Memory usage high: {percent_used:.1f}%"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Memory usage critical: {percent_used:.1f}%"

            details = {
                "percent_used": percent_used,
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
            }

        except Exception as e:
            status = HealthStatus.UNKNOWN
            message = f"Failed to check memory: {str(e)}"
            details = {"error": str(e)}

        duration_ms = (time.time() - start_time) * 1000

        return HealthCheckResult(
            name="memory",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        )

    def _check_disk_space(self) -> HealthCheckResult:
        """Check disk space."""
        start_time = time.time()

        try:
            disk = psutil.disk_usage("/")
            percent_used = disk.percent

            if percent_used < self.disk_threshold:
                status = HealthStatus.HEALTHY
                message = f"Disk usage: {percent_used:.1f}%"
            elif percent_used < 95.0:
                status = HealthStatus.DEGRADED
                message = f"Disk usage high: {percent_used:.1f}%"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Disk usage critical: {percent_used:.1f}%"

            details = {
                "percent_used": percent_used,
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
            }

        except Exception as e:
            status = HealthStatus.UNKNOWN
            message = f"Failed to check disk: {str(e)}"
            details = {"error": str(e)}

        duration_ms = (time.time() - start_time) * 1000

        return HealthCheckResult(
            name="disk_space",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        )

    def _check_cpu(self) -> HealthCheckResult:
        """Check CPU usage."""
        start_time = time.time()

        try:
            # Get CPU usage over 1 second interval
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()

            if cpu_percent < 80.0:
                status = HealthStatus.HEALTHY
                message = f"CPU usage: {cpu_percent:.1f}%"
            elif cpu_percent < 95.0:
                status = HealthStatus.DEGRADED
                message = f"CPU usage high: {cpu_percent:.1f}%"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"CPU usage critical: {cpu_percent:.1f}%"

            details = {
                "percent_used": cpu_percent,
                "cpu_count": cpu_count,
            }

        except Exception as e:
            status = HealthStatus.UNKNOWN
            message = f"Failed to check CPU: {str(e)}"
            details = {"error": str(e)}

        duration_ms = (time.time() - start_time) * 1000

        return HealthCheckResult(
            name="cpu",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        )

    def _check_github_api(self) -> HealthCheckResult:
        """Check GitHub API connectivity."""
        start_time = time.time()

        try:
            # Try to get rate limit info (lightweight API call)
            rate_limit = self.github_client.get_rate_limit()
            core_remaining = rate_limit.core.remaining
            core_limit = rate_limit.core.limit

            if core_remaining > core_limit * 0.2:
                status = HealthStatus.HEALTHY
                message = (
                    f"GitHub API: {core_remaining}/{core_limit} requests remaining"
                )
            elif core_remaining > 0:
                status = HealthStatus.DEGRADED
                message = f"GitHub API rate limit low: {core_remaining}/{core_limit}"
            else:
                status = HealthStatus.UNHEALTHY
                message = "GitHub API rate limit exceeded"

            details = {
                "remaining": core_remaining,
                "limit": core_limit,
                "reset_at": rate_limit.core.reset.isoformat(),
            }

        except Exception as e:
            status = HealthStatus.UNHEALTHY
            message = f"GitHub API unreachable: {str(e)}"
            details = {"error": str(e)}

        duration_ms = (time.time() - start_time) * 1000

        return HealthCheckResult(
            name="github_api",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        )

    def _check_anthropic_api(self) -> HealthCheckResult:
        """Check Anthropic API connectivity."""
        start_time = time.time()

        try:
            # For now, just check if client is configured
            # In production, could make a lightweight API call
            if self.anthropic_client:
                status = HealthStatus.HEALTHY
                message = "Anthropic API client configured"
                details = {"configured": True}
            else:
                status = HealthStatus.DEGRADED
                message = "Anthropic API client not configured"
                details = {"configured": False}

        except Exception as e:
            status = HealthStatus.UNHEALTHY
            message = f"Anthropic API check failed: {str(e)}"
            details = {"error": str(e)}

        duration_ms = (time.time() - start_time) * 1000

        return HealthCheckResult(
            name="anthropic_api",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        )

    def _check_git(self) -> HealthCheckResult:
        """Check git availability."""
        start_time = time.time()

        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                version = result.stdout.strip()
                status = HealthStatus.HEALTHY
                message = f"Git available: {version}"
                details = {"version": version}
            else:
                status = HealthStatus.UNHEALTHY
                message = "Git command failed"
                details = {"error": result.stderr}

        except subprocess.TimeoutExpired:
            status = HealthStatus.UNHEALTHY
            message = "Git command timed out"
            details = {"error": "timeout"}
        except FileNotFoundError:
            status = HealthStatus.UNHEALTHY
            message = "Git not found"
            details = {"error": "not_found"}
        except Exception as e:
            status = HealthStatus.UNHEALTHY
            message = f"Git check failed: {str(e)}"
            details = {"error": str(e)}

        duration_ms = (time.time() - start_time) * 1000

        return HealthCheckResult(
            name="git",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        )

    def _check_multi_agent_coder(self) -> HealthCheckResult:
        """Check multi-agent-coder availability."""
        start_time = time.time()

        try:
            # Check if executable exists
            if not os.path.exists(self.multi_agent_coder_path):
                status = HealthStatus.UNHEALTHY
                message = (
                    f"multi-agent-coder not found at {self.multi_agent_coder_path}"
                )
                details = {"error": "not_found"}
            else:
                # Try to get version
                result = subprocess.run(
                    [self.multi_agent_coder_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    version = result.stdout.strip()
                    status = HealthStatus.HEALTHY
                    message = f"multi-agent-coder available: {version}"
                    details = {"version": version, "path": self.multi_agent_coder_path}
                else:
                    status = HealthStatus.DEGRADED
                    message = (
                        "multi-agent-coder executable found but version check failed"
                    )
                    details = {"path": self.multi_agent_coder_path}

        except subprocess.TimeoutExpired:
            status = HealthStatus.DEGRADED
            message = "multi-agent-coder version check timed out"
            details = {"error": "timeout"}
        except Exception as e:
            status = HealthStatus.DEGRADED
            message = f"multi-agent-coder check failed: {str(e)}"
            details = {"error": str(e)}

        duration_ms = (time.time() - start_time) * 1000

        return HealthCheckResult(
            name="multi_agent_coder",
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        )

    def _determine_overall_status(
        self, checks: List[HealthCheckResult]
    ) -> HealthStatus:
        """Determine overall health status from individual checks.

        Args:
            checks: List of health check results

        Returns:
            Overall HealthStatus
        """
        if not checks:
            return HealthStatus.UNKNOWN

        # If any check is unhealthy, overall is unhealthy
        if any(c.status == HealthStatus.UNHEALTHY for c in checks):
            return HealthStatus.UNHEALTHY

        # If any check is degraded, overall is degraded
        if any(c.status == HealthStatus.DEGRADED for c in checks):
            return HealthStatus.DEGRADED

        # If any check is unknown, overall is degraded
        if any(c.status == HealthStatus.UNKNOWN for c in checks):
            return HealthStatus.DEGRADED

        # All checks healthy
        return HealthStatus.HEALTHY

    def _build_summary(
        self, checks: List[HealthCheckResult], overall_status: HealthStatus
    ) -> str:
        """Build summary message.

        Args:
            checks: List of health check results
            overall_status: Overall status

        Returns:
            Summary message
        """
        total = len(checks)
        healthy = sum(1 for c in checks if c.status == HealthStatus.HEALTHY)
        degraded = sum(1 for c in checks if c.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for c in checks if c.status == HealthStatus.UNHEALTHY)

        status_emoji = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.DEGRADED: "⚠️",
            HealthStatus.UNHEALTHY: "❌",
            HealthStatus.UNKNOWN: "❓",
        }

        emoji = status_emoji.get(overall_status, "❓")

        parts = [f"{emoji} Overall: {overall_status.value.upper()}"]
        parts.append(f"({healthy}/{total} healthy")

        if degraded > 0:
            parts.append(f", {degraded} degraded")
        if unhealthy > 0:
            parts.append(f", {unhealthy} unhealthy")

        parts.append(")")

        return "".join(parts)
