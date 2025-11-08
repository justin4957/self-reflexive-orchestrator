"""Configuration management for the orchestrator."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import yaml
from dotenv import load_dotenv


@dataclass
class OrchestratorConfig:
    """Main orchestrator configuration."""
    mode: str = "supervised"
    poll_interval: int = 300
    work_dir: str = "./workspace"


@dataclass
class GitHubConfig:
    """GitHub integration configuration."""
    repository: str = ""
    token: str = ""
    base_branch: str = "main"


@dataclass
class IssueProcessingConfig:
    """Issue processing configuration."""
    auto_claim_labels: List[str] = field(default_factory=lambda: ["bot-approved"])
    ignore_labels: List[str] = field(default_factory=lambda: ["wontfix", "manual-only"])
    max_complexity: int = 7
    require_acceptance_criteria: bool = True
    max_concurrent: int = 2


@dataclass
class PRManagementConfig:
    """Pull request management configuration."""
    auto_fix_attempts: int = 2
    require_reviews: int = 1
    auto_merge: bool = True
    merge_strategy: str = "squash"
    ci_timeout: int = 1800


@dataclass
class CodeReviewConfig:
    """Code review configuration."""
    multi_agent_coder_path: str = "../multi_agent_coder/multi_agent_coder"
    review_timeout: int = 600
    require_approval: bool = True


@dataclass
class MultiAgentCoderConfig:
    """Multi-agent-coder integration configuration."""
    executable_path: str = "../multi_agent_coder/multi_agent_coder"
    default_strategy: str = "all"  # all, sequential, dialectical
    default_providers: List[str] = field(default_factory=lambda: [])  # Empty = use all available
    query_timeout: int = 120  # seconds
    enable_for_issue_analysis: bool = True
    enable_for_code_review: bool = True


@dataclass
class RoadmapConfig:
    """Roadmap generation configuration."""
    enabled: bool = True
    generation_frequency: str = "weekly"
    proposals_per_cycle: int = 5
    auto_create_issues: bool = True


@dataclass
class LLMConfig:
    """LLM API configuration."""
    api_key: str = ""
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 8000
    temperature: float = 0.7


@dataclass
class SafetyConfig:
    """Safety and approval configuration."""
    human_approval_required: List[str] = field(
        default_factory=lambda: ["merge_to_main", "breaking_changes", "security_related"]
    )
    max_api_cost_per_day: float = 50.0
    rollback_on_test_failure: bool = True
    max_retries: int = 3


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = "logs/orchestrator.log"
    audit_file: str = "logs/audit.log"
    structured: bool = True


@dataclass
class NotificationsConfig:
    """Notifications configuration."""
    slack_webhook: str = ""
    email: str = ""
    on_events: List[str] = field(
        default_factory=lambda: ["error", "merge", "roadmap_generated", "human_approval_required"]
    )


@dataclass
class RedisConfig:
    """Redis configuration for state management."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""


