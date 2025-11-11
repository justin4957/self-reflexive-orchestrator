"""Issue processing cycle components."""

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional

from github import GithubException, RateLimitExceededException
from github.Issue import Issue

from ..core.config import Config
from ..core.logger import AuditLogger, EventType
from ..core.state import OrchestratorState, StateManager, WorkItem
from ..integrations.github_client import GitHubClient


class RateLimitStatus(Enum):
    """Status of GitHub API rate limit."""

    OK = "ok"
    LIMITED = "limited"
    UNKNOWN = "unknown"


@dataclass
class RateLimitInfo:
    """Thread-safe rate limit information."""

    remaining: int
    reset_time: datetime
    last_checked: datetime
    limit: int

    def is_exceeded(self) -> bool:
        """Check if rate limit is currently exceeded."""
        return self.remaining <= 0 and datetime.now(timezone.utc) < self.reset_time

    def should_refresh(self, interval_seconds: int = 60) -> bool:
        """Check if rate limit info should be refreshed."""
        age = (datetime.now(timezone.utc) - self.last_checked).total_seconds()
        return age >= interval_seconds


@dataclass
class MonitoringStats:
    """Statistics for issue monitoring operations."""

    total_issues_found: int = 0
    issues_claimed: int = 0
    issues_skipped_concurrent_limit: int = 0
    issues_skipped_already_claimed: int = 0
    rate_limit_hits: int = 0
    errors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class IssueMonitor:
    """Monitors GitHub repository for new issues to process.

    Responsibilities:
    - Poll GitHub API for new issues at configured intervals
    - Filter issues by auto_claim_labels and exclude ignored labels
    - Respect max_concurrent limit for issue processing
    - Handle GitHub API rate limits gracefully
    - Add new issues to work queue via StateManager
    - Log all issue claimed events to audit log
    """

    # Configuration constants
    RATE_LIMIT_CHECK_INTERVAL_SECONDS = 60
    RATE_LIMIT_WARNING_THRESHOLD = 100
    ISSUE_BODY_PREVIEW_LENGTH = 500

    def __init__(
        self,
        github_client: GitHubClient,
        state_manager: StateManager,
        config: Config,
        logger: AuditLogger,
    ):
        """Initialize issue monitor.

        Args:
            github_client: GitHub API client instance
            state_manager: State manager for tracking work
            config: Orchestrator configuration
            logger: Audit logger instance
        """
        self.github = github_client
        self.state = state_manager
        self.config = config
        self.logger = logger

        # Rate limiting tracking (thread-safe)
        self._rate_limit_info: Optional[RateLimitInfo] = None
        self._rate_limit_lock = Lock()

        # Statistics
        self.stats = MonitoringStats()

    def check_for_new_issues(self) -> List[WorkItem]:
        """Check for new issues to process.

        Returns:
            List of newly created work items for claimed issues

        Raises:
            GithubException: If GitHub API encounters an error
        """
        try:
            # Check rate limits before making API calls
            rate_status = self._check_rate_limit()
            if rate_status == RateLimitStatus.LIMITED:
                self.logger.warning(
                    "GitHub API rate limit exceeded, skipping issue check",
                    reset_time=(
                        self._rate_limit_info.reset_time.isoformat()
                        if self._rate_limit_info
                        else None
                    ),
                )
                return []
            elif rate_status == RateLimitStatus.UNKNOWN:
                self.logger.warning(
                    "Rate limit status unknown, proceeding with caution",
                )

            # Get issues from GitHub with configured labels
            issues = self._fetch_issues_from_github()
            self.stats.total_issues_found += len(issues)

            if not issues:
                self.logger.debug("No new issues found matching criteria")
                return []

            # Check concurrent processing limit
            in_progress = self.state.get_in_progress_work_items("issue")
            pending = self.state.get_pending_work_items("issue")
            current_count = len(in_progress) + len(pending)

            if current_count >= self.config.issue_processing.max_concurrent:
                self.logger.info(
                    "Max concurrent issues reached, skipping new issues",
                    current=current_count,
                    max=self.config.issue_processing.max_concurrent,
                    issues_found=len(issues),
                )
                self.stats.issues_skipped_concurrent_limit += len(issues)
                return []

            # Process each issue
            claimed_work_items: List[WorkItem] = []
            for issue in issues:
                # Stop if we hit concurrent limit
                if current_count >= self.config.issue_processing.max_concurrent:
                    self.stats.issues_skipped_concurrent_limit += len(issues) - len(
                        claimed_work_items
                    )
                    break

                # Check if already being processed
                existing = self.state.get_work_item("issue", str(issue.number))
                if existing:
                    self.logger.debug(
                        f"Issue #{issue.number} already claimed",
                        issue_number=issue.number,
                        state=existing.state,
                    )
                    self.stats.issues_skipped_already_claimed += 1
                    continue

                # Claim the issue
                work_item = self._claim_issue(issue)
                claimed_work_items.append(work_item)
                current_count += 1

            return claimed_work_items

        except RateLimitExceededException as e:
            self._handle_rate_limit_error(e)
            return []
        except GithubException as e:
            self.logger.error(
                "GitHub API error while checking for issues",
                error=str(e),
                status=e.status,
                exc_info=True,
            )
            self.stats.errors += 1
            raise
        except Exception as e:
            self.logger.error(
                "Unexpected error while checking for issues",
                error=str(e),
                exc_info=True,
            )
            self.stats.errors += 1
            raise

    def _fetch_issues_from_github(self) -> List[Issue]:
        """Fetch issues from GitHub API with configured filters.

        Returns:
            List of GitHub Issue objects matching criteria
        """
        try:
            issues = self.github.get_issues(
                labels=self.config.issue_processing.auto_claim_labels,
                exclude_labels=self.config.issue_processing.ignore_labels,
                state="open",
            )

            self.logger.debug(
                "Fetched issues from GitHub",
                count=len(issues),
                auto_claim_labels=self.config.issue_processing.auto_claim_labels,
                exclude_labels=self.config.issue_processing.ignore_labels,
            )

            return issues

        except GithubException as e:
            self.logger.error(
                "Failed to fetch issues from GitHub",
                error=str(e),
                status=getattr(e, "status", None),
            )
            raise

    def _claim_issue(self, issue: Issue) -> WorkItem:
        """Claim an issue by adding it to work queue.

        Args:
            issue: GitHub Issue object to claim

        Returns:
            Created WorkItem
        """
        # Extract issue metadata
        metadata = {
            "title": issue.title,
            "labels": [label.name for label in issue.labels],
            "author": issue.user.login if issue.user else None,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "url": issue.html_url,
            "body": (
                issue.body[: self.ISSUE_BODY_PREVIEW_LENGTH] if issue.body else None
            ),
        }

        # Add to work queue
        work_item = self.state.add_work_item(
            item_type="issue",
            item_id=str(issue.number),
            initial_state="pending",
            metadata=metadata,
        )

        # Log the claim event
        self.logger.audit(
            EventType.ISSUE_CLAIMED,
            f"Claimed issue #{issue.number}: {issue.title}",
            resource_type="issue",
            resource_id=str(issue.number),
            metadata=metadata,
        )

        self.logger.info(
            f"Claimed issue #{issue.number}",
            issue_number=issue.number,
            title=issue.title,
            labels=[label.name for label in issue.labels],
        )

        self.stats.issues_claimed += 1

        return work_item

    def _check_rate_limit(self) -> RateLimitStatus:
        """Check GitHub API rate limit status (thread-safe).

        Returns:
            RateLimitStatus indicating if we can make API calls
        """
        with self._rate_limit_lock:
            # Check cached info first
            if self._rate_limit_info:
                if self._rate_limit_info.is_exceeded():
                    return RateLimitStatus.LIMITED
                if not self._rate_limit_info.should_refresh(
                    self.RATE_LIMIT_CHECK_INTERVAL_SECONDS
                ):
                    return RateLimitStatus.OK

            # Fetch fresh rate limit info
            try:
                rate_limit = self.github.github.get_rate_limit()
                core_limit = rate_limit.core  # type: ignore[attr-defined]

                self._rate_limit_info = RateLimitInfo(
                    remaining=core_limit.remaining,
                    reset_time=core_limit.reset,
                    last_checked=datetime.now(timezone.utc),
                    limit=core_limit.limit,
                )

                # Log warnings
                if core_limit.remaining < self.RATE_LIMIT_WARNING_THRESHOLD:
                    self.logger.warning(
                        "GitHub API rate limit running low",
                        remaining=core_limit.remaining,
                        limit=core_limit.limit,
                        reset_time=core_limit.reset.isoformat(),
                    )

                if core_limit.remaining <= 0:
                    self.logger.error(
                        "GitHub API rate limit exceeded",
                        reset_time=core_limit.reset.isoformat(),
                    )
                    self.stats.rate_limit_hits += 1
                    return RateLimitStatus.LIMITED

                return RateLimitStatus.OK

            except Exception as e:
                self.logger.error(
                    "Failed to check rate limit",
                    error=str(e),
                    exc_info=True,
                )
                return RateLimitStatus.UNKNOWN

    def _handle_rate_limit_error(self, error: RateLimitExceededException):
        """Handle rate limit exceeded error.

        Args:
            error: Rate limit exception from GitHub API
        """
        self.stats.rate_limit_hits += 1

        # Extract reset time from error if available
        reset_time = None
        if hasattr(error, "reset_time"):
            reset_time = datetime.fromtimestamp(error.reset_time, tz=timezone.utc)

            with self._rate_limit_lock:
                self._rate_limit_info = RateLimitInfo(
                    remaining=0,
                    reset_time=reset_time,
                    last_checked=datetime.now(timezone.utc),
                    limit=(
                        self._rate_limit_info.limit if self._rate_limit_info else 5000
                    ),
                )

        self.logger.error(
            "GitHub API rate limit exceeded",
            reset_time=reset_time.isoformat() if reset_time else None,
            error=str(error),
        )

        self.logger.audit(
            EventType.ERROR_OCCURRED,
            "Rate limit exceeded while monitoring issues",
            metadata={
                "reset_time": reset_time.isoformat() if reset_time else None,
                "error": str(error),
            },
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get monitoring statistics.

        Returns:
            Dictionary with statistics about issue monitoring
        """
        stats_dict = self.stats.to_dict()

        # Add rate limit info if available
        with self._rate_limit_lock:
            if self._rate_limit_info:
                stats_dict.update(
                    {
                        "last_rate_limit_check": self._rate_limit_info.last_checked.isoformat(),
                        "requests_remaining": self._rate_limit_info.remaining,
                        "rate_limit_reset_time": self._rate_limit_info.reset_time.isoformat(),
                        "rate_limit": self._rate_limit_info.limit,
                    }
                )
            else:
                stats_dict.update(
                    {
                        "last_rate_limit_check": None,
                        "requests_remaining": None,
                        "rate_limit_reset_time": None,
                        "rate_limit": None,
                    }
                )

        return stats_dict

    def reset_statistics(self):
        """Reset monitoring statistics."""
        self.stats = MonitoringStats()
