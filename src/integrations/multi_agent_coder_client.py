"""Integration with multi-agent-coder CLI for enhanced analysis."""

import subprocess
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum
from datetime import datetime, timezone

from ..core.logger import AuditLogger


class MultiAgentStrategy(Enum):
    """Available multi-agent-coder routing strategies."""

    ALL = "all"
    SEQUENTIAL = "sequential"
    DIALECTICAL = "dialectical"


@dataclass
class MultiAgentResponse:
    """Response from multi-agent-coder."""

    providers: List[str]
    responses: Dict[str, str]
    strategy: str
    total_tokens: int
    total_cost: float
    success: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class MultiAgentCoderClient:
    """Client for interacting with multi-agent-coder CLI application.

    This client provides integration with the multi-agent-coder Elixir CLI
    located at ../multi_agent_coder, enabling the orchestrator to leverage
    multiple AI providers (Anthropic, OpenAI, DeepSeek, etc.) for enhanced
    code analysis and generation.
    """

    def __init__(
        self,
        multi_agent_coder_path: str,
        logger: AuditLogger,
        default_strategy: MultiAgentStrategy = MultiAgentStrategy.ALL,
        default_providers: Optional[List[str]] = None,
    ):
        """Initialize multi-agent-coder client.

        Args:
            multi_agent_coder_path: Path to multi_agent_coder executable
            logger: Audit logger instance
            default_strategy: Default routing strategy to use
            default_providers: List of providers to use (None = use all available)
        """
        self.executable_path = Path(multi_agent_coder_path)
        self.logger = logger
        self.default_strategy = default_strategy
        self.default_providers = default_providers or []

        # Verify executable exists
        if not self.executable_path.exists():
            raise FileNotFoundError(
                f"multi_agent_coder executable not found at {multi_agent_coder_path}"
            )

        # Statistics
        self.total_calls = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.provider_usage: Dict[str, int] = {}

    def query(
        self,
        prompt: str,
        strategy: Optional[MultiAgentStrategy] = None,
        providers: Optional[List[str]] = None,
        timeout: int = 120,
    ) -> MultiAgentResponse:
        """Query multi-agent-coder with a prompt.

        Args:
            prompt: The prompt to send to multi-agent-coder
            strategy: Routing strategy (defaults to instance default)
            providers: List of provider names to use (defaults to instance default)
            timeout: Timeout in seconds for the request

        Returns:
            MultiAgentResponse with results from all providers

        Raises:
            subprocess.TimeoutExpired: If query times out
            subprocess.CalledProcessError: If multi_agent_coder fails
        """
        strategy = strategy or self.default_strategy
        providers = providers or self.default_providers

        # Build command
        cmd = [str(self.executable_path)]

        # Add strategy flag
        cmd.extend(["-s", strategy.value])

        # Add provider filter if specified
        if providers:
            cmd.extend(["-p", ",".join(providers)])

        # Add prompt
        cmd.append(prompt)

        self.logger.debug(
            "Calling multi-agent-coder",
            strategy=strategy.value,
            providers=providers,
            prompt_length=len(prompt),
        )

        try:
            # Execute multi_agent_coder
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.executable_path.parent,
            )

            # Parse output
            response = self._parse_output(result.stdout, result.stderr)

            # Update statistics
            self.total_calls += 1
            self.total_tokens += response.total_tokens
            self.total_cost += response.total_cost
            for provider in response.providers:
                self.provider_usage[provider] = self.provider_usage.get(provider, 0) + 1

            self.logger.info(
                "multi-agent-coder query completed",
                providers=response.providers,
                tokens=response.total_tokens,
                cost=response.total_cost,
                success=response.success,
            )

            return response

        except subprocess.TimeoutExpired as e:
            self.logger.error(
                "multi-agent-coder query timed out",
                timeout=timeout,
                exc_info=True,
            )
            return MultiAgentResponse(
                providers=[],
                responses={},
                strategy=strategy.value,
                total_tokens=0,
                total_cost=0.0,
                success=False,
                error=f"Query timed out after {timeout}s",
            )

        except subprocess.CalledProcessError as e:
            self.logger.error(
                "multi-agent-coder execution failed",
                error=e.stderr,
                return_code=e.returncode,
                exc_info=True,
            )
            return MultiAgentResponse(
                providers=[],
                responses={},
                strategy=strategy.value,
                total_tokens=0,
                total_cost=0.0,
                success=False,
                error=f"Execution failed: {e.stderr}",
            )

        except Exception as e:
            self.logger.error(
                "Unexpected error calling multi-agent-coder",
                error=str(e),
                exc_info=True,
            )
            return MultiAgentResponse(
                providers=[],
                responses={},
                strategy=strategy.value,
                total_tokens=0,
                total_cost=0.0,
                success=False,
                error=f"Unexpected error: {str(e)}",
            )

    def _parse_output(self, stdout: str, stderr: str) -> MultiAgentResponse:
        """Parse multi-agent-coder output.

        Args:
            stdout: Standard output from multi_agent_coder
            stderr: Standard error from multi_agent_coder

        Returns:
            Parsed MultiAgentResponse
        """
        providers = []
        responses = {}
        total_tokens = 0
        total_cost = 0.0

        # Parse stdout for provider responses
        current_provider = None
        current_response = []

        for line in stdout.split("\n"):
            # Detect provider headers (e.g., "╔═══ ANTHROPIC ═══╗")
            if "═══" in line and "═══" in line:
                if current_provider and current_response:
                    responses[current_provider] = "\n".join(current_response).strip()
                    current_response = []

                # Extract provider name
                provider_match = line.replace("╔═══", "").replace("═══╗", "").strip()
                if provider_match:
                    current_provider = provider_match.lower()
                    providers.append(current_provider)
                continue

            # Skip error lines
            if line.startswith("Error:"):
                continue

            # Collect response lines
            if current_provider:
                current_response.append(line)

        # Add last provider response
        if current_provider and current_response:
            responses[current_provider] = "\n".join(current_response).strip()

        # Parse token and cost information from stderr or stdout
        for line in (stdout + "\n" + stderr).split("\n"):
            if "tokens" in line.lower():
                # Try to extract token count (e.g., "7121 tokens")
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if "token" in part.lower() and i > 0:
                            total_tokens += int(parts[i - 1].replace(",", ""))
                except (ValueError, IndexError):
                    pass

            if "$" in line:
                # Try to extract cost (e.g., "$0.0656")
                try:
                    cost_str = line[line.index("$") + 1 :].split()[0]
                    total_cost += float(cost_str.replace(",", ""))
                except (ValueError, IndexError):
                    pass

        return MultiAgentResponse(
            providers=providers,
            responses=responses,
            strategy=self.default_strategy.value,
            total_tokens=total_tokens,
            total_cost=total_cost,
            success=len(responses) > 0,
        )

    def analyze_issue(
        self,
        issue_title: str,
        issue_body: str,
        labels: List[str],
    ) -> MultiAgentResponse:
        """Analyze a GitHub issue using multi-agent-coder.

        Args:
            issue_title: The issue title
            issue_body: The issue description
            labels: List of issue labels

        Returns:
            MultiAgentResponse with analysis from multiple providers
        """
        prompt = f"""Analyze the following GitHub issue and provide:

1. **Issue Type**: Classify as bug, feature, refactor, documentation, or other
2. **Complexity Score**: Rate from 0-10 (0=trivial, 10=extremely complex)
3. **Actionability**: Is this issue actionable? (yes/no with reasoning)
4. **Key Requirements**: List 3-5 key requirements
5. **Affected Files**: List files likely to be modified (if determinable)
6. **Risks**: Potential risks or challenges
7. **Recommended Approach**: High-level implementation approach

**Issue Title:** {issue_title}

**Labels:** {', '.join(labels) if labels else 'None'}

**Issue Body:**
{issue_body}

Please provide your analysis in a structured format.
"""

        return self.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            timeout=120,
        )

    def review_code(
        self,
        code: str,
        focus_areas: Optional[List[str]] = None,
    ) -> MultiAgentResponse:
        """Review code using multi-agent-coder.

        Args:
            code: The code to review
            focus_areas: Specific areas to focus on (e.g., ["security", "performance"])

        Returns:
            MultiAgentResponse with review feedback from multiple providers
        """
        focus = "\n".join([f"- {area}" for area in (focus_areas or [])])
        default_focus = "- Code quality and best practices\n- Error handling\n- Performance\n- Security\n- Maintainability"

        prompt = f"""Review the following code and provide feedback on:
{focus if focus else default_focus}

**Code:**
```python
{code}
```

Provide specific suggestions for improvement.
"""

        return self.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
            timeout=180,
        )

    def review_pull_request(
        self,
        pr_diff: str,
        pr_description: str,
        files_changed: List[str],
        pr_number: int,
        timeout: int = 600,
    ) -> "PRReviewResult":
        """Review a pull request using multi-agent-coder.

        Args:
            pr_diff: Full diff of the PR
            pr_description: PR description/body
            files_changed: List of files changed in the PR
            pr_number: PR number for reference
            timeout: Timeout in seconds for the review

        Returns:
            PRReviewResult with review feedback from multiple providers
        """
        prompt = f"""Review the following Pull Request and provide comprehensive feedback.

**PR Number:** #{pr_number}

**PR Description:**
{pr_description}

**Files Changed:**
{', '.join(files_changed) if files_changed else 'None'}

**Diff:**
```diff
{pr_diff}
```

Please provide your review covering:
1. **Overall Assessment**: Approve or request changes (with clear reasoning)
2. **Code Quality**: Adherence to best practices, readability, maintainability
3. **Potential Issues**: Bugs, edge cases, security concerns, performance issues
4. **Specific Feedback**: File-specific and line-specific comments where applicable
5. **Suggestions**: Concrete improvements or alternatives

Format your response as:
- **Decision**: APPROVE or CHANGES_REQUESTED
- **Summary**: Brief overall assessment
- **Comments**: Specific feedback items with file/line references where possible
"""

        self.logger.info(
            "Requesting PR review from multi-agent-coder",
            pr_number=pr_number,
            files_changed_count=len(files_changed),
            diff_length=len(pr_diff),
        )

        response = self.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
            timeout=timeout,
        )

        # Parse review response into structured result
        review_result = self._parse_pr_review(response, pr_number)

        self.logger.info(
            "PR review completed",
            pr_number=pr_number,
            approved=review_result.approved,
            comments_count=len(review_result.comments),
            providers=response.providers,
        )

        return review_result

    def _parse_pr_review(
        self, response: MultiAgentResponse, pr_number: int
    ) -> "PRReviewResult":
        """Parse multi-agent response into structured PR review result.

        Args:
            response: Response from multi-agent-coder
            pr_number: PR number being reviewed

        Returns:
            Parsed PRReviewResult
        """
        from dataclasses import dataclass

        # Aggregate responses from all providers
        all_approvals = []
        all_comments = []
        summary_parts = []

        for provider, provider_response in response.responses.items():
            # Check for approval/rejection
            response_lower = provider_response.lower()
            is_approved = (
                "approve" in response_lower
                and "changes_requested" not in response_lower
                and "request changes" not in response_lower
            )
            all_approvals.append(is_approved)

            # Extract comments
            comments = self._extract_review_comments(provider_response, provider)
            all_comments.extend(comments)

            # Add to summary
            summary_parts.append(
                f"**{provider.upper()}**: {provider_response[:200]}..."
            )

        # Overall approval: require majority approval
        approval_count = sum(all_approvals)
        total_reviewers = len(all_approvals)
        approved = (
            approval_count > (total_reviewers / 2) if total_reviewers > 0 else False
        )

        summary = "\n\n".join(summary_parts)

        return PRReviewResult(
            pr_number=pr_number,
            approved=approved,
            reviewer="multi-agent-coder",
            comments=all_comments,
            summary=summary,
            providers_reviewed=list(response.responses.keys()),
            approval_count=approval_count,
            total_reviewers=total_reviewers,
            total_tokens=response.total_tokens,
            total_cost=response.total_cost,
        )

    def _extract_review_comments(
        self, review_text: str, provider: str
    ) -> List["ReviewComment"]:
        """Extract structured comments from review text.

        Args:
            review_text: Raw review text from a provider
            provider: Provider name

        Returns:
            List of ReviewComment objects
        """
        comments = []

        # Split review into lines
        lines = review_text.split("\n")

        current_comment = {
            "message": [],
            "file": None,
            "line": None,
            "severity": "info",
        }

        for line in lines:
            line = line.strip()

            # Look for file references (e.g., "src/foo.py:42" or "In src/foo.py")
            if ":" in line and ("src/" in line or "tests/" in line or ".py" in line):
                # Try to extract file and line
                parts = line.split(":")
                if len(parts) >= 2:
                    file_part = parts[0].strip()
                    # Extract file path
                    if "/" in file_part or ".py" in file_part:
                        current_comment["file"] = file_part.split()[-1]
                        try:
                            current_comment["line"] = int(parts[1].split()[0])
                        except (ValueError, IndexError):
                            pass

            # Determine severity
            line_lower = line.lower()
            if any(
                word in line_lower for word in ["critical", "security", "bug", "error"]
            ):
                current_comment["severity"] = "error"
            elif any(word in line_lower for word in ["warning", "concern", "issue"]):
                current_comment["severity"] = "warning"

            # Collect comment message
            if line and not line.startswith("#"):
                current_comment["message"].append(line)

            # Create comment if we have enough context
            if len(current_comment["message"]) > 2 and (
                current_comment["file"]
                or any(
                    keyword in " ".join(current_comment["message"]).lower()
                    for keyword in [
                        "suggest",
                        "consider",
                        "should",
                        "could",
                        "recommend",
                    ]
                )
            ):
                comments.append(
                    ReviewComment(
                        file=current_comment["file"],
                        line=current_comment["line"],
                        severity=current_comment["severity"],
                        message=" ".join(current_comment["message"]),
                        provider=provider,
                    )
                )
                current_comment = {
                    "message": [],
                    "file": None,
                    "line": None,
                    "severity": "info",
                }

        # Add final comment if present
        if current_comment["message"]:
            comments.append(
                ReviewComment(
                    file=current_comment["file"],
                    line=current_comment["line"],
                    severity=current_comment["severity"],
                    message=" ".join(current_comment["message"]),
                    provider=provider,
                )
            )

        return comments

    def get_statistics(self) -> Dict[str, Any]:
        """Get usage statistics.

        Returns:
            Dictionary with usage statistics
        """
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "provider_usage": self.provider_usage,
            "average_tokens_per_call": (
                self.total_tokens / self.total_calls if self.total_calls > 0 else 0
            ),
            "average_cost_per_call": (
                self.total_cost / self.total_calls if self.total_calls > 0 else 0
            ),
        }

    def reset_statistics(self):
        """Reset usage statistics."""
        self.total_calls = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.provider_usage.clear()


@dataclass
class ReviewComment:
    """A single review comment."""

    message: str
    provider: str
    file: Optional[str] = None
    line: Optional[int] = None
    severity: str = "info"  # info, warning, error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "message": self.message,
            "provider": self.provider,
        }


@dataclass
class PRReviewResult:
    """Result of PR review from multi-agent-coder."""

    pr_number: int
    approved: bool
    reviewer: str
    comments: List[ReviewComment]
    summary: str
    providers_reviewed: List[str] = field(default_factory=list)
    approval_count: int = 0
    total_reviewers: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pr_number": self.pr_number,
            "approved": self.approved,
            "reviewer": self.reviewer,
            "comments": [c.to_dict() for c in self.comments],
            "summary": self.summary,
            "providers_reviewed": self.providers_reviewed,
            "approval_count": self.approval_count,
            "total_reviewers": self.total_reviewers,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "reviewed_at": self.reviewed_at.isoformat(),
        }
