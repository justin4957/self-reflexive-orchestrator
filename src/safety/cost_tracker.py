"""Cost tracking for API usage across all providers.

Tracks costs, tokens, and requests for:
- GitHub API
- Anthropic API (Claude)
- Multi-agent-coder (Anthropic, DeepSeek, OpenAI, Perplexity)

Enforces daily cost ceilings and provides usage reports.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.logger import AuditLogger


class Provider(Enum):
    """API providers we track."""

    GITHUB = "github"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    PERPLEXITY = "perplexity"


class CostLimitExceeded(Exception):
    """Raised when daily cost limit is exceeded."""

    pass


@dataclass
class ProviderUsage:
    """Usage statistics for a single provider."""

    provider: Provider
    requests: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    cost: float = 0.0
    last_request_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "provider": self.provider.value,
            "requests": self.requests,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tokens_total": self.tokens_total,
            "cost": self.cost,
            "last_request_time": (
                self.last_request_time.isoformat() if self.last_request_time else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderUsage":
        """Create from dictionary."""
        return cls(
            provider=Provider(data["provider"]),
            requests=data.get("requests", 0),
            tokens_input=data.get("tokens_input", 0),
            tokens_output=data.get("tokens_output", 0),
            tokens_total=data.get("tokens_total", 0),
            cost=data.get("cost", 0.0),
            last_request_time=(
                datetime.fromisoformat(data["last_request_time"])
                if data.get("last_request_time")
                else None
            ),
        )


@dataclass
class DailyUsage:
    """Daily usage tracking."""

    date: str  # YYYY-MM-DD
    provider_usage: Dict[Provider, ProviderUsage] = field(default_factory=dict)
    total_cost: float = 0.0
    total_tokens: int = 0
    total_requests: int = 0
    started_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "date": self.date,
            "provider_usage": {
                p.value: usage.to_dict() for p, usage in self.provider_usage.items()
            },
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "total_requests": self.total_requests,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_updated_at": (
                self.last_updated_at.isoformat() if self.last_updated_at else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyUsage":
        """Create from dictionary."""
        provider_usage = {}
        for provider_str, usage_data in data.get("provider_usage", {}).items():
            provider = Provider(provider_str)
            provider_usage[provider] = ProviderUsage.from_dict(usage_data)

        return cls(
            date=data["date"],
            provider_usage=provider_usage,
            total_cost=data.get("total_cost", 0.0),
            total_tokens=data.get("total_tokens", 0),
            total_requests=data.get("total_requests", 0),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if data.get("started_at")
                else None
            ),
            last_updated_at=(
                datetime.fromisoformat(data["last_updated_at"])
                if data.get("last_updated_at")
                else None
            ),
        )


class CostTracker:
    """Tracks API costs and enforces daily limits.

    Responsibilities:
    - Track API usage per provider
    - Track tokens and costs
    - Enforce daily cost ceilings
    - Alert when approaching limits
    - Provide usage reports
    - Persist state to disk
    """

    # Cost per 1K tokens (approximate rates as of 2025)
    TOKEN_COSTS = {
        Provider.ANTHROPIC: {
            "input": 0.003,  # $3 per 1M input tokens
            "output": 0.015,  # $15 per 1M output tokens
        },
        Provider.DEEPSEEK: {
            "input": 0.001,  # $1 per 1M tokens (very cheap)
            "output": 0.001,
        },
        Provider.OPENAI: {
            "input": 0.005,  # $5 per 1M input tokens (GPT-4)
            "output": 0.015,  # $15 per 1M output tokens
        },
        Provider.PERPLEXITY: {
            "input": 0.002,  # $2 per 1M tokens (estimated)
            "output": 0.002,
        },
        Provider.GITHUB: {
            "request": 0.0,  # GitHub API is free (rate limited)
        },
    }

    # Alert thresholds
    WARNING_THRESHOLD = 0.8  # 80% of daily limit
    CRITICAL_THRESHOLD = 0.95  # 95% of daily limit

    def __init__(
        self,
        max_daily_cost: float,
        logger: AuditLogger,
        state_file: Optional[str] = None,
    ):
        """Initialize cost tracker.

        Args:
            max_daily_cost: Maximum cost allowed per day ($)
            logger: Audit logger
            state_file: Path to state persistence file
        """
        self.max_daily_cost = max_daily_cost
        self.logger = logger
        self.state_file = Path(
            state_file if state_file else "./state/cost_tracker.json"
        )

        # Load or initialize today's usage
        self.daily_usage = self._load_daily_usage()

        self.logger.info(
            "cost_tracker_initialized",
            max_daily_cost=max_daily_cost,
            state_file=str(self.state_file),
            current_cost=self.daily_usage.total_cost,
        )

    def track_request(
        self,
        provider: Provider,
        tokens_input: int = 0,
        tokens_output: int = 0,
        cost: Optional[float] = None,
    ):
        """Track a single API request.

        Args:
            provider: API provider
            tokens_input: Input tokens used
            tokens_output: Output tokens used
            cost: Actual cost (if known), otherwise estimated

        Raises:
            CostLimitExceeded: If daily cost limit exceeded
        """
        # Calculate cost if not provided
        if cost is None:
            cost = self._estimate_cost(provider, tokens_input, tokens_output)

        # Check if adding this request would exceed the limit
        projected_cost = self.daily_usage.total_cost + cost
        if projected_cost > self.max_daily_cost:
            raise CostLimitExceeded(
                f"Daily cost limit would be exceeded: ${projected_cost:.4f} > ${self.max_daily_cost:.2f}"
            )

        # Get or create provider usage
        if provider not in self.daily_usage.provider_usage:
            self.daily_usage.provider_usage[provider] = ProviderUsage(provider=provider)

        usage = self.daily_usage.provider_usage[provider]

        # Update provider usage
        usage.requests += 1
        usage.tokens_input += tokens_input
        usage.tokens_output += tokens_output
        usage.tokens_total += tokens_input + tokens_output
        usage.cost += cost
        usage.last_request_time = datetime.now(timezone.utc)

        # Update daily totals
        self.daily_usage.total_requests += 1
        self.daily_usage.total_tokens += tokens_input + tokens_output
        self.daily_usage.total_cost += cost
        self.daily_usage.last_updated_at = datetime.now(timezone.utc)

        # Save state
        self._save_state()

        # Log the request
        self.logger.info(
            "api_request_tracked",
            provider=provider.value,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost=cost,
            daily_total_cost=self.daily_usage.total_cost,
            daily_total_tokens=self.daily_usage.total_tokens,
        )

        # Check for alerts
        self._check_limits()

    def track_multi_agent_call(
        self,
        provider_costs: Dict[str, float],
        provider_tokens: Dict[str, Dict[str, int]],
    ):
        """Track multi-agent-coder call with multiple providers.

        Args:
            provider_costs: Cost per provider {"anthropic": 0.05, ...}
            provider_tokens: Tokens per provider {"anthropic": {"input": 1000, "output": 500}, ...}
        """
        for provider_name, cost in provider_costs.items():
            # Map provider name to enum
            try:
                provider = Provider(provider_name.lower())
            except ValueError:
                self.logger.warning(
                    "unknown_provider_in_multi_agent_call",
                    provider=provider_name,
                    cost=cost,
                )
                continue

            # Get token counts
            tokens = provider_tokens.get(provider_name, {})
            tokens_input = tokens.get("input", 0)
            tokens_output = tokens.get("output", 0)

            # Track the request
            self.track_request(
                provider=provider,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost=cost,
            )

    def can_afford_operation(self, estimated_cost: float) -> bool:
        """Check if we can afford an operation.

        Args:
            estimated_cost: Estimated cost of operation

        Returns:
            True if operation is within daily limit
        """
        projected_cost = self.daily_usage.total_cost + estimated_cost
        return projected_cost <= self.max_daily_cost

    def estimate_multi_agent_cost(
        self, prompt_tokens: int, expected_output_tokens: int, num_providers: int = 4
    ) -> float:
        """Estimate cost of multi-agent operation.

        Args:
            prompt_tokens: Tokens in prompt
            expected_output_tokens: Expected output tokens per provider
            num_providers: Number of providers to query

        Returns:
            Estimated total cost
        """
        total_cost = 0.0

        # Assume all 4 providers are used
        providers = [
            Provider.ANTHROPIC,
            Provider.DEEPSEEK,
            Provider.OPENAI,
            Provider.PERPLEXITY,
        ]

        for provider in providers[:num_providers]:
            cost = self._estimate_cost(provider, prompt_tokens, expected_output_tokens)
            total_cost += cost

        return total_cost

    def get_remaining_budget(self) -> float:
        """Get remaining budget for today.

        Returns:
            Remaining budget in dollars
        """
        return max(0.0, self.max_daily_cost - self.daily_usage.total_cost)

    def get_usage_report(self) -> Dict[str, Any]:
        """Get comprehensive usage report.

        Returns:
            Dictionary with usage statistics
        """
        remaining = self.get_remaining_budget()
        percentage_used = (
            (self.daily_usage.total_cost / self.max_daily_cost * 100)
            if self.max_daily_cost > 0
            else 0
        )

        # Per-provider breakdown
        provider_breakdown = {}
        for provider, usage in self.daily_usage.provider_usage.items():
            provider_breakdown[provider.value] = {
                "requests": usage.requests,
                "tokens_input": usage.tokens_input,
                "tokens_output": usage.tokens_output,
                "tokens_total": usage.tokens_total,
                "cost": usage.cost,
                "cost_percentage": (
                    (usage.cost / self.daily_usage.total_cost * 100)
                    if self.daily_usage.total_cost > 0
                    else 0
                ),
            }

        return {
            "date": self.daily_usage.date,
            "daily_limit": self.max_daily_cost,
            "total_cost": self.daily_usage.total_cost,
            "remaining_budget": remaining,
            "percentage_used": percentage_used,
            "total_tokens": self.daily_usage.total_tokens,
            "total_requests": self.daily_usage.total_requests,
            "provider_breakdown": provider_breakdown,
            "status": self._get_status(),
        }

    def reset_daily_usage(self):
        """Reset daily usage (called at start of new day)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.daily_usage = DailyUsage(
            date=today,
            started_at=datetime.now(timezone.utc),
        )
        self._save_state()

        self.logger.info("daily_usage_reset", date=today)

    def _estimate_cost(
        self, provider: Provider, tokens_input: int, tokens_output: int
    ) -> float:
        """Estimate cost for a request.

        Args:
            provider: API provider
            tokens_input: Input tokens
            tokens_output: Output tokens

        Returns:
            Estimated cost in dollars
        """
        if provider == Provider.GITHUB:
            # GitHub API is free
            return 0.0

        costs = self.TOKEN_COSTS.get(provider, {"input": 0.003, "output": 0.015})

        input_cost = (tokens_input / 1000) * costs["input"]
        output_cost = (tokens_output / 1000) * costs["output"]

        return input_cost + output_cost

    def _check_limits(self):
        """Check if approaching or exceeding limits."""
        percentage = (
            self.daily_usage.total_cost / self.max_daily_cost
            if self.max_daily_cost > 0
            else 0
        )

        if percentage >= self.CRITICAL_THRESHOLD:
            self.logger.error(
                "cost_limit_critical",
                current_cost=self.daily_usage.total_cost,
                max_cost=self.max_daily_cost,
                percentage=percentage * 100,
            )
        elif percentage >= self.WARNING_THRESHOLD:
            self.logger.warning(
                "cost_limit_warning",
                current_cost=self.daily_usage.total_cost,
                max_cost=self.max_daily_cost,
                percentage=percentage * 100,
            )

    def _get_status(self) -> str:
        """Get current status string."""
        percentage = (
            self.daily_usage.total_cost / self.max_daily_cost
            if self.max_daily_cost > 0
            else 0
        )

        if percentage >= 1.0:
            return "EXCEEDED"
        elif percentage >= self.CRITICAL_THRESHOLD:
            return "CRITICAL"
        elif percentage >= self.WARNING_THRESHOLD:
            return "WARNING"
        else:
            return "OK"

    def _load_daily_usage(self) -> DailyUsage:
        """Load daily usage from disk.

        Returns:
            DailyUsage for today (new if file doesn't exist or date mismatch)
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not self.state_file.exists():
            self.logger.info(
                "cost_tracker_state_not_found",
                state_file=str(self.state_file),
                action="creating_new",
            )
            return DailyUsage(date=today, started_at=datetime.now(timezone.utc))

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)

            usage = DailyUsage.from_dict(data)

            # Check if it's from today
            if usage.date != today:
                self.logger.info(
                    "cost_tracker_new_day",
                    previous_date=usage.date,
                    new_date=today,
                    action="resetting_usage",
                )
                return DailyUsage(date=today, started_at=datetime.now(timezone.utc))

            self.logger.info(
                "cost_tracker_state_loaded",
                state_file=str(self.state_file),
                current_cost=usage.total_cost,
            )

            return usage

        except Exception as e:
            self.logger.error(
                "cost_tracker_state_load_failed",
                state_file=str(self.state_file),
                error=str(e),
                action="creating_new",
            )
            return DailyUsage(date=today, started_at=datetime.now(timezone.utc))

    def _save_state(self):
        """Save state to disk."""
        try:
            # Ensure state directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.state_file, "w") as f:
                json.dump(self.daily_usage.to_dict(), f, indent=2)

            self.logger.debug(
                "cost_tracker_state_saved",
                state_file=str(self.state_file),
            )

        except Exception as e:
            self.logger.error(
                "cost_tracker_state_save_failed",
                state_file=str(self.state_file),
                error=str(e),
            )
