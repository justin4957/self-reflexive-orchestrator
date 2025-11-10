"""Rate limiting for API requests.

Manages rate limits for GitHub API and other services, with intelligent
throttling and backoff strategies.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from enum import Enum
import time
import json

from ..core.logger import AuditLogger


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded and cannot proceed."""

    pass


@dataclass
class RateLimitInfo:
    """Rate limit information for an API."""

    limit: int  # Maximum requests allowed
    remaining: int  # Requests remaining
    reset_time: datetime  # When limit resets
    used: int = 0  # Requests used

    @property
    def percentage_used(self) -> float:
        """Calculate percentage of limit used."""
        if self.limit == 0:
            return 0.0
        return (self.used / self.limit) * 100

    @property
    def time_until_reset(self) -> timedelta:
        """Calculate time until reset."""
        now = datetime.now(timezone.utc)
        return max(timedelta(0), self.reset_time - now)

    @property
    def seconds_until_reset(self) -> float:
        """Get seconds until reset."""
        return self.time_until_reset.total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "limit": self.limit,
            "remaining": self.remaining,
            "used": self.used,
            "reset_time": self.reset_time.isoformat(),
            "percentage_used": self.percentage_used,
            "seconds_until_reset": self.seconds_until_reset,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RateLimitInfo":
        """Create from dictionary."""
        return cls(
            limit=data["limit"],
            remaining=data["remaining"],
            used=data.get("used", data["limit"] - data["remaining"]),
            reset_time=datetime.fromisoformat(data["reset_time"]),
        )


