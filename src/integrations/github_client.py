"""GitHub API integration for the orchestrator."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from github import Github, GithubException
from github.Repository import Repository
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.GithubObject import NotSet

from ..core.logger import AuditLogger


class GitHubClient:
    """Wrapper around PyGithub for orchestrator operations."""

    def __init__(self, token: str, repository: str, logger: AuditLogger):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token
            repository: Repository in format "owner/repo"
            logger: Audit logger instance
        """
        self.token = token
        self.repository_name = repository
        self.logger = logger

        # Initialize GitHub client
        self.github = Github(token)
        self.repo: Repository = self.github.get_repo(repository)

    def get_issues(
        self,
        labels: Optional[List[str]] = None,
        state: str = "open",
        exclude_labels: Optional[List[str]] = None,
    ) -> List[Issue]:
        """Get issues from repository.

        Args:
            labels: Filter by labels (issues must have ALL labels)
            state: Issue state (open, closed, all)
            exclude_labels: Exclude issues with these labels

        Returns:
            List of matching issues
        """
        try:
            issues = self.repo.get_issues(state=state, labels=labels or [])

            # Filter out PRs (GitHub API treats PRs as issues)
            issues = [issue for issue in issues if not issue.pull_request]

            # Filter out excluded labels
            if exclude_labels:
                issues = [
                    issue
                    for issue in issues
                    if not any(label.name in exclude_labels for label in issue.labels)
                ]

            return list(issues)

        except GithubException as e:
            self.logger.error(
                "Failed to fetch issues",
                error=str(e),
                repository=self.repository_name,
            )
            raise

    def get_issue(self, issue_number: int) -> Issue:
        """Get a specific issue by number.

        Args:
            issue_number: Issue number

        Returns:
            Issue object
        """
        try:
            return self.repo.get_issue(issue_number)
        except GithubException as e:
            self.logger.error(
                f"Failed to fetch issue #{issue_number}",
                error=str(e),
                issue_number=issue_number,
            )
            raise

    def create_comment(self, issue_number: int, body: str):
        """Add a comment to an issue or PR.

        Args:
            issue_number: Issue/PR number
            body: Comment text
        """
        try:
            issue = self.repo.get_issue(issue_number)
            issue.create_comment(body)
            self.logger.info(
                f"Created comment on issue #{issue_number}",
                issue_number=issue_number,
            )
        except GithubException as e:
            self.logger.error(
                f"Failed to create comment on issue #{issue_number}",
                error=str(e),
                issue_number=issue_number,
            )
            raise

    def add_labels(self, issue_number: int, labels: List[str]):
        """Add labels to an issue.

        Args:
            issue_number: Issue number
            labels: List of label names
        """
        try:
            issue = self.repo.get_issue(issue_number)
            issue.add_to_labels(*labels)
            self.logger.info(
                f"Added labels to issue #{issue_number}",
                issue_number=issue_number,
                labels=labels,
            )
        except GithubException as e:
            self.logger.error(
                f"Failed to add labels to issue #{issue_number}",
                error=str(e),
                issue_number=issue_number,
                labels=labels,
            )
            raise

    def remove_label(self, issue_number: int, label: str):
        """Remove a label from an issue.

        Args:
            issue_number: Issue number
            label: Label name to remove
        """
        try:
            issue = self.repo.get_issue(issue_number)
            issue.remove_from_labels(label)
            self.logger.info(
                f"Removed label from issue #{issue_number}",
                issue_number=issue_number,
                label=label,
            )
        except GithubException as e:
            self.logger.error(
                f"Failed to remove label from issue #{issue_number}",
                error=str(e),
                issue_number=issue_number,
                label=label,
            )
            raise

    def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = False,
    ) -> PullRequest:
        """Create a pull request.

        Args:
            title: PR title
            body: PR description
            head: Head branch name
            base: Base branch name
            draft: Create as draft PR

        Returns:
            Created PullRequest object
        """
        try:
            pr = self.repo.create_pull(
                title=title,
                body=body,
                head=head,
                base=base,
                draft=draft,
            )
            self.logger.pr_created(
                pr_number=pr.number,
                pr_title=title,
                branch=head,
            )
            return pr
        except GithubException as e:
            self.logger.error(
                "Failed to create pull request",
                error=str(e),
                title=title,
                head=head,
                base=base,
            )
            raise

    def get_pull_request(self, pr_number: int) -> PullRequest:
        """Get a specific pull request.

        Args:
            pr_number: PR number

        Returns:
            PullRequest object
        """
        try:
            return self.repo.get_pull(pr_number)
        except GithubException as e:
            self.logger.error(
                f"Failed to fetch PR #{pr_number}",
                error=str(e),
                pr_number=pr_number,
            )
            raise

    def get_pr_checks(self, pr_number: int) -> Dict[str, Any]:
        """Get CI/CD check status for a PR.

        Args:
            pr_number: PR number

        Returns:
            Dictionary with check status information
        """
        try:
            pr = self.repo.get_pull(pr_number)
            commit = pr.get_commits().reversed[0]  # Latest commit

            # Get check runs
            check_runs = commit.get_check_runs()

            # Get statuses (for older CI systems)
            statuses = commit.get_statuses()

            all_checks = []

            # Process check runs (GitHub Actions, etc.)
            for check in check_runs:
                all_checks.append(
                    {
                        "name": check.name,
                        "status": check.status,
                        "conclusion": check.conclusion,
                        "started_at": (
                            check.started_at.isoformat() if check.started_at else None
                        ),
                        "completed_at": (
                            check.completed_at.isoformat()
                            if check.completed_at
                            else None
                        ),
                    }
                )

            # Process commit statuses
            for status in statuses:
                all_checks.append(
                    {
                        "name": status.context,
                        "status": "completed",
                        "conclusion": status.state,
                        "description": status.description,
                    }
                )

            # Determine overall status
            if not all_checks:
                overall = "no_checks"
            elif any(c.get("conclusion") == "failure" for c in all_checks):
                overall = "failed"
            elif all(
                c.get("conclusion") in ["success", "neutral", "skipped"]
                or c.get("status") == "success"
                for c in all_checks
            ):
                overall = "passed"
            elif any(c.get("status") in ["queued", "in_progress"] for c in all_checks):
                overall = "pending"
            else:
                overall = "unknown"

            return {
                "overall": overall,
                "checks": all_checks,
            }

        except GithubException as e:
            self.logger.error(
                f"Failed to get checks for PR #{pr_number}",
                error=str(e),
                pr_number=pr_number,
            )
            raise

    def merge_pull_request(
        self,
        pr_number: int,
        merge_method: str = "squash",
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> bool:
        """Merge a pull request.

        Args:
            pr_number: PR number
            merge_method: Merge method (merge, squash, rebase)
            commit_title: Custom commit title
            commit_message: Custom commit message

        Returns:
            True if merged successfully
        """
        try:
            pr = self.repo.get_pull(pr_number)

            result = pr.merge(
                commit_title=commit_title or NotSet,
                commit_message=commit_message or NotSet,
                merge_method=merge_method,
            )

            if result.merged:
                self.logger.pr_merged(
                    pr_number=pr_number,
                    pr_title=pr.title,
                    merge_commit=result.sha,
                )
                return True
            else:
                self.logger.warning(
                    f"Failed to merge PR #{pr_number}",
                    pr_number=pr_number,
                    message=result.message,
                )
                return False

        except GithubException as e:
            self.logger.error(
                f"Failed to merge PR #{pr_number}",
                error=str(e),
                pr_number=pr_number,
            )
            raise

    def close_issue(self, issue_number: int, comment: Optional[str] = None):
        """Close an issue.

        Args:
            issue_number: Issue number
            comment: Optional comment to add before closing
        """
        try:
            issue = self.repo.get_issue(issue_number)

            if comment:
                issue.create_comment(comment)

            issue.edit(state="closed")

            self.logger.info(
                f"Closed issue #{issue_number}",
                issue_number=issue_number,
            )

        except GithubException as e:
            self.logger.error(
                f"Failed to close issue #{issue_number}",
                error=str(e),
                issue_number=issue_number,
            )
            raise

    def create_issue(
        self,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
    ) -> Issue:
        """Create a new issue.

        Args:
            title: Issue title
            body: Issue description
            labels: List of label names
            assignees: List of user logins to assign

        Returns:
            Created Issue object
        """
        try:
            issue = self.repo.create_issue(
                title=title,
                body=body,
                labels=labels or [],
                assignees=assignees or [],
            )

            self.logger.info(
                f"Created issue #{issue.number}: {title}",
                issue_number=issue.number,
                title=title,
                labels=labels,
            )

            return issue

        except GithubException as e:
            self.logger.error(
                "Failed to create issue",
                error=str(e),
                title=title,
            )
            raise

    def request_review(self, pr_number: int, reviewers: List[str]):
        """Request reviews on a pull request.

        Args:
            pr_number: PR number
            reviewers: List of reviewer usernames
        """
        try:
            pr = self.repo.get_pull(pr_number)
            pr.create_review_request(reviewers=reviewers)

            self.logger.info(
                f"Requested review on PR #{pr_number}",
                pr_number=pr_number,
                reviewers=reviewers,
            )

        except GithubException as e:
            self.logger.error(
                f"Failed to request review on PR #{pr_number}",
                error=str(e),
                pr_number=pr_number,
                reviewers=reviewers,
            )
            raise

    def get_file_contents(self, path: str, ref: Optional[str] = None) -> str:
        """Get contents of a file from the repository.

        Args:
            path: File path in repository
            ref: Branch/commit/tag reference (defaults to default branch)

        Returns:
            File contents as string
        """
        try:
            contents = self.repo.get_contents(path, ref=ref or NotSet)
            if isinstance(contents, list):
                raise ValueError(f"Path {path} is a directory, not a file")
            return contents.decoded_content.decode("utf-8")

        except GithubException as e:
            self.logger.error(
                f"Failed to get file contents: {path}",
                error=str(e),
                path=path,
                ref=ref,
            )
            raise
