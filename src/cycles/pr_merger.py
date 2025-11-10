"""PR merging with validation and rollback capability.

Handles safe merging of pull requests with comprehensive validation,
tagging for rollback, and supervisor mode support.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from ..core.config import PRManagementConfig, SafetyConfig
from ..core.logger import AuditLogger, EventType
from ..integrations.git_ops import GitOps
from ..integrations.github_client import GitHubClient


class MergeValidationError(Exception):
    """Exception raised when merge validation fails."""

    pass


class MergeStrategy(Enum):
    """Supported merge strategies."""

    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


@dataclass
class MergeValidation:
    """Result of merge validation checks."""

    checks_passed: bool = False
    reviews_approved: bool = False
    no_conflicts: bool = False
    branch_up_to_date: bool = False
    required_reviews_met: bool = False
    all_valid: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "checks_passed": self.checks_passed,
            "reviews_approved": self.reviews_approved,
            "no_conflicts": self.no_conflicts,
            "branch_up_to_date": self.branch_up_to_date,
            "required_reviews_met": self.required_reviews_met,
            "all_valid": self.all_valid,
            "errors": self.errors,
        }


@dataclass
class MergeResult:
    """Result of PR merge operation."""

    pr_number: int
    success: bool
    merge_commit_sha: Optional[str] = None
    rollback_tag: Optional[str] = None
    validation: Optional[MergeValidation] = None
    linked_issues_closed: List[int] = field(default_factory=list)
    error: Optional[str] = None
    merged_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pr_number": self.pr_number,
            "success": self.success,
            "merge_commit_sha": self.merge_commit_sha,
            "rollback_tag": self.rollback_tag,
            "validation": self.validation.to_dict() if self.validation else None,
            "linked_issues_closed": self.linked_issues_closed,
            "error": self.error,
            "merged_at": self.merged_at.isoformat(),
        }


class PRMerger:
    """Safely merges pull requests with validation and rollback capability.

    Responsibilities:
    - Validate all checks passed
    - Verify review approval received
    - Check for merge conflicts
    - Verify branch is up to date
    - Create rollback tags
    - Merge using configured strategy
    - Close linked issues
    - Handle merge failures gracefully
    - Support supervised mode with approval gates
    """

    def __init__(
        self,
        git_ops: GitOps,
        github_client: GitHubClient,
        logger: AuditLogger,
        pr_config: PRManagementConfig,
        safety_config: SafetyConfig,
    ):
        """Initialize PR merger.

        Args:
            git_ops: Git operations client
            github_client: GitHub API client
            logger: Audit logger
            pr_config: PR management configuration
            safety_config: Safety configuration
        """
        self.git_ops = git_ops
        self.github_client = github_client
        self.logger = logger
        self.pr_config = pr_config
        self.safety_config = safety_config

        # Statistics
        self.total_merges = 0
        self.failed_merges = 0
        self.validation_failures = 0

    def merge_pull_request(
        self,
        pr_number: int,
        require_approval: bool = True,
    ) -> MergeResult:
        """Merge a pull request with full validation.

        Args:
            pr_number: PR number to merge
            require_approval: Whether to require human approval (supervised mode)

        Returns:
            MergeResult with merge outcome
        """
        self.logger.info(
            "Starting PR merge process",
            pr_number=pr_number,
            require_approval=require_approval,
        )

        try:
            # Fetch PR details
            pr = self.github_client.get_pull_request(pr_number)

            # Validate merge preconditions
            validation = self._validate_merge_preconditions(pr_number, pr)

            if not validation.all_valid:
                self.validation_failures += 1
                self.logger.warning(
                    "PR merge validation failed",
                    pr_number=pr_number,
                    errors=validation.errors,
                )
                return MergeResult(
                    pr_number=pr_number,
                    success=False,
                    validation=validation,
                    error=f"Validation failed: {'; '.join(validation.errors)}",
                )

            self.logger.info(
                "PR merge validation passed",
                pr_number=pr_number,
            )

            # Check if human approval is required
            if (
                require_approval
                and "merge_to_main" in self.safety_config.human_approval_required
            ):
                approval_result = self._request_human_approval(pr_number, pr)
                if not approval_result:
                    self.logger.info(
                        "PR merge denied by human",
                        pr_number=pr_number,
                    )
                    return MergeResult(
                        pr_number=pr_number,
                        success=False,
                        validation=validation,
                        error="Human approval denied",
                    )

            # Create rollback tag
            rollback_tag = self._create_rollback_tag(pr_number, pr)

            # Execute merge
            merge_commit = self._execute_merge(pr_number, pr)

            # Close linked issues
            linked_issues = self._close_linked_issues(pr_number, pr)

            # Add closing comment to PR
            self._add_closing_comment(pr_number, pr)

            # Update statistics
            self.total_merges += 1

            # Log to audit trail
            self.logger.audit(
                EventType.PR_MERGED,
                f"Merged PR #{pr_number}: {pr.title}",
                resource_type="pr",
                resource_id=str(pr_number),
                metadata={
                    "merge_commit": merge_commit,
                    "rollback_tag": rollback_tag,
                    "linked_issues_closed": linked_issues,
                    "merge_strategy": self.pr_config.merge_strategy,
                },
            )

            return MergeResult(
                pr_number=pr_number,
                success=True,
                merge_commit_sha=merge_commit,
                rollback_tag=rollback_tag,
                validation=validation,
                linked_issues_closed=linked_issues,
            )

        except Exception as e:
            self.failed_merges += 1
            self.logger.error(
                "Failed to merge PR",
                pr_number=pr_number,
                error=str(e),
                exc_info=True,
            )

            return MergeResult(
                pr_number=pr_number,
                success=False,
                error=str(e),
            )

    def _validate_merge_preconditions(self, pr_number: int, pr: Any) -> MergeValidation:
        """Validate all merge preconditions.

        Args:
            pr_number: PR number
            pr: PullRequest object from GitHub

        Returns:
            MergeValidation with check results
        """
        validation = MergeValidation()
        errors = []

        # Check CI/CD status
        checks = self.github_client.get_pr_checks(pr_number)
        validation.checks_passed = checks["overall"] == "passed"
        if not validation.checks_passed:
            errors.append(f"CI checks not passed (status: {checks['overall']})")

        # Check review approval
        # GitHub's PR object has review state
        reviews = pr.get_reviews()
        approved_reviews = sum(1 for r in reviews if r.state == "APPROVED")
        validation.reviews_approved = approved_reviews > 0

        validation.required_reviews_met = (
            approved_reviews >= self.pr_config.require_reviews
        )

        if not validation.required_reviews_met:
            errors.append(
                f"Required reviews not met ({approved_reviews}/{self.pr_config.require_reviews})"
            )

        # Check for merge conflicts
        validation.no_conflicts = not pr.mergeable_state == "dirty"
        if not validation.no_conflicts:
            errors.append("PR has merge conflicts")

        # Check if branch is up to date
        # GitHub's mergeable_state can be: clean, unstable, dirty, unknown, blocked
        validation.branch_up_to_date = pr.mergeable_state in ["clean", "unstable"]
        if not validation.branch_up_to_date and pr.mergeable_state != "unknown":
            errors.append(f"Branch not up to date (state: {pr.mergeable_state})")

        # Overall validation
        validation.all_valid = (
            validation.checks_passed
            and validation.required_reviews_met
            and validation.no_conflicts
            and validation.branch_up_to_date
        )

        validation.errors = errors

        return validation

    def _request_human_approval(self, pr_number: int, pr: Any) -> bool:
        """Request human approval for merge (supervised mode).

        Args:
            pr_number: PR number
            pr: PullRequest object

        Returns:
            True if approved, False if denied
        """
        self.logger.human_approval_requested(
            action=f"merge PR #{pr_number}",
            reason="Merge to main requires human approval (supervised mode)",
            resource_type="pr",
            resource_id=str(pr_number),
        )

        # In a real implementation, this would:
        # 1. Send notification (Slack, email, etc.)
        # 2. Wait for approval response
        # 3. Return approval decision
        #
        # For now, we'll simulate by checking if auto_merge is enabled
        # In production, this would integrate with ApprovalManager

        # Auto-approve if auto_merge is enabled (autonomous mode)
        if self.pr_config.auto_merge:
            self.logger.info(
                "Auto-approving merge (auto_merge enabled)",
                pr_number=pr_number,
            )
            return True

        # Otherwise, would wait for human approval
        # This is a placeholder for the full implementation
        self.logger.info(
            "Merge requires manual approval (auto_merge disabled)",
            pr_number=pr_number,
        )
        return False

    def _create_rollback_tag(self, pr_number: int, pr: Any) -> str:
        """Create a git tag for rollback before merging.

        Args:
            pr_number: PR number
            pr: PullRequest object

        Returns:
            Tag name created
        """
        try:
            tag_name = f"pre-merge-{pr_number}"

            # Create tag at current HEAD of base branch
            self.git_ops.run_command(
                f"git tag -a {tag_name} -m 'Pre-merge tag for PR #{pr_number}'"
            )

            # Push tag to remote
            self.git_ops.run_command(f"git push origin {tag_name}")

            self.logger.info(
                "Created rollback tag",
                pr_number=pr_number,
                tag=tag_name,
            )

            return tag_name

        except Exception as e:
            self.logger.warning(
                "Failed to create rollback tag",
                pr_number=pr_number,
                error=str(e),
            )
            return f"pre-merge-{pr_number} (creation failed)"

    def _execute_merge(self, pr_number: int, pr: Any) -> str:
        """Execute the merge operation.

        Args:
            pr_number: PR number
            pr: PullRequest object

        Returns:
            Merge commit SHA

        Raises:
            MergeValidationError: If merge fails
        """
        try:
            # Merge using GitHub API
            success = self.github_client.merge_pull_request(
                pr_number=pr_number,
                merge_method=self.pr_config.merge_strategy,
            )

            if not success:
                raise MergeValidationError(f"GitHub merge failed for PR #{pr_number}")

            # Get updated PR to get merge commit
            pr = self.github_client.get_pull_request(pr_number)
            merge_commit = pr.merge_commit_sha

            self.logger.info(
                "PR merged successfully",
                pr_number=pr_number,
                merge_commit=merge_commit,
                strategy=self.pr_config.merge_strategy,
            )

            return merge_commit

        except Exception as e:
            self.logger.error(
                "Failed to execute merge",
                pr_number=pr_number,
                error=str(e),
                exc_info=True,
            )
            raise MergeValidationError(f"Merge execution failed: {e}")

    def _close_linked_issues(self, pr_number: int, pr: Any) -> List[int]:
        """Close issues linked to the PR.

        Args:
            pr_number: PR number
            pr: PullRequest object

        Returns:
            List of closed issue numbers
        """
        closed_issues = []

        try:
            # Parse PR body for issue references
            # GitHub automatically closes issues with keywords like:
            # "Closes #123", "Fixes #456", "Resolves #789"
            body = pr.body or ""

            import re

            # Find all issue references with closing keywords
            patterns = [
                r"[Cc]loses?\s+#(\d+)",
                r"[Ff]ixes?\s+#(\d+)",
                r"[Rr]esolves?\s+#(\d+)",
            ]

            for pattern in patterns:
                matches = re.findall(pattern, body)
                for match in matches:
                    issue_number = int(match)
                    if issue_number not in closed_issues:
                        closed_issues.append(issue_number)

            # GitHub auto-closes these, but we log them
            if closed_issues:
                self.logger.info(
                    "Linked issues will be closed by GitHub",
                    pr_number=pr_number,
                    issues=closed_issues,
                )

            return closed_issues

        except Exception as e:
            self.logger.warning(
                "Failed to parse linked issues",
                pr_number=pr_number,
                error=str(e),
            )
            return []

    def _add_closing_comment(self, pr_number: int, pr: Any) -> None:
        """Add a closing comment to the merged PR.

        Args:
            pr_number: PR number
            pr: PullRequest object
        """
        try:
            comment = f"""✅ **PR Merged Successfully**

This pull request has been merged using the `{self.pr_config.merge_strategy}` strategy.

**Merge Details:**
- Strategy: {self.pr_config.merge_strategy}
- Merged at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

🤖 _Merged by Self-Reflexive Orchestrator_
"""

            self.github_client.create_comment(pr_number, comment)

            self.logger.debug(
                "Added closing comment to PR",
                pr_number=pr_number,
            )

        except Exception as e:
            self.logger.warning(
                "Failed to add closing comment",
                pr_number=pr_number,
                error=str(e),
            )

    def get_statistics(self) -> Dict[str, Any]:
        """Get merge statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_merges": self.total_merges,
            "failed_merges": self.failed_merges,
            "validation_failures": self.validation_failures,
        }

    def reset_statistics(self):
        """Reset merge statistics."""
        self.total_merges = 0
        self.failed_merges = 0
        self.validation_failures = 0