class RateLimiter:
    """Manages rate limits and throttling for API requests.

    Responsibilities:
    - Track rate limits per API
    - Throttle requests when approaching limits
    - Pause operations when limits exceeded
    - Implement exponential backoff
    - Provide rate limit status
    - Persist state to disk
    """

    # Throttling thresholds
    WARNING_THRESHOLD = 0.8  # Start throttling at 80%
    CRITICAL_THRESHOLD = 0.95  # Heavy throttling at 95%
    BLOCK_THRESHOLD = 1.0  # Block at 100%

    # Throttling delays (seconds)
    WARNING_DELAY = 1.0  # 1 second delay when warning
    CRITICAL_DELAY = 5.0  # 5 second delay when critical
    BACKOFF_MULTIPLIER = 2.0  # Exponential backoff multiplier

    def __init__(
        self,
        logger: AuditLogger,
        enable_throttling: bool = True,
        state_file: Optional[str] = None,
    ):
        """Initialize rate limiter.

        Args:
            logger: Audit logger
            enable_throttling: Enable automatic throttling
            state_file: Path to state persistence file
        """
        self.logger = logger
        self.enable_throttling = enable_throttling
        self.state_file = Path(
            state_file if state_file else "./state/rate_limiter.json"
        )

        # Rate limit tracking per API
        self.rate_limits: Dict[str, RateLimitInfo] = {}

        # Backoff tracking
        self.backoff_delays: Dict[str, float] = {}

        # Load state
        self._load_state()

        self.logger.info(
            "rate_limiter_initialized",
            enable_throttling=enable_throttling,
            state_file=str(self.state_file),
        )

    def update_rate_limit(
        self, api: str, limit: int, remaining: int, reset_time: datetime
    ):
        """Update rate limit information for an API.

        Args:
            api: API identifier (e.g., "github", "anthropic")
            limit: Maximum requests allowed
            remaining: Requests remaining
            reset_time: When limit resets
        """
        used = limit - remaining

        self.rate_limits[api] = RateLimitInfo(
            limit=limit,
            remaining=remaining,
            used=used,
            reset_time=reset_time,
        )

        self._save_state()

        self.logger.info(
            "rate_limit_updated",
            api=api,
            limit=limit,
            remaining=remaining,
            used=used,
            percentage_used=self.rate_limits[api].percentage_used,
            seconds_until_reset=self.rate_limits[api].seconds_until_reset,
        )

    def check_rate_limit(self, api: str, required_requests: int = 1) -> bool:
        """Check if request is within rate limit.

        Args:
            api: API identifier
            required_requests: Number of requests needed

        Returns:
            True if request can proceed

        Raises:
            RateLimitExceeded: If rate limit exceeded and cannot proceed
        """
        if api not in self.rate_limits:
            # No rate limit info yet, allow
            return True

        limit_info = self.rate_limits[api]

        # Check if we have enough requests remaining
        if limit_info.remaining < required_requests:
            # Calculate wait time
            wait_time = limit_info.seconds_until_reset

            self.logger.error(
                "rate_limit_exceeded",
                api=api,
                remaining=limit_info.remaining,
                required=required_requests,
                wait_time_seconds=wait_time,
            )

            raise RateLimitExceeded(
                f"Rate limit exceeded for {api}. "
                f"Need {required_requests} requests, only {limit_info.remaining} remaining. "
                f"Resets in {wait_time:.0f} seconds."
            )

        return True

    def wait_if_needed(self, api: str, required_requests: int = 1):
        """Wait if approaching rate limit (throttling).

        Args:
            api: API identifier
            required_requests: Number of requests needed
        """
        if not self.enable_throttling:
            return

        if api not in self.rate_limits:
            return

        limit_info = self.rate_limits[api]
        percentage_used = limit_info.percentage_used

        # Calculate throttle delay based on usage
        delay = 0.0

        if percentage_used >= self.CRITICAL_THRESHOLD * 100:
            # Critical threshold - heavy delay
            delay = self.CRITICAL_DELAY
            self.logger.warning(
                "rate_limit_critical_throttling",
                api=api,
                percentage_used=percentage_used,
                delay_seconds=delay,
            )

        elif percentage_used >= self.WARNING_THRESHOLD * 100:
            # Warning threshold - light delay
            delay = self.WARNING_DELAY
            self.logger.info(
                "rate_limit_warning_throttling",
                api=api,
                percentage_used=percentage_used,
                delay_seconds=delay,
            )

        if delay > 0:
            self.logger.info(
                "rate_limit_throttle_wait",
                api=api,
                delay_seconds=delay,
                percentage_used=percentage_used,
            )
            time.sleep(delay)

    def track_request(self, api: str, requests_used: int = 1):
        """Track that a request was made.

        Args:
            api: API identifier
            requests_used: Number of requests used
        """
        if api in self.rate_limits:
            self.rate_limits[api].remaining -= requests_used
            self.rate_limits[api].used += requests_used
            self._save_state()

            self.logger.debug(
                "rate_limit_request_tracked",
                api=api,
                remaining=self.rate_limits[api].remaining,
                used=self.rate_limits[api].used,
            )

    def get_status(self, api: Optional[str] = None) -> Dict[str, Any]:
        """Get rate limit status.

        Args:
            api: Specific API to check (None for all)

        Returns:
            Dictionary with rate limit status
        """
        if api:
            if api not in self.rate_limits:
                return {"api": api, "status": "unknown", "info": None}

            limit_info = self.rate_limits[api]
            return {
                "api": api,
                "status": self._get_api_status(api),
                "info": limit_info.to_dict(),
            }

        # Return status for all APIs
        all_status = {}
        for api_name, limit_info in self.rate_limits.items():
            all_status[api_name] = {
                "status": self._get_api_status(api_name),
                "info": limit_info.to_dict(),
            }

        return {"apis": all_status, "throttling_enabled": self.enable_throttling}

    def wait_for_reset(self, api: str):
        """Wait for rate limit to reset.

        Args:
            api: API identifier
        """
        if api not in self.rate_limits:
            return

        limit_info = self.rate_limits[api]
        wait_time = limit_info.seconds_until_reset

        if wait_time > 0:
            self.logger.warning(
                "rate_limit_waiting_for_reset",
                api=api,
                wait_time_seconds=wait_time,
            )
            time.sleep(wait_time + 1)  # Add 1 second buffer

    def implement_backoff(self, api: str, error: Optional[Exception] = None):
        """Implement exponential backoff for an API.

        Args:
            api: API identifier
            error: Optional error that triggered backoff
        """
        # Get current backoff delay or start with WARNING_DELAY
        current_delay = self.backoff_delays.get(api, self.WARNING_DELAY)

        # Apply exponential backoff
        new_delay = min(current_delay * self.BACKOFF_MULTIPLIER, 60.0)  # Max 60s
        self.backoff_delays[api] = new_delay

        self.logger.warning(
            "rate_limit_backoff",
            api=api,
            delay_seconds=new_delay,
            error=str(error) if error else None,
        )

        time.sleep(new_delay)

    def reset_backoff(self, api: str):
        """Reset backoff delay for an API.

        Args:
            api: API identifier
        """
        if api in self.backoff_delays:
            del self.backoff_delays[api]
            self.logger.info("rate_limit_backoff_reset", api=api)

    def _get_api_status(self, api: str) -> str:
        """Get status string for an API.

        Args:
            api: API identifier

        Returns:
            Status string: "ok", "warning", "critical", "exceeded"
        """
        if api not in self.rate_limits:
            return "unknown"

        limit_info = self.rate_limits[api]
        percentage = limit_info.percentage_used

        if percentage >= 100:
            return "exceeded"
        elif percentage >= self.CRITICAL_THRESHOLD * 100:
            return "critical"
        elif percentage >= self.WARNING_THRESHOLD * 100:
            return "warning"
        else:
            return "ok"

    def _load_state(self):
        """Load rate limit state from disk."""
        if not self.state_file.exists():
            self.logger.info(
                "rate_limiter_state_not_found",
                state_file=str(self.state_file),
                action="creating_new",
            )
            return

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)

            # Load rate limits
            for api, limit_data in data.get("rate_limits", {}).items():
                self.rate_limits[api] = RateLimitInfo.from_dict(limit_data)

            # Load backoff delays
            self.backoff_delays = data.get("backoff_delays", {})

            self.logger.info(
                "rate_limiter_state_loaded",
                state_file=str(self.state_file),
                apis_tracked=list(self.rate_limits.keys()),
            )

        except Exception as e:
            self.logger.error(
                "rate_limiter_state_load_failed",
                state_file=str(self.state_file),
                error=str(e),
                action="continuing_with_empty_state",
            )

    def _save_state(self):
        """Save rate limit state to disk."""
        try:
            # Ensure state directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "rate_limits": {
                    api: info.to_dict() for api, info in self.rate_limits.items()
                },
                "backoff_delays": self.backoff_delays,
            }

            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)

            self.logger.debug(
                "rate_limiter_state_saved",
                state_file=str(self.state_file),
            )

        except Exception as e:
            self.logger.error(
                "rate_limiter_state_save_failed",
                state_file=str(self.state_file),
                error=str(e),
            )
