"""Rollback mechanism for failed operations.

Provides comprehensive rollback capabilities including:
- Commit tagging before risky operations
- Git revert functionality
- Branch cleanup
- Rollback point tracking
- Manual and automatic rollback triggers
"""

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.logger import AuditLogger
from ..integrations.github_client import GitHubClient


@dataclass
class RollbackPoint:
    """Represents a point in time that can be rolled back to."""

    commit_sha: str
    tag_name: str
    description: str
    created_at: datetime
    branch_name: str
    work_item_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "commit_sha": self.commit_sha,
            "tag_name": self.tag_name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "branch_name": self.branch_name,
            "work_item_id": self.work_item_id,
            "metadata": self.metadata,
        }


@dataclass
class RollbackResult:
    """Result of rollback operation."""

    success: bool
    rollback_point: RollbackPoint
    reverted_commits: List[str]
    cleaned_branches: List[str]
    error: Optional[str] = None
    revert_commit_sha: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "rollback_point": self.rollback_point.to_dict(),
            "reverted_commits": self.reverted_commits,
            "cleaned_branches": self.cleaned_branches,
            "error": self.error,
            "revert_commit_sha": self.revert_commit_sha,
        }


class RollbackManager:
    """Manages rollback operations for failed changes.

    Responsibilities:
    - Create rollback points before risky operations
    - Execute rollbacks when needed
    - Clean up branches after rollback
    - Track rollback history
    - Support manual rollback via CLI
    """

    def __init__(
        self,
        repository_path: str,
        github_client: Optional[GitHubClient],
        logger: AuditLogger,
        auto_cleanup_branches: bool = True,
    ):
        """Initialize rollback manager.

        Args:
            repository_path: Path to git repository
            github_client: GitHub client for PR operations
            logger: Audit logger
            auto_cleanup_branches: Automatically clean up branches after rollback
        """
        self.repository_path = Path(repository_path)
        self.github_client = github_client
        self.logger = logger
        self.auto_cleanup_branches = auto_cleanup_branches

        # Verify git repository
        if not (self.repository_path / ".git").exists():
            raise ValueError(f"Not a git repository: {repository_path}")

        self.logger.info(
            "rollback_manager_initialized",
            repository_path=str(self.repository_path),
            auto_cleanup=auto_cleanup_branches,
        )

    def create_rollback_point(
        self,
        description: str,
        work_item_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RollbackPoint:
        """Create a rollback point by tagging current commit.

        Args:
            description: Description of rollback point
            work_item_id: Optional work item ID
            metadata: Optional additional metadata

        Returns:
            Created RollbackPoint
        """
        # Get current commit
        commit_sha = self._get_current_commit()
        branch_name = self._get_current_branch()

        # Generate tag name
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        tag_name = f"rollback-point-{timestamp}"
        if work_item_id:
            tag_name = f"rollback-{work_item_id}-{timestamp}"

        # Create git tag
        self._create_git_tag(tag_name, commit_sha, description)

        rollback_point = RollbackPoint(
            commit_sha=commit_sha,
            tag_name=tag_name,
            description=description,
            created_at=datetime.now(timezone.utc),
            branch_name=branch_name,
            work_item_id=work_item_id,
            metadata=metadata or {},
        )

        self.logger.info(
            "rollback_point_created",
            tag_name=tag_name,
            commit_sha=commit_sha[:8],
            branch=branch_name,
            work_item_id=work_item_id,
        )

        return rollback_point

    def rollback(
        self,
        rollback_point: RollbackPoint,
        cleanup_branches: Optional[bool] = None,
        create_revert_commit: bool = True,
    ) -> RollbackResult:
        """Rollback to a specific point.

        Args:
            rollback_point: Point to rollback to
            cleanup_branches: Override auto_cleanup_branches
            create_revert_commit: Create a revert commit (vs hard reset)

        Returns:
            RollbackResult with details
        """
        self.logger.info(
            "rollback_started",
            tag_name=rollback_point.tag_name,
            target_commit=rollback_point.commit_sha[:8],
        )

        try:
            # Get current commit for tracking
            current_commit = self._get_current_commit()

            # Get commits to revert
            commits_to_revert = self._get_commits_between(
                rollback_point.commit_sha,
                current_commit,
            )

            revert_commit_sha = None

            if create_revert_commit:
                # Create revert commit (safer, preserves history)
                revert_commit_sha = self._create_revert_commit(
                    rollback_point.commit_sha,
                    f"Rollback to {rollback_point.tag_name}: {rollback_point.description}",
                )
            else:
                # Hard reset (dangerous, loses history)
                self._hard_reset(rollback_point.commit_sha)

            # Cleanup branches if enabled
            cleaned_branches = []
            should_cleanup = (
                cleanup_branches
                if cleanup_branches is not None
                else self.auto_cleanup_branches
            )

            if should_cleanup and rollback_point.branch_name:
                try:
                    self._cleanup_branch(rollback_point.branch_name)
                    cleaned_branches.append(rollback_point.branch_name)
                except Exception as e:
                    self.logger.warning(
                        "branch_cleanup_failed",
                        branch=rollback_point.branch_name,
                        error=str(e),
                    )

            result = RollbackResult(
                success=True,
                rollback_point=rollback_point,
                reverted_commits=commits_to_revert,
                cleaned_branches=cleaned_branches,
                revert_commit_sha=revert_commit_sha,
            )

            self.logger.info(
                "rollback_completed",
                tag_name=rollback_point.tag_name,
                commits_reverted=len(commits_to_revert),
                branches_cleaned=len(cleaned_branches),
            )

            return result

        except Exception as e:
            self.logger.error(
                "rollback_failed",
                tag_name=rollback_point.tag_name,
                error=str(e),
                exc_info=True,
            )

            return RollbackResult(
                success=False,
                rollback_point=rollback_point,
                reverted_commits=[],
                cleaned_branches=[],
                error=str(e),
            )

    def rollback_pr(
        self,
        pr_number: int,
        reason: str,
        create_revert_pr: bool = True,
    ) -> RollbackResult:
        """Rollback a merged PR.

        Args:
            pr_number: PR number to rollback
            reason: Reason for rollback
            create_revert_pr: Create a revert PR (vs direct revert)

        Returns:
            RollbackResult
        """
        if not self.github_client:
            raise ValueError("GitHub client required for PR rollback")

        self.logger.info(
            "pr_rollback_started",
            pr_number=pr_number,
            reason=reason,
        )

        try:
            # Get PR details
            pr = self.github_client.get_pull_request(pr_number)

            if not pr.merged:
                raise ValueError(f"PR #{pr_number} is not merged")

            # Get merge commit
            merge_commit = pr.merge_commit_sha

            if create_revert_pr:
                # Create revert PR
                revert_branch = f"revert-pr-{pr_number}"
                self._create_branch(revert_branch)
                self._checkout_branch(revert_branch)

                # Revert the merge commit
                self._git_revert_merge(merge_commit)

                # Push revert branch
                self._push_branch(revert_branch)

                # Create revert PR
                revert_pr = self.github_client.create_pull_request(
                    title=f"Revert PR #{pr_number}: {pr.title}",
                    body=f"""This reverts PR #{pr_number}.

**Reason for Rollback**: {reason}

**Original PR**: #{pr_number}
**Original Title**: {pr.title}
**Merge Commit**: {merge_commit[:8]}

🤖 Automated rollback""",
                    head=revert_branch,
                    base=pr.base.ref,
                )

                self.logger.info(
                    "revert_pr_created",
                    original_pr=pr_number,
                    revert_pr=revert_pr.number,
                )

                # Create dummy rollback point for result
                rollback_point = RollbackPoint(
                    commit_sha=merge_commit,
                    tag_name=f"rollback-pr-{pr_number}",
                    description=f"Rollback PR #{pr_number}",
                    created_at=datetime.now(timezone.utc),
                    branch_name=revert_branch,
                    work_item_id=f"pr-{pr_number}",
                )

                return RollbackResult(
                    success=True,
                    rollback_point=rollback_point,
                    reverted_commits=[merge_commit],
                    cleaned_branches=[],
                    revert_commit_sha=revert_pr.head.sha,
                )

            else:
                # Direct revert on current branch
                self._git_revert_merge(merge_commit)

                rollback_point = RollbackPoint(
                    commit_sha=merge_commit,
                    tag_name=f"rollback-pr-{pr_number}",
                    description=f"Rollback PR #{pr_number}",
                    created_at=datetime.now(timezone.utc),
                    branch_name=self._get_current_branch(),
                    work_item_id=f"pr-{pr_number}",
                )

                return RollbackResult(
                    success=True,
                    rollback_point=rollback_point,
                    reverted_commits=[merge_commit],
                    cleaned_branches=[],
                    revert_commit_sha=self._get_current_commit(),
                )

        except Exception as e:
            self.logger.error(
                "pr_rollback_failed",
                pr_number=pr_number,
                error=str(e),
                exc_info=True,
            )

            raise

    def list_rollback_points(self) -> List[RollbackPoint]:
        """List all rollback points (tags).

        Returns:
            List of RollbackPoint objects
        """
        result = self._run_git_command(["tag", "-l", "rollback-*"])

        rollback_points = []
        for tag in result.stdout.strip().split("\n"):
            if not tag:
                continue

            try:
                # Get tag details
                tag_info = self._run_git_command(
                    ["show", tag, "--format=%H%n%s%n%ci", "--no-patch"]
                )

                lines = tag_info.stdout.strip().split("\n")
                if len(lines) >= 3:
                    commit_sha = lines[0]
                    description = lines[1]
                    created_at_str = lines[2]

                    rollback_point = RollbackPoint(
                        commit_sha=commit_sha,
                        tag_name=tag,
                        description=description,
                        created_at=datetime.fromisoformat(
                            created_at_str.replace(" ", "T")
                        ),
                        branch_name="unknown",
                    )
                    rollback_points.append(rollback_point)

            except Exception as e:
                self.logger.warning(
                    "failed_to_parse_rollback_point",
                    tag=tag,
                    error=str(e),
                )

        return rollback_points

    def _get_current_commit(self) -> str:
        """Get current commit SHA."""
        result = self._run_git_command(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def _get_current_branch(self) -> str:
        """Get current branch name."""
        result = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def _create_git_tag(self, tag_name: str, commit_sha: str, message: str):
        """Create annotated git tag."""
        self._run_git_command(["tag", "-a", tag_name, commit_sha, "-m", message])

    def _get_commits_between(self, start_commit: str, end_commit: str) -> List[str]:
        """Get list of commits between two commits."""
        result = self._run_git_command(["rev-list", f"{start_commit}..{end_commit}"])
        commits = result.stdout.strip().split("\n")
        return [c for c in commits if c]

    def _create_revert_commit(self, target_commit: str, message: str) -> str:
        """Create a revert commit."""
        # Revert to target commit (creates new commit)
        self._run_git_command(["revert", "--no-commit", f"{target_commit}..HEAD"])
        self._run_git_command(["commit", "-m", message])
        return self._get_current_commit()

    def _hard_reset(self, commit_sha: str):
        """Hard reset to commit (DANGEROUS - loses history)."""
        self._run_git_command(["reset", "--hard", commit_sha])

    def _git_revert_merge(self, merge_commit: str):
        """Revert a merge commit."""
        self._run_git_command(["revert", "-m", "1", merge_commit])

    def _cleanup_branch(self, branch_name: str):
        """Delete a branch locally and remotely."""
        current_branch = self._get_current_branch()

        # Can't delete current branch
        if branch_name == current_branch:
            self.logger.warning(
                "cannot_delete_current_branch",
                branch=branch_name,
            )
            return

        # Delete local branch
        try:
            self._run_git_command(["branch", "-D", branch_name])
        except subprocess.CalledProcessError:
            pass  # Branch might not exist locally

        # Delete remote branch
        try:
            self._run_git_command(["push", "origin", "--delete", branch_name])
        except subprocess.CalledProcessError:
            pass  # Branch might not exist remotely

    def _create_branch(self, branch_name: str):
        """Create a new branch."""
        self._run_git_command(["checkout", "-b", branch_name])

    def _checkout_branch(self, branch_name: str):
        """Checkout a branch."""
        self._run_git_command(["checkout", branch_name])

    def _push_branch(self, branch_name: str):
        """Push branch to remote."""
        self._run_git_command(["push", "-u", "origin", branch_name])

    def _run_git_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run git command in repository.

        Args:
            args: Git command arguments

        Returns:
            CompletedProcess result

        Raises:
            subprocess.CalledProcessError: If command fails
        """
        result = subprocess.run(
            ["git"] + args,
            cwd=self.repository_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result
