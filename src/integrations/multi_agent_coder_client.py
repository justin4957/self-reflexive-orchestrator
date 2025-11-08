"""Integration with multi-agent-coder CLI for enhanced analysis."""

import subprocess
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

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

        for line in stdout.split('\n'):
            # Detect provider headers (e.g., "╔═══ ANTHROPIC ═══╗")
            if '═══' in line and '═══' in line:
                if current_provider and current_response:
                    responses[current_provider] = '\n'.join(current_response).strip()
                    current_response = []

                # Extract provider name
                provider_match = line.replace('╔═══', '').replace('═══╗', '').strip()
                if provider_match:
                    current_provider = provider_match.lower()
                    providers.append(current_provider)
                continue

            # Skip error lines
            if line.startswith('Error:'):
                continue

            # Collect response lines
            if current_provider:
                current_response.append(line)

        # Add last provider response
        if current_provider and current_response:
            responses[current_provider] = '\n'.join(current_response).strip()

        # Parse token and cost information from stderr or stdout
        for line in (stdout + '\n' + stderr).split('\n'):
            if 'tokens' in line.lower():
                # Try to extract token count (e.g., "7121 tokens")
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if 'token' in part.lower() and i > 0:
                            total_tokens += int(parts[i-1].replace(',', ''))
                except (ValueError, IndexError):
                    pass

            if '$' in line:
                # Try to extract cost (e.g., "$0.0656")
                try:
                    cost_str = line[line.index('$')+1:].split()[0]
                    total_cost += float(cost_str.replace(',', ''))
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

        prompt = f"""Review the following code and provide feedback on:
{focus if focus else "- Code quality and best practices\n- Error handling\n- Performance\n- Security\n- Maintainability"}

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