@dataclass
class Config:
    """Complete orchestrator configuration."""
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    issue_processing: IssueProcessingConfig = field(default_factory=IssueProcessingConfig)
    pr_management: PRManagementConfig = field(default_factory=PRManagementConfig)
    code_review: CodeReviewConfig = field(default_factory=CodeReviewConfig)
    multi_agent_coder: MultiAgentCoderConfig = field(default_factory=MultiAgentCoderConfig)
    roadmap: RoadmapConfig = field(default_factory=RoadmapConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create Config from dictionary."""
        return cls(
            orchestrator=OrchestratorConfig(**data.get("orchestrator", {})),
            github=GitHubConfig(**data.get("github", {})),
            issue_processing=IssueProcessingConfig(**data.get("issue_processing", {})),
            pr_management=PRManagementConfig(**data.get("pr_management", {})),
            code_review=CodeReviewConfig(**data.get("code_review", {})),
            multi_agent_coder=MultiAgentCoderConfig(**data.get("multi_agent_coder", {})),
            roadmap=RoadmapConfig(**data.get("roadmap", {})),
            llm=LLMConfig(**data.get("llm", {})),
            safety=SafetyConfig(**data.get("safety", {})),
            logging=LoggingConfig(**data.get("logging", {})),
            notifications=NotificationsConfig(**data.get("notifications", {})),
            redis=RedisConfig(**data.get("redis", {})),
        )

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []

        # Validate orchestrator mode
        valid_modes = ["manual", "supervised", "autonomous"]
        if self.orchestrator.mode not in valid_modes:
            errors.append(f"Invalid mode: {self.orchestrator.mode}. Must be one of {valid_modes}")

        # Validate GitHub config
        if not self.github.repository:
            errors.append("GitHub repository is required")
        if not self.github.token:
            errors.append("GitHub token is required (or set GITHUB_TOKEN env var)")

        # Validate LLM config
        if not self.llm.api_key:
            errors.append("LLM API key is required (or set ANTHROPIC_API_KEY env var)")

        # Validate merge strategy
        valid_strategies = ["merge", "squash", "rebase"]
        if self.pr_management.merge_strategy not in valid_strategies:
            errors.append(
                f"Invalid merge strategy: {self.pr_management.merge_strategy}. "
                f"Must be one of {valid_strategies}"
            )

        # Validate roadmap frequency
        valid_frequencies = ["daily", "weekly", "monthly"]
        if self.roadmap.generation_frequency not in valid_frequencies:
            errors.append(
                f"Invalid roadmap frequency: {self.roadmap.generation_frequency}. "
                f"Must be one of {valid_frequencies}"
            )

        # Validate paths
        if self.roadmap.enabled:
            mac_path = Path(self.code_review.multi_agent_coder_path)
            if not mac_path.exists():
                errors.append(
                    f"multi-agent-coder path does not exist: {self.code_review.multi_agent_coder_path}"
                )

        return errors


class ConfigManager:
    """Manages configuration loading and environment variables."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize config manager.

        Args:
            config_path: Path to configuration file. If None, uses default locations.
        """
        self.config_path = config_path or self._find_config_file()
        self.config: Optional[Config] = None

    def _find_config_file(self) -> str:
        """Find configuration file in standard locations."""
        possible_paths = [
            "config/orchestrator-config.yaml",
            "orchestrator-config.yaml",
            os.path.expanduser("~/.orchestrator/config.yaml"),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        raise FileNotFoundError(
            f"No configuration file found. Checked: {possible_paths}\n"
            "Please copy config/orchestrator-config.yaml.example to config/orchestrator-config.yaml"
        )

    def load(self) -> Config:
        """Load configuration from file and environment."""
        # Load environment variables
        load_dotenv()

        # Load YAML configuration
        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f) or {}

        # Create config from dict
        config = Config.from_dict(data)

        # Override with environment variables
        config = self._apply_env_overrides(config)

        # Validate configuration
        errors = config.validate()
        if errors:
            raise ValueError(f"Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

        self.config = config
        return config

    def _apply_env_overrides(self, config: Config) -> Config:
        """Apply environment variable overrides to configuration."""
        # GitHub token
        if env_token := os.getenv("GITHUB_TOKEN"):
            config.github.token = env_token

        # LLM API key
        if env_api_key := os.getenv("ANTHROPIC_API_KEY"):
            config.llm.api_key = env_api_key

        # Redis password
        if env_redis_pass := os.getenv("REDIS_PASSWORD"):
            config.redis.password = env_redis_pass

        # Orchestrator mode
        if env_mode := os.getenv("ORCHESTRATOR_MODE"):
            config.orchestrator.mode = env_mode

        return config

    def reload(self) -> Config:
        """Reload configuration from file."""
        return self.load()

    def get(self) -> Config:
        """Get current configuration, loading if necessary."""
        if self.config is None:
            return self.load()
        return self.config
